from homelab.core.shell import run as shell


def run():
    print("Homelab Report")
    print("================")
    print()
    print("Host")
    print(shell("hostnamectl | grep -E 'Static hostname|Operating System|Kernel'"))
    print()
    print("Proxmox")
    print(shell("pveversion"))
    print()
    print("Storage")
    print(shell("pvesm status"))
    print()
    print("Containers")
    print(shell("pct list"))
    print()
    print("Temperaturas")
    print(shell("sensors 2>/dev/null | grep -E 'Package id 0|CPUTIN|Core 0|temp1' || true"))
