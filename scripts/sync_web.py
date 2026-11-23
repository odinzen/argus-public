"""Copy the pure-Python core into web/argus/ for local testing of the web app.

Production (GitHub Pages) assembles these via .github/workflows/pages.yml, so the
copies under web/argus/ are gitignored. Run this, then serve web/ locally:

    python scripts/sync_web.py
    python -m http.server -d web 8000   # then open http://localhost:8000
"""

import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "src" / "argus"
dst = root / "web" / "argus"
dst.mkdir(parents=True, exist_ok=True)
# Copy every pure-Python module so `import argus` resolves in the browser; the package
# __init__ pulls in the whole core, so a curated subset goes stale the moment it grows.
modules = sorted(src.glob("*.py"))
for module in modules:
    shutil.copy(module, dst / module.name)
(dst / "modules.json").write_text(json.dumps([m.name for m in modules]), encoding="utf-8")
print(f"synced core -> {dst}")
