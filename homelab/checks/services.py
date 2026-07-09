from homelab.core.shell import run as shell


SERVICES = [
    ("ssh", "SSH"),
    ("pveproxy", "Proxmox Web UI"),
    ("pvedaemon", "Proxmox Daemon"),
    ("lcdproc", "LCDproc"),
    ("pve-lcd-status", "LCD Status"),
    ("tailscaled", "Tailscale"),
]


def service_exists(service):
    return shell(f"systemctl list-unit-files | awk '{{print $1}}' | grep -qx '{service}.service' && echo yes || true") == "yes"


def service_active(service):
    return shell(f"systemctl is-active {service} 2>/dev/null || true")


def run():
    items = []
    score = 10
    applicable = 0

    for service, label in SERVICES:
        if not service_exists(service):
            continue

        applicable += 1
        active = service_active(service)
        status = "ok" if active == "active" else "warn"

        if status != "ok":
            score -= 2

        items.append({"name": label, "value": active, "status": status})

    if applicable == 0:
        items.append({"name": "Serviços", "value": "nenhum serviço opcional detetado", "status": "info"})

    return {
        "title": "Serviços",
        "score": max(score, 0),
        "max_score": 10,
        "items": items,
    }
