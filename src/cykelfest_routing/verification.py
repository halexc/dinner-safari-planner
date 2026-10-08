"""Route diagnostics and shared distance preferences for automatic assignment."""

import json
from dataclasses import dataclass
from itertools import combinations, pairwise

from geopy.distance import geodesic

from .data import COURSES

WARNING_TYPES = (
    "Route contains stops with few guests.",
    "Route contains stops with many guests.",
    "Short Route segment.",
    "Long Route segment.",
    "Participant is not hosting.",
    "Participant is repeat host.",
    "Participant is not assigned all 3 stops.",
    "Repeat meetups.",
)


@dataclass
class SegmentPreferences:
    minimum_km: float = 0.5
    maximum_km: float = 3.0


def route_signature(data, pid, preferences, ignored_warnings=()):
    stops = []
    for sid in data.route_stops(pid):
        stop = data.stops.get(sid)
        host = data.participants.get(stop.host) if stop else None
        stops.append(
            [
                stop.model_dump() if stop else None,
                [host.latitude, host.longitude, data.route_stops(host.id)] if host else None,
            ]
        )
    return json.dumps(
        [
            data.route_stops(pid),
            stops,
            preferences.minimum_km,
            preferences.maximum_km,
            sorted(ignored_warnings),
        ],
        sort_keys=True,
    )


def verify_route(data, pid, preferences, ignored_warnings=()):
    route = data.route_for(pid)
    if route is None:
        return {"warnings": [], "errors": []}
    stops = [data.stops.get(sid) for sid in route.stops]
    warnings, errors = [], []
    if not route.has_route:
        errors.append("Empty route.")
    if any(stop and len(stop.guests) < 2 for stop in stops):
        warnings.append("Route contains stops with few guests.")
    if any(stop and len(stop.guests) > 2 for stop in stops):
        warnings.append("Route contains stops with many guests.")
    lengths = [
        geodesic(a, b).km
        for a, b in pairwise(data.coordinates(pid))
        if a is not None and b is not None
    ]
    if any(length < preferences.minimum_km for length in lengths):
        warnings.append("Short Route segment.")
    if any(length > preferences.maximum_km for length in lengths):
        warnings.append("Long Route segment.")
    if any(length > 3 * preferences.maximum_km for length in lengths):
        errors.append("Route segment exceeds hard maximum distance.")
    hosting = sum(stop is not None and stop.host == pid for stop in stops)
    if hosting == 0:
        warnings.append("Participant is not hosting.")
    if hosting > 1:
        warnings.append("Participant is repeat host.")
    if any(stop is None for stop in stops):
        warnings.append("Participant is not assigned all 3 stops.")
    distinct_stops = {stop.id: stop for stop in stops if stop is not None}
    attendees = [
        ({stop.host, *stop.guests} & data.participants.keys()) for stop in distinct_stops.values()
    ]
    if any(len(first & second) >= 2 for first, second in combinations(attendees, 2)):
        warnings.append("Repeat meetups.")
    if any(
        (stop is not None and stop.host not in data.participants) or (sid and stop is None)
        for sid, stop in zip(route.stops, stops, strict=True)
    ):
        errors.append("Route contains stop(s) without a host.")
    if any(
        (host := data.participants.get(stop.host)) is not None
        and (assigned := data.route_stops(host.id)[COURSES.index(stop.course)])
        and assigned != stop.id
        for stop in stops
        if stop is not None
    ):
        errors.append("Host already assigned to other stop.")
    return {
        "warnings": [warning for warning in warnings if warning not in ignored_warnings],
        "errors": errors,
    }
