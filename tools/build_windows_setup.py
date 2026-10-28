"""Compile the checked Windows bundle into a graphical NSIS installer."""
import argparse
import hashlib
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from package_company_windows import ROOT, download


NSIS_URL = "https://downloads.sourceforge.net/project/nsis/NSIS%203/3.11/nsis-3.11.zip"
NSIS_SHA256 = "c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1"


def nsis_string(value):
    return str(value).replace("$", "$$").replace('"', '$\\"')


def build(output, compiler=None, http=False):
    tag = (ROOT / "COMPANY_RELEASE").read_text().strip()
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)-company\.(\d+)", tag)
    if not match:
        raise ValueError("Invalid company release version")
    if compiler is None:
        cache = ROOT / ".cache/nsis"
        cache.mkdir(parents=True, exist_ok=True)
        archive_path = cache / "nsis-3.11.zip"
        payload = download(NSIS_URL, archive_path)
        if hashlib.sha256(payload).hexdigest() != NSIS_SHA256:
            raise ValueError("NSIS compiler checksum mismatch")
        with zipfile.ZipFile(archive_path) as archive:
            if not all(n.startswith("nsis-3.11/") and ".." not in Path(n).parts for n in archive.namelist()):
                raise ValueError("Invalid NSIS archive paths")
            archive.extractall(cache)
        compiler = cache / "nsis-3.11/makensis.exe"
    output = output.resolve()
    package_path = output / f"rustdesk-server-company-windows-x86_64-{tag}.zip"
    setup = output / f"rustdesk-server-company-{tag}-{'HTTP-' if http else ''}Setup.exe"
    build_root = ROOT / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setup-", dir=build_root) as directory:
        temporary = Path(directory).resolve()
        assert temporary.is_relative_to(build_root.resolve())
        prefix = f"rustdesk-server-company-windows-x86_64-{tag}/"
        with zipfile.ZipFile(package_path) as archive:
            names = archive.namelist()
            if not all(n.startswith(prefix) and ".." not in Path(n).parts for n in names):
                raise ValueError("Invalid management bundle paths")
            archive.extractall(temporary)
        bundle = temporary / prefix.rstrip("/")
        copying = compiler.parent / "COPYING"
        (bundle / "licenses/NSIS-COPYING.txt").write_bytes(copying.read_bytes())
        files = sorted(p.relative_to(bundle) for p in bundle.rglob("*") if p.is_file())
        directories = {p.parent for p in files}
        for path in list(directories):
            directories.update(path.parents)
        deletion = temporary / "delete-files.nsh"
        lines = [f'Delete "$INSTDIR\\{nsis_string(str(path))}"' for path in files]
        lines.extend(f'RMDir "$INSTDIR\\{nsis_string(str(path))}"' for path in
                     sorted((d for d in directories if str(d) != "."), key=lambda p: len(p.parts), reverse=True))
        deletion.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = [str(compiler), "/V2", "/INPUTCHARSET", "UTF8",
                   f"/DRELEASE_TAG={tag}", f"/DVERSION_NUM={'.'.join(match.groups())}",
                   f"/DPAYLOAD_DIR={bundle}", f"/DSETUP_OUT={setup}", f"/DDELETE_INCLUDE={deletion}",
                   str(ROOT / f"management/windows/setup/Company{'Http' if http else ''}Setup.nsi")]
        subprocess.run(command, cwd=ROOT, check=True, timeout=300)
    if not setup.read_bytes().startswith(b"MZ"):
        raise ValueError("The compiler did not produce a Windows installer")
    checksums = output / "SHA256SUMS"
    previous = [line for line in checksums.read_text().splitlines() if not line.endswith("  " + setup.name)]
    previous.append(f"{hashlib.sha256(setup.read_bytes()).hexdigest()}  {setup.name}")
    checksums.write_text("\n".join(previous) + "\n", encoding="utf-8")
    print(f"{setup.name}: {setup.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/company-release")
    parser.add_argument("--makensis", type=Path)
    parser.add_argument("--http", action="store_true", help="Build the certificate-free plaintext HTTP installer")
    args = parser.parse_args()
    build(args.output, args.makensis.resolve() if args.makensis else None, args.http)
