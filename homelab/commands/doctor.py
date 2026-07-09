from datetime import datetime
from homelab.core.logger import Logger
from homelab.checks import system, storage, network, containers, backups, gpu, services, temperatures


CHECKS = [
    system.run,
    storage.run,
    network.run,
    containers.run,
    backups.run,
    gpu.run,
    services.run,
    temperatures.run,
]


def status_icon(status):
    if status == "ok":
        return "✔"
    if status == "warn":
        return "⚠"
    if status == "fail":
        return "✖"
    return "•"


def run():
    logger = Logger("doctor")

    logger.print("Homelab Toolkit")
    logger.print("Doctor")
    logger.print("======")
    logger.print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logger.print("")

    total_score = 0
    max_score = 0
    warnings = []

    for check in CHECKS:
        result = check()

        title = result.get("title", "Sem título")
        score = result.get("score", 0)
        max_points = result.get("max_score", 0)
        items = result.get("items", [])

        total_score += score
        max_score += max_points

        logger.print(title)
        logger.print("=" * len(title))

        for item in items:
            icon = status_icon(item.get("status", "info"))
            name = item.get("name", "")
            value = item.get("value", "")

            line = f"{icon} {name}"
            if value:
                line += f": {value}"

            logger.print(line)

            if item.get("status") in ["warn", "fail"]:
                warnings.append(line)

        logger.print("")

    health = int((total_score / max_score) * 100) if max_score else 0

    logger.print("Health Score")
    logger.print("============")
    logger.print(f"{health}/100")
    logger.print("")

    if warnings:
        logger.print("Avisos")
        logger.print("======")
        for warning in warnings:
            logger.print(warning)
        logger.print("")

    logger.print(f"Log: {logger.path}")
