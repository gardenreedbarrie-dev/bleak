"""Part kits several section 5.8.1 designs share: cups, mugs and saucers, the syrup bottles, jars, a kettle, a
service bell, a parasol canopy and fringe, a goblin exhaust stack and a gauge.

Each function returns {part name: geom.Mesh} built around the origin (base at z 0 unless noted), sized by its
arguments, with readable proportions (section 5.8: every visible part at least 0.06 yd across) and section 5.4
side counts. The caller places the meshes (geom.translate / transform), merges what shares a paint, and wraps
them in build.Part with its own paints, so a Stormwind and an Orgrimmar piece can share a shape and differ in
look. Some kits also return positions the caller needs (a spout tip for a steam emitter) under keys starting
with "at_".
"""

import math

from . import geom as G

TAU = 2.0 * math.pi


# ------------------------------------------------------------------------------------------------ cups

def cup(top_r=0.07, height=0.1, saucer_r=None, handle=True, sides=10, fill=0.82, wall=0.01):
    """A porcelain cup (lathe, a real wall so the bake does not see the inner wall through the outer one) with a
    loop handle on its +Y side and an optional saucer under it; the cup's foot stands on the saucer.
    Keys: cup, coffee (a disc at `fill` of the height, with a disc chart for tex.g_coffee), handle, saucer
    (when saucer_r), at_top (the rim centre, for a steam wisp)."""
    base_z = 0.0
    out = {}
    if saucer_r:
        sh = max(0.012, saucer_r * 0.12)
        sprof = [(0.0, 0.0), (saucer_r * 0.72, 0.0), (saucer_r, sh * 0.85), (saucer_r * 0.95, sh),
                 (0.0, sh * 0.8)]
        out["saucer"] = G.lathe(sprof, sides + 2, name="saucer")
        base_z = sh * 0.8
    foot = top_r * 0.62
    prof = [(0.0, base_z), (foot, base_z), (top_r * 0.96, base_z + height * 0.9), (top_r, base_z + height),
            (top_r - wall, base_z + height * 0.96), (foot - wall * 0.5, base_z + height * 0.38),
            (0.0, base_z + height * 0.36)]
    out["cup"] = G.lathe(prof, sides, name="cup")
    rf = top_r * 0.96 - wall * 0.9
    out["coffee"] = G.disc(rf, sides, base_z + height * fill, name="coffee")
    if handle:
        hr = height * 0.3
        tube = max(0.012, height * 0.08)
        ring = G.torus(hr, tube, 10, 5, arc=math.pi * 1.25, start=-math.pi * 0.625, name="handle")
        out["handle"] = G.transform(ring, G.mat_chain(G.mat_translate(0.0, top_r * 0.9, base_z + height * 0.58),
                                                      G.mat_rot_z(math.pi / 2), G.mat_rot_x(math.pi / 2)))
    out["at_top"] = (0.0, 0.0, base_z + height)
    return out


def mug(r=0.075, height=0.16, handle=True, sides=10, fill=0.85, wall=0.014):
    """A chunky mug (the Orgrimmar clay mug, a tankard-like cup): nearly straight walls flaring a little at the
    base, a thick rounded lip and a big D handle on its +Y side. Keys: mug, coffee, handle, at_top."""
    prof = [(0.0, 0.0), (r * 1.06, 0.0), (r * 1.08, height * 0.08), (r * 0.98, height * 0.3), (r, height * 0.92),
            (r * 1.03, height), (r - wall, height * 0.99), (r - wall * 1.1, height * 0.12), (0.0, height * 0.1)]
    out = {"mug": G.lathe(prof, sides, name="mug")}
    out["coffee"] = G.disc(r - wall * 1.05, sides, height * fill, name="coffee")
    if handle:
        path = [(0.0, r * 0.85, height * 0.8), (0.0, r * 1.45, height * 0.78), (0.0, r * 1.6, height * 0.5),
                (0.0, r * 1.45, height * 0.24), (0.0, r * 0.85, height * 0.22)]
        out["handle"] = G.sweep(path, max(0.016, height * 0.09), 6, name="handle")
    out["at_top"] = (0.0, 0.0, height)
    return out


# --------------------------------------------------------------------------------------------- bottles

# Eight bottle shapes for the syrup racks (section 5.8.1: each a different shape, about 1.5x real size), as
# lathe profiles in units of the bottle's height (r, z), bottom to top, and the label band (z0, z1).
BOTTLES = {
    "honey": ([(0.0, 0.0), (0.26, 0.0), (0.3, 0.12), (0.3, 0.42), (0.22, 0.58), (0.1, 0.66), (0.09, 0.86),
               (0.11, 0.9)], (0.16, 0.42)),
    "vanilla": ([(0.0, 0.0), (0.16, 0.0), (0.17, 0.05), (0.17, 0.6), (0.11, 0.7), (0.07, 0.76), (0.07, 0.92),
                 (0.085, 0.95)], (0.18, 0.54)),
    "caramel": ([(0.0, 0.0), (0.22, 0.0), (0.24, 0.05), (0.24, 0.52), (0.2, 0.6), (0.09, 0.66), (0.08, 0.85),
                 (0.1, 0.88)], (0.14, 0.48)),
    "cinnamon": ([(0.0, 0.0), (0.24, 0.0), (0.25, 0.06), (0.19, 0.5), (0.1, 0.68), (0.075, 0.86), (0.09, 0.9)],
                 (0.12, 0.42)),
    "chocolate": ([(0.0, 0.0), (0.28, 0.0), (0.29, 0.08), (0.29, 0.45), (0.25, 0.52), (0.12, 0.58), (0.11, 0.74),
                   (0.13, 0.78)], (0.14, 0.42)),
    "berry": ([(0.0, 0.0), (0.18, 0.0), (0.27, 0.16), (0.27, 0.34), (0.18, 0.56), (0.08, 0.68), (0.07, 0.86),
               (0.09, 0.89)], (0.14, 0.4)),
    "mint": ([(0.0, 0.0), (0.2, 0.0), (0.21, 0.06), (0.21, 0.36), (0.26, 0.46), (0.21, 0.58), (0.08, 0.66),
              (0.07, 0.86), (0.09, 0.9)], (0.1, 0.34)),
    "cream": ([(0.0, 0.0), (0.2, 0.0), (0.21, 0.04), (0.21, 0.66), (0.17, 0.74), (0.08, 0.78)], (0.16, 0.56)),
}
BOTTLES["cactus"] = BOTTLES["berry"]


def _radius_at(pts, z):
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return pts[-1][0]


def bottle(key, height=0.3, sides=10):
    """One syrup bottle (BOTTLES[key], see emblem.SYRUPS for the keys and colours), base at z 0: glass (a closed
    lathe; paint it with tex.g_bottle_glass and a liquid), a cork or cap on top, for "cream" the canister's
    nozzle, and the label: an opaque open band that follows the wall 2 % outside it over the label zone (its
    chart wraps once round: paint the label with paint2d.label through paint2d.wrap_front). Keys: glass, cap,
    label, band (z0, z1), at_top."""
    prof, (b0, b1) = BOTTLES[key]
    pts = [(r * height, z * height) for r, z in prof]
    zs = [b0 * height + (b1 - b0) * height * k / 4.0 for k in range(5)]
    label = G.lathe([(_radius_at(pts, z) * 1.02 + 0.002, z) for z in zs], sides, name="label")
    top_r, top_z = pts[-1]
    pts.append((0.0, top_z))
    out = {"glass": G.lathe(pts, sides, name="glass"), "label": label}
    if key == "cream":
        nz = [(0.0, top_z - 0.005), (0.045 * height / 0.3, top_z), (0.04 * height / 0.3, top_z + 0.04 * height / 0.3),
              (0.022 * height / 0.3, top_z + 0.1 * height / 0.3), (0.0, top_z + 0.105 * height / 0.3)]
        out["cap"] = G.lathe(nz, 8, name="nozzle")
        cap_top = nz[-1][1]
    else:
        ch = max(0.04, height * 0.12)
        cr = max(0.03, top_r * 1.05)
        out["cap"] = G.cylinder(cr, ch, 8, True, z0=top_z - ch * 0.3)
        cap_top = top_z + ch * 0.7
    out["band"] = (b0 * height, b1 * height)
    out["at_top"] = (0.0, 0.0, cap_top)
    return out


def jar(r=0.1, height=0.22, lid=True, fill=0.6, sides=12, neck=0.88):
    """A glass jar (the tip jar, a bean jar, the rack's spare jars): straight walls, rounded shoulders, an open
    neck; the contents (an opaque inner lathe up to `fill` of the height, slightly inside the glass, with a
    domed top) and an optional lid with a knob. Keys: glass, contents, lid (when lid), at_top."""
    prof = [(0.0, 0.0), (r * 0.92, 0.0), (r, height * 0.06), (r, height * 0.78), (r * 0.9, height * neck),
            (r * 0.8, height * 0.94), (r * 0.82, height)]
    out = {"glass": G.lathe(prof, sides, cap_top=False, name="glass")}
    ci = r * 0.9
    fz = height * fill
    cprof = [(0.0, height * 0.02), (ci, height * 0.02), (ci, fz * 0.9), (ci * 0.75, fz * 0.98), (0.0, fz)]
    out["contents"] = G.lathe(cprof, sides, name="contents")
    top = height
    if lid:
        lh = max(0.03, height * 0.1)
        lprof = [(0.0, height - lh * 0.2), (r * 0.9, height - lh * 0.2), (r * 0.92, height + lh * 0.6),
                 (r * 0.7, height + lh), (0.0, height + lh)]
        knob = G.sphere(max(0.025, r * 0.25), 8, 4, z0=height + lh * 0.85)
        out["lid"] = G.merge([G.lathe(lprof, sides, name="lid"), knob])
        top = height + lh + max(0.025, r * 0.25) * 2
    out["at_top"] = (0.0, 0.0, top)
    return out


# ---------------------------------------------------------------------------------------------- kettle

def kettle(r=0.16, height=0.24, spout=0.16, sides=16):
    """A stovetop kettle (both kettle stoves): a squat bulbous body, a lid with a knob, a swept spout from the
    lower +X side rising forward, and an arched handle over the top along Y. Base at z 0. Keys: body, lid,
    spout, handle, at_spout (the spout's tip, for the steam emitter)."""
    prof = [(0.0, 0.0), (r * 0.78, 0.0), (r * 0.95, height * 0.12), (r, height * 0.38), (r * 0.92, height * 0.66),
            (r * 0.66, height * 0.88), (r * 0.45, height * 0.92)]
    out = {"body": G.lathe(prof, sides, name="body")}
    lid = [(0.0, height * 0.88), (r * 0.5, height * 0.88), (r * 0.48, height * 0.97), (r * 0.3, height * 1.03),
           (0.0, height * 1.04)]
    knob_r = max(0.025, r * 0.17)
    out["lid"] = G.merge([G.lathe(lid, 10, name="lid"), G.sphere(knob_r, 8, 4, z0=height * 1.02)])
    root = (r * 0.82, 0.0, height * 0.3)
    tip = (r + spout * 0.85, 0.0, height * 0.3 + spout * 0.8)
    path = G.bezier_path(root, (r + spout * 0.35, 0.0, height * 0.32), (r + spout * 0.6, 0.0, height * 0.5), tip, 6)
    out["spout"] = G.sweep(path, lambda t: max(0.018, r * 0.2) * (1.0 - 0.45 * t), 8, name="spout")
    hz0 = height * 0.82
    hr = r * 0.62
    arc = G.arc_path((0.0, 0.0, hz0), hr, 0.0, math.pi, 8, ("y", "z"))
    out["handle"] = G.sweep(arc, max(0.016, r * 0.1), 6, name="handle")
    out["at_spout"] = tip
    return out


# ----------------------------------------------------------------------------------------------- bells

def bell(r=0.07, sides=12):
    """A service bell (both counters): a round base plate, a domed bell and a plunger button on top. Base at
    z 0. Keys: base, dome, button, at_top."""
    bh = max(0.016, r * 0.22)
    base = G.lathe([(0.0, 0.0), (r * 1.15, 0.0), (r * 1.2, bh * 0.6), (r * 1.1, bh), (0.0, bh)], sides,
                   name="base")
    dome = G.dome(r, r * 0.85, 4, sides, z0=bh)
    stem_h = r * 0.35
    button = G.merge([G.cylinder(max(0.012, r * 0.12), stem_h, 6, False, z0=bh + r * 0.8),
                      G.sphere(max(0.03, r * 0.3), 8, 4, z0=bh + r * 0.8 + stem_h * 0.7)])
    return {"base": base, "dome": dome, "button": button,
            "at_top": (0.0, 0.0, bh + r * 0.8 + stem_h * 0.7 + max(0.03, r * 0.3) * 2)}


# --------------------------------------------------------------------------------------------- canopy

def canopy(radius=1.4, rim_z=2.55, apex_z=3.1, panels=8, rings=3, billow=0.04, irregular=0.0, seed=1,
           under_gap=0.012, sag_points=None, sag=0.0):
    """A parasol canopy (both parasols, section 5.8.1) as two shells: "top" with outward normals and one chart
    per panel ("panel0".., s across the panel, t from the apex down, so tex.g_fabric_stripes stripes run across
    a panel), and "under" a hand's breadth below it with downward normals and charts "under0".. for the darker
    painted underside players see from their chairs. Each panel billows down between its ribs by `billow`;
    irregular (0..1) jitters the rim radius and the rib angles per panel (the Orgrimmar hide); sag_points
    [(x, y)] and sag lower the cloth between poles (geom.sag). Keys: top, under, at_ribs [(x, y, z) at the rim]."""
    angs = []
    rims = []
    for i in range(panels):
        jit = (G._hash3(i, 3, 1, seed) - 0.5) * irregular * (TAU / panels) * 0.35
        angs.append(TAU * i / panels + jit)
        rims.append(radius * (1.0 - irregular * 0.12 * G._hash3(i, 5, 2, seed)))
    top_parts, under_parts = [], []
    cols = 3
    slant = math.hypot(radius, apex_z - rim_z)
    for i in range(panels):
        a0, a1 = angs[i], angs[(i + 1) % panels] + (TAU if i == panels - 1 else 0.0)
        r0, r1 = rims[i], rims[(i + 1) % panels]
        chord = 2.0 * max(r0, r1) * math.sin((a1 - a0) / 2.0)
        for shell in ("top", "under"):
            m = G.Mesh()
            ch = m.chart(chord, slant, ("panel%d" if shell == "top" else "under%d") % i)
            grid = {}
            for k in range(rings + 1):
                t = k / float(rings)
                for j in range(cols + 1):
                    u = j / float(cols)
                    a = a0 + (a1 - a0) * u
                    rr = (r0 + (r1 - r0) * u) * t
                    z = apex_z - (apex_z - rim_z) * t - billow * math.sin(math.pi * u) * t
                    if shell == "under":
                        z -= under_gap
                    p = (math.cos(a) * rr, math.sin(a) * rr, z)
                    s = chord / 2.0 + (u - 0.5) * chord * t
                    if shell == "under":
                        s = chord - s
                    grid[(k, j)] = m.vert(p, (0.0, 0.0, 1.0 if shell == "top" else -1.0), ch, s, slant * t)
            for k in range(rings):
                for j in range(cols):
                    a, b = grid[(k, j)], grid[(k, j + 1)]
                    c, d = grid[(k + 1, j + 1)], grid[(k + 1, j)]
                    if shell == "top":
                        m.tri(a, d, c)
                        m.tri(a, c, b)
                    else:
                        m.tri(a, c, d)
                        m.tri(a, b, c)
            (top_parts if shell == "top" else under_parts).append(m)
    top = G.merge(top_parts)
    under = G.merge(under_parts)
    if sag_points and sag:
        top = G.sag(top, sag_points, sag)
        under = G.sag(under, sag_points, sag)
    top = G.recompute_normals(top, 40.0)
    under = G.recompute_normals(under, 40.0)
    ribs = [(math.cos(a) * r, math.sin(a) * r, rim_z) for a, r in zip(angs, rims)]
    return {"top": top, "under": under, "at_ribs": ribs}


def fringe(radius=1.4, rim_z=2.55, depth=0.14, sides=24, flare=0.04):
    """The scalloped fringe hanging from a canopy's rim: an open band (one shell; give it the cutout preset,
    which draws both sides, and paint scallops into its alpha). Its chart runs around (s) and down (t)."""
    return G.lathe([(radius + flare, rim_z - depth), (radius, rim_z)], sides, smooth=True, name="fringe")


# --------------------------------------------------------------------------------------------- exhausts

def exhaust(base, height=0.35, r=0.06, spikes=6, bend=None, sides=8):
    """A goblin exhaust stack (Orgrimmar gadgets): a pipe rising `height` from `base` (or, with bend (dx, dy),
    curving over sideways by that much, like an exhaust out of a machine's side), a flared mouth and a collar
    of `spikes` iron spikes a little under it. Paint the pipe with tex.g_soot (darkest at the top); put
    emitters.exhaust_smoke at at_top. Keys: pipe, mouth, collar (when spikes), at_top."""
    x, y, z = base
    if bend:
        dx, dy = bend
        path = G.bezier_path((x, y, z), (x, y, z + height * 0.6), (x + dx * 0.4, y + dy * 0.4, z + height),
                             (x + dx, y + dy, z + height), 7)
    else:
        path = [(x, y, z), (x, y, z + height)]
    top = path[-1]
    tang = G.norm(G.sub(path[-1], path[-2]))
    pipe = G.sweep(path, r, sides, name="pipe")
    m = G.mat_chain(G.mat_translate(*top), G.mat_look(tang))
    mouth = G.transform(G.lathe([(r * 0.85, -r * 0.2), (r * 1.25, r * 0.25), (r * 1.3, r * 0.5), (r * 0.9, r * 0.5),
                                 (r * 0.8, r * 0.1)], sides, name="mouth"), m)
    out = {"pipe": pipe, "mouth": mouth, "at_top": G.add(top, G.mul(tang, r * 0.6))}
    if spikes:
        ring_at = path[max(0, len(path) - 3)] if bend else G.lerp(path[0], path[-1], 0.78)
        axis = tang if not bend else G.norm(G.sub(path[-1], path[-3]))
        out["collar"] = G.merge([G.transform(G.torus(r * 1.05, max(0.012, r * 0.3), sides, 4),
                                             G.mat_chain(G.mat_translate(*ring_at), G.mat_look(axis))),
                                 G.spike_ring(ring_at, r * 1.15, spikes, max(0.03, r * 0.45), max(0.06, r * 1.4),
                                              axis, 0.15)])
    return out


# ---------------------------------------------------------------------------------------------- gauges

def gauge(center, facing, r=0.08, depth=0.04, bezel=0.016, sides=16):
    """A round gauge on any face (goblin gauges at odd angles, a pressure dial): a case whose front cap carries
    the dial decal (decal key "cyl_top", e.g. paint2d.gauge_face with bands and needle_deg), and a bezel ring.
    center: the back of the case on the surface; facing: the dial's normal. Keys: case, bezel, at_face."""
    m = G.mat_chain(G.mat_translate(*center), G.mat_disc_facing(facing))
    case = G.transform(G.cylinder(r, depth, sides, (False, True)), m)
    ring = G.transform(G.torus(r + bezel * 0.2, bezel, sides, 4), G.mat_chain(m, G.mat_translate(0, 0, depth)))
    f = G.norm(facing)
    return {"case": case, "bezel": ring, "at_face": G.add(center, G.mul(f, depth))}
