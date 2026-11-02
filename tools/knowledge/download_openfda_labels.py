"""Download openFDA's drug label export (CC0) into the data folder outside the repo.

    python tools/knowledge/download_openfda_labels.py

Files land in ../DATA/knowledge/openfda_label/ (or $DATA_DIR/knowledge/...), with
a manifest of sizes and SHA-256 checksums. A file already present with the
manifest's checksum is skipped, so the script can be rerun after a failure.
"""

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

MANIFEST_URL = "https://api.fda.gov/download.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT.parent / "DATA"))
OUT_DIR = DATA_DIR / "knowledge" / "openfda_label"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MANIFEST_URL, timeout=60) as response:
        label = json.load(response)["results"]["drug"]["label"]
    previous_path = OUT_DIR / "manifest.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    known = {f["name"]: f["sha256"] for f in previous.get("files", [])} if previous.get("export_date") == label["export_date"] else {}
    files = []
    for part in label["partitions"]:
        name = part["file"].rsplit("/", 1)[1]
        target = OUT_DIR / name
        if not (target.exists() and known.get(name) == sha256(target)):
            temporary = target.with_suffix(".part")
            urllib.request.urlretrieve(part["file"], temporary)
            temporary.replace(target)
        files.append({"name": name, "url": part["file"], "records": part["records"],
                      "bytes": target.stat().st_size, "sha256": sha256(target)})
        print(f"{name}: {target.stat().st_size / 1e6:.1f} MB", flush=True)
    manifest = {"source": MANIFEST_URL, "export_date": label["export_date"],
                "licence": "CC0 1.0 (https://open.fda.gov/terms/)", "total_records": label["total_records"], "files": files}
    previous_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files, {sum(f['records'] for f in files)} records", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
