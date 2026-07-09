from homelab.core.shell import run as shell


def current_state():

    return {

        "hostname": shell("hostname"),

        "kernel": shell("uname -r"),

        "proxmox": shell("pveversion"),

    }


def compare(manifest):

    current = current_state()

    result = []

    def add(name, backup, current):

        status = "ok" if backup == current else "warning"

        result.append(
            {
                "name": name,
                "backup": backup,
                "current": current,
                "status": status,
            }
        )

    add(
        "Hostname",
        manifest.get("hostname", "?"),
        current["hostname"],
    )

    add(
        "Kernel",
        manifest.get("kernel", "?"),
        current["kernel"],
    )

    add(
        "Proxmox",
        manifest.get("proxmox", "?"),
        current["proxmox"],
    )

    return result
