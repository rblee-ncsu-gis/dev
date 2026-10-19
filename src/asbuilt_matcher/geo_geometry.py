"""Small 2D geometry kernel for a bounded county-scale localization pilot.

WGS84 coordinates are projected to a bounded local ellipsoidal east/north frame
for distance comparisons; geographic outputs retain longitude/latitude. No datum
conversion or EPSG:2264 reprojection is performed. This cannot establish survey
registration or grade-separated connectivity.
"""

import math
from functools import lru_cache

EARTH_RADIUS_M = 6371008.8
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


@lru_cache(maxsize=16)
def _frame(origin):
    lon, lat = map(math.radians, origin)
    s, c = math.sin(lat), math.cos(lat)
    sl, cl = math.sin(lon), math.cos(lon)
    radius = WGS84_A / math.sqrt(1-WGS84_E2*s*s)
    return ((radius*c*cl,radius*c*sl,radius*(1-WGS84_E2)*s),
            (-sl,cl,0),(-s*cl,-s*sl,c),(c*cl,c*sl,s))


def parts(geometry):
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return [[coords]]
    if kind == "MultiPoint":
        return [coords]
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
            minimum = 4 if "Polygon" in geometry["type"] else 1 if "Point" in geometry["type"] else 2
            if not isinstance(ring, list) or len(ring) < minimum:
                raise ValueError("Too few positions")
            for p in ring:
                if (not isinstance(p, list) or len(p) not in (2, 3)
                        or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in p)
                        or not -180 <= p[0] <= 180 or not -80 <= p[1] <= 80):
                    raise ValueError("Expected finite WGS84 longitude/latitude positions (latitude within +/-80)")
            if "Polygon" in geometry["type"] and ring[0][:2] != ring[-1][:2]:
                raise ValueError("Polygon rings must be closed")
            if len({tuple(p[:2]) for p in ring}) < (3 if "Polygon" in geometry["type"] else 1 if "Point" in geometry["type"] else 2):
                raise ValueError("Geometry is degenerate")
    b = bounds(geometry)
    if b[2] - b[0] > 5 or b[3] - b[1] > 5:
        raise ValueError("County-scale geometry required; antimeridian/global geometry unsupported")
    return b


def project(point, origin):
    """WGS84 ellipsoid -> local east/north tangent plane in metres (height 0).

    This explicitly defined local projection replaces the earlier spherical
    scale approximation. It is bounded to county extents, not EPSG:2264.
    """
    base,east,north,_ = _frame(tuple(origin))
    lon,lat = math.radians(point[0]),math.radians(point[1])
    radius = WGS84_A / math.sqrt(1-WGS84_E2*math.sin(lat)**2)
    xyz = [radius*math.cos(lat)*math.cos(lon),radius*math.cos(lat)*math.sin(lon),radius*(1-WGS84_E2)*math.sin(lat)]
    delta = [xyz[i]-base[i] for i in range(3)]
    return sum(delta[i]*east[i] for i in range(3)),sum(delta[i]*north[i] for i in range(3))


def unproject(point, origin):
    base,east,north,up = _frame(tuple(origin))
    q = [base[i]+east[i]*point[0]+north[i]*point[1] for i in range(3)]
    axes = [WGS84_A**2,WGS84_A**2,WGS84_A**2*(1-WGS84_E2)]
    a = sum(up[i]**2/axes[i] for i in range(3))
    b = 2*sum(q[i]*up[i]/axes[i] for i in range(3))
    c = sum(q[i]**2/axes[i] for i in range(3))-1
    discriminant = b*b-4*a*c
    if discriminant < 0:
        raise ValueError("Local projected point is outside the visible ellipsoid")
    height = (-b+math.sqrt(discriminant))/(2*a)
    x,y,z = [q[i]+up[i]*height for i in range(3)]
    return [math.degrees(math.atan2(y,x)),math.degrees(math.atan2(z,(1-WGS84_E2)*math.hypot(x,y)))]


def segments(geometry):
    if "Point" in geometry["type"]:
        return
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
    if "Point" in geometry["type"]:
        return min(math.dist(p, project(q, origin)) for q in vertices(geometry))
    return min(point_segment_distance(p, project(a, origin), project(b, origin)) for a, b in segments(geometry))


def geometry_distance(left, right, origin):
    if "Point" in left["type"]:
        return min(point_distance(p, right, origin) for p in vertices(left))
    if "Point" in right["type"]:
        return min(point_distance(p, left, origin) for p in vertices(right))
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
