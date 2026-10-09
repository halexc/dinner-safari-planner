"""OSM preview generation. Lines are illustrative, not calculated cycling paths."""

import json
from html import escape
from itertools import pairwise
from pathlib import Path

import folium

from .data import COURSES, DinnerData
from .localization import tr, translate_html
from .theme import map_css

COLORS = ("#187f71", "#e99b33", "#8158b5", "#267ac0", "#d36579")
STOP_OUTLINES = {
    "Appetizer": "#f2d428",
    "Main dish": "#1acb55",
    "Dessert": "#2e8ad5",
    "No course": "#636363",
    "Multiple courses": "#dc3545",
}


def host_outlines(data):
    """One marker represents a hosting address, possibly used for several courses."""
    courses = {pid: set() for pid in data.participants}
    assigned = {sid for route in data.routes.values() for sid in route.stops if sid}
    for sid in assigned:
        stop = data.stops.get(sid)
        if stop and stop.host in courses and stop.course in COURSES:
            courses[stop.host].add(stop.course)
    return {
        pid: STOP_OUTLINES[
            next(iter(values))
            if len(values) == 1
            else "Multiple courses"
            if values
            else "No course"
        ]
        for pid, values in courses.items()
    }


def host_group_colors(data):
    """The first listed group determines an address's optional outer outline."""
    colors = {}
    for group in data.groups.values():
        hosts = set(group.participants)
        stops = set(group.stops)
        for rid in group.routes:
            if rid in data.routes:
                stops.update(data.routes[rid].stops)
        hosts.update(data.stops[sid].host for sid in stops if sid in data.stops)
        for pid in hosts:
            colors.setdefault(pid, group.color)
    return colors


OSM_ATTRIBUTION = (
    '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'
)
MAP_STYLES = {
    "standard": (
        "OpenStreetMap Standard",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        OSM_ATTRIBUTION,
    ),
    "positron": (
        "CARTO Positron (Light)",
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        OSM_ATTRIBUTION + ' · <a href="https://carto.com/attributions">CARTO</a>',
    ),
    "dark_matter": (
        "CARTO Dark Matter (Dark)",
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        OSM_ATTRIBUTION + ' · <a href="https://carto.com/attributions">CARTO</a>',
    ),
}


def safe_text(value: str) -> str:
    """Escape HTML and template-literal delimiters used by Folium's generated JS."""
    return escape(value).replace("`", "&#96;").replace("$", "&#36;").replace("\\", "&#92;")


def map_html(
    data: DinnerData,
    selected: str | None,
    mode: str,
    show_hosts: bool,
    draft=None,
    dark=False,
    map_style="standard",
    focus_route=False,
    locked_hosts=None,
    color_by_groups=False,
    group_colors=None,
) -> str:
    locked_hosts = locked_hosts or {}
    points = [
        (p.latitude, p.longitude) for p in data.participants.values() if p.latitude is not None
    ]
    map_ = folium.Map(
        location=points[0] if points else [59.3293, 18.0686],
        zoom_start=12,
        tiles=None,
        control_scale=True,
    )
    title, tiles, attribution = MAP_STYLES[map_style]
    base_layer = folium.TileLayer(
        tiles=tiles, attr=attribution, name=title, subdomains="abcd"
    ).add_to(map_)
    selected_hosts = {}
    outlines = host_outlines(data)
    group_colors = (
        (host_group_colors(data) if group_colors is None else group_colors)
        if color_by_groups
        else {}
    )
    nodes, edges = [], []
    if selected in data.participants:
        for index, sid in enumerate(data.route_stops(selected)):
            stop = data.stops.get(sid)
            if stop:
                selected_hosts.setdefault(stop.host, []).append(index + 1)
    if draft is None:
        for host in data.participants.values():
            numbers = selected_hosts.get(host.id, [])
            if host.latitude is not None and (show_hosts or numbers or host.id in locked_hosts):
                if numbers or host.id in locked_hosts or host.id in group_colors:
                    size = 28 if numbers or host.id in locked_hosts else 20
                    shadow = (
                        f",0 0 0 6px {group_colors[host.id]}80" if host.id in group_colors else ""
                    )
                    background = (
                        "repeating-linear-gradient(135deg,#187f71 0px,#187f71 4px,#18232ddd 4px,#18232ddd 8px)"
                        if host.id in locked_hosts
                        else "#187f71"
                    )
                    marker = folium.Marker(
                        [host.latitude, host.longitude],
                        icon=folium.DivIcon(
                            icon_size=(size, size),
                            icon_anchor=(size / 2, size / 2),
                            html=f'<div style="width:{size}px;height:{size}px;box-sizing:border-box;border:3px solid {outlines[host.id]};border-radius:50%;background:{background};color:white;display:flex;align-items:center;justify-content:center;font:bold 13px sans-serif;box-shadow:0 1px 4px #0005{shadow}">'
                            + "/".join(map(str, numbers))
                            + "</div>",
                        ),
                        tooltip=safe_text(
                            host.name
                            + (" · " + locked_hosts[host.id] if host.id in locked_hosts else "")
                        ),
                        popup=f"<b>{safe_text(host.name)}</b><br>{safe_text(host.address)}",
                    ).add_to(map_)
                else:
                    marker = folium.CircleMarker(
                        [host.latitude, host.longitude],
                        radius=10,
                        color=outlines[host.id],
                        weight=3,
                        fill=True,
                        fill_color="#187f71",
                        fill_opacity=0.9,
                        tooltip=safe_text(host.name),
                        popup=f"<b>{safe_text(host.name)}</b><br>{safe_text(host.address)}",
                    ).add_to(map_)
                nodes.append(
                    {
                        "id": host.id,
                        "marker": marker.get_name(),
                        "position": [host.latitude, host.longitude],
                    }
                )
    if mode != "Hosts only" and draft is None:
        for index, participant in enumerate(data.participants.values()):
            if not any(data.route_stops(participant.id)) or (
                mode == "Selected route" and participant.id != selected
            ):
                continue
            coordinates = data.coordinates(participant.id)
            route_hosts = [
                data.stops[sid].host if sid in data.stops else None
                for sid in data.route_stops(participant.id)
            ]
            for leg, (start, end) in enumerate(pairwise(coordinates)):
                if start is not None and end is not None:
                    line = folium.PolyLine(
                        [start, end],
                        color=COLORS[index % len(COLORS)],
                        weight=6 if participant.id == selected else 3,
                        opacity=0.9 if participant.id == selected else 0.45,
                        tooltip=safe_text(participant.name) + " · " + tr("straight-line preview"),
                        bubbling_mouse_events=False,
                    ).add_to(map_)
                    edges.append(
                        {
                            "line": line.get_name(),
                            "ids": route_hosts[leg : leg + 2],
                            "coordinates": [start, end],
                            "participant": participant.id,
                        }
                    )
    if points:
        route_points = (
            [point for point in data.coordinates(selected) if point is not None]
            if focus_route and selected in data.participants
            else []
        )
        map_.fit_bounds(route_points or points, padding=(35, 35), max_zoom=14)
    html = map_.get_root().render()
    html = html.replace("</head>", f'<style id="cykelfest-theme">{map_css(dark)}</style></head>')
    html += f"<script>window.cykelfestMap = {map_.get_name()};window.cykelfestBaseLayer = {base_layer.get_name()};</script>"
    html += (
        "<script>window.cykelfestFitHosts = function () { const points = "
        + json.dumps(points)
        + "; if (points.length) window.cykelfestMap.fitBounds(points, {padding: [35, 35], maxZoom: 14}); };</script>"
    )
    overlap = Path(__file__).with_name("map_overlap.js").read_text(encoding="utf-8")
    html += f"<script>{overlap}</script>"
    if draft is None:
        node_js = ",".join(
            f"{{id:{json.dumps(node['id'])}, marker:{node['marker']}, position:{json.dumps(node['position'])}}}"
            for node in nodes
        )
        edge_js = ",".join(
            f"{{line:{edge['line']}, ids:{json.dumps(edge['ids'])}, coordinates:{json.dumps(edge['coordinates'])}}}"
            for edge in edges
        )
        registration = f"window.cykelfestOverlap.setData([{node_js}], [{edge_js}]);"
        html += "<script>" + registration.replace("<", "\\u003c") + "</script>"
        blocked = ",".join(node["marker"] for node in nodes if node["id"] in locked_hosts)
        html += f"<script>for (const marker of [{blocked}]) {{ marker.unbindPopup(); marker.on('click', e => L.DomEvent.stop(e.originalEvent)); }}</script>"
        interactions = ",".join(
            f"{{line:{edge['line']}, participant:{json.dumps(edge['participant'])}}}"
            for edge in edges
        ).replace("<", "\\u003c")
        html += '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        html += (
            "<script>if (typeof qt !== 'undefined') new QWebChannel(qt.webChannelTransport, channel => {"
            " const bridge = channel.objects.routeEditor;"
            f" for (const edge of [{interactions}]) edge.line.on('dblclick', event => {{"
            " if (event.originalEvent) L.DomEvent.stop(event.originalEvent);"
            " bridge.selectRoute(edge.participant);"
            " }); });</script>"
        )
    if draft is not None:
        labels = {
            "remove": [tr("Remove appetizer"), tr("Remove main dish"), tr("Remove dessert")],
            "guests": tr("guests"),
            "unavailable": tr("unavailable for this course"),
            "rightClick": tr("right-click to remove"),
        }
        html += (
            "<script>window.cykelfestI18n = "
            + json.dumps(labels).replace("<", "\\u003c")
            + ";</script>"
        )
        state = draft.payload()
        for host in state["hosts"]:
            host["groupColor"] = group_colors.get(host["id"], "")
        state["hosts"] = [host for host in state["hosts"] if host["id"] in data.participants]
        for host in state["hosts"]:
            host["locked"] = locked_hosts.get(host["id"], "")
            if host["locked"]:
                host["eligible"] = [False, False, False]
        payload = json.dumps(state).replace("<", "\\u003c")
        editor = Path(__file__).with_name("map_editor.js").read_text(encoding="utf-8")
        html += (
            '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
            f"<script>window.cykelfestMap = {map_.get_name()};"
            f"window.cykelfestEditorState = {payload};</script><script>{editor}</script>"
        )
    # A visible fallback also covers blocked CDN scripts, where Qt reports a successful HTML load.
    fallback = '<div id="map-fallback" style="position:absolute;inset:0;padding:30px;background:#eef4f2;color:#24443e;font:16px sans-serif;z-index:999">Loading OpenStreetMap…<br><br>If the map stays here, check internet access to map tiles and Leaflet assets.</div>'
    html = html.replace("<body>", "<body>" + translate_html(fallback))
    return html.replace(
        "</html>",
        '<script>if(typeof L!=="undefined" && document.querySelector(".leaflet-container")){document.getElementById("map-fallback").remove();}</script></html>',
    )
