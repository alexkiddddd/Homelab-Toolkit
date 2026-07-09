from pathlib import Path
from homelab.core.shell import run as shell


def run():
    dri = Path("/dev/dri")
    render = Path("/dev/dri/renderD128")
    gpu = shell("lspci | grep -Ei 'vga|display' | head -1")

    items = []

    if not dri.exists():
        return {
            "title": "GPU",
            "score": 10,
            "max_score": 10,
            "items": [{"name": "GPU passthrough", "value": "não aplicável", "status": "info"}],
        }

    items.append({"name": "GPU", "value": gpu or "detetada", "status": "ok"})
    items.append({"name": "/dev/dri", "value": "disponível", "status": "ok"})
    items.append({"name": "renderD128", "value": "disponível" if render.exists() else "em falta", "status": "ok" if render.exists() else "warn"})

    score = 10 if render.exists() else 7

    return {
        "title": "GPU",
        "score": score,
        "max_score": 10,
        "items": items,
    }
