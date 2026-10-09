"""Exercise two real local instances and render session controls/locked map nodes."""

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from cykelfest_routing.collaboration_dialog import CollaborationDialog
from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    windows = []
    for role in ("host", "client"):
        preferences = QSettings(str(output / f"collaboration-{role}.ini"), QSettings.IniFormat)
        preferences.clear()
        window = MainWindow(demo_data() if role == "host" else None, preferences=preferences)
        window.show()
        windows.append(window)
    host, client = windows
    host.collaboration.host("Planner", host.data, host.project_settings(), port=0)
    client.collaboration.connect("Editor", f"127.0.0.1:{host.collaboration.server.serverPort()}")
    pump(2)
    assert client.collaboration.mode == "client"
    assert not client.new_project_button.isEnabled()
    pump(10)
    client.refresh("P001")
    client.edit_route()
    pump(4)
    assert host.collaboration.foreign_nodes()
    host.grab().save(str(output / "collaboration-host-locked.png"))
    client.grab().save(str(output / "collaboration-client-edit.png"))
    dialog = CollaborationDialog(host)
    dialog.show()
    pump(0.3)
    dialog.grab().save(str(output / "collaboration-host-dialog.png"))
    dialog.close()
    dialog = CollaborationDialog(client)
    dialog.show()
    pump(0.3)
    dialog.grab().save(str(output / "collaboration-client-dialog.png"))
    dialog.close()
    client.revert_route()
    assert not host.collaboration.locks
    for window in reversed(windows):
        window.collaboration.disconnect()
        window.dirty = False
        window.close()
    pump(0.1)
    print("PASS: local TCP sync, permissions, locks, and session-control previews")


if __name__ == "__main__":
    main()
