from homelab.core.shell import run as shell


def get_temp(pattern, field):
    return shell(
        f"sensors 2>/dev/null | awk '/{pattern}/ {{gsub(/[+°C]/,\"\",${field}); print ${field}; exit}}'"
    )


def run():
    cpu = get_temp("Package id 0:", 4)
    mb = get_temp("CPUTIN:", 2)

    items = []
    score = 5

    if cpu:
        value = f"{cpu}C"
        status = "ok"
        try:
            if float(cpu) >= 80:
                status = "fail"
                score -= 4
            elif float(cpu) >= 70:
                status = "warn"
                score -= 2
        except Exception:
            pass

        items.append({"name": "CPU", "value": value, "status": status})
    else:
        items.append({"name": "CPU", "value": "não disponível", "status": "info"})

    if mb:
        items.append({"name": "Motherboard", "value": f"{mb}C", "status": "ok"})

    return {
        "title": "Temperaturas",
        "score": max(score, 0),
        "max_score": 5,
        "items": items,
    }
