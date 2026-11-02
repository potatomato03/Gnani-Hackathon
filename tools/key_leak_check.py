"""Confirm no key is in any repo file or in git history, without printing it.

    python tools/key_leak_check.py .                  # every key in the credentials folder
    python tools/key_leak_check.py . path/to/key.txt  # one key file
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "credentials"))
from sync_env import secret_values  # noqa: E402

repo = Path(sys.argv[1])
keys = [Path(sys.argv[2]).read_text(encoding="utf-8-sig").strip()] if len(sys.argv) > 2 else secret_values()
tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, text=True).stdout.split("\0")
others = subprocess.run(
    ["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=repo, capture_output=True, text=True
).stdout.split("\0")
files = [name for name in tracked + others if name and (repo / name).is_file()]
history = subprocess.run(["git", "log", "--all", "-p", "--format="], cwd=repo, capture_output=True).stdout
hits = [name for name in files if any(key.encode() in (repo / name).read_bytes() for key in keys)]
print("keys:", len(keys), "| files checked:", len(files), "| files containing a key:", len(hits))
print("any key in git history:", any(key.encode() in history for key in keys))
