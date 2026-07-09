from pathlib import Path
import time


LXC_BACKUP_DIR = Path("/mnt/pve/backups/dump")
HOST_BACKUP_DIR = Path("/mnt/pve/backups/host-config")


def age_label(path):
    age = time.time() - path.stat().st_mtime
    hours = int(age / 3600)

    if hours < 24:
        return f"há {hours}h"

    days = int(hours / 24)
    return f"há {days}d"


def newest(pattern_dir, pattern):
    files = list(pattern_dir.glob(pattern)) if pattern_dir.exists() else []
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def run():
    lxc = newest(LXC_BACKUP_DIR, "vzdump-lxc-*.tar.zst")
    host = newest(HOST_BACKUP_DIR, "proxmox-host-*.tar.zst")

    items = []
    score = 20

    if lxc:
        age = (time.time() - lxc.stat().st_mtime) / 3600
        status = "ok" if age <= 36 else "warn"
        if status != "ok":
            score -= 5
        items.append({"name": "Último backup LXC", "value": age_label(lxc), "status": status})
    else:
        score -= 10
        items.append({"name": "Backup LXC", "value": "não encontrado", "status": "fail"})

    if host:
        age = (time.time() - host.stat().st_mtime) / 3600
        status = "ok" if age <= 168 else "warn"
        if status != "ok":
            score -= 5
        items.append({"name": "Último backup host", "value": age_label(host), "status": status})
    else:
        score -= 10
        items.append({"name": "Backup host", "value": "não encontrado", "status": "fail"})

    return {
        "title": "Backups",
        "score": max(score, 0),
        "max_score": 20,
        "items": items,
    }
