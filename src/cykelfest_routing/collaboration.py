"""Local/VPN collaboration: framed JSON over TCP, with an authoritative host."""

import json
import struct
import time
from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import (
    QAbstractSocket,
    QHostAddress,
    QNetworkInterface,
    QTcpServer,
    QTcpSocket,
)

from .data import MODELS, DataGroup, DinnerData, next_record_id
from .project import ProjectFile

MAX_FRAME = 16 * 1024 * 1024
TABLES = ("participants", "stops", "routes", "groups")


def snapshot(data, settings):
    return {
        **{k: {rid: r.model_dump() for rid, r in getattr(data, k).items()} for k in TABLES},
        "settings": settings.model_dump(mode="json"),
    }


def decode_snapshot(state):
    state = {"groups": {}, **state}
    if any(rid != record["id"] for k in TABLES for rid, record in state[k].items()):
        raise ValueError("Invalid record identifiers")
    project = ProjectFile.model_validate(
        {
            "format": "cykelfest-dinner-safari",
            "version": 2,
            **{k: list(state[k].values()) for k in TABLES},
            "settings": state["settings"],
        }
    )
    data = DinnerData()
    for k in TABLES:
        setattr(data, k, {r.id: r for r in getattr(project, k)})
    return data, project.settings


def difference(before, after):
    return {
        k: {
            rid: {"before": before[k].get(rid), "after": after[k].get(rid)}
            for rid in before[k].keys() | after[k].keys()
            if before[k].get(rid) != after[k].get(rid)
        }
        for k in TABLES
    }


def resources(patch, state):
    result = set()
    for kind, changes in patch.items():
        for rid, change in changes.items():
            if kind == "participants":
                result.add(rid)
            elif kind == "routes":
                result.update(
                    pid for pid, p in state["participants"].items() if p["route_id"] == rid
                )
            for record in (change["before"], change["after"]):
                if record and kind == "stops":
                    result.add(record["host"])
                if record and kind == "routes":
                    for field in ("appetizer_stop_id", "main_stop_id", "dessert_stop_id"):
                        stop = state["stops"].get(record[field])
                        if stop:
                            result.add(stop["host"])
    return result - {""}


class Peer(QObject):
    message = Signal(object)
    closed = Signal()

    def __init__(self, socket, parent):
        super().__init__(parent)
        self.socket = socket
        socket.setParent(self)
        self.buffer = bytearray()
        self.last_seen = time.monotonic()
        self.awaiting = None
        self.ready = False
        self.name = ""
        self.id = uuid4().hex
        self.completed = {}
        socket.readyRead.connect(self.read)
        socket.disconnected.connect(self.closed)
        socket.errorOccurred.connect(lambda *_: self.closed.emit())

    def send(self, message):
        raw = json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_FRAME or self.socket.bytesToWrite() > 2 * MAX_FRAME:
            self.socket.abort()
            return
        self.socket.write(struct.pack("!I", len(raw)) + raw)

    def read(self):
        self.buffer.extend(bytes(self.socket.readAll()))
        try:
            while len(self.buffer) >= 4:
                size = struct.unpack("!I", self.buffer[:4])[0]
                if size > MAX_FRAME or size == 0:
                    raise ValueError("Invalid frame")
                if len(self.buffer) < size + 4:
                    break
                raw = bytes(self.buffer[4 : size + 4])
                del self.buffer[: size + 4]
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise TypeError("Invalid message")
                self.last_seen = time.monotonic()
                self.message.emit(message)
        except (ValueError, UnicodeError, TypeError):
            self.socket.abort()

    def shutdown(self, *, graceful=False):
        self.socket.readyRead.disconnect(self.read)
        self.socket.disconnected.disconnect()
        self.socket.errorOccurred.disconnect()
        if graceful:
            self.socket.flush()
            self.socket.disconnectFromHost()
        else:
            self.socket.abort()
        self.deleteLater()


class CollaborationSession(QObject):
    state_received = Signal(object)
    status_changed = Signal()
    locks_changed = Signal()
    failed = Signal(str)
    reply = Signal(str, object)

    def __init__(self, parent=None, *, timeout=15):
        super().__init__(parent)
        self.mode = "offline"
        self.name = ""
        self.id = "host"
        self.state = None
        self.revision = 0
        self.locks = {}
        self.peers = {}
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self.accept)
        self.peer = None
        self.timeout = timeout
        self.connect_started = None
        self.received_initial = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.responses = {}
        self.busy = False

    def host(self, name, data, settings, port=45454):
        if self.mode != "offline":
            raise ValueError("Session already active")
        initial = snapshot(data, settings)
        decode_snapshot(initial)
        if not self.server.listen(QHostAddress.SpecialAddress.AnyIPv4, port):
            raise ValueError(self.server.errorString())
        self.state = initial
        self.name = name.strip() or "Host"
        self.mode = "host"
        self.id = "host"
        self.revision = 0
        self.status_changed.emit()

    def addresses(self):
        addresses = [
            entry.ip().toString()
            for interface in QNetworkInterface.allInterfaces()
            if interface.flags() & QNetworkInterface.InterfaceFlag.IsUp
            for entry in interface.addressEntries()
            if entry.ip().protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol
            and not entry.ip().isLoopback()
        ]
        return [
            f"{ip}:{self.server.serverPort()}" for ip in dict.fromkeys(addresses or ["127.0.0.1"])
        ]

    def connect(self, name, address):
        if self.mode != "offline":
            return
        host, sep, port = address.strip().rpartition(":")
        if not sep:
            host, port = address.strip(), "45454"
        try:
            port = int(port)
            if not host or not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            self.failed.emit("Connection failed...")
            return
        self.name = name.strip() or "Guest"
        self.mode = "connecting"
        self.received_initial = False
        self.connect_started = time.monotonic()
        socket = QTcpSocket(self)
        self.peer = Peer(socket, self)
        self.peer.message.connect(self.client_message)
        self.peer.closed.connect(self.connection_lost)
        socket.connected.connect(
            lambda: (
                self.peer.send({"type": "hello", "version": 1, "name": self.name})
                if self.peer
                else None
            )
        )
        self.status_changed.emit()
        socket.connectToHost(host, port)

    def accept(self):
        while self.server.hasPendingConnections():
            peer = Peer(self.server.nextPendingConnection(), self)
            self.peers[peer.id] = peer
            peer.message.connect(lambda m, p=peer: self.host_message(p, m))
            peer.closed.connect(lambda p=peer: self.remove_peer(p))

    def remove_peer(self, peer):
        if self.peers.pop(peer.id, None) is None:
            return
        peer.shutdown()
        self.release(peer.id)
        self.status_changed.emit()

    def broadcast(self):
        for peer in list(self.peers.values()):
            if peer.ready:
                self.send_state(peer)

    def send_state(self, peer):
        if peer.awaiting is None:
            peer.awaiting = time.monotonic()
        peer.send(
            {
                "type": "state",
                "revision": self.revision,
                "state": self.state,
                "locks": self.locks,
                "id": peer.id,
                "busy": self.busy,
            }
        )

    def host_message(self, peer, message):
        if peer.id not in self.peers:
            return
        kind = message.get("type")
        if kind == "hello" and not peer.name:
            if message.get("version") != 1:
                self.remove_peer(peer)
                return
            peer.name = str(message.get("name", "Guest"))[:80]
            self.send_state(peer)
        elif kind == "ack" and peer.name:
            if message.get("revision") == self.revision:
                peer.awaiting = None
                if not peer.ready:
                    peer.ready = True
                    self.send_state(peer)
                    peer.send({"type": "ready"})
                    self.status_changed.emit()
            elif not peer.ready:
                # Host edits during the initial snapshot must not strand the joiner.
                self.send_state(peer)
        elif kind == "ping":
            peer.send({"type": "pong"})
        elif kind == "request" and peer.ready:
            request = message.get("request")
            if not isinstance(request, str) or not request or len(request) > 80:
                self.remove_peer(peer)
                return
            if request in peer.completed:
                peer.send(peer.completed[request])
                return
            try:
                result = self.execute(peer.id, message["action"], message.get("payload", {}))
                response = {"type": "reply", "request": request, "ok": True, "result": result}
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                response = {
                    "type": "reply",
                    "request": request,
                    "ok": False,
                    "error": str(error),
                }
            peer.completed[request] = response
            if len(peer.completed) > 128:
                del peer.completed[next(iter(peer.completed))]
            peer.send(response)

    def execute(self, owner, action, payload):
        if owner != "host" and self.busy and action != "release":
            raise ValueError("The host is running a project-wide operation. Please retry later.")
        if action == "lock":
            requested = set(payload["nodes"])
            if not requested <= self.state["participants"].keys():
                raise ValueError("Reference unavailable")
            if any(self.locks.get(node, {}).get("owner", owner) != owner for node in requested):
                raise ValueError("This node is being edited by another collaborator.")
            name = self.name if owner == "host" else self.peers[owner].name
            for node in requested:
                self.locks[node] = {"owner": owner, "name": name}
            self.broadcast()
            self.locks_changed.emit()
            return None
        if action == "release":
            self.release(owner)
            return None
        if action != "patch":
            raise ValueError("Unsupported collaboration action")
        patch = {"groups": {}, **payload["changes"]}
        if set(patch) != set(TABLES):
            raise ValueError("Invalid patch")
        if any(
            self.locks.get(node, {}).get("owner", owner) != owner
            for node in resources(patch, self.state)
        ):
            raise ValueError("This node is being edited by another collaborator.")
        trial = deepcopy(self.state)
        if "settings" in payload:
            if owner != "host":
                raise ValueError("Only the host can change project settings.")
            if self.locks and payload["settings"] != trial["settings"]:
                raise ValueError("Finish active route edits before changing project settings.")
            trial["settings"] = payload["settings"]
        mappings = {k: {} for k in TABLES}
        for k in TABLES:
            reserved = dict(trial[k])
            for rid, change in patch[k].items():
                if change["before"] is None and change["after"] is not None:
                    if k == "groups" and rid in reserved:
                        raise ValueError("The record changed. Please retry your edit.")
                    new_id = (
                        rid
                        if k == "groups"
                        else next_record_id(
                            reserved, {"participants": "P", "stops": "S", "routes": "R"}[k]
                        )
                    )
                    mappings[k][rid] = new_id
                    reserved[new_id] = None
                elif self.state[k].get(rid) != change["before"]:
                    raise ValueError("The record changed. Please retry your edit.")
        for k in TABLES:
            for rid, change in patch[k].items():
                record = deepcopy(change["after"])
                if record is None:
                    trial[k].pop(rid, None)
                    continue
                rid = mappings[k].get(rid, rid)
                record["id"] = rid
                if k == "participants":
                    record["route_id"] = mappings["routes"].get(
                        record["route_id"], record["route_id"]
                    )
                elif k == "stops":
                    record["host"] = mappings["participants"].get(record["host"], record["host"])
                    record["guests"] = [
                        mappings["participants"].get(p, p) for p in record["guests"]
                    ]
                elif k == "routes":
                    for field in ("appetizer_stop_id", "main_stop_id", "dessert_stop_id"):
                        record[field] = mappings["stops"].get(record[field], record[field])
                else:
                    for table in MODELS:
                        record[table] = [
                            mappings[table].get(value, value) for value in record[table]
                        ]
                (DataGroup if k == "groups" else MODELS[k]).model_validate(record)
                trial[k][rid] = record
        decode_snapshot(trial)
        self.state = trial
        self.revision += 1
        self.broadcast()
        self.state_received.emit(deepcopy(trial))
        return mappings

    def release(self, owner):
        self.locks = {node: lock for node, lock in self.locks.items() if lock["owner"] != owner}
        self.broadcast()
        self.locks_changed.emit()

    def client_message(self, message):
        try:
            kind = message.get("type")
            if kind == "state":
                decode_snapshot(message["state"])
                self.state = message["state"]
                self.received_initial = True
                self.revision = message["revision"]
                self.id = message["id"]
                self.locks = message["locks"]
                self.busy = message.get("busy", False)
                self.peer.send({"type": "ack", "revision": self.revision})
                if self.mode == "client":
                    self.state_received.emit(deepcopy(self.state))
                    self.locks_changed.emit()
            elif kind == "ready" and self.mode == "connecting":
                if self.received_initial:
                    self.mode = "client"
                    self.state_received.emit(deepcopy(self.state))
                    self.locks_changed.emit()
                    self.status_changed.emit()
            elif kind == "reply":
                self.responses[message["request"]] = message
                self.reply.emit(message["request"], message)
            elif kind == "end":
                self.disconnect()
        except (ValueError, KeyError, TypeError, AttributeError):
            self.connection_lost()

    def request(self, action, payload=None):
        if self.mode == "host":
            return self.execute("host", action, payload or {})
        if self.mode != "client":
            raise ValueError("Host unreachable...")
        request = uuid4().hex
        loop = QEventLoop()

        def received(rid, _):
            if rid == request:
                loop.quit()

        self.reply.connect(received)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        self.peer.send(
            {"type": "request", "request": request, "action": action, "payload": payload or {}}
        )
        loop.exec()
        self.reply.disconnect(received)
        timer.stop()
        reply = self.responses.pop(request, None)
        if reply is None:
            self.connection_lost()
            raise ValueError("Host unreachable...")
        if not reply["ok"]:
            raise ValueError(reply["error"])
        return reply.get("result")

    def publish(self, data, settings):
        new = snapshot(data, settings)
        payload = {"changes": difference(self.state, new)}
        if self.mode == "host":
            payload["settings"] = new["settings"]
        return self.request("patch", payload)

    def replace(self, data, settings):
        if self.mode != "host" or self.locks:
            raise ValueError("Finish active route edits before replacing the project.")
        state = snapshot(data, settings)
        decode_snapshot(state)
        self.state = state
        self.revision += 1
        self.broadcast()

    def foreign_nodes(self):
        return {node: lock["name"] for node, lock in self.locks.items() if lock["owner"] != self.id}

    def set_busy(self, busy):
        if self.mode == "host":
            self.busy = busy
            self.broadcast()
            self.status_changed.emit()

    def tick(self):
        now = time.monotonic()
        if self.mode == "host":
            for peer in list(self.peers.values()):
                if now - peer.last_seen > self.timeout or (
                    peer.awaiting and now - peer.awaiting > self.timeout
                ):
                    self.remove_peer(peer)
        elif self.peer:
            if now - self.peer.last_seen > self.timeout or (
                self.mode == "connecting" and now - self.connect_started > 5
            ):
                self.connection_lost()
            else:
                self.peer.send({"type": "ping"})

    def connection_lost(self):
        if self.mode not in ("client", "connecting"):
            return
        error = "Connection failed..." if self.mode == "connecting" else "Host unreachable..."
        self.disconnect()
        self.failed.emit(error)

    def disconnect(self):
        self.mode = "offline"
        self.busy = False
        self.server.close()
        peers = list(self.peers.values())
        self.peers.clear()
        for peer in peers:
            peer.send({"type": "end"})
            peer.shutdown(graceful=True)
        peer, self.peer = self.peer, None
        if peer:
            peer.shutdown()
        self.locks.clear()
        self.locks_changed.emit()
        self.status_changed.emit()
