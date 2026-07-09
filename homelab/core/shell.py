import subprocess


def run(cmd, timeout=30, logger=None, show=False, fatal=False):
    if logger:
        logger.write(f"$ {cmd}")

    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout
    )

    output = result.stdout.strip()

    if output:
        if show:
            print(output)
        if logger:
            logger.write(output)

    if result.returncode != 0 and fatal:
        raise RuntimeError(f"Comando falhou ({result.returncode}): {cmd}")

    return output
