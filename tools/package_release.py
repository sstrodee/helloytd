"""Prepare the Windows release from an already tested portable archive."""

import argparse
import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("portable", type=Path)
    args = parser.parse_args()

    launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
    match = re.search(r'AssemblyFileVersion\("(\d+\.\d+\.\d+)\.0"\)', launcher)
    if not match:
        raise ValueError("Could not determine the package version from Launcher.cs")
    version = match[1]
    additions = {
        "helloytd/Прочти меня.txt": ROOT / "portable-readme.txt",
        "helloytd/README.txt": ROOT / "portable-readme.en.txt",
        "helloytd/THIRD_PARTY_NOTICES.md": ROOT / "THIRD_PARTY_NOTICES.md",
        "helloytd/licenses/GPL-3.0-only.txt": ROOT / "licenses" / "GPL-3.0-only.txt",
        "helloytd/licenses/LGPL-3.0-only.txt": ROOT / "licenses" / "LGPL-3.0-only.txt",
    }
    if (license_file := ROOT / "LICENSE").is_file():
        additions["helloytd/LICENSE"] = license_file
    for path in additions.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    output = ROOT / "dist" / f"helloytd-{version}-windows-x64.zip"
    checksum = output.with_suffix(".zip.sha256")
    if output.exists() or checksum.exists():
        raise FileExistsError("The release package or checksum already exists")
    with ZipFile(args.portable) as source:
        modules = {f"helloytd/app/{path.name}": path for path in (ROOT / "app").glob("*.py")}
        bundled_modules = {name for name in source.namelist() if name.startswith("helloytd/app/") and name.endswith(".py")}
        if modules.keys() != bundled_modules or any(source.read(name) != path.read_bytes()
                                                     for name, path in modules.items()):
            raise ValueError("Portable source does not match the current app")
        for name in source.namelist():
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != "helloytd" or ".." in parts or "\\" in name
                    or parts[:2] == ("helloytd", "data")):
                raise ValueError(f"Unexpected path in portable: {name}")

        with ZipFile(output, "x", ZIP_DEFLATED, compresslevel=6) as archive:
            for item in source.infolist():
                if item.filename not in additions:
                    with source.open(item) as incoming, archive.open(item, "w") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
            for name, path in additions.items():
                archive.write(path, name)
    with ZipFile(output) as archive:
        if bad := archive.testzip():
            raise ValueError(f"Invalid archive entry: {bad}")
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with checksum.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(f"{digest}  {output.name}\n")
    print(output)
    print(checksum)


if __name__ == "__main__":
    main()
