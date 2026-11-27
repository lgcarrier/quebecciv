"""projection.json : comment le navigateur passe d'une longitude-latitude aux unités de carte (« Me localiser »,
ext/locate) : azimutale équivalente de Lambert sphérique centrée sur core/quebec.py LON0, LAT0, km mis à l'échelle
`scale` depuis le coin (min_x, max_y) plus `margin`. Pas de médaillon (insets) pour le Québec."""

from __future__ import annotations

from ..core.geo import R_EARTH_KM
from ..core.quebec import LAT0, LON0
from ..core.store import load_interim, write_web

REQUIRES = ["_world"]
PRODUCES = ["projection.json"]


def build() -> None:
    p = load_interim("_world")["projection"]
    write_web("projection.json", {
        "kind": "laea", "lon0": LON0, "lat0": LAT0, "radius_km": R_EARTH_KM,
        "min_x": p["min_x"], "max_y": p["max_y"], "margin": p["margin"], "scale": p["scale"],
        "inset_pad": 0, "insets": [],
    })
