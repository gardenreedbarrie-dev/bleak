"""Load and check a terrain map spec (JSON).

Every object is checked for unknown keys (a typo is an error, not a silently ignored setting). Keys starting with
"_" are comments and are ignored everywhere. See Tools/MapForge/README.md, section "Terrain", for the format.
"""

from __future__ import annotations

import json
import re

from . import coords
from .shapes import RiverPath, parse_shape
from .spec_errors import SpecError

FORMAT = "mapforge-terrain/1"

_DIR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def _check_keys(obj, allowed: set[str], required: set[str], where: str) -> dict:
    if not isinstance(obj, dict):
        raise SpecError(f"{where}: expected an object")
    keys = {k for k in obj if not k.startswith("_")}
    extra = keys - allowed
    if extra:
        raise SpecError(f"{where}: unknown keys {sorted(extra)} (allowed: {sorted(allowed)})")
    missing = required - keys
    if missing:
        raise SpecError(f"{where}: missing keys {sorted(missing)}")
    return obj


def _num(obj: dict, key: str, where: str, default=None, lo=None, hi=None) -> float:
    if key not in obj or obj[key] is None:
        if default is None:
            raise SpecError(f"{where}.{key}: required")
        return float(default)
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{where}.{key}: expected a number")
    value = float(value)
    if lo is not None and value < lo:
        raise SpecError(f"{where}.{key}: must be >= {lo}")
    if hi is not None and value > hi:
        raise SpecError(f"{where}.{key}: must be <= {hi}")
    return value


def _int(obj: dict, key: str, where: str, default=None, lo=None, hi=None) -> int:
    if key not in obj or obj[key] is None:
        if default is None:
            raise SpecError(f"{where}.{key}: required")
        return int(default)
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"{where}.{key}: expected an integer")
    if lo is not None and value < lo:
        raise SpecError(f"{where}.{key}: must be >= {lo}")
    if hi is not None and value > hi:
        raise SpecError(f"{where}.{key}: must be <= {hi}")
    return value


def _vec(value, n: int, where: str, allow_none_last: bool = False) -> list:
    if not isinstance(value, list) or not (len(value) == n or (allow_none_last and len(value) == n - 1)):
        raise SpecError(f"{where}: expected a list of {n} numbers")
    out = []
    for i, v in enumerate(value):
        if v is None and allow_none_last and i == n - 1:
            out.append(None)
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise SpecError(f"{where}[{i}]: expected a number")
        out.append(float(v))
    if len(out) == n - 1:
        out.append(None)
    return out


def _color(value, where: str) -> tuple[int, int, int]:
    if isinstance(value, str) and re.match(r"^#[0-9a-fA-F]{6}$", value):
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in value):
        return (value[0], value[1], value[2])
    raise SpecError(f"{where}: expected '#rrggbb' or [r, g, b]")


def normalize_path(path: str, where: str, extensions: tuple[str, ...]) -> str:
    """Client path form: backslashes, no leading separator, known extension, ASCII."""
    if not isinstance(path, str) or not path.strip():
        raise SpecError(f"{where}: expected a path")
    p = path.strip().replace("/", "\\")
    while p.startswith("\\"):
        p = p[1:]
    try:
        p.encode("ascii")
    except UnicodeEncodeError:
        raise SpecError(f"{where}: client paths must be ASCII: {path!r}") from None
    if "\\\\" in p or any(c in p for c in "\0\r\n\t\"<>|*?"):
        raise SpecError(f"{where}: invalid characters in path {path!r}")
    if not p.lower().endswith(extensions):
        raise SpecError(f"{where}: {path!r} must end with {' or '.join(extensions)}")
    if len(p) >= 256:
        raise SpecError(f"{where}: path longer than 255 characters (the client copies names into 256-byte buffers)")
    return p


def is_placeholder(path: str) -> bool:
    return "todo" in path.lower()


# Extra assets: art from later expansions, written {"modern": path, "fallback": 3.3.5 path, "kind": ...} wherever a
# texture or doodad path goes. `package.py resolve-assets` checks which modern files exist on the VPS and writes a
# resolution file; with it the build uses each modern file it found, and the fallback otherwise (always without it).
ASSET_KINDS = ("texture", "doodad")


class AssetUse:
    """One place in the spec that names an extra asset, and which path the build uses there."""

    __slots__ = ("where", "kind", "modern", "fallback", "path", "modern_used", "reason", "entry")

    def __init__(self, where, kind, modern, fallback, path, modern_used, reason, entry):
        self.where = where
        self.kind = kind
        self.modern = modern
        self.fallback = fallback
        self.path = path  # the one the files reference
        self.modern_used = modern_used
        self.reason = reason  # why the fallback is used ("" when the modern file is)
        self.entry = entry  # the resolution entry, or None


class Texture:
    def __init__(self, name, path, color, effect_id, mtxf_flags, modern=False):
        self.name = name
        self.path = path
        self.color = color
        self.effect_id = effect_id
        self.mtxf_flags = mtxf_flags
        self.modern = modern  # path is a resolved extra asset (shipped in the map archive)


class Placement:
    def __init__(self, kind, model, x, y, z, z_offset, rotation, scale, uid, radius, flags, bounds, doodad_set,
                 name_set, label, modern=False):
        self.kind = kind  # "doodad" | "wmo"
        self.model = model
        self.x = x
        self.y = y
        self.z = z  # None = on the ground
        self.z_offset = z_offset
        self.rotation = rotation  # file order (rx, ry, rz), degrees
        self.scale = scale
        self.uid = uid  # None = assign
        self.radius = radius
        self.flags = flags
        self.bounds = bounds  # model-local [[min], [max]] or None
        self.doodad_set = doodad_set
        self.name_set = name_set
        self.label = label
        self.modern = modern  # a resolved extra asset: client tiles only, never the server's extract tiles


class Spec:
    """A checked spec. Attributes mirror the JSON (see the README)."""

    def __init__(self):
        self.directory = ""
        self.map_id = None  # Map.dbc id, optional (copied into the manifest and pois.json)
        self.tx0 = self.tx1 = self.ty0 = self.ty1 = 0
        self.seed = 0
        self.area_id = 0
        self.areas = []  # [(area_id, shape)]
        self.base_height = 0.0
        self.noise = []  # [dict]
        self.features = []  # [dict] (checked, shapes parsed)
        self.textures: list[Texture] = []
        self.texture_rules = []
        self.holes = []  # [shape]
        self.doodads: list[Placement] = []
        self.wmos: list[Placement] = []
        self.water = []  # [dict]
        self.uid_base = 1
        # [dict(name, kind, id, title, x, y, z, z_offset, z_from, radius, flatten, weight, param, facing)]
        self.pois = []
        self.roads = []  # [dict(name, shape (Polyline), texture, width, fade, strength)]
        self.scatter = []  # [dict] (checked scatter groups, see _parse_scatter)
        self.lakes = []  # [dict] (see _parse_lake)
        self.rivers = []  # [dict] (see _parse_river)
        self.generated: list[Placement] = []  # doodads the spec implies (waterfalls), placed after its own
        self.beaches = None  # dict (see _parse_beaches) or None
        self.assets: list[AssetUse] = []
        self.resolution = None  # extra_assets.Resolution, or None (every extra asset falls back)
        self.preview = True
        self.warnings: list[str] = []

    @property
    def tiles(self) -> list[tuple[int, int]]:
        return [(tx, ty) for ty in range(self.ty0, self.ty1 + 1) for tx in range(self.tx0, self.tx1 + 1)]

    def texture_index(self, name: str, where: str) -> int:
        for i, t in enumerate(self.textures):
            if t.name == name:
                return i
        raise SpecError(f"{where}: unknown texture '{name}'")

    def world_bounds(self) -> tuple[float, float, float, float]:
        """(min_x, max_x, min_y, max_y) covered by the tile range."""
        x0, _, y0, _ = coords.tile_bounds(self.tx1, self.ty1)
        _, x1, _, y1 = coords.tile_bounds(self.tx0, self.ty0)
        return (x0, x1, y0, y1)

    def mountain_features(self) -> list[dict]:
        return [f for f in self.features if f["type"] == "mountains"]


def _asset(spec: Spec, value, where: str, kind: str, extensions: tuple[str, ...]) -> tuple[str, bool, AssetUse | None]:
    """A client path, or an extra asset {"modern", "fallback", "kind"}: (the path to use, modern used, use).

    For a doodad the second value means "client tiles only": False for a modern path that resolved as a stock
    3.3.5 file, which every client and the server's extractors have, so the server copy keeps it (collision, line
    of sight)."""
    if not isinstance(value, dict):
        return normalize_path(value, where, extensions), False, None
    _check_keys(value, {"modern", "fallback", "kind"}, {"modern", "fallback"}, where)
    given = value.get("kind", kind)
    if given not in ASSET_KINDS:
        raise SpecError(f"{where}.kind: 'texture' or 'doodad'")
    if given != kind:
        raise SpecError(f"{where}.kind: '{given}', but this field takes a {kind}")
    modern = normalize_path(value["modern"], f"{where}.modern", extensions)
    fallback = normalize_path(value["fallback"], f"{where}.fallback", extensions)
    if modern.lower() == fallback.lower():
        raise SpecError(f"{where}: modern and fallback are the same path")
    for label, path in (("modern", modern), ("fallback", fallback)):
        if is_placeholder(path):
            spec.warnings.append(f"{where}.{label} {path!r} is a TODO placeholder")
    entry = spec.resolution.lookup(modern) if spec.resolution is not None else None
    if spec.resolution is None:
        used, reason = False, "no resolution file (offline build): every extra asset uses its fallback"
    elif entry is None:
        used, reason = False, "not in the resolution file (run package.py resolve-assets on this spec)"
    elif entry.get("kind") != kind:
        used, reason = False, f"resolved as a {entry.get('kind')}, used here as a {kind}"
    elif entry.get("status") != "resolved":
        used, reason = False, entry.get("reason") or "not found in the sources"
    else:
        used, reason = True, ""
    use = AssetUse(where, kind, modern, fallback, modern if used else fallback, used, reason, entry)
    spec.assets.append(use)
    return use.path, used and not (kind == "doodad" and (entry or {}).get("source") == "stock"), use


def _parse_noise(obj, where: str) -> dict:
    _check_keys(obj, {"scale", "amplitude", "octaves", "persistence", "lacunarity", "seed"}, {"scale", "amplitude"},
                where)
    return {
        "scale": _num(obj, "scale", where, lo=1.0),
        "amplitude": _num(obj, "amplitude", where),
        "octaves": _int(obj, "octaves", where, default=1, lo=1, hi=8),
        "persistence": _num(obj, "persistence", where, default=0.5, lo=0.0, hi=1.0),
        "lacunarity": _num(obj, "lacunarity", where, default=2.0, lo=1.0, hi=4.0),
        "seed": _int(obj, "seed", where, default=0),
    }


def _parse_feature(obj, where: str, spec: Spec) -> dict:
    if not isinstance(obj, dict) or "type" not in obj:
        raise SpecError(f"{where}: a feature needs a 'type'")
    kind = obj["type"]
    if kind == "hill":
        _check_keys(obj, {"type", "center", "radius", "height", "shape"}, {"center", "radius", "height"}, where)
        shape = obj.get("shape", "smooth")
        if shape not in ("smooth", "cone", "dome"):
            raise SpecError(f"{where}.shape: 'smooth', 'cone' or 'dome'")
        return {"type": "hill", "center": _vec(obj["center"], 2, f"{where}.center"),
                "radius": _num(obj, "radius", where, lo=1.0), "height": _num(obj, "height", where), "shape": shape}
    if kind in ("flatten", "plateau"):
        _check_keys(obj, {"type", "shape", "height", "offset", "falloff", "mode"}, {"shape"}, where)
        mode = obj.get("mode", "set")
        if mode not in ("set", "raise", "lower"):
            raise SpecError(f"{where}.mode: 'set', 'raise' or 'lower'")
        height = obj.get("height")
        if height is not None and (isinstance(height, bool) or not isinstance(height, (int, float))):
            raise SpecError(f"{where}.height: a number, or null for the terrain height at the shape's centre")
        return {"type": "flatten", "shape": parse_shape(obj["shape"], f"{where}.shape"),
                "height": None if height is None else float(height),
                "offset": _num(obj, "offset", where, default=0.0, lo=-coords.HEIGHT_LIMIT, hi=coords.HEIGHT_LIMIT),
                "falloff": _num(obj, "falloff", where, default=0.0, lo=0.0), "mode": mode}
    if kind == "river":
        _check_keys(obj, {"type", "path", "width", "bank", "bed"}, {"path", "width", "bed"}, where)
        path = obj["path"]
        if not isinstance(path, list) or len(path) < 2:
            raise SpecError(f"{where}.path: at least two [x, y] points")
        pts = [tuple(_vec(p, 2, f"{where}.path[{i}]")) for i, p in enumerate(path)]
        return {"type": "river", "path": pts, "width": _num(obj, "width", where, lo=0.0),
                "bank": _num(obj, "bank", where, default=0.0, lo=0.0), "bed": _num(obj, "bed", where)}
    if kind == "ramp":
        _check_keys(obj, {"type", "from", "to", "width", "falloff"}, {"from", "to", "width"}, where)
        return {"type": "ramp", "from": _vec(obj["from"], 3, f"{where}.from", allow_none_last=True),
                "to": _vec(obj["to"], 3, f"{where}.to", allow_none_last=True),
                "width": _num(obj, "width", where, lo=0.0), "falloff": _num(obj, "falloff", where, default=0.0, lo=0.0)}
    if kind == "border":
        _check_keys(obj, {"type", "inset", "width", "height", "jitter", "jitter_scale", "seed"}, {"width", "height"},
                    where)
        return {"type": "border", "inset": _num(obj, "inset", where, default=0.0, lo=0.0),
                "width": _num(obj, "width", where, lo=1.0), "height": _num(obj, "height", where),
                "jitter": _num(obj, "jitter", where, default=0.0, lo=0.0),
                "jitter_scale": _num(obj, "jitter_scale", where, default=100.0, lo=1.0),
                "seed": _int(obj, "seed", where, default=0)}
    if kind == "clamp":
        _check_keys(obj, {"type", "min", "max"}, set(), where)
        lo = _num(obj, "min", where, default=-coords.HEIGHT_LIMIT)
        hi = _num(obj, "max", where, default=coords.HEIGHT_LIMIT)
        if lo > hi:
            raise SpecError(f"{where}: min > max")
        return {"type": "clamp", "min": lo, "max": hi}
    if kind == "mountains":
        return _parse_mountains(obj, where, spec)
    if kind == "water_bodies":
        _check_keys(obj, {"type"}, set(), where)
        return {"type": "water_bodies"}
    raise SpecError(f"{where}.type: unknown feature '{kind}' (hill, flatten, plateau, river, ramp, border, mountains, "
                    "water_bodies, clamp)")


def _parse_mountains(obj, where: str, spec: Spec) -> dict:
    """A mountain range along the edge of the tile range, in place of a plain `border` cliff ring.

    `width` is the range's depth from the tile edge to its foot (the playable valley ends there); `height` the
    [lowest, highest] peaks above the foot, varied along the range by noise; `cliff` the steep wall at the foot
    that keeps players in; `layers` ridge lines from the foothills to the back range; `peak_scale` the spacing of
    peaks; `saddles` how deep the dips between them go (0..1); `ledges` terraced shelves on the faces
    ({step, flat, coverage}, or null); `jitter` / `jitter_scale` make the foot line wander; `corner_radius` rounds
    the range at the map corners.
    """
    _check_keys(obj, {"type", "width", "height", "cliff", "layers", "peak_scale", "saddles", "ledges", "jitter",
                      "jitter_scale", "corner_radius", "seed"}, {"width", "height"}, where)
    x0, x1, y0, y1 = spec.world_bounds()
    extent = min(x1 - x0, y1 - y0)
    width = _num(obj, "width", where, lo=20.0, hi=2000.0)
    if 2.0 * width + 100.0 > extent:
        raise SpecError(f"{where}.width: {width:g} yards on each side leaves less than 100 yards of valley on a "
                        f"{extent:.0f}-yard map")
    height = obj["height"]
    if isinstance(height, (int, float)) and not isinstance(height, bool):
        height = [height, height]
    hmin, hmax = _vec(height, 2, f"{where}.height")
    if not (0.0 < hmin <= hmax <= 2000.0):
        raise SpecError(f"{where}.height: [lowest, highest] peak heights, 0 < lowest <= highest <= 2000")
    cliff = obj.get("cliff", {})
    _check_keys(cliff, {"height", "width"}, set(), f"{where}.cliff")
    cliff_h = _num(cliff, "height", f"{where}.cliff", default=min(30.0, hmin * 0.5), lo=0.0)
    if cliff_h >= hmin:
        raise SpecError(f"{where}.cliff.height: {cliff_h:g} must stay below the lowest peaks ({hmin:g})")
    cliff_w = _num(cliff, "width", f"{where}.cliff", default=12.0, lo=1.0, hi=width * 0.5)
    ledges = obj.get("ledges")
    if ledges is not None and ledges is not False:
        _check_keys(ledges, {"step", "flat", "coverage"}, set(), f"{where}.ledges")
        ledges = {"step": _num(ledges, "step", f"{where}.ledges", default=16.0, lo=2.0, hi=500.0),
                  "flat": _num(ledges, "flat", f"{where}.ledges", default=0.4, lo=0.0, hi=0.9),
                  "coverage": _num(ledges, "coverage", f"{where}.ledges", default=0.5, lo=0.0, hi=1.0)}
    else:
        ledges = None
    jitter = _num(obj, "jitter", where, default=0.0, lo=0.0, hi=width * 0.5)
    return {"type": "mountains", "width": width, "height": (hmin, hmax), "cliff_height": cliff_h,
            "cliff_width": cliff_w, "layers": _int(obj, "layers", where, default=3, lo=1, hi=5),
            "peak_scale": _num(obj, "peak_scale", where, default=110.0, lo=20.0, hi=4000.0),
            "saddles": _num(obj, "saddles", where, default=0.4, lo=0.0, hi=1.0), "ledges": ledges,
            "jitter": jitter, "jitter_scale": _num(obj, "jitter_scale", where, default=220.0, lo=1.0),
            "corner_radius": _num(obj, "corner_radius", where, default=width * 1.5, lo=0.0),
            "seed": _int(obj, "seed", where, default=0)}


def _parse_rule(obj, spec: Spec, where: str) -> dict:
    _check_keys(obj, {"texture", "strength", "shape", "fade", "slope", "height", "noise"}, {"texture"}, where)
    rule = {"texture": spec.texture_index(obj["texture"], f"{where}.texture"),
            "strength": _num(obj, "strength", where, default=1.0, lo=0.0, hi=1.0),
            "shape": None, "fade": _num(obj, "fade", where, default=0.0, lo=0.0),
            "slope": None, "height": None, "noise": None}
    if "shape" in obj:
        rule["shape"] = parse_shape(obj["shape"], f"{where}.shape")
    if "slope" in obj:
        s = _check_keys(obj["slope"], {"min", "max"}, {"min", "max"}, f"{where}.slope")
        lo = _num(s, "min", f"{where}.slope", lo=0.0, hi=90.0)
        hi = _num(s, "max", f"{where}.slope", lo=0.0, hi=90.0)
        if lo == hi:
            raise SpecError(f"{where}.slope: min and max must differ (coverage ramps from min to max)")
        rule["slope"] = (coords.dcos(lo), coords.dcos(hi))  # as normal.z thresholds
    if "height" in obj:
        h = _check_keys(obj["height"], {"min", "max", "fade"}, set(), f"{where}.height")
        rule["height"] = (_num(h, "min", f"{where}.height", default=-coords.HEIGHT_LIMIT),
                          _num(h, "max", f"{where}.height", default=coords.HEIGHT_LIMIT),
                          _num(h, "fade", f"{where}.height", default=0.0, lo=0.0))
    if "noise" in obj:
        n = _check_keys(obj["noise"], {"scale", "threshold", "fade", "seed", "octaves"}, {"scale"}, f"{where}.noise")
        rule["noise"] = {"scale": _num(n, "scale", f"{where}.noise", lo=1.0),
                         "threshold": _num(n, "threshold", f"{where}.noise", default=0.0, lo=-1.0, hi=1.0),
                         "fade": _num(n, "fade", f"{where}.noise", default=0.2, lo=0.001),
                         "seed": _int(n, "seed", f"{where}.noise", default=0),
                         "octaves": _int(n, "octaves", f"{where}.noise", default=2, lo=1, hi=6)}
    return rule


def _parse_placement(obj, kind: str, where: str, spec: Spec) -> Placement:
    allowed = {"model", "position", "z_offset", "rotation", "facing", "scale", "uid", "radius", "flags", "label"}
    allowed.add("bounds")
    if kind == "wmo":
        allowed |= {"doodad_set", "name_set"}
    _check_keys(obj, allowed, {"model", "position"}, where)
    modern = False
    if kind == "doodad":
        model, modern, _ = _asset(spec, obj["model"], f"{where}.model", "doodad", (".m2", ".mdx"))
    else:
        if isinstance(obj["model"], dict):
            raise SpecError(f"{where}.model: WMOs are 3.3.5 files only (extra assets are textures and doodads: "
                            "vmap4_extractor builds the server's collision from the WMOs)")
        model = normalize_path(obj["model"], f"{where}.model", (".wmo",))
        if re.search(r"_\d{3}\.wmo$", model.lower()):
            raise SpecError(f"{where}.model: {model!r} is a WMO group file; place the root .wmo")
    x, y, z = _vec(obj["position"], 3, f"{where}.position", allow_none_last=True)
    if "rotation" in obj and "facing" in obj:
        raise SpecError(f"{where}: give 'rotation' or 'facing', not both")
    if "rotation" in obj:
        rotation = tuple(_vec(obj["rotation"], 3, f"{where}.rotation"))
    else:
        # facing: the server's orientation in degrees (0 = north/+X, counter-clockwise toward +Y/west). The client
        # turns models by rotation.y + 180 degrees about Z (CMap::CreateDoodadDef), so the model's +X axis points
        # along `facing` when rotation.y = facing - 180.
        facing = _num(obj, "facing", where, default=180.0)
        ry = (facing - 180.0) % 360.0
        rotation = (0.0, ry, 0.0)
    scale = _num(obj, "scale", where, default=1.0, lo=1.0 / 1024.0, hi=63.0)
    uid = obj.get("uid")
    if uid is not None and (isinstance(uid, bool) or not isinstance(uid, int) or not (1 <= uid <= 0xFFFFFFFF)):
        raise SpecError(f"{where}.uid: an integer 1..4294967295")
    bounds = None
    if "bounds" in obj:
        b = obj["bounds"]
        if not isinstance(b, list) or len(b) != 2:
            raise SpecError(f"{where}.bounds: [[min x, y, z], [max x, y, z]] in model space (a WMO's MOHD box, an "
                            "M2's header bounding box)")
        lo = _vec(b[0], 3, f"{where}.bounds[0]")
        hi = _vec(b[1], 3, f"{where}.bounds[1]")
        if any(lo[i] > hi[i] for i in range(3)):
            raise SpecError(f"{where}.bounds: min > max")
        bounds = (tuple(lo), tuple(hi))
    if kind == "wmo":
        if scale != 1.0:
            raise SpecError(f"{where}.scale: the 3.3.5a client does not scale WMOs (MODF has no scale it reads)")
        radius = _num(obj, "radius", where, default=32.0, lo=0.5)
        doodad_set = _int(obj, "doodad_set", where, default=0, lo=0, hi=0xFFFF)
        name_set = _int(obj, "name_set", where, default=0, lo=0, hi=0xFFFF)
        flags = _int(obj, "flags", where, default=0, lo=0, hi=0xFFFF)
        if flags & 0x1:
            raise SpecError(f"{where}.flags: 0x1 marks a destructible WMO, which the client only draws through a "
                            "GameObject (CMapChunk::CreateRefs)")
    else:
        radius = _num(obj, "radius", where, default=4.0, lo=0.1)
        doodad_set = name_set = 0
        flags = _int(obj, "flags", where, default=0, lo=0, hi=0xFFFF)
    label = obj.get("label", "")
    if not isinstance(label, str):
        raise SpecError(f"{where}.label: expected a string")
    return Placement(kind, model, x, y, z, _num(obj, "z_offset", where, default=0.0), rotation, scale, uid, radius,
                     flags, bounds, doodad_set, name_set, label, modern)


# POI kinds with fixed meanings (the Royale server's bh_royale_poi rows): the allowed `param` values and whether a
# `weight` above 0 is required. Other kinds are free-form (any integer param, any weight >= 0).
POI_KINDS = {
    "lobby": ((0,), False),
    "landmark": ((0,), False),
    "crate": ((1, 2), False),  # 1 common crate, 2 strongbox
    "orb_shadow": ((0,), False),
    "orb_buff": ((1, 2, 3), False),  # 1 speed, 2 restoration, 3 berserk
    "supply_site": ((0,), False),
    "final_site": ((0,), True),  # weight: how often the storm ends here
    "crossing": ((0,), False),
}
_POI_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_POI_TITLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '.-]{0,63}$")
MAX_POI_ID = 0x7FFFFFFF


def _parse_poi(mk, where: str, spec: Spec, names: set, ids: set) -> dict:
    _check_keys(mk, {"name", "kind", "position", "z_offset", "radius", "flatten", "id", "title", "facing", "weight",
                     "param", "z_from"}, {"name", "position"}, where)
    name = mk["name"]
    if not isinstance(name, str) or not _POI_NAME_RE.match(name) or name in names:
        raise SpecError(f"{where}.name: a unique name of letters, digits, '_', '-', '.' (the server's spawn "
                        "tables key on it)")
    names.add(name)
    kind = mk.get("kind", "poi")
    if not isinstance(kind, str) or not kind:
        raise SpecError(f"{where}.kind: a non-empty string (e.g. landmark, crate, orb_buff, final_site)")
    poi_id = None
    if "id" in mk:
        poi_id = _int(mk, "id", where, lo=1, hi=MAX_POI_ID)
        if poi_id in ids:
            raise SpecError(f"{where}.id: {poi_id} is already used by another POI")
        ids.add(poi_id)
    title = mk.get("title", "")
    if not isinstance(title, str) or (title and not _POI_TITLE_RE.match(title)):
        raise SpecError(f"{where}.title: up to 64 letters, digits, spaces, apostrophes, dots and hyphens, starting "
                        "with a letter or digit (the name players see)")
    x, y, z = _vec(mk["position"], 3, f"{where}.position", allow_none_last=True)
    radius = _num(mk, "radius", where, default=0.0, lo=0.0)
    weight = _int(mk, "weight", where, default=0, lo=0, hi=1000000)
    param = _int(mk, "param", where, default=0, lo=-0x80000000, hi=0x7FFFFFFF)
    facing = _num(mk, "facing", where, default=0.0, lo=-360.0, hi=360.0)
    rule = POI_KINDS.get(kind)
    if rule is not None:
        params, needs_weight = rule
        if param not in params:
            raise SpecError(f"{where}.param: a '{kind}' POI takes param {' or '.join(map(str, params))}")
        if needs_weight and weight <= 0:
            raise SpecError(f"{where}.weight: a '{kind}' POI needs a weight above 0")
        if not needs_weight and weight != 0:
            raise SpecError(f"{where}.weight: only final_site POIs carry a weight")
    z_from = mk.get("z_from")
    if z_from is not None:
        if not isinstance(z_from, str) or not z_from:
            raise SpecError(f"{where}.z_from: the label of a WMO or doodad placement")
        if z is not None:
            raise SpecError(f"{where}: give a z in 'position' or 'z_from', not both")
    flatten = mk.get("flatten", False)
    falloff = None
    if flatten is True:
        falloff = max(4.0, radius * 0.75)
    elif isinstance(flatten, dict):
        _check_keys(flatten, {"falloff"}, set(), f"{where}.flatten")
        falloff = _num(flatten, "falloff", f"{where}.flatten", default=max(4.0, radius * 0.75), lo=0.0)
    elif flatten is not False:
        raise SpecError(f"{where}.flatten: true, false or {{\"falloff\": yards}}")
    if falloff is not None and radius <= 0.0:
        raise SpecError(f"{where}: a flattened point needs a radius")
    if falloff is not None and z_from is not None:
        raise SpecError(f"{where}: a point standing on a placement (z_from) cannot flatten the terrain")
    if falloff is not None:
        # Flatten after every heightmap feature, to the terrain height at the centre (or the given z). The circle is
        # one quad (UNIT_SIZE) wider than the radius: a point's triangle uses vertices up to one quad away, so this
        # keeps the ground flat across the whole stated radius.
        spec.features.append({"type": "flatten",
                              "shape": parse_shape({"circle": {"center": [x, y], "radius": radius + coords.UNIT_SIZE}},
                                                   f"{where}.flatten"),
                              "height": z, "offset": 0.0, "falloff": falloff, "mode": "set"})
    return {"name": name, "kind": kind, "id": poi_id, "title": title, "x": x, "y": y, "z": z,
            "z_offset": _num(mk, "z_offset", where, default=0.0), "z_from": z_from, "radius": radius,
            "flatten": falloff, "weight": weight, "param": param, "facing": facing % 360.0}


def _assign_poi_ids(pois: list) -> None:
    """POIs without an id get the next free one from 1 up, in spec order."""
    used = {p["id"] for p in pois if p["id"] is not None}
    next_id = 1
    for p in pois:
        if p["id"] is None:
            while next_id in used:
                next_id += 1
            p["id"] = next_id
            used.add(next_id)


def _points(value, where: str, minimum: int = 2) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) < minimum:
        raise SpecError(f"{where}: at least {minimum} [x, y] points")
    return [tuple(_vec(p, 2, f"{where}[{i}]")) for i, p in enumerate(value)]


def _parse_road(obj, spec: Spec, names: set, where: str) -> dict:
    """A road: a texture painted along a polyline (and a mask the scatter groups keep clear of)."""
    _check_keys(obj, {"name", "points", "width", "fade", "texture", "strength"}, {"name", "points", "texture"}, where)
    name = obj["name"]
    if not isinstance(name, str) or not _POI_NAME_RE.match(name) or name in names:
        raise SpecError(f"{where}.name: a unique name of letters, digits, '_', '-', '.'")
    names.add(name)
    width = _num(obj, "width", where, default=7.0, lo=1.0, hi=60.0)
    points = _points(obj["points"], f"{where}.points")
    return {"name": name, "points": points, "shape": parse_shape({"polyline": {"points": [list(p) for p in points],
                                                                                "width": width}}, where),
            "texture": spec.texture_index(obj["texture"], f"{where}.texture"), "width": width,
            "fade": _num(obj, "fade", where, default=4.0, lo=0.0, hi=100.0),
            "strength": _num(obj, "strength", where, default=1.0, lo=0.0, hi=1.0)}


def _road_rule(road: dict) -> dict:
    return {"texture": road["texture"], "strength": road["strength"], "shape": road["shape"], "fade": road["fade"],
            "slope": None, "height": None, "noise": None}


# Scatter: deterministic cover. Each group throws one candidate into every cell of a jittered grid (cell size
# sqrt(10000 / density) yards), keeps those that pass its masks and its spacing, and turns them into doodads.
SCATTER_CLEARANCES = ("roads", "river", "pois", "placements")
MAX_SCATTER_CANDIDATES = 200000


def _parse_scatter(obj, where: str, names: set, spec: Spec) -> dict:
    _check_keys(obj, {"name", "seed", "models", "density", "count", "min_spacing", "shape", "exclude", "slope",
                      "height", "clearance", "poi_kinds", "noise", "facing", "dry"},
                {"name", "models", "density"}, where)
    name = obj["name"]
    if not isinstance(name, str) or not _POI_NAME_RE.match(name) or name in names:
        raise SpecError(f"{where}.name: a unique name of letters, digits, '_', '-', '.' (it labels the placements)")
    names.add(name)
    models = obj["models"]
    if not isinstance(models, list) or not models:
        raise SpecError(f"{where}.models: at least one {{model, weight}}")
    out_models = []
    for i, m in enumerate(models):
        mw = f"{where}.models[{i}]"
        _check_keys(m, {"model", "weight", "radius", "body", "scale", "z_offset"}, {"model"}, mw)
        model, modern, _ = _asset(spec, m["model"], f"{mw}.model", "doodad", (".m2", ".mdx"))
        if is_placeholder(model):
            spec.warnings.append(f"{mw}.model {model!r} is a TODO placeholder")
        radius = _num(m, "radius", mw, default=4.0, lo=0.1, hi=200.0)
        scale = m.get("scale", [1.0, 1.0])
        if isinstance(scale, (int, float)) and not isinstance(scale, bool):
            scale = [scale, scale]
        lo, hi = _vec(scale, 2, f"{mw}.scale")
        if not (1.0 / 1024.0 <= lo <= hi <= 63.0):
            raise SpecError(f"{mw}.scale: [min, max] with 1/1024 <= min <= max <= 63")
        out_models.append({"model": model, "modern": modern,
                           "weight": _num(m, "weight", mw, default=1.0, lo=0.0, hi=1000.0),
                           "radius": radius, "body": _num(m, "body", mw, default=radius * 0.5, lo=0.0, hi=200.0),
                           "scale": (lo, hi), "z_offset": _num(m, "z_offset", mw, default=0.0, lo=-50.0, hi=50.0)})
    if sum(m["weight"] for m in out_models) <= 0.0:
        raise SpecError(f"{where}.models: the weights add up to 0")
    if not isinstance(obj.get("dry", True), bool):
        raise SpecError(f"{where}.dry: true (keep out of water, the default) or false")
    if not isinstance(obj.get("exclude", []), list):
        raise SpecError(f"{where}.exclude: a list of shapes")
    group = {"name": name, "seed": _int(obj, "seed", where, default=0, lo=0, hi=0xFFFFFFFF), "models": out_models,
             "density": _num(obj, "density", where, lo=0.001, hi=10000.0),
             "count": _int(obj, "count", where, lo=1, hi=100000) if "count" in obj else None,
             "min_spacing": _num(obj, "min_spacing", where, default=0.0, lo=0.0, hi=1000.0),
             "shape": parse_shape(obj["shape"], f"{where}.shape") if "shape" in obj else None,
             "exclude": [], "slope": None, "height": None, "noise": None, "poi_kinds": None,
             "facing": None, "dry": obj.get("dry", True)}
    for i, shape in enumerate(obj.get("exclude", [])):
        group["exclude"].append(parse_shape(shape, f"{where}.exclude[{i}]"))
    if "slope" in obj:
        s = _check_keys(obj["slope"], {"max"}, {"max"}, f"{where}.slope")
        group["slope"] = coords.dcos(_num(s, "max", f"{where}.slope", lo=0.0, hi=90.0))  # as a normal.z floor
    if "height" in obj:
        h = _check_keys(obj["height"], {"min", "max"}, set(), f"{where}.height")
        lo = _num(h, "min", f"{where}.height", default=-coords.HEIGHT_LIMIT)
        hi = _num(h, "max", f"{where}.height", default=coords.HEIGHT_LIMIT)
        if lo > hi:
            raise SpecError(f"{where}.height: min > max")
        group["height"] = (lo, hi)
    clear = _check_keys(obj.get("clearance", {}), set(SCATTER_CLEARANCES), set(), f"{where}.clearance")
    # None = that mask is off; the clearance from the spec's own placements is always on (1 yard by default).
    group["clearance"] = {k: (_num(clear, k, f"{where}.clearance", lo=0.0, hi=1000.0) if k in clear else None)
                          for k in SCATTER_CLEARANCES}
    if group["clearance"]["placements"] is None:
        group["clearance"]["placements"] = 1.0
    if "poi_kinds" in obj:
        kinds = obj["poi_kinds"]
        if not isinstance(kinds, list) or not all(isinstance(k, str) and k for k in kinds):
            raise SpecError(f"{where}.poi_kinds: a list of POI kinds the 'pois' clearance applies to")
        group["poi_kinds"] = set(kinds)
    if "noise" in obj:
        n = _check_keys(obj["noise"], {"scale", "threshold", "fade", "seed", "octaves"}, {"scale"}, f"{where}.noise")
        group["noise"] = {"scale": _num(n, "scale", f"{where}.noise", lo=1.0),
                          "threshold": _num(n, "threshold", f"{where}.noise", default=0.0, lo=-1.0, hi=1.0),
                          "fade": _num(n, "fade", f"{where}.noise", default=0.2, lo=0.001),
                          "seed": _int(n, "seed", f"{where}.noise", default=0),
                          "octaves": _int(n, "octaves", f"{where}.noise", default=2, lo=1, hi=6)}
    if "facing" in obj:
        group["facing"] = _num(obj, "facing", where, lo=-360.0, hi=360.0)
    x0, x1, y0, y1 = group["shape"].bbox() if group["shape"] is not None else spec.world_bounds()
    cell = (10000.0 / group["density"]) ** 0.5
    candidates = (int((x1 - x0) / cell) + 1) * (int((y1 - y0) / cell) + 1)
    if candidates > MAX_SCATTER_CANDIDATES:
        raise SpecError(f"{where}.density: {candidates} candidate cells (at most {MAX_SCATTER_CANDIDATES}); lower "
                        "the density or give a smaller shape")
    group["cell"] = cell
    return group


# --- water: lakes and rivers -------------------------------------------------------------------------------------

_WATER_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _water_name(obj, where: str, names: set) -> str:
    name = obj["name"]
    if not isinstance(name, str) or not _WATER_NAME_RE.match(name) or name in names:
        raise SpecError(f"{where}.name: a unique name of letters, digits, '_', '-', '.' (lakes and rivers share one "
                        "name space)")
    names.add(name)
    return name


def _parse_lake(obj, where: str, names: set) -> dict:
    """A lake or lagoon: still water at `level` inside `shape`; the terrain is carved into a basin `depth` yards
    deep (reached `shelf` yards in from the shore), the land within `shore` yards outside blends to `freeboard`
    above the water, and `islands` rise out of it."""
    _check_keys(obj, {"name", "liquid_type", "level", "shape", "depth", "shelf", "shore", "freeboard", "min_depth",
                      "islands"}, {"name", "level", "shape"}, where)
    lake = {"name": _water_name(obj, where, names),
            "liquid_type": _int(obj, "liquid_type", where, default=1, lo=1, hi=21),
            "level": _num(obj, "level", where, lo=-coords.HEIGHT_LIMIT, hi=coords.HEIGHT_LIMIT),
            "shape": parse_shape(obj["shape"], f"{where}.shape"),
            "depth": _num(obj, "depth", where, default=6.0, lo=0.25, hi=500.0),
            "shelf": _num(obj, "shelf", where, default=25.0, lo=1.0, hi=2000.0),
            "shore": _num(obj, "shore", where, default=30.0, lo=0.0, hi=2000.0),
            "freeboard": _num(obj, "freeboard", where, default=0.8, lo=0.0, hi=50.0),
            "min_depth": _num(obj, "min_depth", where, default=0.1, lo=0.0, hi=50.0),
            "islands": []}
    islands = obj.get("islands", [])
    if not isinstance(islands, list):
        raise SpecError(f"{where}.islands: a list of {{center, radius, height}}")
    for i, isl in enumerate(islands):
        iw = f"{where}.islands[{i}]"
        _check_keys(isl, {"center", "radius", "height"}, {"center", "radius", "height"}, iw)
        lake["islands"].append({"center": tuple(_vec(isl["center"], 2, f"{iw}.center")),
                                "radius": _num(isl, "radius", iw, lo=2.0, hi=2000.0),
                                "height": _num(isl, "height", iw, lo=0.5, hi=500.0)})
    return lake


def _parse_waterfall(obj, where: str, spec: Spec) -> dict:
    """The models for every step of a river: `model` at the step, `splash` at its foot. The paths come from the
    asset kit, so the spec names them (plain 3.3.5 paths or extra assets with a fallback)."""
    _check_keys(obj, {"model", "splash", "height", "scale", "anchor", "z_offset", "facing_offset", "splash_offset",
                      "splash_scale", "splash_z_offset", "radius"}, {"model"}, where)
    model, modern, _ = _asset(spec, obj["model"], f"{where}.model", "doodad", (".m2", ".mdx"))
    splash = None
    splash_modern = False
    if obj.get("splash") is not None:
        splash, splash_modern, _ = _asset(spec, obj["splash"], f"{where}.splash", "doodad", (".m2", ".mdx"))
    anchor = obj.get("anchor", "top")
    if anchor not in ("top", "bottom"):
        raise SpecError(f"{where}.anchor: 'top' (the model's origin is at the lip) or 'bottom' (at the foot)")
    native = obj.get("height")
    if native is not None:
        native = _num(obj, "height", where, lo=0.1, hi=1000.0)
    return {"model": model, "modern": modern, "splash": splash, "splash_modern": splash_modern, "height": native,
            "scale": _num(obj, "scale", where, default=1.0, lo=1.0 / 1024.0, hi=63.0), "anchor": anchor,
            "z_offset": _num(obj, "z_offset", where, default=0.0, lo=-200.0, hi=200.0),
            "facing_offset": _num(obj, "facing_offset", where, default=0.0, lo=-360.0, hi=360.0),
            "splash_offset": _num(obj, "splash_offset", where, default=3.0, lo=-100.0, hi=100.0),
            "splash_scale": _num(obj, "splash_scale", where, default=1.0, lo=1.0 / 1024.0, hi=63.0),
            "splash_z_offset": _num(obj, "splash_z_offset", where, default=0.0, lo=-50.0, hi=50.0),
            "radius": _num(obj, "radius", where, default=8.0, lo=0.5, hi=200.0)}


def _parse_river(obj, where: str, names: set, spec: Spec) -> dict:
    """A river: `reaches` from the source to the mouth, each holding its water at one `level` (falling
    downstream). Reach k + 1 continues from the last point of reach k; where the level drops the river falls (a
    waterfall model at the step, a splash below it). The channel is `width` wide and `depth` deep, the banks
    blend back to the terrain over `bank` yards and stand `freeboard` above the water at its edge, and each step
    is spread over `fall_run` yards of the bed."""
    _check_keys(obj, {"name", "liquid_type", "width", "depth", "bank", "freeboard", "min_depth", "fall_run",
                      "reaches", "waterfall"}, {"name", "width", "reaches"}, where)
    name = _water_name(obj, where, names)
    reaches = obj["reaches"]
    if not isinstance(reaches, list) or not reaches:
        raise SpecError(f"{where}.reaches: at least one {{level, path}}")
    points: list[tuple[float, float]] = []
    seg_reach: list[int] = []
    levels: list[float] = []
    starts = []  # index into points where each reach begins
    for k, reach in enumerate(reaches):
        rw = f"{where}.reaches[{k}]"
        _check_keys(reach, {"level", "path"}, {"level", "path"}, rw)
        level = _num(reach, "level", rw, lo=-coords.HEIGHT_LIMIT, hi=coords.HEIGHT_LIMIT)
        if levels and level > levels[-1]:
            raise SpecError(f"{rw}.level: {level:g} is above the reach before it ({levels[-1]:g}); a river only "
                            "steps down toward its mouth")
        path = _points(reach["path"], f"{rw}.path", minimum=2 if k == 0 else 1)
        if points and path[0] == points[-1]:
            path = path[1:]
        if not path:
            raise SpecError(f"{rw}.path: needs a point beyond the end of the reach before it")
        starts.append(len(points) - 1 if points else 0)
        for pt in path:
            if points:
                seg_reach.append(k)
            points.append(pt)
        levels.append(level)
    width = _num(obj, "width", where, lo=2.0, hi=300.0)
    river = {"name": name, "liquid_type": _int(obj, "liquid_type", where, default=1, lo=1, hi=21), "width": width,
             "depth": _num(obj, "depth", where, default=2.5, lo=0.25, hi=100.0),
             "bank": _num(obj, "bank", where, default=12.0, lo=0.0, hi=500.0),
             "freeboard": _num(obj, "freeboard", where, default=0.6, lo=0.0, hi=50.0),
             "min_depth": _num(obj, "min_depth", where, default=0.1, lo=0.0, hi=50.0),
             "fall_run": _num(obj, "fall_run", where, default=4.0, lo=0.0, hi=100.0), "levels": levels,
             "points": points, "falls": [], "waterfall": None}
    river["path"] = RiverPath(points, seg_reach, levels, width, river["fall_run"])
    x0, x1, y0, y1 = spec.world_bounds()
    for i, (px, py) in enumerate(points):
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            raise SpecError(f"{where}: point ({px:g}, {py:g}) is outside the map's tiles")
    for k in range(1, len(reaches)):
        drop = levels[k - 1] - levels[k]
        if drop <= 0.0:
            continue
        j = starts[k]
        ax, ay = points[j]
        bx, by = points[j + 1]
        dx, dy = bx - ax, by - ay
        flow = coords.datan2(dy, dx)  # the server's facing: 0 = north (+X), counter-clockwise toward +Y
        river["falls"].append({"reach": k, "x": ax, "y": ay, "top": levels[k - 1], "bottom": levels[k],
                               "drop": drop, "facing": flow % 360.0})
    if obj.get("waterfall") is not None:
        river["waterfall"] = _parse_waterfall(obj["waterfall"], f"{where}.waterfall", spec)
    elif river["falls"]:
        spec.warnings.append(f"{where}: {len(river['falls'])} steps but no 'waterfall' models; the water just steps")
    return river


def _waterfall_placements(river: dict) -> list[Placement]:
    """One waterfall doodad at each step (scaled to the drop when the model's own drop is known) and a splash at
    its foot, `splash_offset` yards downstream."""
    wf = river["waterfall"]
    out: list[Placement] = []
    if wf is None:
        return out
    for n, fall in enumerate(river["falls"], start=1):
        facing = (fall["facing"] + wf["facing_offset"]) % 360.0
        rotation = (0.0, (facing - 180.0) % 360.0, 0.0)
        scale = wf["scale"] if wf["height"] is None else min(63.0, max(1.0 / 1024.0, fall["drop"] / wf["height"]))
        z = (fall["top"] if wf["anchor"] == "top" else fall["bottom"]) + wf["z_offset"]
        out.append(Placement("doodad", wf["model"], fall["x"], fall["y"], z, 0.0, rotation, scale, None,
                             wf["radius"] * scale, 0, None, 0, 0, f"{river['name']} fall {n}", wf["modern"]))
        if wf["splash"] is not None:
            sx = fall["x"] + coords.dcos(fall["facing"]) * wf["splash_offset"]
            sy = fall["y"] + coords.dsin(fall["facing"]) * wf["splash_offset"]
            out.append(Placement("doodad", wf["splash"], sx, sy, fall["bottom"] + wf["splash_z_offset"], 0.0,
                                 rotation, wf["splash_scale"], None, wf["radius"] * wf["splash_scale"], 0, None, 0,
                                 0, f"{river['name']} splash {n}", wf["splash_modern"]))
    return out


# --- beaches ------------------------------------------------------------------------------------------------------


def _parse_beaches(obj, spec: Spec) -> dict:
    """Automatic shore textures: `sand` within `width` yards of every water edge and at most `height` above the
    water, `wet_sand` at the waterline (`wet_width` yards up the shore, `wet_height` above and `wet_depth` below
    the surface), `riverbed` under river water deeper than that and `lakebed` (default: the riverbed) under lakes.
    `slope_max` keeps sand off cliffs; `edge_noise` breaks up the band's width; no sand or wet sand within
    `fall_clearance` yards of a waterfall (its face is rock) or inside an `exclude` shape (a mountain gorge)."""
    where = "beaches"
    _check_keys(obj, {"sand", "wet_sand", "riverbed", "lakebed", "width", "fade", "height", "height_fade",
                      "wet_width", "wet_height", "wet_depth", "bed_fade", "slope_max", "edge_noise", "noise_scale",
                      "seed", "strength", "exclude", "fall_clearance"}, {"sand"}, where)
    if not isinstance(obj.get("exclude", []), list):
        raise SpecError(f"{where}.exclude: a list of shapes")

    def tex(key):
        name = obj.get(key)
        return None if name is None else spec.texture_index(name, f"{where}.{key}")

    slope = _num(obj, "slope_max", where, default=32.0, lo=1.0, hi=89.0)
    out = {"sand": tex("sand"), "wet_sand": tex("wet_sand"), "riverbed": tex("riverbed"), "lakebed": tex("lakebed"),
           "width": _num(obj, "width", where, default=14.0, lo=0.5, hi=300.0),
           "fade": _num(obj, "fade", where, default=5.0, lo=0.0, hi=100.0),
           "height": _num(obj, "height", where, default=2.5, lo=0.0, hi=100.0),
           "height_fade": _num(obj, "height_fade", where, default=1.5, lo=0.0, hi=50.0),
           "wet_width": _num(obj, "wet_width", where, default=3.0, lo=0.0, hi=100.0),
           "wet_height": _num(obj, "wet_height", where, default=0.6, lo=0.0, hi=20.0),
           "wet_depth": _num(obj, "wet_depth", where, default=0.9, lo=0.0, hi=50.0),
           "bed_fade": _num(obj, "bed_fade", where, default=0.8, lo=0.01, hi=50.0),
           "slope_max": slope, "slope_nz": (coords.dcos(slope - 4.0), coords.dcos(slope + 4.0)),
           "edge_noise": _num(obj, "edge_noise", where, default=0.3, lo=0.0, hi=0.9),
           "noise_scale": _num(obj, "noise_scale", where, default=45.0, lo=1.0),
           "seed": _int(obj, "seed", where, default=0),
           "strength": _num(obj, "strength", where, default=1.0, lo=0.0, hi=1.0),
           "exclude": [parse_shape(sh, f"{where}.exclude[{i}]") for i, sh in enumerate(obj.get("exclude", []))],
           "fall_clearance": _num(obj, "fall_clearance", where, default=18.0, lo=0.0, hi=500.0),
           "falls": [(f["x"], f["y"]) for r in spec.rivers for f in r["falls"]]}
    if out["lakebed"] is None:
        out["lakebed"] = out["riverbed"]
    return out


def _beach_rules(beaches: dict) -> list[dict]:
    """The texture rules a beaches section paints, in order: sand, then wet sand, then the beds under water."""
    rules = [{"kind": "beach", "part": "sand", "texture": beaches["sand"]}]
    if beaches["wet_sand"] is not None:
        rules.append({"kind": "beach", "part": "wet", "texture": beaches["wet_sand"]})
    if beaches["riverbed"] is not None:
        rules.append({"kind": "beach", "part": "riverbed", "texture": beaches["riverbed"]})
    if beaches["lakebed"] is not None and beaches["lakebed"] != beaches["riverbed"]:
        rules.append({"kind": "beach", "part": "lakebed", "texture": beaches["lakebed"]})
    for r in rules:
        r["beaches"] = beaches
    return rules


def parse_spec(data: dict, resolution=None) -> Spec:
    """Check a spec. `resolution` (extra_assets.Resolution) says which extra assets' modern files were found;
    without it every extra asset uses its fallback."""
    spec = Spec()
    spec.resolution = resolution
    top = {"format", "map", "seed", "area_id", "areas", "heightmap", "textures", "texture_rules", "holes", "doodads",
           "wmos", "water", "uid_base", "pois", "preview", "roads", "scatter", "lakes", "rivers", "beaches"}
    _check_keys(data, top, {"map", "heightmap", "textures"}, "spec")
    fmt = data.get("format", FORMAT)
    if fmt != FORMAT:
        raise SpecError(f"spec.format: expected '{FORMAT}', got {fmt!r}")

    m = _check_keys(data["map"], {"directory", "tiles", "id"}, {"directory", "tiles"}, "map")
    spec.map_id = _int(m, "id", "map", default=0, lo=0, hi=0xFFFF) if "id" in m else None
    directory = m["directory"]
    if not isinstance(directory, str) or not _DIR_RE.match(directory):
        raise SpecError("map.directory: letters, digits and '_', starting with a letter, at most 63 characters "
                        "(it is Map.dbc's Directory and the folder under World\\Maps)")
    spec.directory = directory
    t = _check_keys(m["tiles"], {"x", "y"}, {"x", "y"}, "map.tiles")
    for axis in ("x", "y"):
        r = t[axis]
        if not isinstance(r, list) or len(r) != 2 or not all(isinstance(v, int) and not isinstance(v, bool)
                                                              for v in r):
            raise SpecError(f"map.tiles.{axis}: [first, last] tile index")
        if not (0 <= r[0] <= r[1] <= 63):
            raise SpecError(f"map.tiles.{axis}: indices 0..63, first <= last")
    spec.tx0, spec.tx1 = m["tiles"]["x"]
    spec.ty0, spec.ty1 = m["tiles"]["y"]
    if len(spec.tiles) > 64:
        raise SpecError("map.tiles: more than 64 tiles; MapForge v1 is meant for battleground-sized maps")

    spec.seed = _int(data, "seed", "spec", default=0, lo=0, hi=0xFFFFFFFF)
    spec.area_id = _int(data, "area_id", "spec", default=0, lo=0, hi=0xFFFFFFFF)
    spec.uid_base = _int(data, "uid_base", "spec", default=1, lo=1, hi=0xFFFFFFFF)
    spec.preview = bool(data.get("preview", True))
    for i, a in enumerate(data.get("areas", [])):
        w = f"areas[{i}]"
        _check_keys(a, {"area_id", "shape"}, {"area_id", "shape"}, w)
        spec.areas.append((_int(a, "area_id", w, lo=0, hi=0xFFFFFFFF), parse_shape(a["shape"], f"{w}.shape")))

    hm = _check_keys(data["heightmap"], {"base", "noise", "features"}, set(), "heightmap")
    spec.base_height = _num(hm, "base", "heightmap", default=0.0, lo=-coords.HEIGHT_LIMIT, hi=coords.HEIGHT_LIMIT)
    spec.noise = [_parse_noise(n, f"heightmap.noise[{i}]") for i, n in enumerate(hm.get("noise", []))]
    features = [_parse_feature(f, f"heightmap.features[{i}]", spec) for i, f in enumerate(hm.get("features", []))]
    markers = [i for i, f in enumerate(features) if f["type"] == "water_bodies"]
    if len(markers) > 1:
        raise SpecError("heightmap.features: at most one {\"type\": \"water_bodies\"} entry")

    # Lakes, then rivers, carve the terrain where the features list holds {"type": "water_bodies"}, or after every
    # feature (before the POIs flatten their spots) when it holds none.
    water_names: set = set()
    for key in ("lakes", "rivers"):
        if not isinstance(data.get(key, []), list):
            raise SpecError(f"{key}: expected a list")
    spec.lakes = [_parse_lake(o, f"lakes[{i}]", water_names) for i, o in enumerate(data.get("lakes", []))]
    spec.rivers = [_parse_river(o, f"rivers[{i}]", water_names, spec) for i, o in enumerate(data.get("rivers", []))]
    carve = [{"type": "lake", "lake": lake, "lakes": spec.lakes} for lake in spec.lakes] + \
            [{"type": "river_reaches", "river": river, "lakes": spec.lakes} for river in spec.rivers]
    if markers:
        features[markers[0]:markers[0] + 1] = carve
    else:
        features += carve
    spec.features = features

    textures = data["textures"]
    if not isinstance(textures, list) or not textures:
        raise SpecError("textures: at least one texture (the first one is the ground everywhere)")
    names = set()
    paths = set()
    for i, tex in enumerate(textures):
        w = f"textures[{i}]"
        _check_keys(tex, {"name", "path", "color", "effect_id", "mtxf_flags"}, {"name", "path"}, w)
        name = tex["name"]
        if not isinstance(name, str) or not name or name in names:
            raise SpecError(f"{w}.name: a unique non-empty name")
        names.add(name)
        path, modern, use = _asset(spec, tex["path"], f"{w}.path", "texture", (".blp",))
        if path.lower() in paths:
            raise SpecError(f"{w}.path: {path!r} is listed twice")
        paths.add(path.lower())
        if is_placeholder(path):
            spec.warnings.append(f"{w}.path {path!r} is a TODO placeholder")
        color = _color(tex.get("color", "#808080"), f"{w}.color")
        mtxf = _int(tex, "mtxf_flags", w, default=0, lo=0, hi=0xFFFFFFFF)
        if modern:
            # A modern texture without a shipped _s.blp needs MTXF flag 1, or a client with specular terrain on
            # loads the missing <name>_s.blp (CMapArea::LoadTerrainTexture). `mtxf_flags` is the fallback's.
            mtxf = 0 if use.entry.get("specular") else 1
        spec.textures.append(Texture(name, path, color, _int(tex, "effect_id", w, default=0, lo=0, hi=0xFFFFFFFF),
                                     mtxf, modern))
    road_names = set()
    spec.roads = [_parse_road(r, spec, road_names, f"roads[{i}]") for i, r in enumerate(data.get("roads", []))]
    # Roads paint where the rule list holds {"roads": true}, or before every rule when it holds none (so later rules,
    # a paved courtyard or rock on cliffs, paint over them).
    if data.get("beaches") is not None:
        spec.beaches = _parse_beaches(data["beaches"], spec)
        if not (data.get("water") or spec.lakes or spec.rivers):
            spec.warnings.append("beaches: the spec has no water, so no shore gets sand")
    rules = data.get("texture_rules", [])
    if not isinstance(rules, list):
        raise SpecError("texture_rules: expected a list")
    markers = [i for i, r in enumerate(rules) if isinstance(r, dict) and "roads" in r]
    if len(markers) > 1:
        raise SpecError("texture_rules: at most one {\"roads\": true} entry")
    beach_markers = [i for i, r in enumerate(rules) if isinstance(r, dict) and "beaches" in r]
    if len(beach_markers) > 1:
        raise SpecError("texture_rules: at most one {\"beaches\": true} entry")
    if beach_markers and spec.beaches is None:
        raise SpecError(f"texture_rules[{beach_markers[0]}]: a {{\"beaches\": true}} entry needs a 'beaches' section")
    road_rules = [_road_rule(r) for r in spec.roads]
    beach_rules = _beach_rules(spec.beaches) if spec.beaches is not None else []
    if not markers:
        spec.texture_rules = list(road_rules)
    for i, r in enumerate(rules):
        if i in markers:
            _check_keys(r, {"roads"}, {"roads"}, f"texture_rules[{i}]")
            if r["roads"] is not True:
                raise SpecError(f"texture_rules[{i}].roads: true (the roads paint here)")
            spec.texture_rules += road_rules
            continue
        if i in beach_markers:
            _check_keys(r, {"beaches"}, {"beaches"}, f"texture_rules[{i}]")
            if r["beaches"] is not True:
                raise SpecError(f"texture_rules[{i}].beaches: true (the beaches paint here)")
            spec.texture_rules += beach_rules
            continue
        spec.texture_rules.append(_parse_rule(r, spec, f"texture_rules[{i}]"))
    if not beach_markers:
        # Without a marker the shore paints last, over everything (sand must show at every water edge).
        spec.texture_rules += beach_rules

    for i, h in enumerate(data.get("holes", [])):
        _check_keys(h, {"shape"}, {"shape"}, f"holes[{i}]")
        spec.holes.append(parse_shape(h["shape"], f"holes[{i}].shape"))

    for i, d in enumerate(data.get("doodads", [])):
        p = _parse_placement(d, "doodad", f"doodads[{i}]", spec)
        if is_placeholder(p.model):
            spec.warnings.append(f"doodads[{i}].model {p.model!r} is a TODO placeholder")
        if p.model.lower().endswith(".mdx"):
            spec.warnings.append(f"doodads[{i}].model {p.model!r}: 3.3.5a ships .m2 files")
        spec.doodads.append(p)
    for i, d in enumerate(data.get("wmos", [])):
        p = _parse_placement(d, "wmo", f"wmos[{i}]", spec)
        if is_placeholder(p.model):
            spec.warnings.append(f"wmos[{i}].model {p.model!r} is a TODO placeholder")
        spec.wmos.append(p)

    poi_names = set()
    poi_ids = set()
    for i, mk in enumerate(data.get("pois", [])):
        spec.pois.append(_parse_poi(mk, f"pois[{i}]", spec, poi_names, poi_ids))
    _assign_poi_ids(spec.pois)

    for i, w in enumerate(data.get("water", [])):
        where = f"water[{i}]"
        _check_keys(w, {"liquid_type", "height", "shape", "min_depth"}, {"height", "shape"}, where)
        liquid_type = _int(w, "liquid_type", where, default=1, lo=1, hi=21)
        spec.water.append({"liquid_type": liquid_type, "height": _num(w, "height", where),
                           "shape": parse_shape(w["shape"], f"{where}.shape"),
                           "min_depth": _num(w, "min_depth", where, default=0.0, lo=0.0)})

    for river in spec.rivers:
        spec.generated += _waterfall_placements(river)

    scatter_names = set()
    groups = data.get("scatter", [])
    if not isinstance(groups, list):
        raise SpecError("scatter: expected a list of groups")
    spec.scatter = [_parse_scatter(g, f"scatter[{i}]", scatter_names, spec) for i, g in enumerate(groups)]
    return spec


def load_spec(path: str, resolution=None) -> Spec:
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise SpecError(f"{path}: invalid JSON: {e}") from None
    return parse_spec(data, resolution)
