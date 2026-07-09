from pathlib import Path

CONFIG = Path("/etc/homelab/homelab.yaml")


def get(key, default=""):
    if not CONFIG.exists():
        return default

    section = None

    for line in CONFIG.read_text().splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue

        if not line.startswith(" ") and line.endswith(":"):
            section = line.replace(":", "").strip()
            continue

        if section and line.startswith("  "):
            k, _, v = line.strip().partition(":")
            if f"{section}.{k}" == key:
                return v.strip().strip('"').strip("'")

    return default
