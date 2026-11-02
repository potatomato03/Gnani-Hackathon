from pathlib import Path
import sys
REPO_ROOT = Path(__file__).resolve().parents[3]
for relative in ('tools/corpus', 'services/api', 'tools/eval'):
    sys.path.insert(0, str(REPO_ROOT / relative))
