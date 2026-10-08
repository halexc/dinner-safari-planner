"""Verify the installed stack offline without opening a desktop window."""

import os
from importlib.metadata import version
from io import StringIO

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import folium
import geopy.distance
import networkx as nx
import osmnx as ox
import pandas as pd
from ortools.sat.python import cp_model
from pydantic import BaseModel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QTableView, QTabWidget
from shapely.geometry import Point


def main() -> None:
    for package in (
        "cykelfest-routing",
        "PySide6",
        "folium",
        "osmnx",
        "networkx",
        "ortools",
        "pandas",
        "pydantic",
        "geopy",
        "shapely",
        "scipy",
        "scikit-learn",
        "pytest",
        "ruff",
    ):
        print(f"{package}: {version(package)}")

    app = QApplication([])
    tabs = QTabWidget()
    tabs.addTab(QTableView(), "Participants")
    assert tabs.count() == 1
    assert QWebEngineView is not None

    html = folium.Map(location=[59.3293, 18.0686], tiles="OpenStreetMap").get_root().render()
    assert "openstreetmap.org" in html

    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=18.0686, y=59.3293)
    graph.add_node(2, x=18.0696, y=59.3303)
    graph.add_node(3, x=18.0706, y=59.3313)
    graph.add_edge(1, 2, length=100)
    graph.add_edge(2, 3, length=200)
    assert ox.routing.shortest_path(graph, 1, 3, weight="length") == [1, 2, 3]
    assert ox.distance.nearest_nodes(graph, X=18.0686, Y=59.3293) == 1
    projected = ox.projection.project_graph(graph)
    assert (
        ox.distance.nearest_nodes(projected, X=projected.nodes[1]["x"], Y=projected.nodes[1]["y"])
        == 1
    )

    model = cp_model.CpModel()
    assignment = model.new_int_var(0, 2, "course")
    model.add(assignment != 0)
    model.minimize(assignment)
    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    assert solver.value(assignment) == 1

    class Participant(BaseModel):
        id: str
        name: str

    participant = Participant(id="001", name="Alex & Sam")
    frame = pd.DataFrame([participant.model_dump()])
    restored = pd.read_csv(StringIO(frame.to_csv(index=False)), dtype=str)
    assert restored.iloc[0]["id"] == "001"
    assert Point(18.0686, 59.3293).distance(Point(18.0686, 59.3293)) == 0
    assert geopy.distance.geodesic((59.3293, 18.0686), (59.33, 18.07)).meters > 0
    app.quit()
    print("PASS: Qt widgets, WebEngine import, OSM HTML, graph routing, CP-SAT, CSV and validation")


if __name__ == "__main__":
    main()
