"""Record the build interpreter, dependency versions and redistribution licenses."""
import importlib.metadata
import json
import re
import sys
from pathlib import Path


destination = Path(__file__).resolve().parents[1] / "dist/native/runtime-licenses"
destination.mkdir(parents=True, exist_ok=True)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.is_file():
    raise RuntimeError("The Windows Python distribution LICENSE.txt is required")
(destination / "Python-LICENSE.txt").write_bytes(python_license.read_bytes())
versions = {}
for distribution in importlib.metadata.distributions():
    name = distribution.metadata["Name"]
    versions[name] = distribution.version
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    for entry in distribution.files or []:
        if not re.match(r"(?i)^(license|copying|notice)([._-]|$)", entry.name):
            continue
        source = distribution.locate_file(entry)
        if source.is_file():
            target = destination / safe_name / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
(destination.parent / "build-info.json").write_text(json.dumps({
    "python": sys.version.split()[0], "packages": dict(sorted(versions.items()))
}, indent=2) + "\n", encoding="utf-8")
print("Runtime licenses and build dependency versions collected")
