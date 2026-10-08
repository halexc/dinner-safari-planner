"""Participant handouts and aggregate straight-line solution distances."""

import csv
from collections import Counter
from itertools import pairwise

from geopy.distance import geodesic


def result_rows(data):
    for participant in data.participants.values():
        row = {"Participant name": participant.name}
        hosting = []
        for title, sid in zip(
            ("Appetizer", "Main Dish", "Dessert"), data.route_stops(participant.id), strict=True
        ):
            stop = data.stops.get(sid)
            host = data.participants.get(stop.host) if stop else None
            row[title] = host.address if host else ""
            if host and host.id == participant.id:
                row[title] = "(H) " + row[title]
                hosting.append(stop)
        # Include everyone attending any course hosted by this pairing, once each.
        attendees = dict.fromkeys(pid for stop in hosting for pid in [stop.host, *stop.guests])
        row["Allergies"] = ", ".join(
            person.allergies.strip().strip(",").strip()
            for pid in attendees
            if (person := data.participants.get(pid))
            and person.allergies.strip().strip(",").strip()
        )
        yield row


def write_results(path, data, delimiter=","):
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Participant name", "Appetizer", "Main Dish", "Dessert", "Allergies"],
            delimiter=delimiter,
        )
        writer.writeheader()
        writer.writerows(result_rows(data))


def solution_summary(data, diagnostics):
    legs, totals = [], []
    for pid in data.participants:
        if data.route_for(pid) is None:
            continue
        points = data.coordinates(pid)
        route_legs = [
            geodesic(a, b).km for a, b in pairwise(points) if a is not None and b is not None
        ]
        legs.extend(route_legs)
        # Incomplete/unlocated routes must not lower the total-distance statistics.
        if all(point is not None for point in points):
            totals.append(sum(route_legs))
    return {
        "Average total distance": sum(totals) / len(totals) if totals else None,
        "Shortest leg": min(legs, default=None),
        "Shortest total distance": min(totals, default=None),
        "Longest leg": max(legs, default=None),
        "Longest total length": max(totals, default=None),
        "warnings": Counter(
            message for result in diagnostics.values() for message in result.get("warnings", [])
        ),
        "errors": Counter(
            message for result in diagnostics.values() for message in result.get("errors", [])
        ),
    }
