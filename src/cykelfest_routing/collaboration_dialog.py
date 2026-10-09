"""Session controls for local and VPN collaboration."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .localization import tr
from .theme import course_icon


class CollaborationDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.session = window.collaboration
        self.setWindowTitle(tr("Collaborate"))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Your name")))
        self.name = QLineEdit(self.session.name)
        self.name.setMaxLength(80)
        layout.addWidget(self.name)
        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.connect_session)
        layout.addWidget(self.connect_button)
        self.disconnect_button = QPushButton(tr("Disconnect"))
        self.disconnect_button.clicked.connect(self.session.disconnect)
        layout.addWidget(self.disconnect_button)
        self.host_button = QPushButton()
        self.host_button.clicked.connect(self.host_session)
        layout.addWidget(self.host_button)
        row = QHBoxLayout()
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.copy = QPushButton(tr("Copy address"))
        self.copy.setText("")
        self.copy.setIcon(course_icon("copy", window.dark_mode))
        self.copy.setFixedSize(36, 36)
        self.copy.setToolTip(tr("Copy address"))
        self.copy.setAccessibleName(tr("Copy address"))
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.address.text()))
        row.addWidget(self.address, 1)
        row.addWidget(self.copy)
        layout.addLayout(row)
        self.members = QListWidget()
        layout.addWidget(self.members)
        self.addresses = QLabel()
        self.addresses.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.addresses)
        self.session.status_changed.connect(self.update_status)
        self.finished.connect(lambda *_: self.session.status_changed.disconnect(self.update_status))
        self.update_status()

    def update_status(self):
        mode = self.session.mode
        self.name.setEnabled(mode == "offline")
        self.disconnect_button.setVisible(mode == "client")
        self.connect_button.setText(tr("Disconnect") if mode == "client" else tr("Connect"))
        if mode == "client":
            self.connect_button.setText(tr("Connected"))
            self.connect_button.setToolTip(tr("Disconnect"))
        self.connect_button.setEnabled(mode in ("offline", "client"))
        self.connect_button.setStyleSheet(
            "background:#169b43;color:white;" if mode == "client" else ""
        )
        self.host_button.setText(tr("Stop Hosting") if mode == "host" else tr("Host"))
        self.host_button.setEnabled(mode in ("offline", "host"))
        self.host_button.setStyleSheet("background:#c63838;color:white;" if mode == "host" else "")
        self.address.setVisible(mode == "host")
        self.copy.setVisible(mode == "host")
        addresses = self.session.addresses() if mode == "host" else []
        self.address.setText(addresses[0] if addresses else "")
        self.addresses.setText("\n".join(addresses[1:]))
        self.members.clear()
        if mode == "host":
            self.members.addItems([p.name for p in self.session.peers.values() if p.ready])
        self.members.setVisible(mode == "host")

    def host_session(self):
        if self.session.mode == "host":
            if self.window.draft:
                self.window.revert_route()
            self.session.disconnect()
            return
        try:
            self.session.host(self.name.text(), self.window.data, self.window.project_settings())
        except ValueError as error:
            QMessageBox.warning(self, tr("Collaborate"), tr(str(error)))

    def connect_session(self):
        if self.session.mode == "client":
            return
        if (
            self.window.dirty
            and QMessageBox.question(
                self,
                tr("Replace unsaved project"),
                tr(
                    "Connecting replaces your project with the host's project. Discard unsaved changes?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Connect"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr("Host address (IP:port)")))
        address = QLineEdit()
        address.setPlaceholderText("192.168.1.20:45454")
        layout.addWidget(address)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)

        def attempt():
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            self.session.connect(self.name.text(), address.text())

        def status():
            if self.session.mode == "client":
                dialog.accept()
            elif self.session.mode == "offline":
                buttons.button(QDialogButtonBox.Ok).setEnabled(True)

        buttons.accepted.connect(attempt)
        address.returnPressed.connect(lambda: attempt() if self.session.mode == "offline" else None)
        self.session.status_changed.connect(status)
        dialog.exec()
        self.session.status_changed.disconnect(status)
        if self.session.mode == "connecting":
            self.session.disconnect()
