"""Online integration check: send actual Qt mouse events into the embedded Leaflet map."""

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
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    data = demo_data()
    data.participants["P004"] = Participant(
        id="P004", name="New pairing", latitude=59.330, longitude=18.088
    )
    data.participants["P005"] = Participant(
        id="P005", name="Fade check", latitude=59.335, longitude=18.095
    )
    data.assign_route("P005", ["", "S002", "S003"])
    preferences = QSettings(str(Path("artifacts") / "check-preferences.ini"), QSettings.IniFormat)
    preferences.clear()
    window = MainWindow(data, preferences=preferences)
    window.data.create_route("P004")
    window.pending_pairing = "P004"
    window.refresh("P004")
    window.show()
    window.edit_route()
    outcome = []

    def finish(error=None):
        if outcome:
            return
        if error:
            print("FAIL:", error)
        else:
            print(
                "PASS: clicks, drags, right-click removal, Safe Edit filtering/toggle, centering, numbering, 500 ms fade and save"
            )
        outcome.append(error)
        window.draft = None
        window.dirty = False
        window.close()
        app.quit()

    def locations(callback):
        window.map.page().runJavaScript(
            """(() => {
            const fadeNode = document.querySelector('[data-host-id="P005"]');
            if (fadeNode && !fadeNode.dataset.trackingFade) {
                fadeNode.dataset.trackingFade = 'true';
                window.cykelfestFadeSamples = [];
                fadeNode.addEventListener('transitionrun', () => {
                    const started = performance.now();
                    function sample() {
                        const opacity = Number(getComputedStyle(fadeNode).opacity);
                        if (opacity > 0.25 && opacity < 1) {
                            window.cykelfestFadeSamples.push({opacity,
                                duration: getComputedStyle(fadeNode).transitionDuration});
                        } else if (performance.now() - started < 600) {
                            requestAnimationFrame(sample);
                        }
                    }
                    requestAnimationFrame(sample);
                });
            }
            return JSON.stringify(window.cykelfestEditor ? {
            points: Object.fromEntries(window.cykelfestEditorState.hosts.map(h => {
                const p = window.cykelfestMap.latLngToContainerPoint([h.lat, h.lon]);
                return [h.id, [Math.round(p.x), Math.round(p.y)]];
            })), markers: window.cykelfestEditor.nodes.getLayers().length,
            labels: Object.fromEntries([...document.querySelectorAll('[data-host-id]')].map(e => [e.dataset.hostId, e.textContent])),
            dark: document.getElementById('cykelfest-theme').textContent.includes('#1d2a32'),
            tiles: window.cykelfestBaseLayer._url,
            stylePreserved: !window.cykelfestStyleCheckpoint || (
                window.cykelfestStyleCheckpoint.map === window.cykelfestMap &&
                window.cykelfestStyleCheckpoint.editor === window.cykelfestEditor &&
                window.cykelfestStyleCheckpoint.center.equals(window.cykelfestMap.getCenter()) &&
                window.cykelfestStyleCheckpoint.zoom === window.cykelfestMap.getZoom()),
            opacities: [...document.querySelectorAll('[data-host-id]')].map(e => {
                const host = window.cykelfestEditorState.hosts.find(h => h.id === e.dataset.hostId);
                const course = window.cykelfestEditorState.next === null ? 0 : window.cykelfestEditorState.next;
                return {id: host.id, actual: Number(getComputedStyle(e).opacity), expected: host.eligible[course] ? 1 : 0.25};
            })
        } : null); })()""",
            lambda result: callback(json.loads(result or "null")),
        )

    def gesture(start, end, callback, right=False):
        def send(info):
            if not info:
                finish("Leaflet / WebChannel did not initialize")
                return
            expected_markers = 5
            if info["markers"] != expected_markers:
                finish(
                    f"Eligibility filtering showed {info['markers']} markers, expected {expected_markers}"
                )
                return
            if any(abs(node["actual"] - node["expected"]) > 0.01 for node in info["opacities"]):
                finish(f"Incorrect eligibility opacity: {info['opacities']}")
                return
            target = window.map.focusProxy()
            first = QPoint(*info["points"][start])
            mouse_button = Qt.RightButton if right else Qt.LeftButton
            initial_gesture = not any(window.draft.stops)
            if initial_gesture:
                window.verify_change_toggle.setChecked(True)
                for dark in (True, False, True):
                    window.dark_mode_toggle.setChecked(dark)
            elif not info["dark"]:
                finish("Map theme did not survive repeated switching during editing")
                return
            elif "dark_all" not in info["tiles"] or not info["stylePreserved"]:
                finish("Map style switching reset the map/editor or failed to update the tiles")
                return
            QTest.mousePress(target, mouse_button, Qt.NoModifier, first)
            if end:
                last = QPoint(*info["points"][end])
                QTest.mouseMove(target, (first + last) / 2, 100)
                QTest.mouseMove(target, last, 100)
                QTest.mouseRelease(target, Qt.LeftButton, Qt.NoModifier, last)
            else:
                QTest.mouseRelease(target, mouse_button, Qt.NoModifier, first)
            if initial_gesture and start == "P001" and not right:
                QTimer.singleShot(200, check_fade)
            if end == "P003":
                QTimer.singleShot(200, check_fade)
            QTimer.singleShot(800, callback)

        locations(send)

    def check_fade(attempt=0):
        window.map.page().runJavaScript(
            """JSON.stringify((() => {
            // Sample inside Chromium: Python's event loop may be occupied by
            // rebuilding tables until after the transition has finished.
            return window.cykelfestFadeSamples?.shift() || null;
        })())""",
            lambda result: verify_fade(json.loads(result or "null"), attempt),
        )

    def verify_fade(value, attempt):
        if value is None and attempt < 5:
            QTimer.singleShot(150, lambda: check_fade(attempt + 1))
            return
        if not value or not 0.25 < value["opacity"] < 1 or value["duration"] != "0.5s":
            finish(f"Marker did not fade over 500 ms: {value}")

    def after_appetizer():
        if outcome:
            return
        if window.draft.host_at(0) != "P001":
            finish(f"Click did not assign appetizer: {window.draft.stops}")
            return
        if not window.verified or not window.verify_on_change:
            finish("Automatic draft verification did not run")
            return
        window.map.page().runJavaScript(
            "window.cykelfestStyleCheckpoint = {map: window.cykelfestMap, editor: window.cykelfestEditor, center: window.cykelfestMap.getCenter(), zoom: window.cykelfestMap.getZoom()};",
            lambda _: switch_styles(),
        )

    def switch_styles():
        for style in ("positron", "standard", "dark_matter"):
            window.osm_combo.setCurrentIndex(window.osm_combo.findData(style))
        QTimer.singleShot(500, lambda: gesture("P002", None, after_main))

    def after_main():
        if window.draft.host_at(1) != "P002":
            finish(f"Click did not assign main: {window.draft.stops}")
            return
        gesture("P004", "P002", after_restart)

    def after_restart():
        if (
            window.draft.host_at(0) != "P004"
            or window.draft.host_at(1) != "P002"
            or window.draft.stops[2]
        ):
            finish(f"Restart drag failed: {window.draft.stops}")
            return
        gesture("P002", "P003", after_continuation)

    def after_continuation():
        if window.draft.host_at(2) != "P003":
            finish(f"Continuation drag failed: {window.draft.stops}")
            return
        Path("artifacts").mkdir(exist_ok=True)
        window.grab().save("artifacts/gui-map-editor.png")
        locations(check_numbering)

    def check_numbering(info):
        if {pid: info["labels"].get(pid) for pid in ("P004", "P002", "P003")} != {
            "P004": "1",
            "P002": "2",
            "P003": "3",
        }:
            finish(f"Incorrect route numbering: {info['labels']}")
            return
        gesture("P004", None, after_remove, right=True)

    def after_remove():
        if window.draft.stops[0] or not all(window.draft.stops[1:]):
            finish(f"Right-click did not remove just appetizer: {window.draft.stops}")
            return
        gesture("P003", None, after_ineligible_click)

    def after_ineligible_click():
        if window.draft.stops[0]:
            finish("Visible but ineligible dessert host was assigned as appetizer")
            return
        gesture("P001", None, after_refill)

    def after_refill():
        if window.draft.host_at(0) != "P001":
            finish("Removed appetizer could not be refilled")
            return
        if any(data.route_stops("P004")):
            finish("Draft leaked into committed tables")
            return
        window.safe_edit_toggle.setChecked(False)
        QTimer.singleShot(650, lambda: locations(check_unsafe_edit))

    def check_unsafe_edit(info):
        if not info or any(abs(node["actual"] - 1) > 0.01 for node in info["opacities"]):
            finish("Disabling Safe Edit did not reveal all host markers")
            return
        if not all(all(host["eligible"]) for host in window.draft.payload()["hosts"]):
            finish("Disabling Safe Edit did not allow all hosts")
            return
        window.safe_edit_toggle.setChecked(True)
        window.course_controls[1][1].click()
        QTimer.singleShot(700, check_center)

    def check_center():
        window.map.page().runJavaScript(
            "JSON.stringify([window.cykelfestMap.getCenter().lat, window.cykelfestMap.getCenter().lng])",
            lambda result: after_center(json.loads(result or "null")),
        )

    def after_center(point):
        expected = window.draft.data.coordinates(window.draft.participant_id)[1]
        if not point or any(abs(a - b) > 0.00001 for a, b in zip(point, expected, strict=True)):
            finish(f"Center button did not move the map to the main stop: {point}")
            return
        window.save_route()
        if data.route_for("P004").main_stop_id != "S002" or "P004" not in data.stops["S003"].guests:
            finish("Save did not update route and guest membership")
            return
        finish()

    QTimer.singleShot(12000, lambda: gesture("P001", None, after_appetizer))
    QTimer.singleShot(30000, lambda: finish("Integration check timed out") if not outcome else None)
    app.exec()
    return 1 if not outcome or outcome[0] else 0


if __name__ == "__main__":
    sys.exit(main())
