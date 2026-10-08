"""Exercise native single clicks and browser double-clicks on embedded route segments."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --log-level=3")

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cykelfest_routing.data import Participant, demo_data
from cykelfest_routing.gui import MainWindow


def main():
    app = QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    data = demo_data()
    data.participants["far"] = Participant(
        id="far", name="Unassigned", latitude=59.38, longitude=18.1
    )
    settings = QSettings("artifacts/map-route-check.ini", QSettings.IniFormat)
    settings.clear()
    window = MainWindow(data, preferences=settings)
    window.resize(1500, 1000)
    window.map_mode.setCurrentIndex(window.map_mode.findData("All routes"))
    window.show()
    outcome = []
    initial_zoom = None

    def finish(error=None):
        if outcome:
            return
        outcome.append(error)
        print(
            "FAIL: " + str(error)
            if error
            else "PASS: no focus rectangle, route double-click selection/fit, course outlines and fit icon"
        )
        window.draft = None
        window.dirty = False
        window.close()
        app.quit()

    def inspect(callback):
        window.map.page().runJavaScript(
            """JSON.stringify((() => {
            if (!window.cykelfestMap || !window.cykelfestOverlap) return null;
            const map = window.cykelfestMap, lines = [], circles = [];
            map.eachLayer(layer => {
                if (layer instanceof L.Polyline && layer.listens('dblclick')) lines.push(layer);
                if (layer instanceof L.CircleMarker) circles.push(layer.options.color);
            });
            if (!lines.length) return null;
            const line = lines[lines.length - 2], points = line.getLatLngs();
            const first = map.latLngToContainerPoint(points[0]), last = map.latLngToContainerPoint(points[1]);
            window.checkRouteLine = line;
            return {point: [Math.round((first.x + last.x)/2), Math.round((first.y + last.y)/2)],
                zoom: map.getZoom(), farVisible: map.getBounds().contains([59.38,18.1]),
                outline: getComputedStyle(line._path).outlineStyle, circles,
                borders: [...document.querySelectorAll('.leaflet-marker-icon > div')].map(e => getComputedStyle(e).borderTopColor)};
        })())""",
            lambda value: callback(json.loads(value or "null")),
        )

    def ready(info):
        nonlocal initial_zoom
        if not info:
            QTimer.singleShot(500, lambda: inspect(ready))
            return
        initial_zoom = info["zoom"]
        try:
            assert set(info["borders"]) == {
                "rgb(242, 140, 40)",
                "rgb(22, 155, 67)",
                "rgb(38, 122, 192)",
            }
            assert "#000000" in info["circles"]
            assert window.fit_hosts_button.text() == ""
            QTest.mouseClick(
                window.map.focusProxy(), Qt.LeftButton, Qt.NoModifier, QPoint(*info["point"])
            )
            QTimer.singleShot(120, lambda: inspect(single_clicked))
        except (AssertionError, KeyError, TypeError, RuntimeError) as error:
            finish(error)

    def single_clicked(info):
        try:
            assert info["outline"] == "none" and window.selected_route == "P001"
            # Offscreen QTest presses carry clickCount=1, even for mouseDClick.
            # Dispatch the DOM dblclick through Leaflet's real event delegation.
            window.map.page().runJavaScript(
                "window.checkRouteLine._path.dispatchEvent(new MouseEvent('dblclick', {bubbles:true, cancelable:true, detail:2}));"
            )
            QTimer.singleShot(1500, lambda: inspect(selected))
        except (AssertionError, KeyError, TypeError, RuntimeError) as error:
            finish(error)

    def selected(info):
        try:
            assert window.selected_route == "P003", (window.selected_route, info)
            assert info and info["zoom"] > initial_zoom and not info["farVisible"], info
            window.fit_hosts_button.click()
            QTimer.singleShot(700, lambda: inspect(fitted))
        except (AssertionError, KeyError, TypeError, RuntimeError) as error:
            finish(error)

    def fitted(info):
        try:
            assert info and info["farVisible"], info
            window.grab().save("artifacts/map-route-controls.png")
            finish()
        except (AssertionError, KeyError, TypeError, RuntimeError) as error:
            finish(error)

    QTimer.singleShot(1000, lambda: inspect(ready))
    QTimer.singleShot(25000, lambda: finish("Map interaction check timed out"))
    app.exec()
    return 1 if not outcome or outcome[0] else 0


if __name__ == "__main__":
    sys.exit(main())
