from pathlib import Path
import subprocess

from homelab.core.logger import Logger

SOURCE_FILE = Path("/opt/homelab/SOURCE")


def run_cmd(cmd, cwd=None, logger=None):
    if logger:
        logger.write("$ " + " ".join(cmd))

    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    output = result.stdout.strip()
    if output:
        print(output)
        if logger:
            logger.write(output)

    if result.returncode != 0:
        raise RuntimeError(f"Comando falhou ({result.returncode}): {' '.join(cmd)}")

    return output


def run():
    logger = Logger("update")

    print("Homelab Update")
    print("==============")

    if not SOURCE_FILE.exists():
        print("Fonte Git não encontrada.")
        print("Reinstala a partir de um clone Git para ativar updates automáticos.")
        print("Exemplo:")
        print("  cd /opt")
        print("  git clone https://github.com/alexkiddddd/Homelab-Toolkit.git homelab-src")
        print("  cd homelab-src")
        print("  ./install")
        print(f"\nLog: {logger.path}")
        return

    source = Path(SOURCE_FILE.read_text().strip())

    if not source.exists():
        print(f"Fonte Git não encontrada: {source}")
        print(f"\nLog: {logger.path}")
        return

    if not (source / ".git").exists():
        print(f"A fonte não é um repositório Git: {source}")
        print(f"\nLog: {logger.path}")
        return

    try:
        print(f"Fonte: {source}")
        print()
        status = run_cmd(["git", "status", "--short"], cwd=source, logger=logger)

        if status:
            print("")
            print("❌ Existem alterações locais na fonte Git.")
            print("Resolve-as antes de atualizar, ou repõe a fonte com:")
            print(f"  cd {source}")
            print("  git reset --hard")
            print(f"Log: {logger.path}")
            return

        run_cmd(["git", "pull", "--ff-only"], cwd=source, logger=logger)
        run_cmd(["bash", "install"], cwd=source, logger=logger)
    except Exception as e:
        print(f"\n❌ Update falhou: {e}")
        print(f"Log: {logger.path}")
        return

    print("\n✔ Update concluído.")
    print(f"Log: {logger.path}")
