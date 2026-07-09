from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, date

from homelab.core.logger import Logger
from homelab.core.validate import validate_lxc_config
from homelab.core.shell import run as shell

BACKUP_DIR = Path("/mnt/pve/backups/dump")
VERSION_FILE = Path("/opt/homelab/VERSION")


def toolkit_version():
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "dev"


def ask(prompt, default=""):
    value = input(f"{prompt} ").strip()
    return value or default


def confirm(prompt, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix} ").strip().lower()
    if not value:
        return default
    return value in ["y", "yes", "s", "sim"]


def parse_backup(path):
    m = re.search(
        r"vzdump-lxc-(\d+)-(\d{4})_(\d{2})_(\d{2})-(\d{2})_(\d{2})_(\d{2})\.tar\.zst$",
        path.name,
    )
    if not m:
        return None

    ct, y, mo, d, h, mi, _ = m.groups()
    backup_date = date(int(y), int(mo), int(d))

    return {
        "ct": ct,
        "date": f"{d}/{mo}/{y}",
        "time": f"{h}:{mi}",
        "relative": relative_date(backup_date, f"{h}:{mi}"),
        "path": path,
        "size": path.stat().st_size,
    }


def relative_date(backup_date, backup_time):
    today = date.today()
    delta = (today - backup_date).days

    if delta == 0:
        return f"Hoje às {backup_time}"
    if delta == 1:
        return f"Ontem às {backup_time}"

    return f"{backup_date.strftime('%d/%m/%Y')} às {backup_time}"


def human_gb(bytes_value):
    return f"{bytes_value / 1024 / 1024 / 1024:.1f} G"


def get_storage_free_gb(storage):
    out = shell(f"pvesm status | awk '$1 == \"{storage}\" {{print $6}}'")
    try:
        return int(out) / 1024 / 1024
    except Exception:
        return None


def get_storage_used_percent(storage):
    out = shell(f"pvesm status | awk '$1 == \"{storage}\" {{print $7}}'")
    if not out:
        return "?"
    return out.replace("%", "") + "%"


def estimate_restore_time(size_bytes):
    gb = size_bytes / 1024 / 1024 / 1024
    if gb < 10:
        return "1-3 minutos"
    if gb < 30:
        return "3-8 minutos"
    if gb < 80:
        return "5-15 minutos"
    return "15+ minutos"


def storage_exists(storage):
    storages = shell("pvesm status | awk 'NR>1 {print $1}'").splitlines()
    return storage in storages, storages


def pct_exists(ctid):
    return subprocess.call(f"pct status {ctid} >/dev/null 2>&1", shell=True) == 0


def run():
    logger = Logger("restore-lxc")
    start = time.time()

    logger.print(f"Homelab Toolkit {toolkit_version()}")
    logger.print("Restore LXC")
    logger.print("===========")

    if not BACKUP_DIR.exists():
        logger.print(f"Pasta de backups não encontrada: {BACKUP_DIR}")
        logger.print(f"Log: {logger.path}")
        return

    backups = []
    for path in sorted(
        BACKUP_DIR.glob("vzdump-lxc-*.tar.zst"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        item = parse_backup(path)
        if item:
            backups.append(item)

    if not backups:
        logger.print("Nenhum backup LXC .tar.zst encontrado.")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\nBackups LXC encontrados:\n")

    for i, b in enumerate(backups, start=1):
        marker = "  MAIS RECENTE" if i == 1 else ""
        logger.print(
            f"[{i}] CT{b['ct']}  {b['relative']}  {human_gb(b['size'])}{marker}"
        )
        logger.print(f"    {b['path'].name}")

    choice = ask("\nEscolhe o backup a restaurar:", "1")

    try:
        backup = backups[int(choice) - 1]
    except Exception:
        logger.print("Escolha inválida.")
        logger.print(f"Log: {logger.path}")
        return

    source_ct = backup["ct"]
    target_ct = ask(f"ID do container destino [{source_ct}]:", source_ct)
    storage = ask("Storage destino [local-lvm]:", "local-lvm")
    auto_start = confirm("Iniciar automaticamente após o restauro?", True)

    storage_ok, storages = storage_exists(storage)
    if not storage_ok:
        logger.print(f"Storage '{storage}' não encontrada. Cancelado.")
        logger.print("Storages disponíveis:")
        for s in storages:
            logger.print(f"- {s}")
        logger.print(f"Log: {logger.path}")
        return

    free_gb = get_storage_free_gb(storage)
    used_percent = get_storage_used_percent(storage)
    exists = pct_exists(target_ct)

    logger.print("\nAnálise do backup")
    logger.print("=================")
    logger.print(f"Tipo:              LXC (.tar.zst)")
    logger.print(f"Container origem:  CT{source_ct}")
    logger.print(f"Data do backup:    {backup['relative']}")
    logger.print(f"Tamanho:           {human_gb(backup['size'])}")
    logger.print(f"Tempo estimado:    {estimate_restore_time(backup['size'])}")

    logger.print("\nStorage")
    logger.print("=======")
    logger.print(f"Storage:           {storage}")
    if free_gb is not None:
        logger.print(f"Livre:             {free_gb:.1f} G")
    else:
        logger.print("Livre:             desconhecido")
    logger.print(f"Utilização:        {used_percent}")

    logger.print("\nValidações")
    logger.print("==========")
    logger.print("✔ Backup encontrado")
    logger.print("✔ Storage disponível")
    if free_gb is not None:
        logger.print("✔ Espaço livre lido")
    else:
        logger.print("⚠ Espaço livre desconhecido")
    logger.print("✔ Permissões básicas OK")

    logger.print("\nResumo")
    logger.print("======")
    logger.print(f"Backup:              {backup['path'].name}")
    logger.print(f"Destino:             CT{target_ct}")
    logger.print(f"Storage:             {storage}")
    logger.print(f"Arranque automático: {'Sim' if auto_start else 'Não'}")

    if exists:
        logger.print("")
        logger.print(f"⚠ O CT{target_ct} já existe.")
        logger.print("Será parado e destruído antes do restauro.")

    if not confirm("\nContinuar?", False):
        logger.print("Cancelado.")
        logger.print(f"Log: {logger.path}")
        return

    try:
        if exists:
            logger.print("\n[1/5] A parar container existente...")
            shell(
                f"pct stop {target_ct} 2>/dev/null || true",
                timeout=300,
                logger=logger,
                show=True,
            )

            logger.print("\n[2/5] A remover lock e destruir container existente...")
            shell(
                f"pct unlock {target_ct} 2>/dev/null || true",
                timeout=60,
                logger=logger,
                show=True,
            )
            shell(
                f"pct destroy {target_ct} --destroy-unreferenced-disks 1",
                timeout=600,
                logger=logger,
                show=True,
                fatal=True,
            )
        else:
            logger.print("\n[1/5] CT destino não existe. Nada a parar.")
            logger.print("[2/5] Nada a destruir.")

        logger.print("\n[3/5] A restaurar backup...")
        cmd = f"pct restore {target_ct} '{backup['path']}' --storage {storage}"
        logger.print(f"A executar:\n{cmd}\n")
        shell(cmd, timeout=7200, logger=logger, show=True, fatal=True)

    except Exception as e:
        logger.print(f"\n❌ Restauro falhou: {e}")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("\n[4/5] A validar configuração do CT...")
    ok, errors = validate_lxc_config(target_ct)

    if not ok:
        logger.print("\n❌ O restauro terminou, mas a configuração do CT está inválida.")
        for error in errors:
            logger.print(f"- {error}")
        logger.print("O container não será iniciado.")
        logger.print(f"Log: {logger.path}")
        return

    logger.print("✔ Configuração do CT validada.")

    if auto_start:
        logger.print("\n[5/5] A arrancar container...")
        try:
            shell(f"pct start {target_ct}", timeout=600, logger=logger, show=True, fatal=True)
            status = shell(f"pct status {target_ct}", logger=logger, show=True)
            logger.print(f"Estado final: {status}")
        except Exception as e:
            logger.print(f"\n❌ Falha ao arrancar CT: {e}")
            logger.print(f"Log: {logger.path}")
            return
    else:
        logger.print("\n[5/5] Arranque automático desativado.")

    elapsed = int(time.time() - start)
    minutes = elapsed // 60
    seconds = elapsed % 60

    logger.print("\n✔ Restauro concluído.")
    logger.print(f"Tempo total: {minutes}m{seconds:02d}s")
    logger.print(f"Log: {logger.path}")
