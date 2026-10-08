"""Exercise overlapping Leaflet nodes using real Qt mouse events in both map modes."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --log-level=3")

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow
from cykelfest_routing.map_view import map_html


def main():
    app = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setFont(QFont("Segoe UI", 10))
    data = demo_data()
    data.participants["P002"].latitude = data.participants["P001"].latitude + (
        0 if "--coincident" in sys.argv else 0.0007
    )
    data.participants["P002"].longitude = data.participants["P001"].longitude
    settings = QSettings("artifacts/overlap-check.ini", QSettings.IniFormat)
    settings.clear()
    window = MainWindow(data, preferences=settings)
    window.resize(1400, 900)
    window.show()
    outcome = []
    editing = False
    circles = False
    original_points = None

    def finish(error=None):
        if outcome:
            return
        outcome.append(error)
        print(
            "FAIL: " + str(error)
            if error
            else "PASS: hover separation, moving edges, clickable nodes, restoration and editing drags"
        )
        window.draft = None
        window.dirty = False
        window.close()
        app.quit()

    def inspect(callback):
        window.map.page().runJavaScript(
            """JSON.stringify((() => {
            const overlap = window.cykelfestOverlap, map = window.cykelfestMap;
            if (!overlap) return null;
            const points = ['P001', 'P002', 'P003'].map(id => {
                const position = overlap.position(id);
                const p = map.latLngToContainerPoint(position);
                return [Math.round(p.x), Math.round(p.y)];
            });
            let edgeMatches = 0, edgeCount = 0, staleEndpoints = 0;
            map.eachLayer(layer => {
                if (!(layer instanceof L.Polyline)) return;
                edgeCount++;
                if (layer.getLatLngs().some(p => p.equals(overlap.position('P001')))) edgeMatches++;
                for (const point of layer.getLatLngs()) {
                    if (!['P001', 'P002', 'P003'].some(id => point.equals(overlap.position(id)))) staleEndpoints++;
                }
            });
            const originals = ORIGINAL_COORDINATES.map(coordinates => {
                const p = map.latLngToContainerPoint(coordinates);
                return [Math.round(p.x), Math.round(p.y)];
            });
            return {points, originals, expanded: overlap.expanded(), edgeMatches, edgeCount, staleEndpoints};
            })())""".replace(
                "ORIGINAL_COORDINATES",
                json.dumps(
                    [
                        [data.participants[pid].latitude, data.participants[pid].longitude]
                        for pid in ("P001", "P002", "P003")
                    ]
                ),
            ),
            lambda result: callback(json.loads(result or "null")),
        )

    def begin():
        inspect(hover)

    def hover(info):
        nonlocal original_points
        if not info:
            finish("Map did not initialize")
            return
        original_points = info["points"]
        target = window.map.focusProxy()
        QTest.mouseMove(target, QPoint(5, 5))
        QTest.mouseMove(target, QPoint(*info["points"][0]), 30)
        QTimer.singleShot(350, lambda: inspect(check_spread))

    def check_spread(info):
        if not info or set(info["expanded"]) != {"P001", "P002"}:
            finish(f"Overlapping nodes did not separate: {info}")
            return
        first, second = (QPoint(*p) for p in info["points"][:2])
        center = [(original_points[0][axis] + original_points[1][axis]) / 2 for axis in (0, 1)]
        for original, displayed in zip(original_points[:2], info["points"][:2], strict=True):
            doubled = [center[axis] + 2 * (original[axis] - center[axis]) for axis in (0, 1)]
            jitter = sum((displayed[axis] - doubled[axis]) ** 2 for axis in (0, 1)) ** 0.5
            if not 13 <= jitter <= 23:
                finish(f"Expansion did not use 2x scaling with a small random offset: {jitter}")
                return
        if first == second:
            finish("Coincident nodes did not separate into different directions")
            return
        if info["edgeCount"] < 2 or not info["edgeMatches"] or info["staleEndpoints"]:
            finish(f"Edges did not follow the displayed node positions: {info}")
            return
        Path("artifacts").mkdir(exist_ok=True)
        mode = "editing" if editing else "circles" if circles else "view"
        window.grab().save(f"artifacts/map-overlap-{mode}.png")
        if editing:
            # Draw from the expanded appetizer to the expanded main-course node.
            target = window.map.focusProxy()
            QTest.mousePress(target, Qt.LeftButton, Qt.NoModifier, first)
            QTest.mouseMove(target, second, 100)
            QTest.mouseRelease(target, Qt.LeftButton, Qt.NoModifier, second)
            QTimer.singleShot(700, check_drag)
        else:
            target = window.map.focusProxy()
            QTest.mouseMove(target, second, 30)
            QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, second)
            QTimer.singleShot(
                300,
                lambda: window.map.page().runJavaScript(
                    "document.querySelector('.leaflet-popup-content')?.textContent || ''",
                    check_click,
                ),
            )

    def check_click(text):
        if "Robin & Kim" not in text:
            finish(f"Expanded node was not distinctly clickable: {text}")
            return
        restore()

    def check_drag():
        if window.draft.host_at(0) != "P001" or window.draft.host_at(1) != "P002":
            finish(f"Expanded-node drag selected the wrong stops: {window.draft.stops}")
            return
        if window.draft.stops[2]:
            finish("Drag did not restart the route")
            return
        restore()

    def restore():
        QTest.mouseMove(window.map.focusProxy(), QPoint(5, 5), 30)
        QTimer.singleShot(350, lambda: inspect(check_restored))

    def check_restored(info):
        nonlocal editing, circles
        if info["expanded"] or info["points"] != info["originals"] or info["staleEndpoints"]:
            finish(f"Nodes did not return to their original positions: {info}")
            return
        if editing:
            assert data.route_stops("P001") == ["S001", "S002", "S003"]
            finish()
        elif not circles:
            circles = True
            window.map.setHtml(
                map_html(data, None, "All routes", True), QUrl("https://cykelfest.local/")
            )
            QTimer.singleShot(2500, begin)
        else:
            editing = True
            window.safe_edit_toggle.setChecked(False)
            window.edit_route()
            QTimer.singleShot(2500, begin)

    QTimer.singleShot(10000, begin)
    QTimer.singleShot(25000, lambda: finish("Check timed out"))
    app.exec()
    return 1 if not outcome or outcome[0] else 0


if __name__ == "__main__":
    sys.exit(main())
