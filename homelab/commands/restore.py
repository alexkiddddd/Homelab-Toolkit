import subprocess

from homelab.core.logger import Logger


def ask(prompt, default=""):
    value = input(f"{prompt} ").strip()
    return value or default


def run_interactive(cmd):
    return subprocess.call(cmd, shell=True)


def run():
    logger = Logger("restore")

    print("Homelab Restore")
    print("===============")
    print()
    print("Este assistente vai guiar a recuperação do homelab.")
    print()
    print("Fases disponíveis:")
    print("1 Restore Host")
    print("2 Restore LXC")
    print("3 Doctor")
    print("0 Sair")
    print()

    choice = ask("Escolha:", "0")

    if choice == "1":
        run_interactive("homelab restore-host")
    elif choice == "2":
        run_interactive("homelab restore-lxc")
    elif choice == "3":
        run_interactive("homelab doctor")
    else:
        print("Cancelado.")

    logger.write("Comando restore executado.")
    print(f"\nLog: {logger.path}")