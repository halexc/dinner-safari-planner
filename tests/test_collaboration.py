import os
import time
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from cykelfest_routing.collaboration import (
    CollaborationSession,
    decode_snapshot,
    difference,
    snapshot,
)
from cykelfest_routing.data import DataGroup, Participant, demo_data
from cykelfest_routing.gui import MainWindow
from cykelfest_routing.project import ProjectSettings


def wait_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.001)
    assert predicate()


@pytest.fixture
def sessions():
    app = QApplication.instance() or QApplication([])
    host, first, second = (CollaborationSession() for _ in range(3))
    host.host("Host", demo_data(), ProjectSettings(), port=0)
    address = f"127.0.0.1:{host.server.serverPort()}"
    first.connect("First", address)
    second.connect("Second", address)
    wait_until(
        lambda: first.mode == second.mode == "client" and all(p.ready for p in host.peers.values())
    )
    yield host, first, second
    for session in (first, second, host):
        session.disconnect()
        session.timer.stop()
        session.deleteLater()
    QApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert app is not None


def test_snapshot_client_edit_and_host_settings_propagate(sessions):
    host, first, second = sessions
    assert first.state == second.state == host.state
    data, settings = decode_snapshot(first.state)
    data.participants["P001"].name = "Changed remotely"
    first.publish(data, settings)
    wait_until(lambda: second.state == first.state == host.state)
    assert host.state["participants"]["P001"]["name"] == "Changed remotely"
    data, settings = decode_snapshot(host.state)
    settings.minimum_segment_km = 0.75
    host.publish(data, settings)
    wait_until(lambda: second.state["settings"]["minimum_segment_km"] == 0.75)


def test_multimodal_groups_propagate_and_remap_new_members(sessions):
    host, first, second = sessions
    data, settings = decode_snapshot(first.state)
    data.participants["P-00009"] = Participant(id="P-00009", name="New member")
    data.groups["new-group"] = DataGroup(
        id="new-group",
        name="Friends",
        color="#abcdef",
        participants=["P-00009"],
        stops=["S002"],
        routes=["R-00001"],
    )
    first.publish(data, settings)
    wait_until(lambda: second.state == host.state == first.state)
    group = host.state["groups"]["new-group"]
    assert group["participants"] == ["P-00001"]
    assert group["stops"] == ["S002"] and group["routes"] == ["R-00001"]
    data, settings = decode_snapshot(second.state)
    data.groups["new-group"].name = "Renamed"
    second.publish(data, settings)
    wait_until(lambda: first.state["groups"]["new-group"]["name"] == "Renamed")


def test_locks_stale_edits_and_host_permissions(sessions):
    host, first, second = sessions
    first.request("lock", {"nodes": ["P001"]})
    wait_until(lambda: "P001" in second.foreign_nodes())
    with pytest.raises(ValueError, match="another collaborator"):
        second.request("lock", {"nodes": ["P001", "P002"]})
    assert "P002" not in host.locks  # Failed acquisition is atomic.
    data, settings = decode_snapshot(second.state)
    data.participants["P001"].name = "Forbidden"
    with pytest.raises(ValueError, match="another collaborator"):
        second.publish(data, settings)
    with pytest.raises(ValueError, match="Only the host"):
        first.request(
            "patch",
            {
                "changes": difference(first.state, first.state),
                "settings": settings.model_dump(mode="json"),
            },
        )
    baseline = deepcopy(first.state)
    first.request("release")
    data, settings = decode_snapshot(first.state)
    data.participants["P001"].name = "Accepted"
    first.publish(data, settings)
    stale = deepcopy(baseline)
    stale["participants"]["P001"]["name"] = "Old edit"
    with pytest.raises(ValueError, match="record changed"):
        second.request("patch", {"changes": difference(baseline, stale)})
    assert host.state["participants"]["P001"]["name"] == "Accepted"


def test_host_allocates_ids_and_preserves_unrelated_concurrent_records(sessions):
    host, first, second = sessions
    baseline = deepcopy(first.state)
    proposed = deepcopy(baseline)
    proposed["participants"]["P-00001"] = Participant(id="P-00001", name="One").model_dump()
    first.request("patch", {"changes": difference(baseline, proposed)})
    proposed["participants"]["P-00001"]["name"] = "Two"
    second.request("patch", {"changes": difference(baseline, proposed)})
    assert host.state["participants"]["P-00001"]["name"] == "One"
    assert host.state["participants"]["P-00002"]["name"] == "Two"


def test_duplicate_request_is_applied_once(sessions):
    host, first, _second = sessions
    state = deepcopy(host.state)
    state["participants"]["P001"]["name"] = "Once"
    message = {
        "type": "request",
        "request": "same-operation",
        "action": "patch",
        "payload": {"changes": difference(host.state, state)},
    }
    revision = host.revision
    peer = host.peers[first.id]
    host.host_message(peer, message)
    host.host_message(peer, message)
    assert host.revision == revision + 1
    assert host.state["participants"]["P001"]["name"] == "Once"


def test_ack_timeout_removes_peer_and_releases_locks(sessions):
    host, first, _second = sessions
    first.request("lock", {"nodes": ["P001"]})
    peer = host.peers[first.id]
    peer.awaiting = time.monotonic() - 30
    host.tick()
    assert first.id not in host.peers and "P001" not in host.locks
    wait_until(lambda: first.mode == "offline")
    assert first.state["participants"]  # Last confirmed context survives.


def test_busy_host_blocks_client_mutations(sessions):
    host, first, _ = sessions
    host.set_busy(True)
    with pytest.raises(ValueError, match="project-wide"):
        first.request("lock", {"nodes": ["P001"]})
    host.set_busy(False)
    first.request("lock", {"nodes": ["P001"]})


def test_connection_failure_and_host_stop_keep_confirmed_context(sessions):
    host, first, second = sessions
    before = deepcopy(first.state)
    host.disconnect()
    wait_until(lambda: first.mode == second.mode == "offline")
    assert first.state == before
    failed = []
    first.failed.connect(failed.append)
    first.connect("First", "invalid:port")
    assert failed == ["Connection failed..."] and first.state == before


def test_real_connection_refusal_keeps_context(sessions):
    host, first, _second = sessions
    before = deepcopy(first.state)
    port = host.server.serverPort()
    first.disconnect()
    host.disconnect()
    errors = []
    first.failed.connect(errors.append)
    first.connect("First", f"127.0.0.1:{port}")
    wait_until(lambda: first.mode == "offline", timeout=8)
    assert errors == ["Connection failed..."] and first.state == before


def test_framing_and_unregistered_connection_cannot_edit(sessions):
    import json
    import struct

    from PySide6.QtNetwork import QTcpSocket

    host, _first, _second = sessions
    socket = QTcpSocket()
    socket.connectToHost("127.0.0.1", host.server.serverPort())
    wait_until(lambda: len(host.peers) == 3)
    before = deepcopy(host.state)
    raw = json.dumps(
        {"type": "request", "request": "unregistered", "action": "patch", "payload": {}}
    ).encode()
    frame = struct.pack("!I", len(raw)) + raw
    socket.write(frame[:2])
    QApplication.processEvents()
    assert host.state == before
    socket.write(frame[2:])
    wait_until(lambda: socket.bytesToWrite() == 0)
    QApplication.processEvents()
    assert host.state == before
    socket.write(struct.pack("!I", 100 * 1024 * 1024))
    wait_until(lambda: len(host.peers) == 2)
    socket.abort()


def test_gui_permissions_drafts_and_disconnect(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    host, client = [
        MainWindow(
            demo_data() if i == 0 else None,
            enable_map=False,
            preferences=QSettings(str(tmp_path / f"{i}.ini"), QSettings.IniFormat),
        )
        for i in range(2)
    ]
    try:
        host.collaboration.host("Host", host.data, host.project_settings(), port=0)
        client.collaboration.connect(
            "Client", f"127.0.0.1:{host.collaboration.server.serverPort()}"
        )
        wait_until(lambda: client.collaboration.mode == "client" and client.data.participants)
        assert not client.new_project_button.isEnabled()
        assert not client.minimum_segment.isEnabled()
        assert client.save_project_button.isEnabled()
        assert not client.export_results_button.isEnabled()
        assert not any(control.isEnabled() for control in client.host_only_controls)
        host.minimum_segment.setValue(0.75)
        wait_until(lambda: client.minimum_segment.value() == 0.75)
        assert not client.minimum_segment.isEnabled()
        # Add an unrelated record before drafting; its incoming edit must survive Save.
        host.data.participants["P004"] = Participant(id="P004", name="Unrelated")
        host.changed()
        wait_until(lambda: "P-00001" in client.data.participants)
        extra_id = "P-00001"
        client.refresh("P001")
        client.edit_route()
        assert client.draft is not None
        before = snapshot(host.data, host.project_settings())
        client.remove_map_stop(client.draft.session, 2)
        assert snapshot(host.data, host.project_settings()) == before
        session = client.draft.session
        host.data.participants[extra_id].name = "Updated during draft"
        host.changed()
        wait_until(lambda: client.data.participants[extra_id].name == "Updated during draft")
        assert client.draft.session == session and client.draft.stops[2] == ""
        wait_until(lambda: "P001" in host.collaboration.foreign_nodes())
        client.save_route()
        wait_until(lambda: host.data.route_stops("P001")[2] == "")
        assert not host.collaboration.locks
        assert host.data.participants[extra_id].name == "Updated during draft"
        assert host.data.participants["P001"].name == client.data.participants["P001"].name
        retained = client.data_snapshot()
        client.collaboration.disconnect()
        assert client.new_project_button.isEnabled() and client.minimum_segment.isEnabled()
        assert client.data_snapshot() == retained
    finally:
        for window in (client, host):
            window.collaboration.disconnect()
            window.draft = None
            window.dirty = False
            window.close()
    assert app is not None
