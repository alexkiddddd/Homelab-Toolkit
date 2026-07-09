from datetime import datetime
from pathlib import Path

CHANGELOG = Path("/etc/homelab/CHANGELOG.md")


def run(args):
    CHANGELOG.parent.mkdir(parents=True, exist_ok=True)

    text = " ".join(args).strip()

    if not text:
        text = input("Descrição: ").strip()

    if not text:
        print("Nota vazia. Cancelado.")
        return

    with CHANGELOG.open("a") as f:
        f.write(f"- {datetime.now().strftime('%Y-%m-%d %H:%M')} - {text}\n")

    print("Nota adicionada.")
