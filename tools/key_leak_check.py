"""Confirm the key is in no repo file, without printing it."""
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
key = Path(sys.argv[2]).read_text(encoding="utf-8-sig").strip()
tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, text=True).stdout.split("\0")
others = subprocess.run(
    ["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=repo, capture_output=True, text=True
).stdout.split("\0")
files = [name for name in tracked + others if name]
hits = [name for name in files if key.encode() in (repo / name).read_bytes()]
print("files checked:", len(files), "| files containing the key:", len(hits))
history = subprocess.run(["git", "log", "--all", "-p", "--format="], cwd=repo, capture_output=True).stdout
print("key in git history:", key.encode() in history)
