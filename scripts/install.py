"""Standard-library installer shared by install.bat and install.command."""

import os
import plistlib
import shutil
import struct
import subprocess
import sys
import venv
from pathlib import Path


def run(command, root):
    subprocess.run([str(part) for part in command], cwd=root, check=True)


def check_python(python, root):
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import sys,struct; print(f'{sys.version_info.major}.{sys.version_info.minor}:{struct.calcsize(\"P\")*8}')",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.strip() != "3.13:64":
        raise ValueError(
            "The existing .venv does not use 64-bit Python 3.13. Close Cykelfest, "
            "rename .venv to .venv-old, and run the installer again."
        )


def create_windows_launcher(root):
    # Pass paths as environment data, never interpolate them into PowerShell code.
    environment = os.environ.copy()
    environment["CYKELFEST_INSTALL_ROOT"] = str(root)
    script = r"""
$ErrorActionPreference = 'Stop'
$projectRoot = $env:CYKELFEST_INSTALL_ROOT
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $projectRoot 'Cykelfest.lnk'))
$shortcut.TargetPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '-m cykelfest_routing'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = (Join-Path $projectRoot 'res\icon.ico') + ',0'
$shortcut.Description = 'Cykelfest dinner safari planner'
$shortcut.Save()
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        cwd=root,
        check=True,
    )
    # Recreate the runnable troubleshooting script from the shipped template.
    path = root / "run.bat"
    path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n")


def create_mac_launcher(root):
    contents = root / "Cykelfest.app" / "Contents"
    resources = contents / "Resources"
    executables = contents / "MacOS"
    resources.mkdir(parents=True, exist_ok=True)
    executables.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "res" / "icon.icns", resources / "icon.icns")
    info = {
        "CFBundleName": "Cykelfest",
        "CFBundleDisplayName": "Cykelfest",
        "CFBundleIdentifier": "org.cykelfest.dinnersafari",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleExecutable": "Cykelfest",
        "CFBundleIconFile": "icon.icns",
        "CFBundlePackageType": "APPL",
        "NSHighResolutionCapable": True,
    }
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    launcher = executables / "Cykelfest"
    launcher.write_text(
        """#!/bin/bash
project_root="$(cd -- "$(dirname -- "$0")/../../.." && pwd)" || exit 1
cd -- "$project_root" || exit 1
"$project_root/.venv/bin/python" -m cykelfest_routing "$@" >> "$project_root/cykelfest-launch.log" 2>&1
result=$?
if [ "$result" -ne 0 ]; then
    /usr/bin/osascript -e 'display alert "Cykelfest could not start" message "Open run.command in the project folder to see the error. If needed, run install.command again. Details are also in cykelfest-launch.log."'
fi
exit "$result"
""",
        encoding="utf-8",
        newline="\n",
    )
    launcher.chmod(0o755)
    for name in ("run.command", "install.command"):
        path = root / name
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        path.chmod(0o755)


def install(root):
    if sys.version_info[:2] != (3, 13) or struct.calcsize("P") != 8:
        raise ValueError("Install 64-bit Python 3.13 first. See INSTALL (For Dummies).md.")
    if sys.platform not in ("win32", "darwin"):
        raise ValueError("These installers support Windows and macOS.")
    required = [
        "pyproject.toml",
        "run.bat",
        "run.command",
        "install.command",
        "res/icon.ico",
        "res/icon.icns",
    ]
    if any(not (root / path).is_file() for path in required):
        raise ValueError(
            "Some project files are missing. Extract the entire downloaded project folder first."
        )
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if environment.exists():
        if not python.is_file():
            raise ValueError(
                "The .venv folder is incomplete. Rename it to .venv-old and rerun this installer."
            )
    else:
        print("Creating the private Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True, symlinks=sys.platform == "darwin").create(environment)
    check_python(python, root)
    print(
        "Checking and installing required packages (this may take several minutes)...", flush=True
    )
    # pip retains satisfying installed dependencies and installs missing/incompatible ones.
    run([python, "-m", "pip", "install", "--editable", root], root)
    run([python, "-m", "pip", "check"], root)
    run(
        [
            python,
            "-c",
            "from cykelfest_routing import gui; from cykelfest_routing.app_icon import icon_path; assert icon_path() is not None; print('Application imports OK.')",
        ],
        root,
    )
    print("Creating the launcher...", flush=True)
    if sys.platform == "win32":
        create_windows_launcher(root)
        name = "Cykelfest.lnk (or run.bat)"
    else:
        create_mac_launcher(root)
        name = "Cykelfest.app (or run.command)"
    print(f"\nInstallation complete! Open {name} in:\n{root}", flush=True)


def main():
    try:
        install(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(
            f"\nInstallation failed: {error}\nSee INSTALL (For Dummies).md for help.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
