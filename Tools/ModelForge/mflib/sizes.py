"""Model sizes: the section 5.8 table (props/__init__.py CATALOGUE) and, when it exists, cafe.json `size`
(Tools/CafeForge/cafe.json, WS-A; read-only here). ModelForge's tests hold every built model's collision or render
footprint to the size (+- 2 cm), which is also what the layout check of section 3.12.3 uses."""

import json
import os

from . import REPO
from .props import CATALOGUE

CAFE_JSON = os.path.join(REPO, "Tools", "CafeForge", "cafe.json")
TOLERANCE = 0.02

# What each kind of piece (PropDef.kind) is held to: the collision budget of section 5.2.6, whether it needs a
# full hull (held to its size; parasols collide on their poles only, table props not at all), the most its
# render geometry may rise above its base (section 5.8: a machine on the back bar ends at most 0.95 above the
# bar top) and the height it stands at in the café (section 3.12.3: on the back bar or the counter at 1.05, or
# on the floor), which the previews use.
KINDS = {
    "machine": {"collision_max": 120, "hull": True, "max_h": 0.95, "base_z": 1.05},    # espresso, grinder, blender
    "rack": {"collision_max": 48, "hull": True, "max_h": 0.95, "base_z": 1.05},        # syrup racks (on the bar)
    "station": {"collision_max": 120, "hull": True, "max_h": None, "base_z": 0.0},     # kettle stove, cold box
    "counter": {"collision_max": 48, "hull": True, "max_h": None, "base_z": 0.0},      # counters, back bars
    "chalkboard": {"collision_max": 48, "hull": True, "max_h": None, "base_z": 0.0},
    "parasol": {"collision_max": 32, "hull": False, "max_h": None, "base_z": 0.0},     # pole(s) only
    "table": {"collision_max": 0, "hull": False, "max_h": None, "base_z": 1.05},       # cups, glass, tip jar
    "test": {"collision_max": 200, "hull": True, "max_h": None, "base_z": 1.05},
}


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


def kind(defn):
    if defn.kind not in KINDS:
        raise KeyError("%s: kind %r is not one of %s" % (defn.name, defn.kind, ", ".join(sorted(KINDS))))
    return KINDS[defn.kind]


def render_target(defn, want):
    """The (W, D, H) the render geometry is held to: render_size when set, else the size (with the depth of the
    portafilter handles, depth_with_handles, when set)."""
    if defn.render_size:
        return tuple(defn.render_size)
    return (want[0], defn.depth_with_handles or want[1], want[2])


def size_problems(defn):
    """Every way a built model misses its size (section 5.8 and cafe.json, within TOLERANCE), as messages:
    the declared size against the catalogue, the render extents against render_target, the collision hull
    against collision_size or the size (kinds with a full hull), no hull for walk-through kinds, the height
    limit of the kind and defn.max_height. Empty when it fits."""
    want, source = expected_size(defn.name, defn.display)
    if want is None and defn.kind == "test" and defn.size:
        want, source = tuple(defn.size), "PropDef.size (test model)"
    if want is None:
        return ["%s has no size in cafe.json or the section 5.8 table" % defn.name]
    out = []
    axes = ("W (Y)", "D (X)", "H")

    def cmp(what, got, target):
        for k in range(3):
            if abs(got[k] - target[k]) > TOLERANCE + 1e-9:
                out.append("%s %s %.3f, want %.3f (+-%.2f; %s)" % (what, axes[k], got[k], target[k], TOLERANCE,
                                                                  source))
    if not defn.size:
        out.append("PropDef.size is not set")
    else:
        cmp("declared size", defn.size, want)
    coll, rend = footprint(defn)
    cmp("render", rend, render_target(defn, want))
    k = kind(defn)
    if k["hull"]:
        if coll is None:
            out.append("no collision hull (kind %s needs one)" % defn.kind)
        else:
            cmp("collision", coll, tuple(defn.collision_size or want))
    elif k["collision_max"] == 0 and coll is not None:
        out.append("kind %s is walk-through but has a collision hull" % defn.kind)
    limit = [v for v in (k["max_h"], defn.max_height) if v is not None]
    if limit and rend[2] > min(limit) + 1e-6:
        out.append("render height %.3f above its base exceeds %.2f" % (rend[2], min(limit)))
    return out
