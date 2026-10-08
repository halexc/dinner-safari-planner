"""Isolated manual route drafts and the map's Qt bridge."""

import json
from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot

from .data import COURSES, STOP_FIELDS, DinnerData, Stop, next_record_id


class RouteDraft:
    def __init__(self, data: DinnerData, participant_id: str, *, safe_edit=True):
        data.ensure_routes()
        self.safe_edit = safe_edit
        self.participant_id = participant_id
        self.session = uuid4().hex
        self.original = data.route_stops(participant_id)[:]
        self.data = deepcopy(data)
        self.data.create_route(participant_id)
        self.original_routes = {pid: data.route_stops(pid)[:] for pid in data.participants}
        self.original_route_ids = {pid: p.route_id for pid, p in data.participants.items()}

    @property
    def stops(self):
        return self.data.route_stops(self.participant_id)

    @property
    def changed(self):
        return any(
            self.data.route_stops(pid) != self.original_routes[pid]
            for pid in self.data.participants
        )

    @property
    def next_course(self):
        return next((index for index, sid in enumerate(self.stops) if not sid), None)

    def host_at(self, index):
        stop = self.data.stops.get(self.stops[index])
        return stop.host if stop else None

    def candidate(self, host_id: str, index: int, data=None):
        data = data or self.data
        host = data.participants.get(host_id)
        if not host:
            return None
        assigned = data.stops.get(data.route_stops(host_id)[index])
        if assigned and assigned.host == host_id and assigned.course == COURSES[index]:
            return assigned
        return next(
            (s for s in data.stops.values() if s.host == host_id and s.course == COURSES[index]),
            None,
        )

    def eligible(self, host_id: str, index: int, data=None):
        data = data or self.data
        host = data.participants.get(host_id)
        if not host:
            return False
        if not self.safe_edit:
            return True
        candidate = self.candidate(host_id, index, data)
        assigned = data.route_stops(host_id)[index]
        return not assigned or (candidate is not None and assigned == candidate.id)

    def assign_host(self, data, host_id, index):
        if not self.eligible(host_id, index, data):
            raise ValueError(f"That host is away during {COURSES[index]}.")
        stop = self.candidate(host_id, index, data)
        if stop is None:
            sid = next_record_id(data.stops, "S")
            stop = Stop(id=sid, host=host_id, course=COURSES[index])
            data.stops[sid] = stop
        stops = data.route_stops(self.participant_id)
        stops[index] = stop.id
        data.assign_route(self.participant_id, stops)

    def restore_host_routes(self, data):
        # Automatic host reservations belong to the final draft, not abandoned sections.
        for pid, stops in self.original_routes.items():
            if pid != self.participant_id:
                if not self.original_route_ids[pid]:
                    # Drop only our automatic reservation. Imported guest lists
                    # may contain unrelated entries even before routes exist.
                    participant = data.participants[pid]
                    data.routes.pop(participant.route_id, None)
                    participant.route_id = ""
                    continue
                for field, sid in zip(STOP_FIELDS, stops, strict=True):
                    setattr(data.route_for(pid), field, sid)

    def synchronize_hosts(self, data):
        self.restore_host_routes(data)
        for index, sid in enumerate(data.route_stops(self.participant_id)):
            stop = data.stops.get(sid)
            if stop:
                host = data.participants.get(stop.host)
                if host and not data.route_stops(host.id)[index]:
                    setattr(data.create_route(host.id), STOP_FIELDS[index], sid)

    def click(self, host_id):
        index = self.next_course
        if index is None:
            raise ValueError("All courses are assigned. Drag a section to remake the route.")
        trial = deepcopy(self.data)
        self.restore_host_routes(trial)
        self.assign_host(trial, host_id, index)
        self.synchronize_hosts(trial)
        self.data = trial

    def replace(self, index, host_id):
        """Replace one course, retaining other assignments and draft isolation."""
        if index not in range(3):
            raise ValueError("Unknown course.")
        trial = deepcopy(self.data)
        self.restore_host_routes(trial)
        self.assign_host(trial, host_id, index)
        self.synchronize_hosts(trial)
        self.data = trial

    def replace_stop(self, index, stop_id):
        """Assign an exact stop selected in the Routes table."""
        if not stop_id:
            self.remove(index)
            return
        trial = deepcopy(self.data)
        self.restore_host_routes(trial)
        stop = trial.stops.get(stop_id)
        if not stop or stop.course != COURSES[index]:
            raise ValueError(f"Select an existing {COURSES[index]} stop.")
        host = trial.participants.get(stop.host)
        if self.safe_edit and (not host or trial.route_stops(host.id)[index] not in ("", stop_id)):
            raise ValueError(f"That host is away during {COURSES[index]}.")
        stops = trial.route_stops(self.participant_id)
        stops[index] = stop_id
        trial.assign_route(self.participant_id, stops)
        self.synchronize_hosts(trial)
        self.data = trial

    def choices(self, index):
        trial = deepcopy(self.data)
        self.restore_host_routes(trial)
        return [
            (host, self.candidate(host.id, index, trial))
            for host in trial.participants.values()
            if self.eligible(host.id, index, trial)
        ]

    def draw(self, start_host, end_host):
        trial = deepcopy(self.data)
        self.restore_host_routes(trial)
        if start_host == self.host_at(1) and self.stops[1]:
            self.assign_host(trial, end_host, 2)
        else:
            trial.assign_route(self.participant_id, ["", "", ""])
            self.assign_host(trial, start_host, 0)
            self.assign_host(trial, end_host, 1)
        self.synchronize_hosts(trial)
        self.data = trial

    def remove(self, index: int):
        if index not in range(3):
            raise ValueError("Unknown course.")
        trial = deepcopy(self.data)
        stops = self.stops[:]
        stops[index] = ""
        trial.assign_route(self.participant_id, stops)
        self.synchronize_hosts(trial)
        self.data = trial

    def commit(self, target: DinnerData):
        # Only save stops still referenced by the final draft; abandoned gestures leave no records.
        for sid in self.stops:
            if sid and sid not in target.stops:
                target.stops[sid] = self.data.stops[sid].model_copy(deep=True)
        target.assign_route(self.participant_id, self.stops)
        for index, sid in enumerate(self.stops):
            stop = target.stops.get(sid)
            host = target.participants.get(stop.host) if stop else None
            if host and not target.route_stops(host.id)[index]:
                setattr(target.create_route(host.id), STOP_FIELDS[index], sid)

    def payload(self):
        from .map_view import host_outlines

        index = self.next_course
        hosts = []
        outlines = host_outlines(self.data)
        for host in self.data.participants.values():
            if host.latitude is None:
                continue
            counts = []
            for course in range(3):
                stop = self.candidate(host.id, course)
                counts.append(len(set(stop.guests)) if stop else 0)
            hosts.append(
                {
                    "id": host.id,
                    "name": host.name,
                    "lat": host.latitude,
                    "lon": host.longitude,
                    "own": host.id == self.participant_id,
                    "eligible": [self.eligible(host.id, course) for course in range(3)],
                    "guests": counts,
                    "outline": outlines[host.id],
                }
            )
        return {
            "session": self.session,
            "next": index,
            "hosts": hosts,
            "route": [self.host_at(course) for course in range(3)],
            "coordinates": self.data.coordinates(self.participant_id),
        }


class MapBridge(QObject):
    stateChanged = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @Slot(str, str)
    def clickHost(self, session, host_id):
        self.window.map_gesture(session, host_id)

    @Slot(str, str, str)
    def drawSection(self, session, start, end):
        self.window.map_gesture(session, start, end)

    @Slot(str, int)
    def removeStop(self, session, index):
        self.window.remove_map_stop(session, index)

    @Slot(str)
    def selectRoute(self, participant_id):
        self.window.select_map_route(participant_id)

    def publish(self, draft):
        self.stateChanged.emit(json.dumps(draft.payload()))
