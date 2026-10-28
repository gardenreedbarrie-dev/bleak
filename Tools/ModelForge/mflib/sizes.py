"""Model sizes: the section 5.8 table (props/__init__.py CATALOGUE) and, when it exists, cafe.json `size`
(Tools/CafeForge/cafe.json, WS-A; read-only here). ModelForge's tests hold every built model's collision or render
footprint to the size (+- 2 cm), which is also what the layout check of section 3.12.3 uses."""

import json
import os

from . import REPO
from .props import CATALOGUE

CAFE_JSON = os.path.join(REPO, "Tools", "CafeForge", "cafe.json")
TOLERANCE = 0.02


def catalogue():
    return {name: {"display": disp, "size": size, "budget": budget} for name, disp, size, budget in CATALOGUE}


def cafe_sizes(path=CAFE_JSON):
    """{display id: (W, D, H)} from cafe.json gameobjects, or {} when the file is absent or unreadable."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for go in doc.get("gameobjects", []):
        disp, size = go.get("display"), go.get("size")
        if isinstance(disp, int) and isinstance(size, list) and len(size) == 3:
            out[disp] = tuple(float(v) for v in size)
    return out


def expected_size(name, display):
    """The size a model is held to: cafe.json when it lists the display, else the section 5.8 table."""
    cs = cafe_sizes()
    if display in cs:
        return cs[display], "cafe.json"
    cat = catalogue().get(name)
    return (cat["size"] if cat else None), "spec section 5.8"


def footprint(defn):
    """(W along Y, D along X, H) of the collision hull, and of the render geometry."""
    cp = defn.collision[0]
    pts = [p for part in defn.parts for p in part.mesh.p]

    def dims(ps):
        if not ps:
            return None
        lo = [min(p[i] for p in ps) for i in range(3)]
        hi = [max(p[i] for p in ps) for i in range(3)]
        return (hi[1] - lo[1], hi[0] - lo[0], hi[2] - lo[2])
    return dims(cp), dims(pts)
