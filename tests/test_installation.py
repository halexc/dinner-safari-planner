"""Installation wiring and launcher artifacts without downloading dependencies."""

import importlib.util
import os
import plistlib
import shutil
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from cykelfest_routing import app_icon

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cykelfest_installer", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_both_platform_icons_load():
    app = QApplication.instance() or QApplication([])
    for platform, filename in (("win32", "icon.ico"), ("darwin", "icon.icns")):
        path = app_icon.icon_path(platform)
        assert path.name == filename
        assert not QIcon(str(path)).pixmap(32, 32).isNull()
    assert app is not None


def test_installed_icon_fallback_and_missing_icon(tmp_path, monkeypatch):
    monkeypatch.setattr(app_icon, "__file__", str(tmp_path / "source/src/package/app_icon.py"))
    monkeypatch.setattr(app_icon.sys, "prefix", str(tmp_path / "environment"))
    target = tmp_path / "environment/share/cykelfest-routing/res/icon.ico"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"placeholder")
    assert app_icon.icon_path("win32") == target
    assert app_icon.icon_path("darwin") is None


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "Dinner Safari's folder"
    root.mkdir()
    for name in (
        "pyproject.toml",
        "run.bat",
        "run.command",
        "install.command",
        "res/icon.ico",
        "res/icon.icns",
    ):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return root


def test_mac_app_bundle_and_scripts(project):
    installer.create_mac_launcher(project)
    contents = project / "Cykelfest.app/Contents"
    info = plistlib.loads((contents / "Info.plist").read_bytes())
    assert info["CFBundleIconFile"] == "icon.icns"
    assert (contents / "Resources/icon.icns").read_bytes() == (ROOT / "res/icon.icns").read_bytes()
    script = (contents / "MacOS/Cykelfest").read_text()
    assert "/../../.." in script
    assert '"$project_root/.venv/bin/python"' in script
    assert "cykelfest-launch.log" in script
    assert b"\r" not in (project / "run.command").read_bytes()


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_install_reuses_environment_and_asks_pip_to_resolve_dependencies(
    project, monkeypatch, platform
):
    monkeypatch.setattr(installer.sys, "platform", platform)
    python = project / ".venv" / ("Scripts/python.exe" if platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    calls, launchers = [], []
    monkeypatch.setattr(installer, "check_python", lambda *args: None)
    monkeypatch.setattr(installer, "run", lambda command, root: calls.append(command))
    monkeypatch.setattr(installer, "create_windows_launcher", launchers.append)
    monkeypatch.setattr(installer, "create_mac_launcher", launchers.append)
    installer.install(project)
    assert calls[0] == [python, "-m", "pip", "install", "--editable", project]
    assert calls[1] == [python, "-m", "pip", "check"]
    assert launchers == [project]


def test_wrong_existing_python_is_rejected(project, monkeypatch):
    monkeypatch.setattr(
        installer.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="3.14:64")
    )
    with pytest.raises(ValueError, match="rename .venv"):
        installer.check_python(project / "python", project)


def test_windows_paths_are_passed_as_data(project, monkeypatch):
    calls = []
    monkeypatch.setattr(
        installer.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    installer.create_windows_launcher(project)
    args, kwargs = calls[0]
    assert str(project) not in args[0][-1]
    assert kwargs["env"]["CYKELFEST_INSTALL_ROOT"] == str(project)
    assert b"\r\n" in (project / "run.bat").read_bytes()
