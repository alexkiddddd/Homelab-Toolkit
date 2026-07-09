from pathlib import Path
import re
import subprocess
import tempfile
import shutil
import json
from datetime import datetime

from homelab.core.logger import Logger
from homelab.core.shell import run as shell
from homelab.services.manifest import load_manifest, ManifestError

HOST_BACKUP_DIR = Path("/mnt/pve/backups/host-config")
PVE_STORAGE_CFG = Path("/etc/pve/storage.cfg")
NETWORK_INTERFACES = Path("/etc/network/interfaces")
HOSTS_FILE = Path("/etc/hosts")
RESOLV_CONF = Path("/etc/resolv.conf")
LCDD_CONF = Path("/etc/LCDd.conf")
LCDPROC_CONF = Path("/etc/lcdproc.conf")
SYSTEMD_SYSTEM_DIR = Path("/etc/systemd/system")
SYSTEMD_UNIT_SUFFIXES = (".service", ".timer", ".mount", ".path", ".socket")


def human_size(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.1f} GB"


def parse_backup(path):
    m = re.search(
        r"proxmox-host-(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.tar\.zst$",
        path.name,
    )
    if not m:
        return None

    y, mo, d, h, mi, _ = m.groups()

    return {
        "path": path,
        "date": f"{d}/{mo}/{y}",
        "time": f"{h}:{mi}",
        "size": path.stat().st_size,
    }


def ask(prompt, default=""):
    value = input(f"{prompt} ").strip()
    return value or default


def confirm(prompt, default=False):
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix} ").strip().lower()
    if not value:
        return default
    return value in ["y", "yes", "s", "sim"]


def current_state():
    return {
        "hostname": shell("hostname"),
        "kernel": shell("uname -r"),
        "proxmox": shell("pveversion"),
        "containers": shell("pct list | awk 'NR>1 {print $1}' | wc -l").strip(),
        "storages": shell("pvesm status | awk 'NR>1 {print $1}' | wc -l").strip(),
        "toolkit": Path("/opt/homelab/VERSION").read_text().strip()
        if Path("/opt/homelab/VERSION").exists()
        else "desconhecido",
    }


def parse_backup_jobs(manifest):
    raw = manifest.get("backup_jobs", [])

    if isinstance(raw, list):
        return raw

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []

    return []


def tailscale_up_command(tailscale_state):
    prefs = tailscale_state.get("prefs", {})
    args = []

    if prefs.get("Hostname"):
        args.append(f"--hostname='{prefs['Hostname']}'")

    routes = prefs.get("AdvertiseRoutes")
    if isinstance(routes, list) and routes:
        args.append(f"--advertise-routes='{','.join(routes)}'")

    tags = prefs.get("AdvertiseTags")
    if isinstance(tags, list) and tags:
        args.append(f"--advertise-tags='{','.join(tags)}'")

    if prefs.get("AcceptRoutes"):
        args.append("--accept-routes")

    if prefs.get("AcceptDNS") is False:
        args.append("--accept-dns=false")

    if prefs.get("RunSSH"):
        args.append("--ssh")

    if prefs.get("AdvertiseExitNode"):
        args.append("--advertise-exit-node")

    if prefs.get("ShieldsUp"):
        args.append("--shields-up")

    return "tailscale up" + (f" {' '.join(args)}" if args else "")


def current_tailscale_state():
    return {
        "installed": shell("command -v tailscale >/dev/null 2>&1 && echo yes || echo no") == "yes",
        "service_enabled": shell("systemctl is-enabled tailscaled 2>/dev/null || true"),
        "service_active": shell("systemctl is-active tailscaled 2>/dev/null || true"),
        "ip4": shell("tailscale ip -4 2>/dev/null || true"),
        "status": shell("tailscale status 2>/dev/null || true"),
    }


def print_tailscale_compare(logger, snapshot_state, current_state):
    logger.print("\nTailscale")
    logger.print("=========")

    if not snapshot_state:
        logger.print("Snapshot sem informação Tailscale detalhada.")
        logger.print("Backups antigos podem conter apenas info/tailscale.txt.")
        return

    prefs = snapshot_state.get("prefs", {})

    logger.print("Snapshot:")
    logger.print(f"  Instalado: {'sim' if snapshot_state.get('installed') else 'não'}")
    logger.print(f"  Serviço:   {snapshot_state.get('service_active', '-')}")
    logger.print(f"  IP:        {snapshot_state.get('ip4') or '-'}")
    logger.print(f"  LoggedOut: {prefs.get('LoggedOut', '-')}")
    logger.print(f"  SSH:       {prefs.get('RunSSH', '-')}")
    logger.print(f"  Rotas:     {prefs.get('AdvertiseRoutes') or '-'}")
    logger.print(f"  Tags:      {prefs.get('AdvertiseTags') or '-'}")
    logger.print(f"  DNS:       {prefs.get('CorpDNS', '-')}")
    logger.print("")

    logger.print("Atual:")
    logger.print(f"  Instalado: {'sim' if current_state.get('installed') else 'não'}")
    logger.print(f"  Serviço:   {current_state.get('service_active', '-')}")
    logger.print(f"  IP:        {current_state.get('ip4') or '-'}")
    logger.print("")
    logger.print("Comando sugerido:")
    logger.print(f"  {tailscale_up_command(snapshot_state)}")
    logger.print("")
    logger.print("Nota: chaves privadas, NodeID e perfil pessoal não são restaurados.")


def restore_tailscale(snapshot_state, logger):
    if not snapshot_state:
        logger.print("❌ Snapshot sem informação Tailscale detalhada.")
        logger.print("Executa um novo homelab backup para incluir este componente.")
        return False

    cmd = tailscale_up_command(snapshot_state)
    current = current_tailscale_state()

    if not current.get("installed"):
        logger.print("❌ Tailscale não está instalado neste host.")
        logger.print("Instala primeiro o Tailscale e volta a executar este passo.")
        logger.print("Referência: https://tailscale.com/download/linux/debian")
        return False

    if current.get("service_active") != "active":
        logger.print("A ativar tailscaled...")
        shell("systemctl enable --now tailscaled", timeout=120, logger=logger, show=True)

    logger.print("Comando preparado:")
    logger.print(cmd)
    logger.print("")
    logger.print("Este comando pode pedir autenticação no browser ou URL de login.")

    if not confirm("Executar tailscale up agora?", False):
        logger.print("Não executado. Comando sugerido:")
        logger.print(cmd)
        return False

    shell(cmd, timeout=300, logger=logger, show=True, fatal=True)

    logger.print("Validação:")
    logger.print(shell("tailscale status 2>/dev/null || true", timeout=60))
    logger.print(shell("tailscale ip -4 2>/dev/null || true", timeout=30))
    return True


def read_optional_file(path):
    return path.read_text() if path.exists() else ""


def snapshot_lcdproc_files(snapshot_root):
    return {
        "LCDd.conf": read_optional_file(snapshot_root / "etc" / "LCDd.conf"),
        "lcdproc.conf": read_optional_file(snapshot_root / "etc" / "lcdproc.conf"),
    }


def current_lcdproc_files():
    return {
        "LCDd.conf": read_optional_file(LCDD_CONF),
        "lcdproc.conf": read_optional_file(LCDPROC_CONF),
    }


def current_lcdproc_state():
    return {
        "installed": shell("command -v LCDd >/dev/null 2>&1 && echo yes || echo no") == "yes",
        "LCDd": shell("systemctl is-active LCDd 2>/dev/null || true"),
        "lcdproc": shell("systemctl is-active lcdproc 2>/dev/null || true"),
    }


def lcdproc_diff_summary(snapshot_files, current_files):
    rows = []

    for name in ["LCDd.conf", "lcdproc.conf"]:
        snapshot = snapshot_files.get(name, "")
        current = current_files.get(name, "")

        if snapshot and current:
            status = "igual" if snapshot == current else "diferente"
        elif snapshot:
            status = "ausente no host atual"
        elif current:
            status = "ausente no snapshot"
        else:
            status = "ausente"

        rows.append((name, status))

    return rows


def print_lcdproc_compare(logger, snapshot_files, current_files, snapshot_state, current_state):
    logger.print("\nLCDproc")
    logger.print("=======")

    if not any(snapshot_files.values()):
        logger.print("Snapshot sem configuração LCDproc.")
        return

    logger.print("Ficheiros:")
    for name, status in lcdproc_diff_summary(snapshot_files, current_files):
        icon = "✔" if status == "igual" else "⚠"
        logger.print(f"{icon} {name}: {status}")

    logger.print("")
    logger.print("Snapshot:")
    if snapshot_state:
        logger.print(f"  Instalado: {'sim' if snapshot_state.get('installed') else 'não'}")
        logger.print(f"  LCDd:      {snapshot_state.get('LCDd_active') or '-'} / {snapshot_state.get('LCDd_enabled') or '-'}")
        logger.print(f"  lcdproc:   {snapshot_state.get('lcdproc_active') or '-'} / {snapshot_state.get('lcdproc_enabled') or '-'}")
    else:
        logger.print("  Estado dos serviços não disponível neste snapshot.")

    logger.print("")
    logger.print("Host atual:")
    logger.print(f"  Instalado: {'sim' if current_state.get('installed') else 'não'}")
    logger.print(f"  LCDd:      {current_state.get('LCDd') or '-'}")
    logger.print(f"  lcdproc:   {current_state.get('lcdproc') or '-'}")


def restore_lcdproc(snapshot_root, snapshot_state, logger):
    snapshot_files = snapshot_lcdproc_files(snapshot_root)

    if not any(snapshot_files.values()):
        logger.print("❌ Snapshot sem ficheiros LCDproc.")
        return False

    targets = {
        "LCDd.conf": LCDD_CONF,
        "lcdproc.conf": LCDPROC_CONF,
    }

    for name, target in targets.items():
        content = snapshot_files.get(name, "")

        if not content.strip():
            logger.print(f"⚠ {name} não encontrado no snapshot. Ignorado.")
            continue

        backup_file(target, logger)
        target.write_text(content)
        logger.print(f"✔ {target} restaurado")

    state = current_lcdproc_state()

    if not state.get("installed"):
        logger.print("")
        logger.print("⚠ LCDproc não parece estar instalado neste host.")
        logger.print("Instala os pacotes necessários antes de ativar os serviços.")
        return True

    if confirm("Ativar/reiniciar serviços LCDproc agora?", False):
        services = []

        if not snapshot_state or snapshot_state.get("LCDd_enabled") in ["enabled", "static", "generated"]:
            services.append("LCDd")

        if snapshot_state and snapshot_state.get("lcdproc_enabled") in ["enabled", "static", "generated"]:
            services.append("lcdproc")

        if not services:
            services = ["LCDd"]

        for service in services:
            shell(f"systemctl enable --now {service} 2>/dev/null || true", timeout=120, logger=logger, show=True)
            shell(f"systemctl restart {service} 2>/dev/null || true", timeout=120, logger=logger, show=True)

        logger.print("Estado:")
        logger.print(shell("systemctl is-active LCDd 2>/dev/null || true"))
        logger.print(shell("systemctl is-active lcdproc 2>/dev/null || true"))
    else:
        logger.print("Serviços não alterados.")

    return True


def list_systemd_units(root):
    units = []

    if not root.exists():
        return units

    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if not path.name.endswith(SYSTEMD_UNIT_SUFFIXES):
            continue

        units.append({
            "name": path.name,
            "path": path,
            "kind": path.suffix.replace(".", ""),
            "is_symlink": path.is_symlink(),
            "enabled": shell(f"systemctl is-enabled '{path.name}' 2>/dev/null || true")
            if root == SYSTEMD_SYSTEM_DIR
            else "",
            "active": shell(f"systemctl is-active '{path.name}' 2>/dev/null || true")
            if root == SYSTEMD_SYSTEM_DIR
            else "",
        })

    return units


def snapshot_systemd_units(snapshot_root):
    return list_systemd_units(snapshot_root / "system" / "system")


def current_systemd_units():
    return list_systemd_units(SYSTEMD_SYSTEM_DIR)


def print_systemd_compare(logger, snapshot_units, current_units, manifest_units):
    logger.print("\nServiços systemd")
    logger.print("================")

    if not snapshot_units:
        logger.print("Snapshot sem unit files em /etc/systemd/system.")
        return

    manifest_by_name = {u.get("name"): u for u in manifest_units if isinstance(u, dict)}
    current_by_name = {u["name"]: u for u in current_units}

    logger.print(f"Unit files no snapshot: {len(snapshot_units)}")
    logger.print("")

    for unit in snapshot_units:
        current = current_by_name.get(unit["name"])
        manifest = manifest_by_name.get(unit["name"], {})
        icon = "✔" if current else "➕"
        link = "symlink" if unit["is_symlink"] else "ficheiro"
        enabled = manifest.get("enabled") or "-"
        active = manifest.get("active") or "-"

        logger.print(f"{icon} {unit['name']} ({link})")
        logger.print(f"  Snapshot: {enabled} / {active}")

        if current:
            logger.print(f"  Atual:    {current.get('enabled') or '-'} / {current.get('active') or '-'}")
        else:
            logger.print("  Atual:    ausente")

        if unit["is_symlink"]:
            logger.print("  ⚠ Symlink: não será restaurado automaticamente.")

        logger.print("")


def parse_selection(value, max_index):
    value = value.strip().lower()

    if value in ["all", "todos", "tudo"]:
        return list(range(max_index))

    selected = []

    for part in value.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            index = int(part) - 1
        except ValueError:
            continue

        if 0 <= index < max_index:
            selected.append(index)

    return sorted(set(selected))


RESTORE_COMPONENTS = {
    "1": {
        "name": "Toolkit",
        "summary": "Restaurar Toolkit para /opt/homelab",
    },
    "2": {
        "name": "Configuração Homelab",
        "summary": "Restaurar Configuração Homelab para /etc/homelab",
    },
    "3": {
        "name": "Jobs de Backup",
        "summary": "Restaurar Jobs de Backup do Proxmox",
    },
    "5": {
        "name": "Storages Proxmox",
        "summary": "Restaurar Storages Proxmox para /etc/pve/storage.cfg",
        "warning": "Isto restaura as definições Proxmox, não cria discos, mounts ou datasets.",
    },
    "6": {
        "name": "Rede Proxmox",
        "summary": "Restaurar Rede Proxmox para /etc/network/interfaces",
        "warning": "Isto pode alterar IP, gateway, bridges e acesso ao host. A rede não será reiniciada automaticamente.",
    },
    "7": {
        "name": "Tailscale",
        "summary": "Reconfigurar Tailscale",
        "warning": "Chaves privadas e identidade antiga não serão restauradas. Poderá ser necessário autenticar novamente.",
    },
    "8": {
        "name": "LCDproc",
        "summary": "Restaurar configuração LCDproc",
        "warning": "Isto restaura /etc/LCDd.conf e /etc/lcdproc.conf quando existirem.",
    },
    "9": {
        "name": "Serviços systemd",
        "summary": "Restaurar serviços systemd selecionados",
        "warning": "Unit files serão escolhidos manualmente. Symlinks e diretórios .wants não serão restaurados automaticamente.",
    },
}

RESTORE_ORDER = ["1", "2", "5", "6", "7", "8", "3", "9"]
RESTORE_RECOMMENDED_ORDER = ["1", "2", "5", "6", "7", "8", "3"]


def parse_component_selection(value):
    value = value.strip().lower()

    if not value or value == "0":
        return []

    if value in ["all", "todos", "tudo"]:
        return RESTORE_RECOMMENDED_ORDER.copy()

    selected = []

    for part in value.split(","):
        part = part.strip()

        if part == "4":
            selected.extend(["1", "2"])
            continue

        if part in RESTORE_COMPONENTS:
            selected.append(part)

    return [key for key in RESTORE_ORDER if key in set(selected)]


def print_component_summary(logger, selected):
    for key in selected:
        component = RESTORE_COMPONENTS[key]
        logger.print(f"✔ {component['summary']}")

        warning = component.get("warning")
        if warning:
            logger.print(f"⚠ {warning}")


def print_component_final_summary(logger, selected):
    labels = {
        "1": "Toolkit restaurado",
        "2": "Configuração Homelab restaurada",
        "3": "Jobs de Backup restaurados",
        "5": "Storages Proxmox restauradas",
        "6": "Rede Proxmox restaurada",
        "7": "Tailscale processado",
        "8": "LCDproc processado",
        "9": "Serviços systemd processados",
    }

    for key in selected:
        logger.print(f"✔ {labels[key]}")


def restore_systemd_units(snapshot_root, manifest_units, logger):
    units = [u for u in snapshot_systemd_units(snapshot_root) if not u["is_symlink"]]

    if not units:
        logger.print("❌ Nenhum unit file restaurável encontrado no snapshot.")
        return False

    manifest_by_name = {u.get("name"): u for u in manifest_units if isinstance(u, dict)}

    logger.print("Unit files disponíveis")
    logger.print("======================")

    for index, unit in enumerate(units, start=1):
        manifest = manifest_by_name.get(unit["name"], {})
        enabled = manifest.get("enabled") or "-"
        active = manifest.get("active") or "-"
        logger.print(f"[{index}] {unit['name']} ({enabled} / {active})")

    choice = ask("Escolhe unidades para restaurar, separado por vírgulas, ou 'all' [cancelar]:", "")
    selected = parse_selection(choice, len(units))

    if not selected:
        logger.print("Cancelado. Nenhum serviço restaurado.")
        return False

    SYSTEMD_SYSTEM_DIR.mkdir(parents=True, exist_ok=True)

    for index in selected:
        unit = units[index]
        target = SYSTEMD_SYSTEM_DIR / unit["name"]

        backup_file(target, logger)
        shutil.copy2(unit["path"], target)
        logger.print(f"✔ {unit['name']} restaurado")

    logger.print("A recarregar systemd...")
    shell("systemctl daemon-reload", timeout=120, logger=logger, show=True)

    for index in selected:
        unit = units[index]
        manifest = manifest_by_name.get(unit["name"], {})

        if manifest.get("enabled") == "enabled":
            if confirm(f"Ativar {unit['name']}?", False):
                shell(f"systemctl enable '{unit['name']}'", timeout=120, logger=logger, show=True)

        if manifest.get("active") == "active":
            if confirm(f"Iniciar/reiniciar {unit['name']}?", False):
                shell(f"systemctl restart '{unit['name']}'", timeout=120, logger=logger, show=True)

    return True


def parse_storage_cfg(text):
    storages = []
    current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if not line.startswith((" ", "\t")) and ":" in line:
            storage_type, storage_id = line.split(":", 1)
            current = {
                "id": storage_id.strip(),
                "type": storage_type.strip(),
                "options": {},
            }
            storages.append(current)
            continue

        if current and line.startswith((" ", "\t")):
            key, _, value = line.strip().partition(" ")
            current["options"][key.strip()] = value.strip()

    return storages


def parse_network_interfaces(text):
    interfaces = {}
    auto = set()
    current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        parts = line.split()

        if parts[0] == "auto":
            auto.update(parts[1:])
            current = None
            continue

        if parts[0] == "iface" and len(parts) >= 4:
            current = parts[1]
            interfaces[current] = {
                "name": current,
                "family": parts[2],
                "method": parts[3],
                "auto": current in auto,
                "options": {},
            }
            continue

        if current and len(parts) >= 2:
            interfaces[current]["options"][parts[0]] = " ".join(parts[1:])

    for name in auto:
        interfaces.setdefault(
            name,
            {
                "name": name,
                "family": "",
                "method": "",
                "auto": True,
                "options": {},
            },
        )

    return interfaces


def bridge_ports(network_defs):
    ports = set()

    for iface in network_defs.values():
        value = iface["options"].get("bridge-ports", "")

        for port in value.split():
            if port and port != "none":
                ports.add(port)

    return sorted(ports)


def network_summary(network_defs):
    summary = []

    for name in sorted(network_defs):
        iface = network_defs[name]
        options = iface["options"]

        summary.append(
            {
                "name": name,
                "method": iface.get("method", ""),
                "address": options.get("address", "-"),
                "gateway": options.get("gateway", "-"),
                "bridge_ports": options.get("bridge-ports", "-"),
            }
        )

    return summary


def snapshot_network_files(snapshot_root):
    paths = {
        "interfaces": snapshot_root / "etc" / "interfaces",
        "hosts": snapshot_root / "etc" / "hosts",
        "resolv": snapshot_root / "etc" / "resolv.conf",
    }

    return {
        name: path.read_text() if path.exists() else ""
        for name, path in paths.items()
    }


def current_network_files():
    paths = {
        "interfaces": NETWORK_INTERFACES,
        "hosts": HOSTS_FILE,
        "resolv": RESOLV_CONF,
    }

    return {
        name: path.read_text() if path.exists() else ""
        for name, path in paths.items()
    }


def current_physical_interfaces():
    output = shell("ls /sys/class/net 2>/dev/null || true")
    interfaces = []

    for name in output.splitlines():
        if not name or name == "lo":
            continue
        if name.startswith(("vmbr", "tap", "veth", "fwbr", "fwln", "fwpr")):
            continue
        interfaces.append(name)

    return sorted(interfaces)


def print_network_compare(logger, snapshot_files, current_files, physical_interfaces):
    snapshot_defs = parse_network_interfaces(snapshot_files.get("interfaces", ""))
    current_defs = parse_network_interfaces(current_files.get("interfaces", ""))
    snapshot_by_name = snapshot_defs
    current_by_name = current_defs

    logger.print("\nRede Proxmox")
    logger.print("============")

    if not snapshot_defs:
        logger.print("Nenhuma configuração /etc/network/interfaces encontrada no snapshot.")
        return

    logger.print("Resumo do snapshot:")
    for item in network_summary(snapshot_defs):
        logger.print(f"✔ {item['name']} ({item['method']})")
        logger.print(f"  Address     : {item['address']}")
        logger.print(f"  Gateway     : {item['gateway']}")
        logger.print(f"  Bridge ports: {item['bridge_ports']}")
        logger.print("")

    all_names = sorted(set(snapshot_by_name) | set(current_by_name))
    logger.print("Diferenças:")

    if not all_names:
        logger.print("Nenhuma interface encontrada.")

    for name in all_names:
        snapshot = snapshot_by_name.get(name)
        current = current_by_name.get(name)

        if snapshot and current:
            icon = "✔" if snapshot == current else "⚠"
            logger.print(f"{icon} {name}")

            if snapshot != current:
                keys = sorted(set(snapshot["options"]) | set(current["options"]))
                for key in keys:
                    snapshot_value = snapshot["options"].get(key, "ausente")
                    current_value = current["options"].get(key, "ausente")

                    if snapshot_value != current_value:
                        logger.print(f"  - {key}: snapshot='{snapshot_value}' atual='{current_value}'")
        elif snapshot:
            logger.print(f"➕ {name} existe no snapshot, ausente no host atual")
        else:
            logger.print(f"➖ {name} ausente no snapshot, existe no host atual")

    missing_ports = [
        port for port in bridge_ports(snapshot_defs)
        if port not in physical_interfaces and not port.startswith("bond")
    ]

    if missing_ports:
        logger.print("")
        logger.print("⚠ Interfaces físicas referidas pelo snapshot não encontradas neste host:")
        for port in missing_ports:
            logger.print(f"- {port}")

        if physical_interfaces:
            logger.print("Interfaces físicas disponíveis:")
            for port in physical_interfaces:
                logger.print(f"- {port}")


def replace_interface_name(text, old, new):
    pattern = rf"(?<![A-Za-z0-9_.:-]){re.escape(old)}(?![A-Za-z0-9_.:-])"
    return re.sub(pattern, new, text)


def backup_file(path, logger):
    if not path.exists():
        return None

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = Path("/etc/homelab/restore-backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dst = backup_dir / f"{path.name}.before-restore-{stamp}"
    backup_dst.write_text(path.read_text())
    logger.print(f"Backup anterior: {backup_dst}")
    return backup_dst


def restore_network(snapshot_root, logger):
    snapshot_files = snapshot_network_files(snapshot_root)
    interfaces_text = snapshot_files.get("interfaces", "")

    if not interfaces_text.strip():
        logger.print("❌ /etc/network/interfaces não encontrado ou vazio no snapshot.")
        return False

    snapshot_defs = parse_network_interfaces(interfaces_text)
    physical_interfaces = current_physical_interfaces()
    missing_ports = [
        port for port in bridge_ports(snapshot_defs)
        if port not in physical_interfaces and not port.startswith("bond")
    ]

    if missing_ports:
        logger.print("Mapeamento de interfaces")
        logger.print("========================")
        logger.print("Algumas interfaces físicas do snapshot não existem neste host.")

        for port in missing_ports:
            replacement = ask(f"Mapear {port} para [manter {port}]:", port)

            if replacement != port:
                interfaces_text = replace_interface_name(interfaces_text, port, replacement)
                logger.print(f"✔ {port} -> {replacement}")

    backup_file(NETWORK_INTERFACES, logger)
    NETWORK_INTERFACES.parent.mkdir(parents=True, exist_ok=True)
    NETWORK_INTERFACES.write_text(interfaces_text)
    logger.print("✔ Rede restaurada para /etc/network/interfaces")

    if snapshot_files.get("hosts") and confirm("Restaurar também /etc/hosts?", True):
        backup_file(HOSTS_FILE, logger)
        HOSTS_FILE.write_text(snapshot_files["hosts"])
        logger.print("✔ /etc/hosts restaurado")

    if snapshot_files.get("resolv") and confirm("Restaurar também /etc/resolv.conf?", False):
        backup_file(RESOLV_CONF, logger)
        RESOLV_CONF.write_text(snapshot_files["resolv"])
        logger.print("✔ /etc/resolv.conf restaurado")

    logger.print("")
    logger.print("⚠ A rede não foi reiniciada automaticamente.")
    logger.print("Valida a consola local antes de aplicar as alterações.")
    logger.print("Comando sugerido quando estiveres pronto: ifreload -a")
    return True


def snapshot_storage_cfg(snapshot_root):
    path = snapshot_root / "pve" / "storage.cfg"

    if not path.exists():
        return "", []

    text = path.read_text()
    return text, parse_storage_cfg(text)


def current_storage_cfg():
    if not PVE_STORAGE_CFG.exists():
        return "", []

    text = PVE_STORAGE_CFG.read_text()
    return text, parse_storage_cfg(text)


def print_storage_cfg_compare(logger, snapshot_storages, current_storages):
    snapshot_by_id = {s["id"]: s for s in snapshot_storages}
    current_by_id = {s["id"]: s for s in current_storages}

    all_ids = sorted(set(snapshot_by_id) | set(current_by_id))

    logger.print("\nStorages Proxmox")
    logger.print("================")

    if not all_ids:
        logger.print("Nenhuma storage encontrada no snapshot ou no host atual.")
        return

    for storage_id in all_ids:
        snapshot = snapshot_by_id.get(storage_id)
        current = current_by_id.get(storage_id)

        if snapshot and current:
            icon = "✔" if snapshot == current else "⚠"
            logger.print(f"{icon} {storage_id}")
            logger.print(f"  Snapshot: {snapshot['type']}")
            logger.print(f"  Atual:    {current['type']}")

            if snapshot != current:
                keys = sorted(set(snapshot["options"]) | set(current["options"]))
                for key in keys:
                    snapshot_value = snapshot["options"].get(key, "ausente")
                    current_value = current["options"].get(key, "ausente")

                    if snapshot_value != current_value:
                        logger.print(f"  - {key}: snapshot='{snapshot_value}' atual='{current_value}'")
        elif snapshot:
            logger.print(f"➕ {storage_id}")
            logger.print(f"  Snapshot: {snapshot['type']}")
            logger.print("  Atual:    ausente")
        else:
            logger.print(f"➖ {storage_id}")
            logger.print("  Snapshot: ausente")
            logger.print(f"  Atual:    {current['type']}")

        logger.print("")


def restore_storage_cfg(snapshot_root, logger):
    snapshot_text, snapshot_storages = snapshot_storage_cfg(snapshot_root)

    if not snapshot_text.strip() or not snapshot_storages:
        logger.print("❌ storage.cfg não encontrado ou vazio no snapshot.")
        return False

    if PVE_STORAGE_CFG.exists():
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_dir = Path("/etc/homelab/restore-backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_dst = backup_dir / f"storage.cfg.before-restore-{stamp}"
        backup_dst.write_text(PVE_STORAGE_CFG.read_text())
        logger.print(f"Backup anterior: {backup_dst}")

    PVE_STORAGE_CFG.write_text(snapshot_text)

    logger.print("✔ Storages Proxmox restauradas para /etc/pve/storage.cfg")
    logger.print(f"Storages restauradas: {len(snapshot_storages)}")
    return True


def print_compare(logger, label, backup_value, current_value):
    icon = "✔" if str(backup_value) == str(current_value) else "⚠"
    logger.print(f"{icon} {label}")
    logger.print(f"    Snapshot: {backup_value}")
    logger.print(f"    Atual:    {current_value}")
    logger.print("")


def extract_snapshot(archive_path):
    tmp = tempfile.mkdtemp(prefix="homelab-restore-host-")
    subprocess.check_call(
        f"tar --zstd -xf '{archive_path}' -C '{tmp}'",
        shell=True,
    )

    roots = [p for p in Path(tmp).iterdir() if p.is_dir()]
    if not roots:
        raise RuntimeError("Snapshot extraído sem diretoria raiz.")

    return Path(tmp), roots[0]


def restore_toolkit(snapshot_root, logger):
    src = snapshot_root / "homelab"
    dst = Path("/opt/homelab")

    if not src.exists():
        logger.print("❌ Toolkit não encontrado no snapshot.")
        return False

    backup_dst = Path("/opt/homelab.before-restore")

    if dst.exists():
        if backup_dst.exists():
            shutil.rmtree(backup_dst)
        shutil.copytree(dst, backup_dst, symlinks=True)

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, symlinks=True)

    logger.print("✔ Toolkit restaurado para /opt/homelab")
    logger.print(f"Backup anterior: {backup_dst}")
    return True


def restore_homelab_config(snapshot_root, logger):
    dst = Path("/etc/homelab")

    candidates = [
        snapshot_root / "etc" / "homelab",
        snapshot_root / "homelab" / "config",
    ]

    src = None
    for candidate in candidates:
        if candidate.exists():
            src = candidate
            break

    if not src:
        old_yaml = snapshot_root / "homelab" / "homelab.yaml"
        if old_yaml.exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_yaml, dst / "homelab.yaml")
            logger.print("✔ homelab.yaml restaurado para /etc/homelab")
            return True

        logger.print("❌ Configuração Homelab não encontrada no snapshot.")
        return False

    backup_dst = Path("/etc/homelab.before-restore")

    if dst.exists():
        if backup_dst.exists():
            shutil.rmtree(backup_dst)
        shutil.copytree(dst, backup_dst, symlinks=True)

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, symlinks=True)

    logger.print("✔ Configuração Homelab restaurada para /etc/homelab")
    logger.print(f"Backup anterior: {backup_dst}")
    return True

def restore_backup_jobs(backup_jobs, logger):
    if not backup_jobs:
        logger.print("❌ Nenhum Job de Backup encontrado no snapshot.")
        return False

    logger.print("Jobs de Backup")
    logger.print("==============")

    for job in backup_jobs:
        job_id = job.get("id")

        if not job_id:
            logger.print("⚠ Job sem ID ignorado.")
            continue

        exists = shell(f"pvesh get /cluster/backup/{job_id} >/dev/null 2>&1 && echo yes || echo no")

        if exists == "yes":
            logger.print(f"⚠ Job já existe: {job_id}")

            if not confirm("Substituir este job?", False):
                logger.print("Ignorado.")
                continue

            shell(f"pvesh delete /cluster/backup/{job_id}", timeout=60)

        args = [
            f"--id {job_id}",
            f"--enabled {job.get('enabled', 1)}",
            f"--schedule '{job.get('schedule')}'",
            f"--storage '{job.get('storage')}'",
            f"--mode '{job.get('mode', 'snapshot')}'",
            f"--compress '{job.get('compress', 'zstd')}'",
        ]

        if job.get("all") is not None:
            args.append(f"--all {job.get('all')}")

        if job.get("vmid"):
            args.append(f"--vmid '{job.get('vmid')}'")

        prune = job.get("prune-backups", {})
        if isinstance(prune, dict) and prune:
            prune_str = ",".join([f"{k}={v}" for k, v in prune.items()])
            args.append(f"--prune-backups '{prune_str}'")

        if job.get("notes-template"):
            args.append(f"--notes-template '{job.get('notes-template')}'")

        cmd = "pvesh create /cluster/backup " + " ".join(args)

        logger.print(f"A recriar job: {job_id}")
        shell(cmd, timeout=60, logger=logger, show=True, fatal=True)

        check = shell(f"pvesh get /cluster/backup/{job_id} >/dev/null 2>&1 && echo yes || echo no")

        if check == "yes":
            logger.print(f"✔ Job recriado: {job_id}")
        else:
            logger.print(f"❌ Não foi possível validar o job: {job_id}")

    return True

def run():
    logger = Logger("restore-host")

    logger.print("Homelab Restore Host")
    logger.print("====================")

    backups = []

    for path in sorted(
        HOST_BACKUP_DIR.glob("proxmox-host-*.tar.zst"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        item = parse_backup(path)
        if item:
            backups.append(item)

    if not backups:
        logger.print("Nenhum snapshot encontrado.")
        logger.print(f"Diretoria: {HOST_BACKUP_DIR}")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\nSnapshots encontrados:\n")

    for i, b in enumerate(backups, start=1):
        marker = "  MAIS RECENTE" if i == 1 else ""
        logger.print(f"[{i}] {b['date']} {b['time']}  {human_size(b['size'])}{marker}")
        logger.print(f"    {b['path'].name}")

    choice = ask("\nEscolhe o snapshot para analisar:", "1")

    try:
        backup = backups[int(choice) - 1]
    except Exception:
        logger.print("Escolha inválida.")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\nAnálise do Snapshot")
    logger.print("===================")
    logger.print(f"Ficheiro: {backup['path'].name}")
    logger.print(f"Data:     {backup['date']} {backup['time']}")
    logger.print(f"Tamanho:  {human_size(backup['size'])}")

    try:
        manifest = load_manifest(backup["path"])
    except ManifestError as e:
        logger.print("\n❌ Não foi possível ler o manifest.json.")
        logger.print(str(e))
        logger.print(f"Log: {logger.path}")
        return

    containers = manifest.get("containers", [])
    storages = manifest.get("storages", [])
    backup_jobs = parse_backup_jobs(manifest)
    tailscale_state = manifest.get("tailscale", {})
    lcdproc_state = manifest.get("lcdproc", {})
    systemd_units = manifest.get("systemd_units", [])
    current = current_state()
    _, current_storage_defs = current_storage_cfg()
    current_network = current_network_files()
    physical_interfaces = current_physical_interfaces()
    current_tailscale = current_tailscale_state()
    current_lcdproc = current_lcdproc_files()
    current_lcdproc_services = current_lcdproc_state()
    current_units = current_systemd_units()

    snapshot_toolkit = manifest.get("toolkit_version", "desconhecido")
    current_toolkit = current["toolkit"]

    if snapshot_toolkit != current_toolkit:
        logger.print("")
        logger.print("Toolkit")
        logger.print("=======")
        logger.print(f"Snapshot : {snapshot_toolkit}")
        logger.print(f"Atual    : {current_toolkit}")
        logger.print("")
        logger.print("⚠ As versões do Toolkit são diferentes.")
        logger.print("Se escolheres restaurar o Toolkit, será pedida nova confirmação.")

    logger.print("\nResumo do Snapshot")
    logger.print("==================")
    logger.print(f"Host:        {manifest.get('hostname', 'desconhecido')}")
    logger.print(f"Toolkit:     {snapshot_toolkit}")
    logger.print(f"Proxmox:     {manifest.get('proxmox', 'desconhecido')}")
    logger.print(f"Kernel:      {manifest.get('kernel', 'desconhecido')}")
    logger.print(f"Containers:  {len(containers)}")
    logger.print(f"Storages:    {len(storages)}")
    logger.print(f"Backup Jobs: {len(backup_jobs)}")

    if backup_jobs:
        logger.print("\nJobs de Backup")
        logger.print("==============")
        for job in backup_jobs:
            logger.print(f"✔ {job.get('id', 'sem-id')}")
            logger.print(f"  Storage : {job.get('storage', '-')}")
            logger.print(f"  Schedule: {job.get('schedule', '-')}")
            logger.print(f"  Mode    : {job.get('mode', '-')}")
            logger.print(f"  Compress: {job.get('compress', '-')}")
            logger.print("")

    tmp = None
    snapshot_root = None
    snapshot_storage_defs = []

    try:
        tmp, snapshot_root = extract_snapshot(backup["path"])
        _, snapshot_storage_defs = snapshot_storage_cfg(snapshot_root)
        print_storage_cfg_compare(logger, snapshot_storage_defs, current_storage_defs)
        print_network_compare(
            logger,
            snapshot_network_files(snapshot_root),
            current_network,
            physical_interfaces,
        )
        print_tailscale_compare(logger, tailscale_state, current_tailscale)
        print_lcdproc_compare(
            logger,
            snapshot_lcdproc_files(snapshot_root),
            current_lcdproc,
            lcdproc_state,
            current_lcdproc_services,
        )
        print_systemd_compare(
            logger,
            snapshot_systemd_units(snapshot_root),
            current_units,
            systemd_units,
        )
    except Exception as e:
        logger.print("\nComponentes Proxmox")
        logger.print("===================")
        logger.print(f"⚠ Não foi possível analisar storage.cfg/rede: {e}")
    finally:
        if tmp and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    logger.print("\nComparação com host atual")
    logger.print("=========================")

    print_compare(logger, "Hostname", manifest.get("hostname", "?"), current["hostname"])
    print_compare(logger, "Toolkit", snapshot_toolkit, current["toolkit"])
    print_compare(logger, "Kernel", manifest.get("kernel", "?"), current["kernel"])
    print_compare(logger, "Proxmox", manifest.get("proxmox", "?"), current["proxmox"])
    print_compare(logger, "Containers", len(containers), current["containers"])
    print_compare(logger, "Storages", len(storages), current["storages"])

    logger.print("Estado")
    logger.print("======")
    logger.print("✔ Análise concluída.")
    logger.print("Nenhuma alteração foi efetuada.")

    logger.print("\nO que pretendes fazer?")
    logger.print("======================")
    logger.print("1 Sair sem restaurar")
    logger.print("2 Restaurar componentes")

    action = ask("\nEscolha:", "1")

    if action != "2":
        logger.print("Cancelado. Nenhuma alteração efetuada.")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\nComponentes disponíveis")
    logger.print("=======================")
    logger.print("1 Toolkit")
    logger.print("2 Configuração Homelab")
    logger.print("3 Jobs de Backup")
    logger.print("4 Toolkit + Configuração Homelab")
    logger.print("5 Storages Proxmox")
    logger.print("6 Rede Proxmox")
    logger.print("7 Tailscale")
    logger.print("8 LCDproc")
    logger.print("9 Serviços systemd")
    logger.print("all Todos os componentes recomendados")
    logger.print("")
    logger.print("Podes escolher vários, por exemplo: 2,5,6,7,8,3")
    logger.print("0 Cancelar")

    selected = parse_component_selection(ask("\nEscolha:", "0"))

    if not selected:
        logger.print("Cancelado. Nenhuma alteração efetuada.")
        logger.print(f"Log: {logger.path}")
        return

    if "1" in selected and snapshot_toolkit != current_toolkit:
        if not confirm("Pretendes restaurar o Toolkit mesmo assim?", False):
            selected = [key for key in selected if key != "1"]

    if not selected:
        logger.print("Cancelado. Nenhuma alteração efetuada.")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\nResumo da operação")
    logger.print("==================")
    logger.print(f"Snapshot: {backup['path'].name}")

    print_component_summary(logger, selected)

    logger.print("")
    logger.print("Segurança")
    logger.print("=========")

    if confirm("Criar snapshot de segurança antes do restauro?", True):
        logger.print("A criar snapshot...")

        try:
            shell("homelab backup", timeout=300)
            logger.print("✔ Snapshot criado com sucesso.")
        except Exception as e:
            logger.print(f"❌ Não foi possível criar o snapshot: {e}")

            if not confirm("Continuar sem snapshot?", False):
                logger.print("Operação cancelada.")
                logger.print(f"Log: {logger.path}")
                return

    if not confirm("\nContinuar?", False):
        logger.print("Cancelado. Nenhuma alteração efetuada.")
        logger.print(f"Log: {logger.path}")
        return

    tmp = None

    try:
        tmp, snapshot_root = extract_snapshot(backup["path"])

        logger.print("\nExecução")
        logger.print("========")

        if "1" in selected:
            restore_toolkit(snapshot_root, logger)

        if "2" in selected:
            restore_homelab_config(snapshot_root, logger)
            
        if "5" in selected:
            restore_storage_cfg(snapshot_root, logger)

        if "6" in selected:
            restore_network(snapshot_root, logger)

        if "7" in selected:
            restore_tailscale(tailscale_state, logger)

        if "8" in selected:
            restore_lcdproc(snapshot_root, lcdproc_state, logger)

        if "3" in selected:
            restore_backup_jobs(backup_jobs, logger)

        if "9" in selected:
            restore_systemd_units(snapshot_root, systemd_units, logger)

    except Exception as e:
        logger.print(f"❌ Falha no restauro: {e}")
        logger.print(f"Log: {logger.path}")
        return

    finally:
        if tmp and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    logger.print("\n✔ Restore Host concluído.")

    if confirm("Executar Homelab Doctor agora?", True):
        logger.print("\nDoctor")
        logger.print("======")
        output = shell("homelab doctor", timeout=120)
        logger.print(output)

    logger.print("\nResumo final")
    logger.print("============")

    print_component_final_summary(logger, selected)

    logger.print(f"\nLog: {logger.path}")
