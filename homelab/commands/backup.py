import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from homelab.core.shell import run as shell
from homelab.core.config import get


def mkdir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def copy_if_exists(src, dst):
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        return

    mkdir(dst)

    if src.is_dir():
        shutil.copytree(
            src,
            dst / src.name,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.tmp")
        )
    else:
        shutil.copy2(src, dst / src.name)


def write_cmd(dst, name, cmd):
    Path(dst, name).write_text(shell(cmd) + "\n")


def get_toolkit_version():
    version_file = Path("/opt/homelab/VERSION")
    return version_file.read_text().strip() if version_file.exists() else "unknown"


def get_containers():
    containers = []
    lines = shell("pct list | awk 'NR>1 {print $1}'").splitlines()

    for ctid in lines:
        hostname = shell(
            f"pct config {ctid} 2>/dev/null | awk -F': ' '/^hostname:/ {{print $2; exit}}'"
        )
        status = shell(f"pct status {ctid} 2>/dev/null | awk '{{print $2}}'")
        containers.append({
            "id": ctid,
            "hostname": hostname,
            "status": status,
        })

    return containers


def get_storages():
    storages = []
    output = shell("pvesm status")

    for line in output.splitlines():
        if not line.strip():
            continue

        if line.startswith("Name"):
            continue

        parts = line.split()

        if len(parts) < 4:
            continue

        storages.append({
            "name": parts[0],
            "type": parts[1] if len(parts) > 1 else "",
            "status": parts[2] if len(parts) > 2 else "",
            "total_kib": parts[3] if len(parts) > 3 else "",
            "used_kib": parts[4] if len(parts) > 4 else "",
            "available_kib": parts[5] if len(parts) > 5 else "",
            "usage": parts[6] if len(parts) > 6 else "",
        })

    return storages


def get_latest_lxc_backups():
    dump = Path("/mnt/pve/backups/dump")
    backups = []

    if not dump.exists():
        return backups

    for path in sorted(dump.glob("vzdump-lxc-*.tar.zst"), key=lambda p: p.stat().st_mtime, reverse=True):
        backups.append(path.name)

    return backups[:10]


def get_tailscale_prefs():
    raw = shell("tailscale debug prefs 2>/dev/null || echo '{}'")

    try:
        prefs = json.loads(raw)
    except Exception:
        return {}

    config = prefs.get("Config")
    if isinstance(config, dict):
        for key in [
            "PrivateNodeKey",
            "OldPrivateNodeKey",
            "NetworkLockKey",
            "NodeID",
        ]:
            config.pop(key, None)

        profile = config.get("UserProfile")
        if isinstance(profile, dict):
            for key in ["ID", "LoginName", "DisplayName", "ProfilePicURL"]:
                profile.pop(key, None)

    return prefs


def get_tailscale_state():
    return {
        "installed": shell("command -v tailscale >/dev/null 2>&1 && echo yes || echo no") == "yes",
        "service_enabled": shell("systemctl is-enabled tailscaled 2>/dev/null || true"),
        "service_active": shell("systemctl is-active tailscaled 2>/dev/null || true"),
        "ip4": shell("tailscale ip -4 2>/dev/null || true"),
        "status": shell("tailscale status 2>/dev/null || true"),
        "prefs": get_tailscale_prefs(),
    }


def get_lcdproc_state():
    return {
        "installed": shell("command -v LCDd >/dev/null 2>&1 && echo yes || echo no") == "yes",
        "LCDd_enabled": shell("systemctl is-enabled LCDd 2>/dev/null || true"),
        "LCDd_active": shell("systemctl is-active LCDd 2>/dev/null || true"),
        "lcdproc_enabled": shell("systemctl is-enabled lcdproc 2>/dev/null || true"),
        "lcdproc_active": shell("systemctl is-active lcdproc 2>/dev/null || true"),
    }


def get_fan_control_state():
    service = "xg210-fan.service"
    script = Path("/usr/local/bin/xg210-fan.sh")
    unit = Path("/etc/systemd/system") / service

    return {
        "service": service,
        "unit_path": str(unit),
        "unit_exists": unit.exists(),
        "script_path": str(script),
        "script_exists": script.exists(),
        "script_mode": oct(script.stat().st_mode & 0o777) if script.exists() else "",
        "enabled": shell(f"systemctl is-enabled {service} 2>/dev/null || true"),
        "active": shell(f"systemctl is-active {service} 2>/dev/null || true"),
    }


def get_systemd_units():
    root = Path("/etc/systemd/system")
    suffixes = (".service", ".timer", ".mount", ".path", ".socket")
    units = []

    if not root.exists():
        return units

    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if not path.name.endswith(suffixes):
            continue

        units.append({
            "name": path.name,
            "kind": path.suffix.replace(".", ""),
            "is_symlink": path.is_symlink(),
            "enabled": shell(f"systemctl is-enabled '{path.name}' 2>/dev/null || true"),
            "active": shell(f"systemctl is-active '{path.name}' 2>/dev/null || true"),
        })

    return units


def run():
    destination = Path(get("backup.destination", "/mnt/pve/backups/host-config"))
    keep = int(get("backup.keep", "30"))

    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    work = Path(f"/tmp/homelab-backup-{stamp}")
    archive = destination / f"proxmox-host-{stamp}.tar.zst"

    print("Homelab Backup")
    print("==============")
    print(f"Destino: {destination}")
    print()

    mkdir(work)
    mkdir(destination)

    for d in [
        work / "etc",
        work / "pve",
        work / "system",
        work / "info",
        work / "containers",
        work / "homelab",
    ]:
        mkdir(d)

    for f in [
        "/etc/fstab",
        "/etc/hosts",
        "/etc/resolv.conf",
        "/etc/network/interfaces",
        "/etc/LCDd.conf",
        "/etc/lcdproc.conf",
        "/etc/modules",
        "/etc/default/grub",
	"/etc/cron.d/homelab-backup",
    ]:
        copy_if_exists(f, work / "etc")

    for d in [
        "/etc/modprobe.d",
        "/etc/homelab",
        "/opt/homelab",
    ]:
        copy_if_exists(d, work)

    copy_if_exists("/usr/local/bin/xg210-fan.sh", work / "usr" / "local" / "bin")

    for f in [
        "/etc/pve/storage.cfg",
        "/etc/pve/datacenter.cfg",
    ]:
        copy_if_exists(f, work / "pve")

    copy_if_exists("/etc/systemd/system", work / "system")

    write_cmd(work / "info", "pveversion.txt", "pveversion -v")
    write_cmd(work / "info", "hostname.txt", "hostnamectl")
    write_cmd(work / "info", "ip_addr.txt", "ip a")
    write_cmd(work / "info", "ip_route.txt", "ip route")
    write_cmd(work / "info", "df_h.txt", "df -h")
    write_cmd(work / "info", "lsblk.txt", "lsblk -f")
    write_cmd(work / "info", "lvs.txt", "lvs")
    write_cmd(work / "info", "vgs.txt", "vgs")
    write_cmd(work / "info", "pvesm_status.txt", "pvesm status")
    write_cmd(work / "info", "mount.txt", "mount")
    write_cmd(work / "info", "sensors.txt", "sensors 2>/dev/null || true")
    write_cmd(work / "info", "packages.txt", "dpkg --get-selections")
    write_cmd(work / "info", "enabled_services.txt", "systemctl list-unit-files --state=enabled")
    write_cmd(work / "info", "crontab_root.txt", "crontab -l 2>/dev/null || true")
    write_cmd(work / "info", "pci.txt", "lspci")
    write_cmd(work / "info", "usb.txt", "lsusb")
    write_cmd(work / "info", "dri.txt", "ls -la /dev/dri 2>/dev/null || true")
    write_cmd(work / "info", "tailscale.txt", "tailscale status 2>/dev/null || true")
    write_cmd(work / "pve", "backup_jobs.json", "pvesh get /cluster/backup --output-format json 2>/dev/null || echo '[]'")
    write_cmd(work / "pve", "backup_jobs.txt", "pvesh get /cluster/backup 2>/dev/null || true")

    for ct in shell("pct list | awk 'NR>1 {print $1}'").splitlines():
        write_cmd(work / "containers", f"{ct}.conf", f"pct config {ct}")

    manifest = {
        "toolkit_version": get_toolkit_version(),
        "backup_date": now.isoformat(timespec="seconds"),
        "hostname": shell("hostname"),
        "proxmox": shell("pveversion"),
        "kernel": shell("uname -r"),
        "containers": get_containers(),
        "storages": get_storages(),
        "linked_lxc_backups": get_latest_lxc_backups(),
        "backup_jobs": shell("pvesh get /cluster/backup --output-format json 2>/dev/null || echo '[]'"),
        "tailscale": get_tailscale_state(),
        "lcdproc": get_lcdproc_state(),
        "fan_control": get_fan_control_state(),
        "systemd_units": get_systemd_units(),
    }

    (work / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    inventory = {
        "cpu": shell("lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//'"),
        "memory": shell("free -h | awk '/Mem:/ {print $2}'"),
        "gpu": shell("lspci | grep -Ei 'vga|display' | head -1"),
        "network": shell("ip -br addr"),
        "storage": get_storages(),
        "containers": get_containers(),
    }

    (work / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))

    (work / "README.md").write_text(f"""# Homelab Host Backup

Data: {now.strftime('%Y-%m-%d %H:%M:%S')}
Host: {manifest["hostname"]}
Toolkit: {manifest["toolkit_version"]}

## Proxmox

{manifest["proxmox"]}

## Containers

{shell("pct list")}

## Storage

{shell("pvesm status")}

Este backup contém a configuração do host Proxmox.
Os backups dos LXC continuam a ser feitos pelo Proxmox.
""")

    print("A comprimir...")
    subprocess.check_call(
        f"tar --zstd "
        f"--exclude='__pycache__' "
        f"--exclude='*.pyc' "
        f"--exclude='*.pyo' "
        f"--exclude='*.tmp' "
        f"-cf '{archive}' -C '{work.parent}' '{work.name}'",
        shell=True
    )

    checksum = shell(f"sha256sum '{archive}'")
    (destination / f"{archive.name}.sha256").write_text(checksum + "\n")

    backups = sorted(
        destination.glob("proxmox-host-*.tar.zst"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old in backups[keep:]:
        old.unlink()
        sha = destination / f"{old.name}.sha256"
        if sha.exists():
            sha.unlink()

    shutil.rmtree(work, ignore_errors=True)

    size_mb = archive.stat().st_size / 1024 / 1024

    print()
    print("✔ Backup criado")
    print(f"Ficheiro: {archive}")
    print(f"Tamanho:  {size_mb:.2f} MB")
    print(f"SHA256:   {archive}.sha256")
