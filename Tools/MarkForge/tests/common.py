"""Shared helpers for the MarkForge tests: the tube body, temporary folders outside the repository and a synthetic
package (a tube-body model written as M2 + skin, CharSections.dbc, skin and underwear textures). No game data."""

import atexit
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
for p in (TOOL, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

import mflib  # noqa: E402,F401  (puts BlpConvert and RaceForge on sys.path)

_TEMPS = []
_CACHE = {}


def temp_dir(tag="mf"):
    d = tempfile.mkdtemp(prefix=f"markforge-{tag}-")
    _TEMPS.append(d)
    return d


@atexit.register
def cleanup():
    for d in _TEMPS:
        shutil.rmtree(d, ignore_errors=True)
    _TEMPS.clear()


def tube():
    """(model, atlas, charts, eye, eye_sep) of the full-detail tube body, cached."""
    if "tube" not in _CACHE:
        from mflib import atlas as A, coords as C, model as M
        m = M.tube_body()
        at = A.rasterise(m)
        e = m.eye_centres()
        sep = 2 * float(e[1])
        A.keepout_zones(at, e, sep, A.other_geometry_cover(m))
        ch = C.Charts(at, e, sep)
        _CACHE["tube"] = (m, at, ch, e, sep)
    return _CACHE["tube"]


def prepared(garment=True):
    """markforge.prepare() on the tube body with the synthetic garment, cached."""
    key = ("prep", garment)
    if key not in _CACHE:
        import markforge as MF
        from mflib import fixture as FX, model as M
        g = FX.synthetic_garment() if garment else None
        if g is None:
            g = np.zeros((512, 512), bool)
        _CACHE[key] = MF.prepare(None, 1, 0, None, False, model_obj=M.tube_body(), garment=g)
    return _CACHE[key]


# --- a synthetic package folder ------------------------------------------------------------------------------------


def pal8_blp(rgb: np.ndarray, alpha: np.ndarray | None = None) -> bytes:
    """A pal8 BLP from an (H, W, 3) uint8 picture of 256 colours or fewer; mips by taking every other texel."""
    import blpconvert
    h, w = rgb.shape[:2]
    flat = rgb.reshape(-1, 3)
    pal, idx = np.unique(flat, axis=0, return_inverse=True)
    if len(pal) > 256:
        raise ValueError("more than 256 colours")
    idx = idx.reshape(h, w).astype(np.uint8)
    a = np.full((h, w), 255, np.uint8) if alpha is None else alpha.astype(np.uint8)
    t_levels, a_levels = [], []
    while True:
        t_levels.append(idx.tobytes())
        a_levels.append(a.tobytes())
        if idx.shape == (1, 1):
            break
        idx = idx[::2 if idx.shape[0] > 1 else 1, ::2 if idx.shape[1] > 1 else 1]
        a = a[::2 if a.shape[0] > 1 else 1, ::2 if a.shape[1] > 1 else 1]
    return blpconvert.pack_pal8(w, h, [tuple(int(v) for v in c) for c in pal], t_levels, a_levels, True)


def skin_picture(tone, seed):
    """512x512 skin of one tone with a little grain, quantised to 64 levels so it stays a palette."""
    rs = np.random.RandomState(seed)
    g = rs.rand(512, 512, 1) * 0.08 - 0.04
    rgb = np.clip(np.array(tone, float)[None, None, :] / 255.0 + g, 0, 1)
    return (np.round(rgb * 63) / 63 * 255).astype(np.uint8)


def model_tables(races):
    """{client path: bytes} of ChrRaces, CreatureDisplayInfo and CreatureModelData naming each race's model:
    races is [(race id, clientFileString, model race file)], both sexes (display 100 + 2 race + sex, model the same
    number), as the client's tables chain them."""
    from rflib import schema_access
    from rflib.dbc import DbcTable
    out = {}
    tables = {n: DbcTable.empty(schema_access.get(n)) for n in ("ChrRaces", "CreatureDisplayInfo", "CreatureModelData")}
    cr, cdi, cmd = tables["ChrRaces"], tables["CreatureDisplayInfo"], tables["CreatureModelData"]
    for race, cfs, model_race in races:
        row = [0] * len(cr.schema.columns)
        cr.set(row, "id", race)
        cr.set_str(row, "clientFileString", cfs)
        cr.set(row, "maleDisplayID", 100 + 2 * race)
        cr.set(row, "femaleDisplayID", 101 + 2 * race)
        cr.rows.append(row)
        for sex, sex_name in ((0, "Male"), (1, "Female")):
            n = 100 + 2 * race + sex
            d = [0] * len(cdi.schema.columns)
            cdi.set(d, "id", n)
            cdi.set(d, "modelID", n)
            cdi.rows.append(d)
            m = [0] * len(cmd.schema.columns)
            cmd.set(m, "id", n)
            cmd.set_str(m, "modelName", f"Character\\{model_race}\\{sex_name}\\{model_race}{sex_name}.mdx")
            cmd.rows.append(m)
    for name, t in tables.items():
        out[t.schema.filename] = t.to_bytes()
    return out


def write_package(root, race_file="Human", sex_name="Male", race=1, sex=0):
    """A package folder with one race and sex: the tube body as its model, two skin colours whose underwear paints
    different bands (so the garment mask must be their union), faces, and the eye sprite the model names."""
    import m2tiny
    from rflib import schema_access
    from rflib.dbc import DbcTable
    from mflib import eyes as E, model as M
    base = f"Character\\{race_file}\\{sex_name}\\"
    folder = os.path.join(root, "Character", race_file, sex_name)
    os.makedirs(folder, exist_ok=True)
    body = M.tube_body(detail=0.5)
    body.eye_texture = base + "deathKnightEyeGlow.blp"
    m2, sk = m2tiny.write(body)
    with open(os.path.join(folder, f"{race_file}{sex_name}.m2"), "wb") as f:
        f.write(m2)
    with open(os.path.join(folder, f"{race_file}{sex_name}00.skin"), "wb") as f:
        f.write(sk)
    with open(os.path.join(folder, "deathKnightEyeGlow.blp"), "wb") as f:
        f.write(E.synthetic_source())
    schema = schema_access.get("CharSections")
    t = DbcTable.empty(schema)
    bands = {0: (20, 60), 1: (70, 110)}  # rows of the band each colour's underwear paints, in its section
    rid = 1
    for colour, tone in ((0, (200, 160, 140)), (1, (120, 90, 80))):
        skin = skin_picture(tone, colour + 1)
        names = {k: f"{base}{race_file}{sex_name}{k}00_0{colour}.blp" for k in ("Skin", "FaceLower", "FaceUpper",
                                                                                   "NakedPelvisSkin", "NakedTorsoSkin")}
        with open(os.path.join(root, *names["Skin"].split("\\")), "wb") as f:
            f.write(pal8_blp(skin))
        lo, hi = bands[colour]
        for key, (x, y) in (("NakedPelvisSkin", (256, 192)), ("NakedTorsoSkin", (256, 0))):
            uw = skin[y:y + 128, x:x + 256].copy()
            uw[lo:hi, 30:220] = (90, 30, 30)  # the cloth
            with open(os.path.join(root, *names[key].split("\\")), "wb") as f:
                f.write(pal8_blp(uw))
        with open(os.path.join(root, *names["FaceLower"].split("\\")), "wb") as f:
            f.write(pal8_blp(skin[384:512, 0:256].copy()))
        with open(os.path.join(root, *names["FaceUpper"].split("\\")), "wb") as f:
            f.write(pal8_blp(skin[320:384, 0:256].copy()))
        for section, var, tex in ((0, 0, [names["Skin"], "", ""]),
                                  (1, 0, [names["FaceLower"], names["FaceUpper"], ""]),
                                  (4, 0, [names["NakedPelvisSkin"], names["NakedTorsoSkin"], ""])):
            row = [0] * len(schema.columns)
            t.set(row, "id", rid)
            rid += 1
            t.set(row, "raceID", race)
            t.set(row, "sexID", sex)
            t.set(row, "baseSection", section)
            for i, s in enumerate(tex):
                t.set_str(row, f"textureName[{i}]", s)
            t.set(row, "flags", 0x11)
            t.set(row, "variationIndex", var)
            t.set(row, "colorIndex", colour)
            t.rows.append(row)
    os.makedirs(os.path.join(root, "DBFilesClient"), exist_ok=True)
    t.write(os.path.join(root, "DBFilesClient", "CharSections.dbc"))
    return bands
