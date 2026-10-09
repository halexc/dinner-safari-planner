// Leaflet pointer gestures. Python remains authoritative for draft edits and eligibility.
(function () {
    const map = window.cykelfestMap;
    const labels = window.cykelfestI18n;
    let state = window.cykelfestEditorState;
    let bridge = null;
    let gesture = null;
    let busy = false;
    const nodes = L.layerGroup().addTo(map);
    const markers = new Map();
    const route = L.layerGroup().addTo(map);
    const rubberBand = L.polyline([], {color: '#267ac0', weight: 4, dashArray: '8 6'}).addTo(map);
    const container = map.getContainer();
    const text = value => {
        const element = document.createElement('span');
        element.textContent = value;
        return element.innerHTML;
    };
    const countColor = count => count === 0 ? '#169b43' : count === 1 ? '#95d938' : '#f3cf28';
    function removeCourse(index) {
        if (!bridge || busy) return;
        busy = true;
        map.closePopup();
        bridge.removeStop(state.session, index);
    }
    function createMarker(host) {
        const marker = L.marker([host.lat, host.lon], {
            icon: L.divIcon({className: 'route-node', iconSize: [36, 36], iconAnchor: [18, 18],
                html: '<div class="route-node-circle"></div>'}),
            opacity: 0, draggable: false, bubblingMouseEvents: false
        }).addTo(nodes);
        const record = {marker, host, indices: []};
        markers.set(host.id, record);
        const element = marker.getElement();
        element.dataset.hostId = host.id;
        element.style.transition = 'opacity 0.5s ease';
        element.style.display = 'flex';
        element.style.alignItems = 'center';
        element.style.justifyContent = 'center';
        marker.bindTooltip('');
        element.addEventListener('pointerdown', event => {
            if (event.button !== 0 || !bridge || busy || gesture || record.host.locked) return;
            event.preventDefault();
            event.stopPropagation();
            gesture = {host: record.host, x: event.clientX, y: event.clientY, moved: false};
            window.cykelfestOverlap.hold(true);
            map.dragging.disable();
            container.setPointerCapture(event.pointerId);
        });
        element.addEventListener('contextmenu', event => {
            event.preventDefault();
            event.stopPropagation();
            if (!bridge || busy || gesture || !record.indices.length || record.host.locked) return;
            if (record.indices.length === 1) {
                removeCourse(record.indices[0]);
            } else {
                const choices = document.createElement('div');
                for (const index of record.indices) {
                    const choice = document.createElement('button');
                    choice.textContent = labels.remove[index];
                    choice.style.display = 'block';
                    choice.style.margin = '6px 0';
                    choice.addEventListener('click', () => removeCourse(index));
                    choices.appendChild(choice);
                }
                L.popup().setLatLng(marker.getLatLng()).setContent(choices).openOn(map);
            }
        });
        // Establish opacity zero before starting the 500 ms entrance transition.
        element.getBoundingClientRect();
        return record;
    }
    function render(course, duringDrag = false) {
        const hostIds = new Set(state.hosts.map(host => host.id));
        for (const [id, record] of markers) {
            if (!hostIds.has(id)) { nodes.removeLayer(record.marker); markers.delete(id); }
        }
        route.clearLayers();
        const edges = [];
        for (let i = 0; i < 2; i++) {
            if (state.coordinates[i] && state.coordinates[i + 1]) {
                const line = L.polyline([state.coordinates[i], state.coordinates[i + 1]], {
                    color: '#187f71', weight: 5, interactive: false
                }).addTo(route);
                edges.push({line, ids: state.route.slice(i, i + 2), coordinates: state.coordinates.slice(i, i + 2)});
            }
        }
        for (const host of state.hosts) {
            const indices = state.route.flatMap((id, index) => id === host.id ? [index] : []);
            const mainAnchor = host.id === state.route[1];
            const markerCourse = indices.includes(course) ? course : indices.length ? indices[0] : course;
            const color = host.own ? '#267ac0' : countColor(host.guests[markerCourse]);
            const record = markers.get(host.id) || createMarker(host);
            record.host = host;
            record.indices = indices;
            record.marker.setOpacity(host.locked || host.eligible[course] ? 1 : 0.25);
            const element = record.marker.getElement();
            // Keep hover, removal and continuation gestures available. Python
            // still rejects assignments to unavailable hosts in Safe Edit.
            element.style.pointerEvents = 'auto';
            element.style.cursor = bridge && !busy ? 'crosshair' : 'wait';
            const circle = element.firstElementChild;
            circle.style.cssText = 'box-sizing:border-box;border-radius:50%;display:flex;align-items:center;justify-content:center;' +
                `font:bold 13px sans-serif;color:${host.own ? 'white' : '#163c35'};box-shadow:0 1px 4px #0005;` +
                `width:${indices.length ? 32 : 24}px;height:${indices.length ? 32 : 24}px;` +
                `background:${color};border:${mainAnchor ? 4 : 3}px solid ${host.outline};`;
            circle.textContent = indices.map(index => index + 1).join('/');
            if (host.locked) {
                circle.style.background = `repeating-linear-gradient(135deg,${color} 0px,${color} 4px,#18232ddd 4px,#18232ddd 8px)`;
                element.style.cursor = 'not-allowed';
            }
            record.marker.setTooltipContent(text(host.name) + ' · ' + host.guests[markerCourse] + ' ' + labels.guests +
                (host.eligible[course] ? '' : ' · ' + labels.unavailable) +
                (indices.length ? ' · ' + labels.rightClick : ''));
            record.marker.setZIndexOffset(indices.length ? 1000 : 0);
        }
        window.cykelfestOverlap.setData([...markers].map(([id, record]) => ({
            id, marker: record.marker, position: [record.host.lat, record.host.lon]
        })), edges);
    }
    const point = event => {
        const rect = container.getBoundingClientRect();
        return L.point(event.clientX - rect.left, event.clientY - rect.top);
    };
    function cancel() {
        gesture = null;
        window.cykelfestOverlap.hold(false);
        rubberBand.setLatLngs([]);
        map.dragging.enable();
        render(state.next === null ? 0 : state.next);
    }
    container.addEventListener('pointermove', event => {
        if (!gesture) return;
        if (!gesture.moved && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 6) {
            gesture.moved = true;
            gesture.course = gesture.host.id === state.route[1] ? 2 : 1;
            render(gesture.course, true);
        }
        if (gesture.moved) {
            rubberBand.setLatLngs([window.cykelfestOverlap.position(gesture.host.id), map.containerPointToLatLng(point(event))]);
        }
    });
    container.addEventListener('pointerup', event => {
        if (!gesture) return;
        const current = gesture;
        let end = null;
        if (current.moved) {
            let distance = 22;
            for (const host of state.hosts) {
                if (!host.eligible[current.course]) continue;
                const candidateDistance = map.latLngToContainerPoint(markers.get(host.id).marker.getLatLng()).distanceTo(point(event));
                if (candidateDistance < distance) { distance = candidateDistance; end = host; }
            }
        }
        cancel();
        if (current.moved && end) {
            busy = true;
            bridge.drawSection(state.session, current.host.id, end.id);
        } else if (!current.moved) {
            busy = true;
            bridge.clickHost(state.session, current.host.id);
        }
    });
    container.addEventListener('pointercancel', cancel);
    container.addEventListener('lostpointercapture', () => { if (gesture) cancel(); });
    window.addEventListener('blur', cancel);
    new QWebChannel(qt.webChannelTransport, channel => {
        bridge = channel.objects.routeEditor;
        bridge.stateChanged.connect(value => {
            const update = JSON.parse(value);
            if (update.session !== state.session) return;
            state = update;
            window.cykelfestEditorState = state;
            busy = false;
            cancel();
        });
        render(state.next === null ? 0 : state.next);
    });
    render(state.next === null ? 0 : state.next);
    // Expose markers for integration checks without replacing native pointer handling.
    window.cykelfestEditor = {nodes, state: () => state};
})();
