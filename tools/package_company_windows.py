"""Create the Windows management add-on; never include hbbs data or private keys."""
import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDORS = {
    "caddy_2.11.7_windows_amd64.zip": {
        "url": "https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_windows_amd64.zip",
        "algorithm": "sha512",
        "digest": "c308154504e53755958ffc62d8a2657ab17eefd6dd25c45dbb2c3d93d29519971f77ca652f7d0f2bcb7f980b9ba3822478865e29969d0272d7613550a43152b1",
    },
    "WinSW-x64.exe": {
        "url": "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe",
        "algorithm": "sha256",
        "digest": "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da",
    },
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def download(url, path):
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "RustDesk-company-packager"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        path.write_bytes(payload)
    return path.read_bytes()


def source_paths():
    # An explicit allowlist excludes upstream .env, db_v2.sqlite3 and id_ed25519.
    paths = []
    for relative in git("ls-files", "-z").split("\0"):
        if not relative or not (relative in {"README.md", "LICENSE", "COMPANY_RELEASE", "docs/environment-variables.md"}
                                or relative.startswith(("management/", "tools/", "docs/company/"))):
            continue
        path = ROOT / relative
        if any(part in {"data", "__pycache__", ".venv"} for part in Path(relative).parts) or path.name.startswith(".env"):
            continue
        if ".sqlite" in path.name or path.suffix.lower() in {".exe", ".dll", ".zip", ".db", ".pyc"}:
            continue
        paths.append(path)
    required = {"management/app.py", "management/db.py", "management/models.py", "management/security.py",
                "management/static/index.html", "management/windows/Install-Management.ps1"}
    if not required <= {path.relative_to(ROOT).as_posix() for path in paths}:
        raise ValueError("Required management sources are missing from Git; stage all release files first")
    return paths


def package(executable, output, cache):
    tag = (ROOT / "COMPANY_RELEASE").read_text().strip()
    if not re.fullmatch(r"v\d+\.\d+\.\d+-company\.\d+", tag):
        raise ValueError("Invalid company release version")
    binary = executable.read_bytes()
    if not binary.startswith(b"MZ"):
        raise ValueError("Expected a built Windows management executable")
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    vendors = {}
    for name, spec in VENDORS.items():
        payload = download(spec["url"], cache / name)
        if hashlib.new(spec["algorithm"], payload).hexdigest() != spec["digest"]:
            raise ValueError(f"Vendor checksum mismatch: {name}")
        vendors[name] = payload
    manifest = {
        "release": tag, "repository": "https://github.com/fanqisyx/rustdesk-server",
        "commit": git("rev-parse", "HEAD"), "working_tree_dirty": bool(git("status", "--porcelain")),
        "api_version": "0.1.0", "schema_version": 2,
        "compatible_client": "v1.5.1-company.1",
        "plaintext_http_minimum_client": "v1.5.1-company.2",
        "setup_compiler": "NSIS 3.11",
        "management_exe_sha256": hashlib.sha256(binary).hexdigest(),
        "build": json.loads((executable.parent / "build-info.json").read_text(encoding="utf-8")),
        "vendors": VENDORS,
        "deployment": "Add company management alongside existing hbbs/hbbr; no keys or databases bundled",
    }
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    source_zip = output / f"rustdesk-management-source-{tag}.zip"
    prefix = f"rustdesk-management-source-{tag}/"
    with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_paths():
            archive.writestr(prefix + path.relative_to(ROOT).as_posix(), path.read_bytes())
        archive.writestr(prefix + "release-manifest.json", payload)
        for path in sorted((executable.parent / "runtime-licenses").rglob("*")):
            if path.is_file():
                archive.writestr(prefix + "licenses/runtime/" + path.relative_to(executable.parent / "runtime-licenses").as_posix(), path.read_bytes())
    windows_zip = output / f"rustdesk-server-company-windows-x86_64-{tag}.zip"
    prefix = f"rustdesk-server-company-windows-x86_64-{tag}/"
    with zipfile.ZipFile(windows_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(prefix + "rustdesk-management.exe", binary)
        for path in sorted((ROOT / "management/windows").glob("*")):
            if path.is_file() and (path.name == "Caddyfile.ip" or path.suffix in {".md", ".xml", ".ps1"}):
                archive.writestr(prefix + "windows/" + path.name, path.read_bytes())
        archive.writestr(prefix + "README.md", (ROOT / "management/windows/README.md").read_bytes())
        archive.writestr(prefix + "VALIDATION.md", (ROOT / "management/VALIDATION.md").read_bytes())
        archive.writestr(prefix + "RustDesk-Windows-Server-Manual-zh-CN.pdf", (ROOT / "docs/company/RustDesk-Windows-Server-Manual-zh-CN.pdf").read_bytes())
        archive.writestr(prefix + "LICENSE", (ROOT / "LICENSE").read_bytes())
        archive.writestr(prefix + "release-manifest.json", payload)
        for path in sorted((executable.parent / "runtime-licenses").rglob("*")):
            if path.is_file():
                archive.writestr(prefix + "licenses/runtime/" + path.relative_to(executable.parent / "runtime-licenses").as_posix(), path.read_bytes())
        with zipfile.ZipFile(io.BytesIO(vendors["caddy_2.11.7_windows_amd64.zip"])) as caddy:
            archive.writestr(prefix + "windows/caddy.exe", caddy.read("caddy.exe"))
        for name in ("rdm-api-service.exe", "rdm-https-service.exe"):
            archive.writestr(prefix + "windows/" + name, vendors["WinSW-x64.exe"])
        for name, url in {
            "Caddy-LICENSE.txt": "https://raw.githubusercontent.com/caddyserver/caddy/v2.11.7/LICENSE",
            "WinSW-LICENSE.txt": "https://raw.githubusercontent.com/winsw/winsw/v2.12.0/LICENSE.txt",
        }.items():
            archive.writestr(prefix + "licenses/" + name, download(url, cache / name))
        archive.writestr(prefix + "THIRD_PARTY.md", (
            "Caddy 2.11.7: Apache-2.0; WinSW 2.12.0: MIT. See licenses/.\n"
            "Management runtime includes Python and dependencies from management/requirements-build.txt.\n"
            "PyInstaller 6.16.0 uses its bootloader distribution exception.\n"
            "Management source, build scripts and dependency versions accompany this release.\n"))
    manifest_path = output / "release-manifest.json"
    manifest_path.write_bytes(payload)
    notes = output / f"release-notes-{tag}.md"
    notes.write_bytes((ROOT / f"docs/company/{tag}.md").read_bytes())
    manual = output / "RustDesk-Windows-Server-Manual-zh-CN.pdf"
    shutil.copyfile(ROOT / "docs/company/RustDesk-Windows-Server-Manual-zh-CN.pdf", manual)
    assets = [windows_zip, source_zip, manifest_path, notes, manual]
    (output / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in assets), encoding="utf-8")
    for path in assets + [output / "SHA256SUMS"]:
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "dist/native/rustdesk-management.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/company-release")
    parser.add_argument("--vendor-cache", type=Path, default=ROOT / ".cache/company-vendors")
    args = parser.parse_args()
    package(args.executable.resolve(), args.output.resolve(), args.vendor_cache.resolve())
