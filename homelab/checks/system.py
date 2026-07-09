from homelab.core.shell import run as shell


def run():
    pve = shell("pveversion 2>/dev/null")
    kernel = shell("uname -r")
    uptime = shell("uptime -p")

    items = [
        {"name": "Proxmox", "value": pve or "não detetado", "status": "ok" if pve else "fail"},
        {"name": "Kernel", "value": kernel, "status": "ok"},
        {"name": "Uptime", "value": uptime.replace("up ", ""), "status": "ok"},
    ]

    score = 10 if pve else 0

    return {
        "title": "Sistema",
        "score": score,
        "max_score": 10,
        "items": items,
    }
