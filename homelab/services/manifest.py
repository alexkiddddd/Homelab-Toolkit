import json
import subprocess
import tempfile
from pathlib import Path


class ManifestError(Exception):
    pass


def load_manifest(archive_path):
    archive_path = Path(archive_path)

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            f"tar --zstd -xf '{archive_path}' -C '{tmp}' --wildcards '*/manifest.json'",
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
        )

        if result.returncode != 0:
            raise ManifestError(result.stdout.strip())

        manifests = list(Path(tmp).rglob("manifest.json"))

        if not manifests:
            raise ManifestError("manifest.json não encontrado.")

        return json.loads(manifests[0].read_text())
        
        
def load_backup_jobs(snapshot_root):
    import json

    path = snapshot_root / "pve" / "backup_jobs.json"

    if not path.exists():
        return []

    try:
        return json.loads(path.read_text())
    except Exception:
        return []