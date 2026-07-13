import subprocess
from pathlib import Path

from homelab.core.logger import Logger

HOST_BACKUP_DIR = Path("/mnt/pve/backups/host-config")
LXC_BACKUP_DIR = Path("/mnt/pve/backups/dump")
BACKUP_STORAGE_DIR = Path("/mnt/pve/backups")


def ask(prompt, default=""):
    value = input(f"{prompt} ").strip()
    return value or default


def confirm(prompt, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix} ").strip().lower()
    if not value:
        return default
    return value in ["y", "yes", "s", "sim"]


def run_interactive(cmd):
    return subprocess.call(cmd)


def backup_count(path, pattern):
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))


def path_state(path):
    if not path.exists():
        return "ausente"
    if not path.is_dir():
        return "não é diretoria"
    return "ok"


def print_backup_storage_bootstrap(host_backups, lxc_backups):
    print("Bootstrap da storage de backups")
    print("===============================")
    print("O Toolkit precisa de ler os backups antes de restaurar o host.")
    print("Disponibiliza temporariamente a NAS/storage de backups e volta a executar:")
    print()
    print("  homelab restore")
    print()
    print("Caminhos esperados:")
    print(f"  Host snapshots: {HOST_BACKUP_DIR}")
    print(f"  LXC backups:    {LXC_BACKUP_DIR}")
    print()
    print("Exemplos rápidos:")
    print("  NFS:")
    print("    mkdir -p /mnt/pve/backups")
    print("    mount -t nfs <NAS_IP>:/<export> /mnt/pve/backups")
    print()
    print("  SMB/CIFS:")
    print("    apt install -y cifs-utils")
    print("    mkdir -p /mnt/pve/backups")
    print("    mount -t cifs //<NAS_IP>/<share> /mnt/pve/backups -o username=<user>")
    print()
    print("Depois do restore, a configuração permanente das storages Proxmox pode ser reposta")
    print("a partir do snapshot, incluindo /etc/pve/storage.cfg.")
    print()

    if host_backups == 0:
        print("⚠ Sem snapshots de host, o Restore Host não consegue arrancar.")
    if lxc_backups == 0:
        print("⚠ Sem backups LXC, o Restore LXC não terá containers para restaurar.")
    print()


def print_preflight():
    host_backups = backup_count(HOST_BACKUP_DIR, "proxmox-host-*.tar.zst")
    lxc_backups = backup_count(LXC_BACKUP_DIR, "vzdump-lxc-*.tar.zst")

    print("Pré-verificação")
    print("===============")
    print(f"Storage base:   {path_state(BACKUP_STORAGE_DIR)} em {BACKUP_STORAGE_DIR}")
    print(f"Host dir:       {path_state(HOST_BACKUP_DIR)}")
    print(f"LXC dir:        {path_state(LXC_BACKUP_DIR)}")
    print(f"Host snapshots: {host_backups} em {HOST_BACKUP_DIR}")
    print(f"LXC backups:    {lxc_backups} em {LXC_BACKUP_DIR}")
    print()

    if host_backups == 0:
        print("⚠ Nenhum snapshot de host encontrado.")
    if lxc_backups == 0:
        print("⚠ Nenhum backup LXC encontrado.")
    if host_backups == 0 or lxc_backups == 0:
        print()

    if host_backups == 0:
        print_backup_storage_bootstrap(host_backups, lxc_backups)

        if not confirm("Continuar mesmo sem snapshots de host?", False):
            return False

    return True


def run_guided(logger):
    print("Modo guiado")
    print("===========")
    print()
    print("Sequência recomendada:")
    print("1 Restore Host: Toolkit, config, storages, rede, Tailscale, LCDproc, jobs")
    print("2 Restore LXC")
    print("3 Doctor final")
    print()

    if not print_preflight():
        print("Cancelado.")
        logger.write("Modo guiado cancelado: snapshots de host ausentes.")
        return

    if not confirm("Continuar com recuperação guiada?", False):
        print("Cancelado.")
        return

    while True:
        print()
        print("Fase 1: Restore Host")
        print("====================")
        print("Executa esta fase as vezes necessárias para restaurar componentes diferentes.")
        logger.write("A executar restore-host.")
        run_interactive(["homelab", "restore-host"])

        if not confirm("Foi restaurado algum componente nesta fase?", False):
            if confirm("Sair do modo guiado agora?", True):
                print("Modo guiado terminado.")
                logger.write("Modo guiado terminado sem avançar para as próximas fases.")
                return

            if not confirm("Voltar ao restore-host?", False):
                break

            continue

        if not confirm("Restaurar outro componente do host?", False):
            break

    if confirm("Avançar para restore LXC?", True):
        print()
        print("Fase 2: Restore LXC")
        print("===================")
        logger.write("A executar restore-lxc.")
        run_interactive(["homelab", "restore-lxc"])

    if confirm("Executar Doctor final?", True):
        print()
        print("Fase 3: Doctor")
        print("==============")
        logger.write("A executar doctor.")
        run_interactive(["homelab", "doctor"])


def run():
    logger = Logger("restore")

    print("Homelab Restore")
    print("===============")
    print()
    print("Este assistente vai guiar a recuperação do homelab.")
    print()
    print("Fases disponíveis:")
    print("1 Recuperação guiada")
    print("2 Restore Host")
    print("3 Restore LXC")
    print("4 Doctor")
    print("0 Sair")
    print()

    choice = ask("Escolha:", "0")

    if choice == "1":
        run_guided(logger)
    elif choice == "2":
        run_interactive(["homelab", "restore-host"])
    elif choice == "3":
        run_interactive(["homelab", "restore-lxc"])
    elif choice == "4":
        run_interactive(["homelab", "doctor"])
    else:
        print("Cancelado.")

    logger.write("Comando restore executado.")
    print(f"\nLog: {logger.path}")
