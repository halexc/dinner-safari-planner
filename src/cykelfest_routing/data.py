"""GUI data and transactional CSV exchange, independent of Qt."""

import csv
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

COURSES = ("Appetizer", "Main dish", "Dessert")
STOP_FIELDS = ("appetizer_stop_id", "main_stop_id", "dessert_stop_id")


def next_record_id(records, prefix):
    """Generate a collision-free five-digit ID while preserving imported IDs."""
    numbers = [int(rid[2:]) for rid in records if re.fullmatch(rf"{prefix}-\d{{5}}", rid)]
    number = max(numbers, default=0) + 1
    if number > 99999:
        raise ValueError(f"No {prefix}-XXXXX IDs remain available.")
    return f"{prefix}-{number:05d}"


class Participant(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    address: str = ""
    allergies: str = ""
    route_id: str = ""
    _legacy_stops: list[str] | None = PrivateAttr(default=None)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or leave both empty.")
        return self


class Stop(BaseModel):
    id: str = Field(min_length=1)
    host: str = ""
    guests: list[str] = Field(default_factory=list)
    course: Literal["Appetizer", "Main dish", "Dessert"] = "Appetizer"


class Route(BaseModel):
    id: str = Field(pattern=r"^R-[0-9]{5}$")
    appetizer_stop_id: str = ""
    main_stop_id: str = ""
    dessert_stop_id: str = ""

    @property
    def stops(self) -> list[str]:
        return [getattr(self, field) for field in STOP_FIELDS]

    @property
    def has_route(self) -> bool:
        return any(self.stops)


MODELS = {"participants": Participant, "stops": Stop, "routes": Route}
CSV_REQUIRED = {"participants": {"name"}, "stops": set(), "routes": set()}


@dataclass
class CSVSource:
    headers: list[str]
    rows: list[tuple[int, list[str]]]


def csv_source(path, delimiter=","):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        try:
            headers = next(reader, None)
            if not headers:
                raise ValueError("The CSV file has no header row.")
            rows = []
            for row in reader:
                if not row:
                    continue
                rows.append((reader.line_num, row))
        except csv.Error as error:
            raise ValueError(f"CSV row {reader.line_num}: {error}") from error
    return CSVSource(headers, rows)


def infer_csv_mapping(source, kind):
    """Return unambiguous recognized header mappings and whether review is needed."""
    fields = list(MODELS[kind].model_fields)
    if kind == "participants":
        fields += list(STOP_FIELDS)  # Preserve legacy participant imports.
    aliases = {re.sub(r"[^a-z0-9]", "", field): field for field in fields}
    aliases.update(
        {
            "namepairing": "name",
            "pairing": "name",
            "route": "route_id",
            "appetizer": "appetizer_stop_id",
            "maindish": "main_stop_id",
            "maincourse": "main_stop_id",
            "dessert": "dessert_stop_id",
        }
    )
    matches = {field: [] for field in fields}
    unknown = False
    for column, title in enumerate(source.headers):
        field = aliases.get(re.sub(r"[^a-z0-9]", "", title.strip().casefold()))
        if field in matches:
            matches[field].append(column)
        else:
            unknown = True
    mapping = {field: columns[0] for field, columns in matches.items() if len(columns) == 1}
    ambiguous = any(len(columns) > 1 for columns in matches.values())
    malformed = any(len(row) != len(source.headers) for _, row in source.rows)
    review = (
        unknown or ambiguous or malformed or not CSV_REQUIRED[kind].issubset(mapping) or not mapping
    )
    return mapping, review


def read_csv(path: str | Path, kind: str, delimiter: str = ",", *, mapping=None) -> dict:
    return parse_csv(csv_source(path, delimiter), kind, mapping=mapping)


def parse_csv(source, kind, *, mapping=None):
    model = MODELS[kind]
    result = {}
    if mapping is None:
        mapping, review = infer_csv_mapping(source, kind)
        if review:
            raise ValueError(
                "CSV columns need mapping. Import through the GUI to select the source columns."
            )
    fields = set(model.model_fields) | (set(STOP_FIELDS) if kind == "participants" else set())
    selected = {field: column for field, column in mapping.items() if column is not None}
    if not CSV_REQUIRED[kind].issubset(selected):
        raise ValueError("Select a CSV column for Name / pairing.")
    if any(
        field not in fields or type(column) is not int or not 0 <= column < len(source.headers)
        for field, column in selected.items()
    ):
        raise ValueError("Invalid CSV column mapping.")
    if len(set(selected.values())) != len(selected):
        raise ValueError("Each CSV column can be mapped to only one data column.")
    for line, row in source.rows:
        if len(row) != len(source.headers):
            raise ValueError(
                f"CSV row {line}: expected {len(source.headers)} columns, found {len(row)}. Check the delimiter and quoting."
            )
    reserved = {}
    id_column = selected.get("id")
    if id_column is not None:
        for line, row in source.rows:
            rid = row[id_column].strip()
            if rid:
                if rid in reserved:
                    raise ValueError(f"CSV row {line}: Duplicate ID: {rid}")
                reserved[rid] = None
    for line, row in source.rows:
        try:
            mapped = {field: row[column].strip() for field, column in selected.items()}
            values = {
                field: value for field, value in mapped.items() if field in model.model_fields
            }
            if not values.get("id"):
                values["id"] = next_record_id(
                    reserved, {"participants": "P", "stops": "S", "routes": "R"}[kind]
                )
                reserved[values["id"]] = None
            if kind == "participants":
                for field in ("latitude", "longitude"):
                    if not values.get(field):
                        values[field] = None
            elif kind == "stops":
                values["guests"] = json.loads(values.get("guests") or "[]")
                if not values.get("course"):
                    values.pop("course", None)
            record = model(**values)
            if kind == "participants" and any(field in mapped for field in STOP_FIELDS):
                record._legacy_stops = [mapped.get(field, "") for field in STOP_FIELDS]
            result[record.id] = record
        except (ValueError, TypeError) as error:
            raise ValueError(f"CSV row {line}: {error}") from error
    return result


def write_csv(path: str | Path, records: dict, kind: str, delimiter: str = ",") -> None:
    model = MODELS[kind]
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(model.model_fields), delimiter=delimiter)
        writer.writeheader()
        for record in records.values():
            row = record.model_dump()
            if kind == "stops":
                row["guests"] = json.dumps(row["guests"], ensure_ascii=False)
            writer.writerow(row)


class DinnerData:
    def __init__(self):
        self.participants: dict[str, Participant] = {}
        self.stops: dict[str, Stop] = {}
        self.routes: dict[str, Route] = {}

    def ensure_routes(self):
        """Maintain distinct explicit route links and migrate legacy assignments."""
        claimed = [p.route_id for p in self.participants.values() if p.route_id]
        if len(claimed) != len(set(claimed)):
            raise ValueError("Each participant must reference a different route ID.")
        reserved = dict.fromkeys([*self.routes, *claimed])
        for participant in self.participants.values():
            if not participant.route_id and participant._legacy_stops is not None:
                participant.route_id = next_record_id(reserved, "R")
                reserved[participant.route_id] = None
            if not participant.route_id:
                continue
            if participant.route_id not in self.routes:
                self.routes[participant.route_id] = Route(id=participant.route_id)
            if participant._legacy_stops is not None:
                for field, sid in zip(STOP_FIELDS, participant._legacy_stops, strict=True):
                    setattr(self.routes[participant.route_id], field, sid)
                participant._legacy_stops = None
        linked = {p.route_id for p in self.participants.values()}
        self.routes = {rid: route for rid, route in self.routes.items() if rid in linked}

    def route_for(self, participant_id):
        """Read an existing route without implicitly creating one."""
        return self.routes.get(self.participants[participant_id].route_id)

    def route_stops(self, participant_id):
        route = self.route_for(participant_id)
        return route.stops if route else ["", "", ""]

    def create_route(self, participant_id):
        route = self.route_for(participant_id)
        if route is None:
            route = Route(id=next_record_id(self.routes, "R"))
            self.routes[route.id] = route
            self.participants[participant_id].route_id = route.id
        return route

    def remove_route(self, participant_id):
        participant = self.participants[participant_id]
        self.routes.pop(participant.route_id, None)
        participant.route_id = ""
        for stop in self.stops.values():
            stop.guests = [guest for guest in stop.guests if guest != participant_id]

    def clear_routes(self):
        for pid in self.participants:
            self.remove_route(pid)
        self.routes.clear()

    def participant_for_route(self, route_id):
        return next((p for p in self.participants.values() if p.route_id == route_id), None)

    def delete_records(self, kind, record_ids):
        """Delete a batch and clear references, preserving stops used by other routes."""
        record_ids = set(record_ids) & getattr(self, kind).keys()
        removed_routes = set(record_ids) if kind == "routes" else set()
        removed_stops = set(record_ids) if kind == "stops" else set()
        if kind == "participants":
            removed_routes.update(
                p.route_id
                for pid, p in self.participants.items()
                if pid in record_ids and p.route_id
            )
            for stop in self.stops.values():
                affected = stop.host in record_ids or bool(record_ids.intersection(stop.guests))
                if stop.host in record_ids:
                    stop.host = ""
                stop.guests = [pid for pid in stop.guests if pid not in record_ids]
                if affected and not stop.host and not stop.guests:
                    removed_stops.add(stop.id)
            for pid in record_ids:
                del self.participants[pid]
        route_stops = {
            sid
            for rid in removed_routes
            if (route := self.routes.get(rid)) is not None
            for sid in route.stops
            if sid
        }
        owners = {p.id for p in self.participants.values() if p.route_id in removed_routes}
        for p in self.participants.values():
            if p.route_id in removed_routes:
                p.route_id = ""
        for rid in removed_routes:
            self.routes.pop(rid, None)
        still_used = {sid for route in self.routes.values() for sid in route.stops if sid}
        removed_stops.update(route_stops - still_used)
        for stop in self.stops.values():
            stop.guests = [pid for pid in stop.guests if pid not in owners]
        for sid in removed_stops:
            self.stops.pop(sid, None)
        for route in self.routes.values():
            for field in STOP_FIELDS:
                if getattr(route, field) in removed_stops:
                    setattr(route, field, "")

    def replace_table(self, kind, records):
        """Validate a CSV replacement before changing the live workspace."""
        trial = deepcopy(self)
        setattr(trial, kind, deepcopy(records))
        if kind == "routes":
            linked = {p.route_id for p in trial.participants.values() if p.route_id}
            if set(records) != linked:
                raise ValueError(
                    "Routes CSV must contain exactly the Route IDs linked by Participants. Import Participants first."
                )
        trial.ensure_routes()
        if kind == "routes":
            for pid in trial.participants:
                if trial.route_for(pid) is None:
                    continue
                trial.assign_route(pid, trial.route_for(pid).stops)
        self.participants, self.routes, self.stops = trial.participants, trial.routes, trial.stops

    def assign_route(self, participant_id: str, stop_ids: list[str]) -> None:
        """Update both references and guest membership together."""
        if len(stop_ids) != 3:
            raise ValueError("A route must contain exactly three course references.")
        route = self.create_route(participant_id)
        for stop in self.stops.values():
            stop.guests = [guest for guest in stop.guests if guest != participant_id]
        for field, stop_id in zip(STOP_FIELDS, stop_ids, strict=True):
            setattr(route, field, stop_id)
            stop = self.stops.get(stop_id)
            if stop and stop.host != participant_id:
                stop.guests.append(participant_id)

    def issues(self, participant_id: str) -> list[str]:
        issues = []
        seen = set()
        for course, stop_id in zip(COURSES, self.route_stops(participant_id), strict=True):
            stop = self.stops.get(stop_id)
            if not stop:
                issues.append(
                    f"{course}: {'unknown stop ' + stop_id if stop_id else 'no stop assigned'}"
                )
                continue
            if stop_id in seen:
                issues.append(f"Stop {stop_id} visited more than once")
            seen.add(stop_id)
            if stop.course != course:
                issues.append(f"{course}: {stop_id} is a {stop.course} stop")
            if stop.host not in self.participants:
                issues.append(f"{stop_id}: unknown host {stop.host}")
            if participant_id != stop.host and participant_id not in stop.guests:
                issues.append(f"{stop_id}: pairing is absent from the guest list")
            if len(stop.guests) != len(set(stop.guests)):
                issues.append(f"{stop_id}: duplicate guest IDs")
            if stop.host in stop.guests:
                issues.append(f"{stop_id}: host also listed as a guest")
            unknown = set(stop.guests) - self.participants.keys()
            if unknown:
                issues.append(f"{stop_id}: unknown guests {', '.join(sorted(unknown))}")
        for stop in self.stops.values():
            if (
                participant_id in stop.guests or stop.host == participant_id
            ) and stop.id not in seen:
                issues.append(f"{stop.id}: attendance is missing from this route")
        return issues

    def coordinates(self, participant_id: str) -> list[tuple[float, float] | None]:
        points = []
        for stop_id in self.route_stops(participant_id):
            stop = self.stops.get(stop_id)
            host = self.participants.get(stop.host) if stop else None
            points.append(
                (host.latitude, host.longitude) if host and host.latitude is not None else None
            )
        return points


def demo_data() -> DinnerData:
    data = DinnerData()
    for number, (name, address, lat, lon) in enumerate(
        [
            ("Alex & Sam", "Example host A, Stockholm", 59.3293, 18.0686),
            ("Robin & Kim", "Example host B, Stockholm", 59.3370, 18.0500),
            ("Charlie & Dani", "Example host C, Stockholm", 59.3150, 18.0750),
        ],
        1,
    ):
        pid = f"P{number:03}"
        data.participants[pid] = Participant(
            id=pid, name=name, address=address, latitude=lat, longitude=lon
        )
        sid = f"S{number:03}"
        data.stops[sid] = Stop(id=sid, host=pid, course=COURSES[number - 1])
    for pid in data.participants:
        data.assign_route(pid, list(data.stops))
    return data
