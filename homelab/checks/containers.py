from homelab.core.shell import run as shell


def get_hostname(ctid):
    hostname = shell(
        f"pct config {ctid} 2>/dev/null | awk -F': ' '/^hostname:/ {{print $2; exit}}'"
    )
    return hostname or "sem-hostname"


def run():
    lines = shell("pct list | awk 'NR>1 {print $1,$2}'").splitlines()

    items = []
    score = 15

    if not lines:
        return {
            "title": "Containers",
            "score": 15,
            "max_score": 15,
            "items": [
                {"name": "LXC", "value": "nenhum container encontrado", "status": "ok"}
            ],
        }

    for line in lines:
        parts = line.split()
        ctid = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        hostname = get_hostname(ctid)

        state = "ok" if status == "running" else "warn"

        if status != "running":
            score -= 5

        items.append({
            "name": f"CT{ctid} ({hostname})",
            "value": status,
            "status": state,
        })

    return {
        "title": "Containers",
        "score": max(score, 0),
        "max_score": 15,
        "items": items,
    }
