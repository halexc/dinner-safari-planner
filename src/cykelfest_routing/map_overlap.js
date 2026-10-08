// Spread nearby nodes in screen space without changing their stored coordinates.
(function () {
    const map = window.cykelfestMap;
    let records = new Map(), edges = [], expanded = [], frame = null, held = false;
    const originals = new Map();
    const container = map.getContainer();
    function position(id, fallback) {
        return records.get(id)?.marker.getLatLng() || fallback;
    }
    function redraw() {
        for (const edge of edges) {
            edge.line.setLatLngs(edge.ids.map((id, i) => position(id, edge.coordinates[i])));
        }
    }
    function move(targets, immediate = false) {
        if (frame !== null) cancelAnimationFrame(frame);
        const starts = new Map([...targets].map(([id]) => [id, records.get(id).marker.getLatLng()]));
        const started = performance.now();
        function animate(now) {
            const fraction = immediate ? 1 : Math.min(1, (now - started) / 180);
            const eased = fraction * fraction * (3 - 2 * fraction);
            for (const [id, end] of targets) {
                const start = starts.get(id);
                records.get(id)?.marker.setLatLng([
                    start.lat + (end.lat - start.lat) * eased,
                    start.lng + (end.lng - start.lng) * eased
                ]);
            }
            redraw();
            frame = fraction < 1 ? requestAnimationFrame(animate) : null;
        }
        if (immediate) animate(started); else frame = requestAnimationFrame(animate);
    }
    function reset(immediate = false) {
        const targets = new Map([...records.keys()].map(id => [id, originals.get(id)]));
        expanded = [];
        move(targets, immediate);
    }
    function spread(id) {
        if (held || expanded.length || !records.has(id)) return;
        const group = new Set([id]);
        // Include chains of overlaps, not just nodes coinciding exactly.
        let changed = true;
        while (changed) {
            changed = false;
            for (const candidate of records.keys()) {
                if (group.has(candidate)) continue;
                const point = map.latLngToContainerPoint(originals.get(candidate));
                if ([...group].some(member => point.distanceTo(
                    map.latLngToContainerPoint(originals.get(member))) < 36)) {
                    group.add(candidate);
                    changed = true;
                }
            }
        }
        if (group.size < 2) return;
        expanded = [...group];
        const points = expanded.map(key => map.latLngToContainerPoint(originals.get(key)));
        const center = L.point(points.reduce((sum, p) => sum + p.x, 0) / points.length,
            points.reduce((sum, p) => sum + p.y, 0) / points.length);
        const sector = 2 * Math.PI / expanded.length;
        let targets, bestSeparation = -1;
        // Try a few small offsets to avoid pushing nearby nodes back together.
        // Keep the best spacing without increasing the requested offset size.
        for (let attempt = 0; attempt < 12; attempt++) {
            const rotation = Math.random() * 2 * Math.PI;
            const candidates = points.map((point, index) => {
                // Separate angular sectors give coincident nodes distinct
                // directions, with random rotation, angle jitter and radius.
                const angle = rotation + index * sector + (Math.random() - 0.5) * sector * 0.4;
                const radius = 8 + Math.random() * 2;
                const offset = L.point(Math.cos(angle) * radius, Math.sin(angle) * radius);
                return center.add(point.add(offset).subtract(center).multiplyBy(2));
            });
            let separation = Infinity;
            for (let i = 0; i < candidates.length; i++) {
                for (let j = i + 1; j < candidates.length; j++) {
                    separation = Math.min(separation, candidates[i].distanceTo(candidates[j]));
                }
            }
            if (separation > bestSeparation) {
                targets = candidates;
                bestSeparation = separation;
            }
            if (separation >= 28) break;
        }
        move(new Map(expanded.map((key, index) => [key, map.containerPointToLatLng(targets[index])])));
    }
    container.addEventListener('pointermove', event => {
        if (!expanded.length || held) return;
        const rect = container.getBoundingClientRect();
        const point = L.point(event.clientX - rect.left, event.clientY - rect.top);
        // Keep the whole cluster open while moving between its nodes.
        const points = expanded.flatMap(id => [
            map.latLngToContainerPoint(originals.get(id)),
            map.latLngToContainerPoint(records.get(id).marker.getLatLng())
        ]);
        const padding = 26;
        if (point.x < Math.min(...points.map(p => p.x)) - padding ||
            point.x > Math.max(...points.map(p => p.x)) + padding ||
            point.y < Math.min(...points.map(p => p.y)) - padding ||
            point.y > Math.max(...points.map(p => p.y)) + padding) reset();
    });
    container.addEventListener('pointerleave', () => { if (!held) reset(); });
    map.on('zoomstart movestart', () => reset(true));
    window.cykelfestOverlap = {
        setData(nodes, connections) {
            const previous = records;
            records = new Map(nodes.map(node => [node.id, node]));
            edges = connections;
            for (const node of nodes) {
                node.marker.bringToFront?.();
                originals.set(node.id, L.latLng(node.position));
                if (previous.get(node.id)?.marker !== node.marker) {
                    node.marker.on('mouseover', () => spread(node.id));
                    // Native pointer events also cover custom editing markers.
                    node.marker.getElement()?.addEventListener('pointerenter', () => spread(node.id));
                }
            }
            expanded = expanded.filter(id => records.has(id));
            redraw();
        },
        position,
        hold(value) { held = value; },
        reset,
        expanded: () => [...expanded]
    };
})();
