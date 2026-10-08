"""Render the real desktop UI offscreen for visual inspection."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea

from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow


def main():
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    app = QApplication([])
    # Windows' offscreen Qt platform does not populate the native font database.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    preferences = QSettings(str(output / "preview-preferences.ini"), QSettings.IniFormat)
    preferences.clear()
    window = MainWindow(demo_data(), preferences=preferences)
    # Exercise simultaneous warnings and errors without changing the sample source.
    window.data.stops["S003"].host = ""
    window.verify_routes()
    window.resize(1400, 900)
    window.show()

    def capture():
        window.map.page().runJavaScript(
            "JSON.stringify({leaflet: typeof L !== 'undefined', map: !!document.querySelector('.leaflet-container'), fallback: !!document.getElementById('map-fallback')})",
            lambda result: print("Map state:", result),
        )
        window.grab().save(str(output / "gui-map.png"))
        window.tabs.setCurrentIndex(1)
        QTimer.singleShot(300, capture_participants)

    def capture_participants():
        window.grab().save(str(output / "gui-participants.png"))
        window.tabs.setCurrentIndex(2)
        QTimer.singleShot(300, capture_stops)

    def capture_stops():
        window.grab().save(str(output / "gui-stops.png"))
        window.tabs.setCurrentIndex(3)
        QTimer.singleShot(300, capture_routes)

    def capture_routes():
        window.grab().save(str(output / "gui-routes.png"))
        window.tabs.setCurrentIndex(4)
        QTimer.singleShot(300, capture_settings)

    def capture_settings():
        window.grab().save(str(output / "gui-settings-light.png"))
        scroll = window.tabs.widget(4).findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        QTimer.singleShot(300, capture_warnings)

    def capture_warnings():
        window.grab().save(str(output / "gui-project-warnings-light.png"))
        scroll = window.tabs.widget(4).findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(0)
        window.dark_mode_toggle.setChecked(True)
        QTimer.singleShot(300, capture_dark_settings)

    def capture_dark_settings():
        window.grab().save(str(output / "gui-settings-dark.png"))
        window.tabs.setCurrentIndex(1)
        QTimer.singleShot(300, capture_dark_table)

    def capture_dark_table():
        window.grab().save(str(output / "gui-participants-dark.png"))
        window.tabs.setCurrentIndex(0)
        QTimer.singleShot(2500, capture_dark_map)

    def capture_dark_map():
        window.grab().save(str(output / "gui-map-dark.png"))
        print("Saved GUI previews to", output.resolve())
        window.dirty = False  # Discard preview-only theme changes without a close prompt.
        window.close()
        app.quit()

    QTimer.singleShot(12000, capture)
    app.exec()


if __name__ == "__main__":
    main()
