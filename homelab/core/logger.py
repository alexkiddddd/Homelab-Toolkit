from datetime import datetime
from pathlib import Path

LOG_DIR = Path("/var/log/homelab")


class Logger:
    def __init__(self, name):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = LOG_DIR / f"{name}-{timestamp}.log"

    def write(self, text):
        with self.path.open("a") as f:
            f.write(str(text) + "\n")

    def print(self, text=""):
        print(text)
        self.write(text)
