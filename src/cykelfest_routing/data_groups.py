"""Shared group controls and local checkbox selection for the data views."""

from uuid import uuid4

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
)

from .data import MODELS, DataGroup
from .localization import tr

GROUP_COLORS = (
    "#59a9dc",
    "#187f71",
    "#e99b33",
    "#dc3545",
    "#8158b5",
    "#d36579",
    "#95d938",
    "#f2d428",
    "#636363",
)


def group_icon(color=None):
    image = QPixmap(24, 24)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen if color else QPen(QColor("#000000"), 2))
    painter.setBrush(QColor(color) if color else Qt.NoBrush)
    painter.drawEllipse(4, 4, 16, 16)
    painter.end()
    return QIcon(image)


def paint_checkbox(painter, rect, widget, state, enabled=True):
    option = QStyleOptionButton()
    option.rect = QRect(0, 0, 16, 16)
    option.rect.moveCenter(rect.center())
    option.state = QStyle.State_Enabled if enabled else QStyle.State_None
    option.state |= {
        Qt.Checked: QStyle.State_On,
        Qt.Unchecked: QStyle.State_Off,
        Qt.PartiallyChecked: QStyle.State_NoChange,
    }[state]
    widget.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, option, painter, widget)


class SelectionHeader(QHeaderView):
    def __init__(self, window, kind, table):
        super().__init__(Qt.Horizontal, table)
        self.window, self.kind = window, kind
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, section):
        super().paintSection(painter, rect, section)
        if section == 0:
            records = set(getattr(self.window.data, self.kind))
            selected = self.window.checked_entries[self.kind] & records
            state = (
                Qt.Checked
                if records and selected == records
                else Qt.PartiallyChecked
                if selected
                else Qt.Unchecked
            )
            paint_checkbox(painter, rect, self, state, bool(records))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.logicalIndexAt(event.position().toPoint()) == 0:
            self.window.check_all_entries(self.kind)
            event.accept()
        else:
            super().mousePressEvent(event)


class ColorPalette(QFrame):
    def __init__(self, parent, current, callback):
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_DeleteOnClose)
        layout = QGridLayout(self)
        for index, color in enumerate(GROUP_COLORS):
            control = QToolButton()
            control.setFixedSize(36, 36)
            control.setToolTip(color)
            control.setAccessibleName(color)
            control.setStyleSheet(
                f"background:{color};border:{3 if color == current else 1}px solid #203c37;border-radius:5px;"
            )
            control.clicked.connect(
                lambda checked=False, value=color: (callback(value), self.close())
            )
            layout.addWidget(control, index // 3, index % 3)


class SelectionDelegate(QStyledItemDelegate):
    """Handle checkbox clicks explicitly, including ranges in current sort order."""

    def __init__(self, window, kind, parent):
        super().__init__(parent)
        self.window, self.kind = window, kind

    def paint(self, painter, option, index):
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.features &= ~QStyleOptionViewItem.HasCheckIndicator
        option.widget.style().drawControl(
            QStyle.CE_ItemViewItem, background, painter, option.widget
        )
        paint_checkbox(
            painter, option.rect, option.widget, Qt.CheckState(index.data(Qt.CheckStateRole))
        )

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self.window.check_entry(
                self.kind, index.row(), bool(event.modifiers() & Qt.ShiftModifier)
            )
            return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.window.check_entry(
                self.kind, index.row(), bool(event.modifiers() & Qt.ShiftModifier)
            )
            return True
        return event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick)


class GroupList(QListWidget):
    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item:
            self.edit_group(item.data(Qt.UserRole), event.position().x() < 38)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class DataGroupsMixin:
    def initialize_groups(self):
        if not hasattr(self, "checked_entries"):
            self.checked_entries = {kind: set() for kind in MODELS}
            self.check_anchor = dict.fromkeys(MODELS)
            self.selected_group = None
        self.group_lists = []
        self.group_filters = {}

    def make_group_filter(self, kind):
        combo = QComboBox()
        combo.setMinimumWidth(110)
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setToolTip(tr("Filter by data group"))
        combo.addItem(group_icon(), tr("None"), None)
        self.group_filters[kind] = combo
        combo.currentIndexChanged.connect(
            lambda *_: (
                self.refresh_map()
                if kind == "map"
                else self.filter_table(kind, self.tables[kind][1].text())
            )
        )
        return combo

    def build_group_panel(self):
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Data groups")), 1)
        for text, callback in (("+", self.add_group), ("−", self.remove_group)):
            control = QPushButton(text)
            control.setFixedWidth(36)
            control.clicked.connect(callback)
            top.addWidget(control)
        layout.addLayout(top)
        listing = GroupList()
        listing.setEditTriggers(QListWidget.NoEditTriggers)
        listing.edit_group = self.edit_group
        listing.setMinimumHeight(150)
        listing.currentItemChanged.connect(self.group_selected)
        listing.itemChanged.connect(self.rename_group_item)
        self.group_lists.append(listing)
        layout.addWidget(listing, 1)
        actions = QGridLayout()
        for index, (text, action) in enumerate(
            (
                ("Assign", "assign"),
                ("Unbind", "unbind"),
                ("Select", "select"),
                ("Deselect", "deselect"),
            )
        ):
            control = QPushButton(tr(text))
            control.clicked.connect(lambda checked=False, a=action: self.group_action(a))
            actions.addWidget(control, index // 2, index % 2)
        layout.addLayout(actions)
        return panel

    def refresh_groups(self):
        for listing in self.group_lists:
            listing.blockSignals(True)
            listing.clear()
            for group in self.data.groups.values():
                item = QListWidgetItem(group_icon(group.color), group.name)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                item.setData(Qt.UserRole, group.id)
                listing.addItem(item)
                if group.id == self.selected_group:
                    listing.setCurrentItem(item)
            listing.blockSignals(False)
        for combo in self.group_filters.values():
            selected = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(group_icon(), tr("None"), None)
            for group in self.data.groups.values():
                combo.addItem(group_icon(group.color), group.name, group.id)
            combo.setCurrentIndex(max(0, combo.findData(selected)))
            combo.blockSignals(False)

    def group_selected(self, item, _previous):
        self.selected_group = item.data(Qt.UserRole) if item else None
        for listing in self.group_lists:
            listing.blockSignals(True)
            for row in range(listing.count()):
                candidate = listing.item(row)
                if candidate.data(Qt.UserRole) == self.selected_group:
                    listing.setCurrentItem(candidate)
            listing.blockSignals(False)

    def add_group(self):
        number = 1
        names = {group.name for group in self.data.groups.values()}
        while tr("Group {0}", f"{number:03d}") in names:
            number += 1
        group = DataGroup(id=uuid4().hex, name=tr("Group {0}", f"{number:03d}"))
        self.data.groups[group.id] = group
        self.selected_group = group.id
        self.changed()

    def remove_group(self):
        if self.selected_group in self.data.groups:
            self.data.groups.pop(self.selected_group)
            self.selected_group = None
            self.changed()

    def edit_group(self, group_id, color=False):
        group = self.data.groups.get(group_id)
        if not group:
            return
        if color:
            from PySide6.QtGui import QCursor

            self.group_color_popup = ColorPalette(
                self, group.color, lambda value: self.set_group_color(group_id, value)
            )
            self.group_color_popup.move(QCursor.pos())
            self.group_color_popup.show()
        else:
            listing = (
                self.sender()
                if isinstance(self.sender(), GroupList)
                else next(
                    (view for view in self.group_lists if view.isVisible()), self.group_lists[0]
                )
            )
            for row in range(listing.count()):
                item = listing.item(row)
                if item.data(Qt.UserRole) == group_id:
                    listing.editItem(item)
                    break

    def rename_group_item(self, item):
        group = self.data.groups.get(item.data(Qt.UserRole))
        if group and item.text().strip() and item.text().strip() != group.name:
            group.name = item.text().strip()
            QTimer.singleShot(0, self.changed)
        elif group and not item.text().strip():
            QTimer.singleShot(0, self.refresh_groups)

    def set_group_color(self, group_id, value):
        group = self.data.groups.get(group_id)
        if group:
            group.color = value
            self.changed()

    def group_action(self, action):
        group = self.data.groups.get(self.selected_group)
        if not group:
            return
        for kind in MODELS:
            members = set(getattr(group, kind)) & getattr(self.data, kind).keys()
            if action == "assign":
                setattr(group, kind, sorted(members | self.checked_entries[kind]))
            elif action == "unbind":
                setattr(group, kind, sorted(members - self.checked_entries[kind]))
            elif action == "select":
                self.checked_entries[kind].update(members)
            else:
                self.checked_entries[kind].difference_update(members)
        if action in ("assign", "unbind"):
            self.changed()
        else:
            self.refresh_checkboxes()

    def check_entry(self, kind, row, shift=False):
        table = self.tables[kind][0]
        rid = table.item(row, 0).data(Qt.UserRole)
        checked = rid not in self.checked_entries[kind]
        anchor = self.check_anchor[kind]
        start = next(
            (i for i in range(table.rowCount()) if table.item(i, 0).data(Qt.UserRole) == anchor),
            row,
        )
        rows = range(min(start, row), max(start, row) + 1) if shift else [row]
        for index in rows:
            if table.isRowHidden(index):
                continue
            key = table.item(index, 0).data(Qt.UserRole)
            if checked:
                self.checked_entries[kind].add(key)
            else:
                self.checked_entries[kind].discard(key)
        self.check_anchor[kind] = rid
        table.setCurrentCell(row, 1)
        self.refresh_checkboxes()

    def refresh_checkboxes(self):
        for kind, (table, _search) in self.tables.items():
            self.checked_entries[kind].intersection_update(getattr(self.data, kind))
            table.blockSignals(True)
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                item.setCheckState(
                    Qt.Checked
                    if item.data(Qt.UserRole) in self.checked_entries[kind]
                    else Qt.Unchecked
                )
            table.blockSignals(False)
            table.horizontalHeader().viewport().update()

    def check_all_entries(self, kind):
        records = set(getattr(self.data, kind))
        if records <= self.checked_entries[kind]:
            self.checked_entries[kind].difference_update(records)
        else:
            self.checked_entries[kind].update(records)
        self.refresh_checkboxes()

    def filtered_map_data(self, data):
        """Include full paths of matching routes and the addresses they reference."""
        group = data.groups.get(self.group_filters["map"].currentData())
        if group is None:
            return data
        from copy import deepcopy

        result = deepcopy(data)
        participants = set(group.participants)
        routes = set(group.routes)
        stops = set(group.stops)
        if self.draft:
            participants.add(self.draft.participant_id)
        for person in data.participants.values():
            route = data.route_for(person.id)
            if route and (
                person.id in group.participants
                or route.id in group.routes
                or set(group.stops).intersection(route.stops)
                or (self.draft and person.id == self.draft.participant_id)
            ):
                participants.add(person.id)
                routes.add(route.id)
                stops.update(route.stops)
        participants.update(data.stops[sid].host for sid in stops if sid in data.stops)
        result.participants = {
            pid: p for pid, p in result.participants.items() if pid in participants
        }
        result.routes = {rid: r for rid, r in result.routes.items() if rid in routes}
        result.stops = {sid: s for sid, s in result.stops.items() if sid in stops}
        return result
