#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERSION_FILE = Path("/opt/homelab/VERSION")
COMMIT_FILE = Path("/opt/homelab/COMMIT")


def version():
    value = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "dev"

    if COMMIT_FILE.exists():
        commit = COMMIT_FILE.read_text().strip()
        if commit:
            return f"{value} ({commit})"

    return value


def help_msg():
    print(f"""Homelab Toolkit v{version()}

Comandos:
  backup        Backup da configuração do host
  restore       Assistente de recuperação do homelab
  restore-host  Analisar/restaurar configuração do host
  restore-lxc   Restaurar containers LXC
  report        Relatório rápido do host
  doctor        Diagnóstico do host
  update        Atualizar Toolkit a partir do Git
  note          Registar alteração
  version       Mostrar versão
""")


def main():
    if len(sys.argv) < 2:
        help_msg()
        return

    cmd = sys.argv[1]

    if cmd == "backup":
        from homelab.commands.backup import run
        run()
    elif cmd == "restore":
        from homelab.commands.restore import run
        run()
    elif cmd == "restore-host":
        from homelab.commands.restore_host import run
        run()
    elif cmd == "restore-lxc":
        from homelab.commands.restore_lxc import run
        run()
    elif cmd == "report":
        from homelab.commands.report import run
        run()
    elif cmd == "doctor":
        from homelab.commands.doctor import run
        run()
    elif cmd == "update":
        from homelab.commands.update import run
        run()
    elif cmd == "note":
        from homelab.commands.note import run
        run(sys.argv[2:])
    elif cmd == "version":
        print(version())
    else:
        help_msg()


if __name__ == "__main__":
    main()
