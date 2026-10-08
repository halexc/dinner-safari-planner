"""Coordinated widget palettes and map styling for light and dark modes."""

import re

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF


def course_icon(kind, dark):
    """Draw crisp icons without depending on installed symbol fonts."""
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#e1ebe8" if dark else "#203c37"), 2.5))
    if kind == "center":
        painter.drawEllipse(QPointF(20, 20), 11, 11)
        painter.drawEllipse(QPointF(20, 20), 3, 3)
        for x1, y1, x2, y2 in (
            (20, 3, 20, 11),
            (20, 29, 20, 37),
            (3, 20, 11, 20),
            (29, 20, 37, 20),
        ):
            painter.drawLine(x1, y1, x2, y2)
    else:
        painter.drawPolygon(
            QPolygonF(
                [QPointF(8, 25), QPointF(27, 6), QPointF(34, 13), QPointF(15, 32), QPointF(6, 34)]
            )
        )
        painter.drawLine(23, 10, 30, 17)
        painter.drawLine(8, 25, 15, 32)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


DARK_COLORS = {
    "#f3f6f5": "#141d24",
    "#203c37": "#e1ebe8",
    "#637a73": "#a5bab4",
    "#dbe5e0": "#3b4d54",
    "#e7eeea": "#26353d",
    "#187f71": "#247f74",
    "#ccdbd4": "#465b62",
    "#e5f2ec": "#314c48",
    "#95a59f": "#82938f",
    "#f0f3f1": "#202b32",
    "#126759": "#319c8c",
    "#f5f8f6": "#24313a",
    "#e6eee9": "#35464e",
    "#d6eee4": "#305b53",
    "#eaf0ed": "#26353d",
    "#edf2ef": "#33454c",
    "#e0e9e4": "#3b4d54",
}


def stylesheet(light_style, dark):
    style = light_style
    if dark:
        style = re.sub(r"#[0-9a-f]{6}", lambda match: DARK_COLORS.get(match[0], match[0]), style)
        style = style.replace("background: white", "background: #1d2a32")
    surface, text, border, accent = (
        ("#1d2a32", "#e1ebe8", "#465b62", "#68cfba")
        if dark
        else ("#ffffff", "#203c37", "#ccdbd4", "#187f71")
    )
    return (
        style
        + f"""
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 8px; }}
QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {accent}; selection-color: #142723; }}
QCheckBox::indicator {{ width: 20px; height: 20px; background: {surface}; border: 1px solid {border}; border-radius: 4px; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 3px solid {border}; }}
QPushButton#primary:disabled {{ background: {surface}; color: {"#82938f" if dark else "#95a59f"}; border: 1px solid {border}; }}
QLabel#hint {{ color: {accent}; border: 1px solid {border}; border-radius: 10px; padding: 2px; }}
QLabel#error {{ color: {"#ff9791" if dark else "#b13d38"}; }}
"""
    )


def palette(dark):
    result = QPalette()
    colors = {
        QPalette.Window: "#141d24" if dark else "#f3f6f5",
        QPalette.WindowText: "#e1ebe8" if dark else "#203c37",
        QPalette.Base: "#1d2a32" if dark else "#ffffff",
        QPalette.AlternateBase: "#24313a" if dark else "#f5f8f6",
        QPalette.Text: "#e1ebe8" if dark else "#203c37",
        QPalette.Button: "#26353d" if dark else "#ffffff",
        QPalette.ButtonText: "#e1ebe8" if dark else "#203c37",
        QPalette.Highlight: "#305b53" if dark else "#d6eee4",
        QPalette.HighlightedText: "#e1ebe8" if dark else "#203c37",
        QPalette.Link: "#68cfba" if dark else "#187f71",
        QPalette.ToolTipBase: "#1d2a32" if dark else "#ffffff",
        QPalette.ToolTipText: "#e1ebe8" if dark else "#203c37",
        QPalette.PlaceholderText: "#a5bab4" if dark else "#637a73",
    }
    for role, color in colors.items():
        result.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        result.setColor(QPalette.Disabled, role, QColor("#82938f" if dark else "#95a59f"))
    return result


def map_css(dark):
    base = "path.leaflet-interactive:focus { outline: none; }"
    if not dark:
        return base
    return (
        base
        + """
.leaflet-container { background: #141d24; }
.leaflet-control-zoom a, .leaflet-control-attribution, .leaflet-popup-content-wrapper,
.leaflet-popup-tip, .leaflet-tooltip { background: #1d2a32 !important; color: #e1ebe8 !important; }
.leaflet-control-attribution a, .leaflet-popup-content a { color: #68cfba; }
"""
    )
