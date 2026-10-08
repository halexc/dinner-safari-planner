"""Render each supported language without online maps or live project changes."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow
from cykelfest_routing.localization import LANGUAGES


def main():
    output = Path("artifacts/localization")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    preferences = QSettings(str(output / "preview.ini"), QSettings.IniFormat)
    preferences.clear()
    window = MainWindow(demo_data(), enable_map=False, preferences=preferences)
    window.verify_routes()
    window.show()
    for language in LANGUAGES:
        window.language_combo.setCurrentIndex(window.language_combo.findData(language))
        window.resize(1500, 1000)
        window.tabs.setCurrentIndex(0)
        app.processEvents()
        window.grab().save(str(output / f"{language}-map.png"))
        window.tabs.setCurrentIndex(4)
        app.processEvents()
        window.grab().save(str(output / f"{language}-settings.png"))
    window.dirty = False
    window.close()
    print("Rendered all five languages in artifacts/localization.")


if __name__ == "__main__":
    main()
