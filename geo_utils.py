from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from state import Location


def distance_km(a: Location, b: Location) -> float:
    """Return approximate great-circle distance between two coordinates."""

    earth_radius_km = 6371.0
    lat1 = radians(a.latitude or 0)
    lon1 = radians(a.longitude or 0)
    lat2 = radians(b.latitude or 0)
    lon2 = radians(b.longitude or 0)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(h))


def has_location(value: object) -> bool:
    location = getattr(value, "location", None)
    return (
        location is not None
        and location.latitude is not None
        and location.longitude is not None
    )
