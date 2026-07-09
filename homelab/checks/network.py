from homelab.core.shell import run as shell


def run():
    gateway = shell("ip route | awk '/default/ {print $3; exit}'")
    interface = shell("ip route | awk '/default/ {print $5; exit}'")
    ip = shell(f"ip -4 addr show {interface} | awk '/inet / {{print $2}}' | cut -d/ -f1") if interface else ""

    internet = shell("ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1 && echo ok || echo fail")

    items = [
        {"name": "Interface", "value": interface or "sem gateway", "status": "ok" if interface else "fail"},
        {"name": "IP", "value": ip or "sem IP", "status": "ok" if ip else "fail"},
        {"name": "Gateway", "value": gateway or "não encontrado", "status": "ok" if gateway else "fail"},
        {"name": "Internet", "value": internet, "status": "ok" if internet == "ok" else "warn"},
    ]

    score = 10
    if not interface or not ip or not gateway:
        score -= 6
    if internet != "ok":
        score -= 2

    return {
        "title": "Rede",
        "score": max(score, 0),
        "max_score": 10,
        "items": items,
    }
