"""Find platform icons in source checkouts and installed distributions."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def icon_path(platform=None):
    filename = "icon.icns" if (platform or sys.platform) == "darwin" else "icon.ico"
    for directory in (
        Path(__file__).resolve().parents[2] / "res",
        Path(sys.prefix) / "share" / "cykelfest-routing" / "res",
    ):
        path = directory / filename
        if path.is_file():
            return path
    return None


def application_icon():
    path = icon_path()
    return QIcon(str(path)) if path else QIcon()


def set_windows_app_id():
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Cykelfest.DinnerSafariPlanner"
        )
