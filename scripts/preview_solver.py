"""Render the automatic-assignment review dialog in both GUI themes."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow, SolverPreview
from cykelfest_routing.solver import solve_routes


def main():
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    app = QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    preferences = QSettings(str(output / "solver-preview-preferences.ini"), QSettings.IniFormat)
    preferences.clear()
    window = MainWindow(demo_data(), enable_map=False, preferences=preferences)
    result = solve_routes(window.data, window.segment_preferences, maximum_time=5)
    if result.data is None:
        raise RuntimeError(result.message)
    dialog = SolverPreview(result, window.segment_preferences, (), window)
    dialog.show()

    def capture_light():
        dialog.grab().save(str(output / "gui-solver-light.png"))
        window.dark_mode_toggle.setChecked(True)
        QTimer.singleShot(300, capture_dark)

    def capture_dark():
        dialog.grab().save(str(output / "gui-solver-dark.png"))
        dialog.close()
        window.close()
        app.quit()

    QTimer.singleShot(300, capture_light)
    app.exec()


if __name__ == "__main__":
    main()
