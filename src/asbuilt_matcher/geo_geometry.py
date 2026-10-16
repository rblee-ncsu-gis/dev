"""Small 2D geometry kernel for a bounded county-scale localization pilot.

No CRS transformation. WGS84 coordinates are locally approximated in metres for
distance comparisons only; outputs always retain longitude/latitude. This is not
a survey/georeferencing engine and cannot establish grade-separated connectivity.
"""

import math

EARTH_RADIUS_M = 6371008.8


def parts(geometry):
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind in {"LineString", "Polygon"}:
        return [coords]
    return coords


def vertices(geometry):
    for part in parts(geometry):
        if "Polygon" in geometry["type"]:
            for ring in part:
                yield from ring
        else:
            yield from part


def bounds(geometry):
    points = list(vertices(geometry))
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def validate_geometry(geometry, allowed):
    if not isinstance(geometry, dict) or geometry.get("type") not in allowed:
        raise ValueError("Unsupported or missing geometry type")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise ValueError("Empty geometry")
    for part in parts(geometry):
        rings = part if "Polygon" in geometry["type"] else [part]
        if not isinstance(rings, list) or not rings:
            raise ValueError("Empty geometry part")
        for ring in rings:
            if not isinstance(ring, list) or len(ring) < (4 if "Polygon" in geometry["type"] else 2):
                raise ValueError("Too few positions")
            for p in ring:
                if (not isinstance(p, list) or len(p) not in (2, 3)
                        or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in p)
                        or not -180 <= p[0] <= 180 or not -80 <= p[1] <= 80):
                    raise ValueError("Expected finite WGS84 longitude/latitude positions (latitude within +/-80)")
            if "Polygon" in geometry["type"] and ring[0][:2] != ring[-1][:2]:
                raise ValueError("Polygon rings must be closed")
            if len({tuple(p[:2]) for p in ring}) < (3 if "Polygon" in geometry["type"] else 2):
                raise ValueError("Geometry is degenerate")
    b = bounds(geometry)
    if b[2] - b[0] > 5 or b[3] - b[1] > 5:
        raise ValueError("County-scale geometry required; antimeridian/global geometry unsupported")
    return b


def project(point, origin):
    return ((point[0] - origin[0]) * math.pi / 180 * EARTH_RADIUS_M * math.cos(math.radians(origin[1])),
            (point[1] - origin[1]) * math.pi / 180 * EARTH_RADIUS_M)


def unproject(point, origin):
    return [origin[0] + point[0] / (EARTH_RADIUS_M * math.cos(math.radians(origin[1]))) * 180 / math.pi,
            origin[1] + point[1] / EARTH_RADIUS_M * 180 / math.pi]


def segments(geometry):
    for part in parts(geometry):
        for ring in (part if "Polygon" in geometry["type"] else [part]):
            yield from zip(ring, ring[1:])


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) if length else 0
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def crossing(a, b, c, d):
    """Intersection of two non-collinear segments, including shared endpoints.

    Collinear overlaps are not a unique road intersection and return None.
    """
    r, s = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
    cross = lambda x, y: x[0] * y[1] - x[1] * y[0]
    denom = cross(r, s)
    if abs(denom) < 1e-12:
        return None
    delta = c[0] - a[0], c[1] - a[1]
    t, u = cross(delta, s) / denom, cross(delta, r) / denom
    if -1e-10 <= t <= 1 + 1e-10 and -1e-10 <= u <= 1 + 1e-10:
        return [a[0] + t * r[0], a[1] + t * r[1]]
    return None


def inside_ring(p, ring):
    inside = False
    for a, b in zip(ring, ring[1:]):
        if point_segment_distance(p, a, b) < 1e-10:
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def contains(geometry, point):
    if "Polygon" not in geometry["type"]:
        return False
    return any(inside_ring(point, polygon[0]) and not any(inside_ring(point, r) for r in polygon[1:])
               for polygon in parts(geometry))


def point_distance(point, geometry, origin):
    if contains(geometry, point):
        return 0.0
    p = project(point, origin)
    return min(point_segment_distance(p, project(a, origin), project(b, origin)) for a, b in segments(geometry))


def geometry_distance(left, right, origin):
    # Containment and boundary crossings must be checked, not just bounding boxes.
    if any(contains(left, p) for p in vertices(right)) or any(contains(right, p) for p in vertices(left)):
        return 0.0
    a = [(project(x, origin), project(y, origin)) for x, y in segments(left)]
    b = [(project(x, origin), project(y, origin)) for x, y in segments(right)]
    if any(crossing(x, y, z, w) is not None for x, y in a for z, w in b):
        return 0.0
    return min(min(point_segment_distance(x, z, w), point_segment_distance(y, z, w),
                   point_segment_distance(z, x, y), point_segment_distance(w, x, y))
               for x, y in a for z, w in b)


def road_intersections(left, right, origin):
    points = {}
    for a, b in segments(left):
        for c, d in segments(right):
            p = crossing(project(a, origin), project(b, origin), project(c, origin), project(d, origin))
            if p is not None:
                xy = unproject(p, origin)
                points[tuple(round(n, 9) for n in xy)] = xy
    return list(points.values())


def extent_diagonal(bbox, origin):
    return math.dist(project(bbox[:2], origin), project(bbox[2:], origin))


def neighborhood(point, radius_m, origin):
    p = project(point, origin)
    return unproject([p[0] - radius_m, p[1] - radius_m], origin) + unproject([p[0] + radius_m, p[1] + radius_m], origin)
