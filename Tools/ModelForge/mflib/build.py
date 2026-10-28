"""Turns a prop definition (props/*.py) into the files the client loads (CAFE.SPEC.md sections 5.2, 5.5, 5.9).

    DIR/files/World/Bleakhold/Cafe/<Name>/BH_Cafe_<Name>.m2, BH_Cafe_<Name>00.skin, BH_Cafe_<Name>_Atlas.blp
    DIR/files/World/Bleakhold/Cafe/Shared/BH_Cafe_<Shared>.blp
    DIR/parts/<Name>.parts.json     triangles per named part (m2check input; not shipped)
    DIR/manifest.json               the interface to CafeForge (section 5.9)

Sections: one per (material preset, texture) group, in the order opaque, cutout, chrome, glow, glass; one batch
per section; the parts of a group are contiguous, so m2check can report triangles per named part.
"""

import hashlib
import json
import os

from . import atlas as A
from . import bake as BK
from . import geom as G
from . import m2check as C
from . import m2write as W
from . import material as MAT
from . import mips as MP
from . import skinwrite as S
from . import tex as T

CLIENT_ROOT = "World\\Bleakhold\\Cafe"
PRESET_ORDER = ["opaque", "cutout", "chrome", "glow", "glass", "glass1"]
TOOL_VERSION = 1

SHARED = {
    # name: (w, h, generator, params, format, M2 texture flags)
    "ChromeEnv": (128, 128, "env_gradient", {"sky": T.hexc("B4C2D4"), "zenith": T.hexc("7890B0"),
                                               "horizon": T.hexc("F6ECD8"), "ground": T.hexc("30261C"),
                                               "rim": 0.72},
                  "dxt1", 3),
    "IronEnv": (128, 128, "env_gradient", {"sky": T.hexc("A8A8AC"), "zenith": T.hexc("8E949C"),
                                             "horizon": T.hexc("C0BCB4"), "ground": T.hexc("2E2A28")},
                "dxt1", 3),
    "Steam": (64, 64, "steam_puff", {}, "dxt5", 0),
    "Fire": (64, 64, "fire", {}, "dxt5", 0),
}


class Part:
    """A named piece of a prop: one mesh, one material preset, one texture slot.

    paint: (generator name, params) from tex.GENERATORS, or a callable f(ctx, seed, params) -> colour.
    decals: {chart index (in the mesh) or chart name: f(w_px, h_px) -> tex.Img} composited over the paint.
    visible: counted by the readability rule (every named visible part >= 0.06 yd across, section 5.8).
    ao_floor: the lowest occlusion factor the bake applies to this part (0 = the plain bake)."""

    def __init__(self, name, mesh, material="opaque", texture="atlas", paint=("flat", {}), seed=1, decals=None,
                 weight=None, visible=True, occlude=True, ao_floor=0.0):
        self.name = name
        self.ao_floor = ao_floor    # the bake's occlusion term never darkens this part below it
        self.mesh = mesh
        self.material = material
        self.texture = texture
        self.paint = paint
        self.seed = seed
        self.decals = decals or {}
        self.visible = visible
        self.occlude = occlude
        if weight is not None:
            mesh.set_weight(weight)


class ParticleDef:
    def __init__(self, position, texture="Steam", **overrides):
        self.position = tuple(position)
        self.texture = texture
        self.overrides = overrides


class PropDef:
    def __init__(self, name):
        self.name = name
        self.display = None
        self.size = None            # (W along Y, D along X, H): the cafe.json size
        self.depth_with_handles = None
        self.budget = 4000
        self.collision_max = 120
        self.atlas = {"atlas": 512}
        self.parts = []
        self.particles = []
        self.collision = ([], [])  # (positions, triangles)
        self.model_frame = None
        self.kind = "machine"
        self.max_height = 0.95
        self.sloped_top = False
        self.notes = ""

    def add(self, part):
        self.parts.append(part)
        return part


# ------------------------------------------------------------------------------------------- helpers

def client_dir(name):
    return CLIENT_ROOT + "\\" + name


def disk_path(out, client_path):
    return os.path.join(out, "files", *client_path.split("\\"))


def shared_path(name):
    return CLIENT_ROOT + "\\Shared\\BH_Cafe_" + name + ".blp"


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _source_hash():
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(here)):
        for fn in sorted(files):
            if fn.endswith(".py"):
                with open(os.path.join(root, fn), "rb") as f:
                    h.update(fn.encode())
                    h.update(f.read())
    return h.hexdigest()[:16]


def hull_normals(positions, tris):
    return [G.norm(G.cross(G.sub(positions[b], positions[a]), G.sub(positions[c], positions[a])))
            for a, b, c in tris]


# --------------------------------------------------------------------------------------------- build

class Built:
    """What build_prop returns: paths, the parsed check, statistics."""

    def __init__(self):
        self.m2 = None
        self.skin = None
        self.textures = []
        self.check = None
        self.parts = {}
        self.manifest = None
        self.files = []
        self.defn = None
        self.uvs = None
        self.nobake = {}


def _groups(defn):
    keyed = {}
    order = []
    for pi, part in enumerate(defn.parts):
        k = (PRESET_ORDER.index(part.material), part.texture)
        if k not in keyed:
            keyed[k] = []
            order.append(k)
        keyed[k].append(pi)
    first = {k: i for i, k in enumerate(order)}
    order.sort(key=lambda k: (k[0], first[k]))
    return [(k, keyed[k]) for k in order]


def build_prop(defn, out, tex_scale=1.0, bake=True, particles=True, jobs=None, cache=True, log=print,
               nobake_dir=None):
    """Builds one prop into `out`. nobake_dir: also write an unbaked copy of each own atlas there (the preview's
    bake on/off pair; never shipped)."""
    name = defn.name
    res = Built()
    res.defn = defn
    cdir = client_dir(name)
    m2_client = cdir + "\\BH_Cafe_" + name + ".m2"
    skin_client = cdir + "\\BH_Cafe_" + name + "00.skin"
    os.makedirs(os.path.dirname(disk_path(out, m2_client)), exist_ok=True)

    # ---- textures in M2 order: own atlases, then shared
    slots = []
    for part in defn.parts:
        if part.texture not in slots:
            slots.append(part.texture)
    if particles:
        for pd in defn.particles:
            if pd.texture not in slots:
                slots.append(pd.texture)
    own = [s for s in slots if s not in SHARED]
    shared = [s for s in slots if s in SHARED]
    slots = own + shared
    tex_client = {}
    for s in own:
        suffix = "Atlas" if s == "atlas" else s[0].upper() + s[1:]
        tex_client[s] = cdir + "\\BH_Cafe_" + name + "_" + suffix + ".blp"
    for s in shared:
        tex_client[s] = shared_path(s)
    tex_index = {s: i for i, s in enumerate(slots)}

    # ---- pack each own atlas
    part_uvs = {}
    placements = {}
    for s in own:
        size = defn.atlas.get(s, 512)
        charts = []
        owners = []
        for pi, part in enumerate(defn.parts):
            if part.texture != s:
                continue
            for ci, ch in enumerate(part.mesh.charts):
                charts.append(ch)
                owners.append((pi, ci))
        pl, density = A.pack(charts, (size, size))
        placements[s] = (pl, owners, density, size)
        for (pi, ci), p in zip(owners, pl):
            part_uvs.setdefault(pi, {})[ci] = p
    for pi, part in enumerate(defn.parts):
        m = part.mesh
        if part.texture in placements:
            size = placements[part.texture][3]
            uv = [part_uvs[pi][m.c[v]].uv(m.st[v][0], m.st[v][1], (size, size)) for v in range(len(m.p))]
        else:
            uv = [(0.5, 0.5)] * len(m.p)
        part_uvs[pi] = (part_uvs.get(pi), uv)

    # ---- vertices, sections, batches
    model = W.M2Model("BH_Cafe_" + name)
    skin_sections = []
    batches = []
    indices = []
    mats = []
    parts_map = {}
    for gi, ((preset_i, slot), pis) in enumerate(_groups(defn)):
        preset = MAT.preset(PRESET_ORDER[preset_i])
        vstart = len(model.vertices)
        istart = len(indices)
        lo = [1e9, 1e9, 1e9]
        hi = [-1e9, -1e9, -1e9]
        for pi in pis:
            part = defn.parts[pi]
            m = part.mesh
            base = len(model.vertices)
            uv = part_uvs[pi][1]
            for v in range(len(m.p)):
                model.vertices.append((m.p[v], m.n[v], uv[v]))
                for k in range(3):
                    lo[k] = min(lo[k], m.p[v][k])
                    hi[k] = max(hi[k], m.p[v][k])
            first = (len(indices) - istart) // 3
            for a, b, c in m.t:
                indices.extend((base + a, base + b, base + c))
            parts_map.setdefault(part.name, []).append((gi, first, len(m.t)))
        vcount = len(model.vertices) - vstart
        icount = len(indices) - istart
        centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
        rad = max(G.length(G.sub(model.vertices[v][0], centre)) for v in range(vstart, vstart + vcount))
        sec = S.Section(0, vstart, vcount, istart, icount, centre, centre, rad)
        skin_sections.append(sec)
        mk = (preset["flags"], preset["blend"])
        if mk not in mats:
            mats.append(mk)
        batches.append(S.Batch(gi, mats.index(mk), tex_index[slot], preset["coord"], preset["priority"]))
    model.materials = mats
    model.textures = [(tex_client[s], SHARED[s][5] if s in SHARED else 3) for s in slots]

    # ---- collision
    cpos, ctris = defn.collision
    model.collision_positions = [tuple(p) for p in cpos]
    model.collision_tris = [tuple(t) for t in ctris]
    model.collision_normals = hull_normals(model.collision_positions, model.collision_tris)

    # ---- particles
    if particles:
        for pd in defn.particles:
            p = W.Particle(pd.position, tex_index[pd.texture])
            for k, v in pd.overrides.items():
                if not hasattr(p, k):
                    raise AttributeError("particle has no field %r" % k)
                setattr(p, k, v)
            p.validate()
            model.particles.append(p)

    m2_bytes = W.write_m2(model)
    skin = S.Skin(len(model.vertices))
    skin.indices = indices
    skin.sections = skin_sections
    skin.batches = batches
    skin_bytes = S.write_skin(skin)
    m2_disk = disk_path(out, m2_client)
    skin_disk = disk_path(out, skin_client)
    with open(m2_disk, "wb") as f:
        f.write(m2_bytes)
    with open(skin_disk, "wb") as f:
        f.write(skin_bytes)
    res.m2, res.skin = m2_disk, skin_disk
    res.files = [(m2_client, m2_disk), (skin_client, skin_disk)]

    # ---- textures
    srch = _source_hash()
    for s in own:
        pl, owners, density, size = placements[s]
        tsize = max(16, int(size * tex_scale))
        key = hashlib.sha256(("%s|%s|%s|%d|%d|%s" % (name, s, srch, tsize, int(bake), m2_bytes[:0x140].hex()))
                             .encode() + m2_bytes).hexdigest()[:24]
        dpath = disk_path(out, tex_client[s])
        img, owner = atlas_image(defn, s, pl, owners, size, tsize, bake, jobs, out if cache else None, key, log)
        os.makedirs(os.path.dirname(dpath), exist_ok=True)
        cutout = any(p.material == "cutout" for p in defn.parts if p.texture == s)
        alpha = any(p.material in ("glass", "glass1", "cutout") for p in defn.parts if p.texture == s)
        filled = MP.dilate_islands(img, owner)
        MP.write(dpath, img, "dxt5" if alpha else "dxt1", _cutout_mask(defn, owners, filled) if cutout else False,
                 _pool(jobs))
        res.textures.append((tex_client[s], dpath))
        log("  %s: %dx%d, %.0f texels/yd" % (tex_client[s], tsize, tsize, density * tsize / size))
        if nobake_dir and bake:
            nimg, nowner = atlas_image(defn, s, pl, owners, size, tsize, False, jobs, out if cache else None,
                                       key + "-nobake", log)
            nfilled = MP.dilate_islands(nimg, nowner)
            os.makedirs(nobake_dir, exist_ok=True)
            npath = os.path.join(nobake_dir, os.path.basename(dpath))
            MP.write(npath, nimg, "dxt5" if alpha else "dxt1",
                     _cutout_mask(defn, owners, nfilled) if cutout else False, _pool(jobs))
            res.nobake[tex_client[s]] = npath
    for s in shared:
        dpath = disk_path(out, tex_client[s])
        build_shared(s, dpath, tex_scale)
        res.textures.append((tex_client[s], dpath))
    res.files += res.textures

    # ---- parts map, check
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    pmap_path = os.path.join(out, "parts", name + ".parts.json")
    with open(pmap_path, "w") as f:
        json.dump(parts_map, f, indent=1, sort_keys=True)
    res.parts = parts_map
    m, fnd, summ = C.check_files(m2_disk, parts_map, m2_client)
    res.check = (m, fnd, summ)
    res.manifest = manifest_entry(defn, res, summ, m2_client, skin_client)
    return res


def _cutout_mask(defn, owners, filled):
    """Per-texel cutout mask of one atlas: the texels (gutters included, after dilation) whose chart belongs to a
    cutout part. owners[k] = (part index, chart index) of chart id k, the id the bake writes per texel."""
    cut = {k for k, (pi, _ci) in enumerate(owners) if defn.parts[pi].material == "cutout"}
    return bytearray(1 if o in cut else 0 for o in filled)


_POOL = {}


def _pool(jobs):
    if jobs == 1:
        return None
    if "p" not in _POOL:
        import concurrent.futures
        _POOL["p"] = concurrent.futures.ProcessPoolExecutor(max_workers=jobs or os.cpu_count() or 1)
    return _POOL["p"]


def shutdown():
    p = _POOL.pop("p", None)
    if p is not None:
        p.shutdown()


def build_shared(name, dpath, tex_scale=1.0):
    w, h, gen, params, fmt, _flags = SHARED[name]
    os.makedirs(os.path.dirname(dpath), exist_ok=True)
    img = T.image_from(T.GENERATORS[gen], w, h, 7, params).to_image()
    MP.write(dpath, img, fmt, False, None)
    return dpath


# ------------------------------------------------------------------------------------- atlas painting

_PJOB = {}


def _paint_chunk(rng):
    job = _PJOB
    td = job["td"]
    out = []
    for i in range(rng[0], rng[1]):
        idx = job["idx"][i]
        out.append(_paint_texel(job, td, idx))
    return out


def _paint_texel(job, td, i):
    part = job["parts"][td.part[i]]
    chart = job["charts"][td.chart[i]]
    s, t = td.st[i]
    bake = job["bake"]
    ctx = T.Ctx(s, t, td.pos[i], td.nrm[i], td.curv[i] if bake else 0.0, td.ao[i] if bake else 1.0, chart.w,
                chart.h, chart.name, part.name)
    p = part.paint
    if callable(p):
        c = p(ctx, part.seed, {})
    else:
        c = T.GENERATORS[p[0]](ctx, part.seed, p[1])
    a = c[3] if len(c) == 4 else 1.0
    return (c[0], c[1], c[2], a)


def atlas_image(defn, slot, pl, owners, size, tsize, bake, jobs, cache_dir, key, log):
    """Rasterizes, bakes and paints one atlas. Returns (blpconvert.Image, owner map)."""
    k = tsize / float(size)
    if cache_dir:
        cpath = os.path.join(cache_dir, ".cache", key + ".rgba")
        if os.path.exists(cpath):
            from blpconvert import Image
            with open(cpath, "rb") as f:
                blob = f.read()
            n = tsize * tsize
            img = Image(tsize, tsize, bytearray(blob[:4 * n]))
            owner = list(json.loads(blob[4 * n:].decode()))
            return img, owner
    td = BK.TexelData(tsize, tsize)
    place_of = dict(zip(owners, pl))
    charts = []
    chart_of = {}
    for (pi, ci), p in zip(owners, pl):
        chart_of[(pi, ci)] = len(charts)
        charts.append(defn.parts[pi].mesh.charts[ci])
    occl = []
    for part in defn.parts:
        if part.occlude and part.material in ("opaque", "cutout", "chrome"):
            m = part.mesh
            occl.extend((m.p[a], m.p[b], m.p[c]) for a, b, c in m.t)
    for pi, part in enumerate(defn.parts):
        if part.texture != slot:
            continue
        m = part.mesh
        uvs = []
        for v in range(len(m.p)):
            plc = place_of[(pi, m.c[v])]
            u, vv = plc.uv(m.st[v][0], m.st[v][1], (size, size))
            uvs.append((u * tsize, vv * tsize))
        offset = chart_of[(pi, 0)] if m.charts else 0
        BK.rasterize(td, m, uvs, pi, offset)
    cov = td.covered()
    if bake:
        step = max(1, tsize // 128)
        n = BK.compute_ao(td, occl, step, True, jobs)
        log("  bake: %d texels, %d occlusion samples x %d rays" % (len(cov), n, BK.AO_RAYS))
    zs = [p[2] for part in defn.parts for p in part.mesh.p]
    zmin, zmax = min(zs), max(zs)
    global _PJOB
    _PJOB = {"td": td, "parts": defn.parts, "charts": charts, "bake": bake, "idx": cov}
    colors = _run_paint(len(cov), jobs)
    _PJOB = {}
    img = T.Img(tsize, tsize, (0, 0, 0, 0))
    for i, c in zip(cov, colors):
        img.r[i], img.g[i], img.b[i], img.a[i] = c
    # decals, in chart space
    for pi, part in enumerate(defn.parts):
        if part.texture != slot or not part.decals:
            continue
        for ckey, fn in part.decals.items():
            ci = ckey if isinstance(ckey, int) else [j for j, ch in enumerate(part.mesh.charts) if ch.name == ckey][0]
            plc = place_of[(pi, ci)]
            x0, y0 = int(round(plc.x * k)), int(round(plc.y * k))
            w, h = max(1, int(round(plc.w * k))), max(1, int(round(plc.h * k)))
            dec = fn(w, h)
            cid = chart_of[(pi, ci)]
            for y in range(h):
                for x in range(w):
                    X, Y = x0 + x, y0 + y
                    if not (0 <= X < tsize and 0 <= Y < tsize):
                        continue
                    j = Y * tsize + X
                    if td.chart[j] != cid:
                        continue
                    a = dec.a[y * w + x]
                    if a > 0:
                        img.blend(X, Y, (dec.r[y * w + x], dec.g[y * w + x], dec.b[y * w + x]), a)
    # light
    floors = [part.ao_floor for part in defn.parts]
    for i in cov:
        f = BK.light_factor(td.pos[i], td.nrm[i], td.ao[i], td.curv[i], zmin, zmax, bake,
                            occ_min=floors[td.part[i]])
        c = T.light((img.r[i], img.g[i], img.b[i]), f)
        img.r[i], img.g[i], img.b[i] = c
    out = img.to_image()
    owner = list(td.chart)
    if cache_dir:
        os.makedirs(os.path.join(cache_dir, ".cache"), exist_ok=True)
        with open(os.path.join(cache_dir, ".cache", key + ".rgba"), "wb") as f:
            f.write(bytes(out.data))
            f.write(json.dumps(owner).encode())
    return out, owner


def _run_paint(n, jobs):
    import multiprocessing
    jobs = jobs or os.cpu_count() or 1
    chunk = max(512, n // (jobs * 6) + 1)
    ranges = [(a, min(n, a + chunk)) for a in range(0, n, chunk)]
    if jobs > 1 and n > 4096 and "fork" in multiprocessing.get_all_start_methods():
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(jobs) as pool:
            parts = pool.map(_paint_chunk, ranges)
    else:
        parts = [_paint_chunk(r) for r in ranges]
    out = []
    for p in parts:
        out.extend(p)
    return out


# ------------------------------------------------------------------------------------------ manifest

def measure(defn):
    """Render and collision AABBs, tris per part, max visible-part extent."""
    pts = [p for part in defn.parts for p in part.mesh.p]
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    cp = defn.collision[0]
    clo = tuple(min(p[i] for p in cp) for i in range(3)) if cp else (0, 0, 0)
    chi = tuple(max(p[i] for p in cp) for i in range(3)) if cp else (0, 0, 0)
    return {"render": (lo, hi), "collision": (clo, chi)}


def manifest_entry(defn, res, summ, m2_client, skin_client):
    meas = measure(defn)
    tris = summ.get("counts", {}).get("triangles", 0)
    b = summ.get("bounds", {})
    entry = {
        "name": defn.name, "display": defn.display, "m2": m2_client, "skin": skin_client,
        "textures": [c for c, _d in res.textures],
        "bounds": {"min": [round(v, 4) for v in b.get("min", [0, 0, 0])],
                   "max": [round(v, 4) for v in b.get("max", [0, 0, 0])], "radius": round(b.get("radius", 0), 4)},
        "size": list(defn.size) if defn.size else None,
        "parts": summ.get("parts", {}), "triangles": tris,
        "collisionTriangles": summ.get("counts", {}).get("collisionTriangles", 0),
        "particles": summ.get("counts", {}).get("particles", 0), "customAnims": False,
        "modelFrame": defn.model_frame or default_model_frame(meas),
    }
    return entry


def default_model_frame(meas):
    (lo, hi) = meas["render"]
    cz = (lo[2] + hi[2]) / 2
    r = max(hi[i] - lo[i] for i in range(3)) / 2
    return {"position": [0, 0, round(-cz, 3)], "scale": round(0.9 / max(r, 0.05), 2), "facing": 0.4}


def write_manifest(out, entries, files):
    man = {"tool": "ModelForge", "version": TOOL_VERSION, "models": entries, "icons": [],
           "files": {c: _sha(d) for c, d in sorted(files)}}
    path = os.path.join(out, "manifest.json")
    with open(path, "w") as f:
        json.dump(man, f, indent=2, sort_keys=True)
        f.write("\n")
    return path
