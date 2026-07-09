from pathlib import Path


def validate_lxc_config(ctid):
    conf = Path(f"/etc/pve/lxc/{ctid}.conf")

    if not conf.exists():
        return False, ["ficheiro de configuração não existe"]

    if conf.stat().st_size == 0:
        return False, ["ficheiro de configuração vazio"]

    text = conf.read_text()

    required = ["arch:", "ostype:", "rootfs:", "hostname:", "net0:"]
    missing = [item.replace(":", "") for item in required if item not in text]

    if missing:
        return False, [f"falta: {', '.join(missing)}"]

    return True, []
