from homelab.core.shell import run as shell


def run():
    lines = shell("pvesm status | awk 'NR>1 {print $1,$3,$7}'").splitlines()

    items = []
    score = 20

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue

        name, status, usage = parts[0], parts[1], parts[2]

        try:
            percent = float(usage.replace("%", ""))
        except Exception:
            percent = 0

        state = "ok"
        if status != "active":
            state = "fail"
            score -= 8
        elif percent >= 95:
            state = "warn"
            score -= 4
        elif percent >= 90:
            state = "warn"
            score -= 2

        items.append({
            "name": name,
            "value": f"{status}, {usage}",
            "status": state,
        })

    if not items:
        score = 0
        items.append({"name": "Storage", "value": "nenhuma storage encontrada", "status": "fail"})

    return {
        "title": "Storage",
        "score": max(score, 0),
        "max_score": 20,
        "items": items,
    }
