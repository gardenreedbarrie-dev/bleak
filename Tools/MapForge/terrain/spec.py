"""Load and check a terrain map spec (JSON).

Every object is checked for unknown keys (a typo is an error, not a silently ignored setting). Keys starting with
"_" are comments and are ignored everywhere. See Tools/MapForge/README.md, section "Terrain", for the format.
"""

from __future__ import annotations

import json
import re

from . import coords
from .shapes import parse_shape
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


class Texture:
    def __init__(self, name, path, color, effect_id, mtxf_flags):
        self.name = name
        self.path = path
        self.color = color
        self.effect_id = effect_id
        self.mtxf_flags = mtxf_flags


class Placement:
    def __init__(self, kind, model, x, y, z, z_offset, rotation, scale, uid, radius, flags, bounds, doodad_set,
                 name_set, label):
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
        self.pois = []  # [dict(name, kind, x, y, z, z_offset, radius, flatten)]
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


def _parse_feature(obj, where: str) -> dict:
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
        _check_keys(obj, {"type", "shape", "height", "falloff", "mode"}, {"shape"}, where)
        mode = obj.get("mode", "set")
        if mode not in ("set", "raise", "lower"):
            raise SpecError(f"{where}.mode: 'set', 'raise' or 'lower'")
        height = obj.get("height")
        if height is not None and (isinstance(height, bool) or not isinstance(height, (int, float))):
            raise SpecError(f"{where}.height: a number, or null for the terrain height at the shape's centre")
        return {"type": "flatten", "shape": parse_shape(obj["shape"], f"{where}.shape"),
                "height": None if height is None else float(height),
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
    raise SpecError(f"{where}.type: unknown feature '{kind}' (hill, flatten, plateau, river, ramp, border, clamp)")


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


def _parse_placement(obj, kind: str, where: str) -> Placement:
    allowed = {"model", "position", "z_offset", "rotation", "facing", "scale", "uid", "radius", "flags", "label"}
    allowed.add("bounds")
    if kind == "wmo":
        allowed |= {"doodad_set", "name_set"}
    _check_keys(obj, allowed, {"model", "position"}, where)
    if kind == "doodad":
        model = normalize_path(obj["model"], f"{where}.model", (".m2", ".mdx"))
    else:
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
                     flags, bounds, doodad_set, name_set, label)


def parse_spec(data: dict) -> Spec:
    spec = Spec()
    top = {"format", "map", "seed", "area_id", "areas", "heightmap", "textures", "texture_rules", "holes", "doodads",
           "wmos", "water", "uid_base", "pois", "preview"}
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
    spec.features = [_parse_feature(f, f"heightmap.features[{i}]") for i, f in enumerate(hm.get("features", []))]

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
        path = normalize_path(tex["path"], f"{w}.path", (".blp",))
        if path.lower() in paths:
            raise SpecError(f"{w}.path: {path!r} is listed twice")
        paths.add(path.lower())
        if is_placeholder(path):
            spec.warnings.append(f"{w}.path {path!r} is a TODO placeholder")
        color = _color(tex.get("color", "#808080"), f"{w}.color")
        spec.textures.append(Texture(name, path, color, _int(tex, "effect_id", w, default=0, lo=0, hi=0xFFFFFFFF),
                                     _int(tex, "mtxf_flags", w, default=0, lo=0, hi=0xFFFFFFFF)))
    spec.texture_rules = [_parse_rule(r, spec, f"texture_rules[{i}]")
                          for i, r in enumerate(data.get("texture_rules", []))]

    for i, h in enumerate(data.get("holes", [])):
        _check_keys(h, {"shape"}, {"shape"}, f"holes[{i}]")
        spec.holes.append(parse_shape(h["shape"], f"holes[{i}].shape"))

    for i, d in enumerate(data.get("doodads", [])):
        p = _parse_placement(d, "doodad", f"doodads[{i}]")
        if is_placeholder(p.model):
            spec.warnings.append(f"doodads[{i}].model {p.model!r} is a TODO placeholder")
        if p.model.lower().endswith(".mdx"):
            spec.warnings.append(f"doodads[{i}].model {p.model!r}: 3.3.5a ships .m2 files")
        spec.doodads.append(p)
    for i, d in enumerate(data.get("wmos", [])):
        p = _parse_placement(d, "wmo", f"wmos[{i}]")
        if is_placeholder(p.model):
            spec.warnings.append(f"wmos[{i}].model {p.model!r} is a TODO placeholder")
        spec.wmos.append(p)

    poi_names = set()
    for i, mk in enumerate(data.get("pois", [])):
        where = f"pois[{i}]"
        _check_keys(mk, {"name", "kind", "position", "z_offset", "radius", "flatten"}, {"name", "position"}, where)
        name = mk["name"]
        if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_.-]{1,64}$", name) or name in poi_names:
            raise SpecError(f"{where}.name: a unique name of letters, digits, '_', '-', '.' (the server's spawn "
                            "tables key on it)")
        poi_names.add(name)
        kind = mk.get("kind", "poi")
        if not isinstance(kind, str) or not kind:
            raise SpecError(f"{where}.kind: a non-empty string (e.g. landmark, orb_shrine, crate_drop, storm_center)")
        x, y, z = _vec(mk["position"], 3, f"{where}.position", allow_none_last=True)
        radius = _num(mk, "radius", where, default=0.0, lo=0.0)
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
        spec.pois.append({"name": name, "kind": kind, "x": x, "y": y, "z": z,
                          "z_offset": _num(mk, "z_offset", where, default=0.0), "radius": radius,
                          "flatten": falloff})
        if falloff is not None:
            # Flatten after every heightmap feature, to the terrain height at the centre (or the given z). The
            # circle is one quad (UNIT_SIZE) wider than the radius: a point's triangle uses vertices up to one quad
            # away, so this keeps the ground flat across the whole stated radius.
            spec.features.append({"type": "flatten",
                                  "shape": parse_shape({"circle": {"center": [x, y],
                                                                   "radius": radius + coords.UNIT_SIZE}},
                                                       f"{where}.flatten"),
                                  "height": z, "falloff": falloff, "mode": "set"})

    for i, w in enumerate(data.get("water", [])):
        where = f"water[{i}]"
        _check_keys(w, {"liquid_type", "height", "shape", "min_depth"}, {"height", "shape"}, where)
        liquid_type = _int(w, "liquid_type", where, default=1, lo=1, hi=21)
        spec.water.append({"liquid_type": liquid_type, "height": _num(w, "height", where),
                           "shape": parse_shape(w["shape"], f"{where}.shape"),
                           "min_depth": _num(w, "min_depth", where, default=0.0, lo=0.0)})
    return spec


def load_spec(path: str) -> Spec:
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise SpecError(f"{path}: invalid JSON: {e}") from None
    return parse_spec(data)
