"""Software rasterizer for the previews (CAFE.SPEC.md section 5.6).

* Draws the *parsed* files (m2check.parse), not the writer's objects; textures are decoded from the BLPs with
  blpconvert.decode_blp per mip level.
* The view matrix is built like GxuXformCreateLookAtSgCompat (Engine/Source/Gxu/Gxu.cpp:331-357): looking along
  +X puts screen-right at -Y. Counter-clockwise triangles (outward normals) are front faces: the client culls
  with D3DCULL_CW (CGxDeviceD3d.cpp:66) unless the material flag 0x04 asks for two sides.
* Edge functions with the top-left rule, a float depth buffer, perspective-correct attributes, bilinear sampling
  with wrap or clamp from the texture flags (CM2SceneRender.cpp:104-107), trilinear mip choice from the
  screen-space texel footprint of one output pixel (per pixel on large triangles, at the centroid of small
  ones, where it barely varies), supersampling.
* Lighting as the client: tex x (ambient + diffuse * max(0, -N.L)) per vertex, L the direction the sunlight
  travels; material flag 0x01 (and blend modes 5, 6) unlit; the env slot (coord combo 0xFFFF) uses the sphere
  map uv = 0.5 + 0.5 (n_view.x, -n_view.y).
* Pass 1 draws blend 0 and 1 (alpha key at 0.878, CM2SceneRender.cpp:300); pass 2 draws blend >= 2 far to near
  by (priorityPlane, depth) with the client's blend factors (M2Scene.cpp:30, CGxDeviceD3d.cpp:48-51).
* Particles are billboards at three life stages; an emitter without the head/tail quad flags draws nothing.
  They are lit as the client lights them: an emitter without flag 0x1 gets particle material flag 1
  (M2Model.cpp:7453) and so the lit "Particle" effect (CM2SceneRender.cpp:724, 853-857, 885) with every vertex
  normal set to s_particleNormal, the view matrix's z row, i.e. world up (ParticleSystem2.cpp:812-814, 227):
  ambient + diffuse * max(0, -up.L). Flag 0x1 draws unlit; flag 0x8 draws without fog (M2Model.cpp:7454,
  CM2SceneRender.cpp:859-861).
"""

import math
import os

import blpconvert as B  # noqa: E402

from . import geom as G

SUN = G.norm((-0.4, 0.3, -0.85))   # direction the light travels (section 5.6)

# M2 blend mode -> (src, dst) factors via s_blendModes[0] and the D3D tables
BLEND_FACTORS = {
    2: ("srcalpha", "invsrcalpha"),
    3: ("one", "one"),
    4: ("srcalpha", "one"),
    5: ("dstcolor", "zero"),
    6: ("dstcolor", "srccolor"),
}


class Lighting:
    def __init__(self, ambient=(0.45, 0.45, 0.48), diffuse=(0.75, 0.72, 0.66), direction=SUN, fog=None,
                 sky=((0.55, 0.62, 0.72), (0.82, 0.86, 0.9)), name="neutral"):
        self.ambient = ambient
        self.diffuse = diffuse
        self.direction = G.norm(direction)
        self.fog = fog           # (color, start, end) in yards, or None
        self.sky = sky           # (top colour, horizon colour)
        self.name = name


# Section 5.6 mode 3: first guesses, tuned at the M2 art look in game.
PRESETS = {
    "neutral": Lighting(),
    "sw_day": Lighting((0.46, 0.50, 0.58), (0.92, 0.84, 0.70), G.norm((-0.45, 0.35, -0.82)),
                       ((0.66, 0.74, 0.84), 30.0, 220.0), ((0.38, 0.55, 0.82), (0.78, 0.84, 0.9)), "sw_day"),
    "sw_night": Lighting((0.20, 0.24, 0.38), (0.36, 0.42, 0.62), G.norm((0.3, -0.4, -0.86)),
                         ((0.10, 0.13, 0.22), 25.0, 160.0), ((0.04, 0.06, 0.14), (0.14, 0.18, 0.3)), "sw_night"),
    "org_day": Lighting((0.52, 0.42, 0.34), (1.0, 0.80, 0.56), G.norm((-0.3, 0.5, -0.8)),
                        ((0.78, 0.58, 0.42), 25.0, 180.0), ((0.72, 0.5, 0.34), (0.92, 0.74, 0.54)), "org_day"),
}


# ----------------------------------------------------------------------------------------------- texture

class Texture:
    """A decoded BLP with lazily decoded mip levels."""

    def __init__(self, path, flags=3):
        self.path = path
        self.flags = flags
        with open(path, "rb") as f:
            head = f.read(0x94)
        h = B.read_blp_header(head + bytes(1024))
        self.w, self.h = h["width"], h["height"]
        self.nlevels = B.level_count(self.w, self.h) if h["hasMips"] else 1
        self.levels = {}

    def level(self, n):
        n = max(0, min(self.nlevels - 1, n))
        lv = self.levels.get(n)
        if lv is None:
            img = B.decode_blp(self.path, n)
            lv = (img.width, img.height, bytes(img.data))
            self.levels[n] = lv
        return lv

    def sample_level(self, u, v, n):
        w, h, d = self.level(n)
        wu, wv = self.flags & 1, self.flags & 2
        x = u * w - 0.5
        y = v * h - 0.5
        x0 = math.floor(x)
        y0 = math.floor(y)
        tx, ty = x - x0, y - y0
        x1, y1 = x0 + 1, y0 + 1
        if wu:
            x0 %= w
            x1 %= w
        else:
            x0 = 0 if x0 < 0 else (w - 1 if x0 >= w else x0)
            x1 = 0 if x1 < 0 else (w - 1 if x1 >= w else x1)
        if wv:
            y0 %= h
            y1 %= h
        else:
            y0 = 0 if y0 < 0 else (h - 1 if y0 >= h else y0)
            y1 = 0 if y1 < 0 else (h - 1 if y1 >= h else y1)
        o00 = 4 * (y0 * w + x0)
        o10 = 4 * (y0 * w + x1)
        o01 = 4 * (y1 * w + x0)
        o11 = 4 * (y1 * w + x1)
        a = (1 - tx) * (1 - ty)
        b = tx * (1 - ty)
        c = (1 - tx) * ty
        e = tx * ty
        return ((d[o00] * a + d[o10] * b + d[o01] * c + d[o11] * e) / 255.0,
                (d[o00 + 1] * a + d[o10 + 1] * b + d[o01 + 1] * c + d[o11 + 1] * e) / 255.0,
                (d[o00 + 2] * a + d[o10 + 2] * b + d[o01 + 2] * c + d[o11 + 2] * e) / 255.0,
                (d[o00 + 3] * a + d[o10 + 3] * b + d[o01 + 3] * c + d[o11 + 3] * e) / 255.0)

    def sample(self, u, v, lod):
        if lod <= 0.0 or self.nlevels == 1:
            return self.sample_level(u, v, 0)
        n0 = int(lod)
        f = lod - n0
        a = self.sample_level(u, v, n0)
        if f < 0.02 or n0 + 1 >= self.nlevels:
            return a
        b = self.sample_level(u, v, n0 + 1)
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f,
                a[3] + (b[3] - a[3]) * f)


class TextureSet:
    def __init__(self, root, overrides=None):
        self.root = root
        self.cache = {}
        self.index = None
        self.overrides = overrides or {}

    def _find(self, client):
        if client.lower() in self.overrides:
            return self.overrides[client.lower()]
        cand = os.path.join(self.root, *client.split("\\"))
        if os.path.exists(cand):
            return cand
        if self.index is None:
            self.index = {}
            for base, _d, files in os.walk(self.root):
                for f in files:
                    full = os.path.join(base, f)
                    self.index[os.path.relpath(full, self.root).replace(os.sep, "\\").lower()] = full
        return self.index.get(client.lower())

    def get(self, client, flags):
        k = (client.lower(), flags)
        if k not in self.cache:
            p = self._find(client)
            self.cache[k] = Texture(p, flags) if p else None
        return self.cache[k]


# ------------------------------------------------------------------------------------------------ camera

class Camera:
    def __init__(self, eye, target, fov_y=45.0, width=512, height=512, ss=2, window=None, near=0.05):
        self.eye = tuple(eye)
        self.target = tuple(target)
        self.fov_y = fov_y
        self.width, self.height = width, height
        self.ss = ss
        self.window = window or (0, 0, width, height)   # output pixels actually drawn
        self.near = near
        zv = G.norm(G.sub(self.target, self.eye))
        up = (0.0, 0.0, 1.0)
        if abs(G.dot(zv, up)) > 0.999:
            up = (1.0, 0.0, 0.0)
        xv = G.norm(G.cross(zv, up))
        yv = G.norm(G.cross(xv, zv))
        self.xv, self.yv, self.zv = xv, yv, zv
        self.t = math.tan(math.radians(fov_y) / 2)
        self.aspect = width / float(height)

    def view(self, p):
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        return (G.dot(d, self.xv), G.dot(d, self.yv), G.dot(d, self.zv))

    def view_dir(self, n):
        return (G.dot(n, self.xv), G.dot(n, self.yv), G.dot(n, self.zv))

    def project(self, v):
        """View space -> buffer pixel coordinates (supersampled, inside the window) and depth."""
        x, y, z = v
        nx = x / (z * self.t * self.aspect)
        ny = y / (z * self.t)
        sx = (nx + 1) * 0.5 * self.width
        sy = (1 - ny) * 0.5 * self.height
        return ((sx - self.window[0]) * self.ss, (sy - self.window[1]) * self.ss, z)


# ------------------------------------------------------------------------------------------------ frame

class Frame:
    def __init__(self, cam, lighting, background=None):
        self.cam = cam
        self.lit = lighting
        x0, y0, x1, y1 = cam.window
        self.w = (x1 - x0) * cam.ss
        self.h = (y1 - y0) * cam.ss
        n = self.w * self.h
        self.r = [0.0] * n
        self.g = [0.0] * n
        self.b = [0.0] * n
        self.z = [1e30] * n
        self.mask = [0] * n
        self.background(background)

    def background(self, bg):
        cam = self.cam
        top, hor = self.lit.sky
        if bg == "flat":
            top = hor = (0.24, 0.26, 0.3)
        elif isinstance(bg, tuple):
            top = hor = bg
        for y in range(self.h):
            # the elevation of this row's view ray decides sky vs horizon colour
            sy = cam.window[1] + (y + 0.5) / cam.ss
            ny = 1 - 2 * sy / cam.height
            d = G.add(cam.zv, G.mul(cam.yv, ny * cam.t))
            el = G.norm(d)[2]
            k = max(0.0, min(1.0, el * 2.2 + 0.25))
            c = (hor[0] + (top[0] - hor[0]) * k, hor[1] + (top[1] - hor[1]) * k, hor[2] + (top[2] - hor[2]) * k)
            base = y * self.w
            for x in range(self.w):
                self.r[base + x], self.g[base + x], self.b[base + x] = c

    def to_image(self, gamma=None):
        ss = self.cam.ss
        ow, oh = self.w // ss, self.h // ss
        img = B.Image(ow, oh)
        d = img.data
        inv = 1.0 / (ss * ss)
        for y in range(oh):
            for x in range(ow):
                r = g = b = 0.0
                for dy in range(ss):
                    base = (y * ss + dy) * self.w + x * ss
                    for dx in range(ss):
                        r += self.r[base + dx]
                        g += self.g[base + dx]
                        b += self.b[base + dx]
                o = 4 * (y * ow + x)
                d[o] = _b8(r * inv)
                d[o + 1] = _b8(g * inv)
                d[o + 2] = _b8(b * inv)
                d[o + 3] = 255
        return img

    def coverage_bbox(self):
        xs, ys = [], []
        for i, m in enumerate(self.mask):
            if m:
                xs.append(i % self.w)
                ys.append(i // self.w)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))


def _b8(v):
    v = int(v * 255.0 + 0.5)
    return 0 if v < 0 else (255 if v > 255 else v)


# ---------------------------------------------------------------------------------------------- drawing

class Drawable:
    """Triangles with per-vertex position (world), normal, uv; one material state."""

    def __init__(self, pos, nrm, uv, tris, tex=None, blend=0, flags=0, env=False, color=(1.0, 1.0, 1.0),
                 priority=0, alpha=1.0, tag=1):
        self.pos, self.nrm, self.uv, self.tris = pos, nrm, uv, tris
        self.tex = tex
        self.blend = blend
        self.flags = flags
        self.env = env
        self.color = color
        self.priority = priority
        self.alpha = alpha
        self.tag = tag


def model_drawables(m, textures, xform=None, override_tex=None):
    """Drawables for a parsed model (m2check.parse output), one per batch."""
    sk = m["skin"]
    verts = m["vertices"]
    lookup = sk["lookup"]
    out = []
    nm = G.mat_normal(xform) if xform else None
    for b in sk["batches"]:
        sec = sk["sections"][b["skinSectionIndex"]]
        mat = m["materials"][b["materialIndex"]]
        combo = m["textureCombos"][b["textureComboIndex"]]
        tinfo = m["textures"][combo]
        coord = m["textureCoordCombos"][b["textureCoordComboIndex"]]
        tex = textures.get(tinfo["path"], tinfo["flags"]) if tinfo["path"] else None
        if override_tex and tinfo["path"].lower() in override_tex:
            tex = override_tex[tinfo["path"].lower()]
        idx = sk["indices"][sec["indexStart"]:sec["indexStart"] + sec["indexCount"]]
        used = sorted(set(idx))
        remap = {v: k for k, v in enumerate(used)}
        pos, nrm, uv = [], [], []
        for v in used:
            p, n, uv0, _uv1 = verts[lookup[v]]
            if xform:
                p = G.mat_apply(xform, p)
                n = G.norm(G.mat_apply_dir(nm, n))
            pos.append(p)
            nrm.append(n)
            uv.append(uv0)
        tris = [(remap[idx[k]], remap[idx[k + 1]], remap[idx[k + 2]]) for k in range(0, len(idx), 3)]
        out.append(Drawable(pos, nrm, uv, tris, tex, mat["blend"], mat["flags"], coord > 2,
                            priority=b["priorityPlane"]))
    return out


def mesh_drawable(mesh, color, xform=None, blend=0, alpha=1.0, flags=0, tag=2):
    pos = mesh.p
    nrm = mesh.n
    if xform:
        nm = G.mat_normal(xform)
        pos = [G.mat_apply(xform, p) for p in pos]
        nrm = [G.norm(G.mat_apply_dir(nm, n)) for n in nrm]
    return Drawable(list(pos), list(nrm), [(0.0, 0.0)] * len(pos), list(mesh.t), None, blend, flags, False,
                    color, alpha=alpha, tag=tag)


def _vertex_light(n, lit, unlit):
    if unlit:
        return (1.0, 1.0, 1.0)
    d = -(n[0] * lit.direction[0] + n[1] * lit.direction[1] + n[2] * lit.direction[2])
    d = d if d > 0 else 0.0
    return (min(1.0, lit.ambient[0] + lit.diffuse[0] * d), min(1.0, lit.ambient[1] + lit.diffuse[1] * d),
            min(1.0, lit.ambient[2] + lit.diffuse[2] * d))


def _clip_near(poly, near):
    out = []
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ina = a[0][2] >= near
        inb = b[0][2] >= near
        if ina:
            out.append(a)
        if ina != inb:
            t = (near - a[0][2]) / (b[0][2] - a[0][2])
            out.append(tuple(_lerp_attr(a[k], b[k], t) for k in range(len(a))))
    return out


def _lerp_attr(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def draw(frame, d, pass_blend=False, lod_mode=True):
    """Rasterizes one drawable into the frame. lod_mode False samples mip 0 only."""
    cam, lit = frame.cam, frame.lit
    unlit = bool(d.flags & 1) or d.blend in (5, 6)
    two_sided = bool(d.flags & 4)
    zwrite = not (d.flags & 0x10)
    tex = d.tex
    vview = [cam.view(p) for p in d.pos]
    vlight = [_vertex_light(n, lit, unlit) for n in d.nrm]
    if d.env:
        uvs = []
        for n in d.nrm:
            nv = cam.view_dir(n)
            uvs.append((0.5 + 0.5 * nv[0], 0.5 - 0.5 * nv[1]))
    else:
        uvs = d.uv
    fog = lit.fog if not (d.flags & 2) else None
    W, H = frame.w, frame.h
    R, Gc, Bc, Z, M = frame.r, frame.g, frame.b, frame.z, frame.mask
    cr, cg, cb = d.color
    texsize = (tex.w if tex else 1)
    ss = cam.ss
    alpha_key = d.blend == 1
    blend = d.blend
    for ia, ib, ic in d.tris:
        poly = [(vview[ia], vlight[ia], uvs[ia]), (vview[ib], vlight[ib], uvs[ib]), (vview[ic], vlight[ic], uvs[ic])]
        if min(p[0][2] for p in poly) < cam.near:
            poly = _clip_near(poly, cam.near)
            if len(poly) < 3:
                continue
        proj = [cam.project(p[0]) for p in poly]
        for k in range(1, len(poly) - 1):
            tri = (0, k, k + 1)
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = proj[0], proj[k], proj[k + 1]
            # buffer y grows downward; CCW in y-up space is negative area here
            area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
            if area == 0:
                continue
            if area > 0 and not two_sided:
                continue
            if area > 0:
                # back face of a two-sided material: swap to keep the edge functions positive
                tri = (0, k + 1, k)
                (x1, y1, z1), (x2, y2, z2) = (x2, y2, z2), (x1, y1, z1)
                area = -area
            pa, pb, pc = poly[tri[0]], poly[tri[1]], poly[tri[2]]
            minx = max(0, int(math.floor(min(x0, x1, x2))))
            maxx = min(W - 1, int(math.ceil(max(x0, x1, x2))))
            miny = max(0, int(math.floor(min(y0, y1, y2))))
            maxy = min(H - 1, int(math.ceil(max(y0, y1, y2))))
            if minx > maxx or miny > maxy:
                continue
            inv_area = 1.0 / area
            w0i, w1i, w2i = 1.0 / z0, 1.0 / z1, 1.0 / z2
            la, lb, lc = pa[1], pb[1], pc[1]
            ua, ub, uc = pa[2], pb[2], pc[2]
            # top-left rule bias (edges with y-down orientation, CW in buffer space)
            def bias(ax, ay, bx, by):
                ex, ey = bx - ax, by - ay
                return 0.0 if (ey > 0 or (ey == 0 and ex < 0)) else -1e-9
            b0 = bias(x1, y1, x2, y2)
            b1 = bias(x2, y2, x0, y0)
            b2 = bias(x0, y0, x1, y1)
            # mip footprint: per pixel on big triangles, at the centroid on small ones
            lod = 0.0
            per_pixel_lod = False
            if tex is not None and not d.env and lod_mode:
                if -area > 2000:
                    per_pixel_lod = True
                else:
                    cxm, cym = (x0 + x1 + x2) / 3.0 - 0.5, (y0 + y1 + y2) / 3.0 - 0.5
                    e0c = ((x2 - x1) * (cym + 0.5 - y1) - (y2 - y1) * (cxm + 0.5 - x1)) * inv_area
                    e1c = ((x0 - x2) * (cym + 0.5 - y2) - (y0 - y2) * (cxm + 0.5 - x2)) * inv_area
                    e2c = 1.0 - e0c - e1c
                    qc = e0c * w0i + e1c * w1i + e2c * w2i
                    uc0 = (ua[0] * e0c * w0i + ub[0] * e1c * w1i + uc[0] * e2c * w2i) / qc
                    vc0 = (ua[1] * e0c * w0i + ub[1] * e1c * w1i + uc[1] * e2c * w2i) / qc
                    lod = _lod(cxm, cym, x0, y0, x1, y1, x2, y2, inv_area, w0i, w1i, w2i, ua, ub, uc, uc0, vc0,
                               texsize, ss)
            for py in range(miny, maxy + 1):
                fy = py + 0.5
                base = py * W
                for px in range(minx, maxx + 1):
                    fx = px + 0.5
                    e0 = ((x2 - x1) * (fy - y1) - (y2 - y1) * (fx - x1)) * inv_area
                    if e0 < b0:
                        continue
                    e1 = ((x0 - x2) * (fy - y2) - (y0 - y2) * (fx - x2)) * inv_area
                    if e1 < b1:
                        continue
                    e2 = 1.0 - e0 - e1
                    if e2 < b2:
                        continue
                    q0, q1, q2 = e0 * w0i, e1 * w1i, e2 * w2i
                    qs = q0 + q1 + q2
                    z = 1.0 / qs
                    i = base + px
                    if z >= Z[i]:
                        continue
                    q0 *= z
                    q1 *= z
                    q2 *= z
                    lr = la[0] * q0 + lb[0] * q1 + lc[0] * q2
                    lg = la[1] * q0 + lb[1] * q1 + lc[1] * q2
                    lbb = la[2] * q0 + lb[2] * q1 + lc[2] * q2
                    if tex is not None:
                        u = ua[0] * q0 + ub[0] * q1 + uc[0] * q2
                        v = ua[1] * q0 + ub[1] * q1 + uc[1] * q2
                        if per_pixel_lod:
                            lod = _lod(px, py, x0, y0, x1, y1, x2, y2, inv_area, w0i, w1i, w2i, ua, ub, uc, u, v,
                                       texsize, ss)
                        tr, tg, tb, ta = tex.sample(u, v, lod)
                        tr *= cr
                        tg *= cg
                        tb *= cb
                    else:
                        tr, tg, tb, ta = cr, cg, cb, 1.0
                    if alpha_key and ta < 0.878:
                        continue
                    r, g, b = tr * lr, tg * lg, tb * lbb
                    if fog:
                        fc, fs, fe = fog
                        f = (z - fs) / (fe - fs)
                        if f > 0:
                            f = 1.0 if f > 1 else f
                            r += (fc[0] - r) * f
                            g += (fc[1] - g) * f
                            b += (fc[2] - b) * f
                    if blend <= 1:
                        R[i], Gc[i], Bc[i] = r, g, b
                        Z[i] = z
                        M[i] = d.tag
                    else:
                        a = ta * d.alpha
                        _blend(frame, i, r, g, b, a, blend)
                        if zwrite:
                            Z[i] = z
                        if M[i] == 0:
                            M[i] = d.tag if a > 0.2 else 0


def _lod(px, py, x0, y0, x1, y1, x2, y2, inv_area, w0i, w1i, w2i, ua, ub, uc, u, v, texsize, ss):
    """log2 of the texel footprint of one output pixel (ss buffer pixels)."""
    def at(fx, fy):
        e0 = ((x2 - x1) * (fy - y1) - (y2 - y1) * (fx - x1)) * inv_area
        e1 = ((x0 - x2) * (fy - y2) - (y0 - y2) * (fx - x2)) * inv_area
        e2 = 1.0 - e0 - e1
        q0, q1, q2 = e0 * w0i, e1 * w1i, e2 * w2i
        qs = q0 + q1 + q2
        return ((ua[0] * q0 + ub[0] * q1 + uc[0] * q2) / qs, (ua[1] * q0 + ub[1] * q1 + uc[1] * q2) / qs)
    ux, vx = at(px + 1.5, py + 0.5)
    uy, vy = at(px + 0.5, py + 1.5)
    dx = math.hypot(ux - u, vx - v)
    dy = math.hypot(uy - u, vy - v)
    rho = max(dx, dy) * texsize * ss
    return math.log2(rho) if rho > 1.0 else 0.0


def _blend(frame, i, r, g, b, a, mode):
    R, Gc, Bc = frame.r, frame.g, frame.b
    if mode == 2:
        R[i] = r * a + R[i] * (1 - a)
        Gc[i] = g * a + Gc[i] * (1 - a)
        Bc[i] = b * a + Bc[i] * (1 - a)
    elif mode == 3:
        R[i] = min(1.0, R[i] + r)
        Gc[i] = min(1.0, Gc[i] + g)
        Bc[i] = min(1.0, Bc[i] + b)
    elif mode == 4:
        R[i] = min(1.0, R[i] + r * a)
        Gc[i] = min(1.0, Gc[i] + g * a)
        Bc[i] = min(1.0, Bc[i] + b * a)
    elif mode == 5:
        R[i] *= r
        Gc[i] *= g
        Bc[i] *= b
    elif mode == 6:
        R[i] = min(1.0, 2 * R[i] * r)
        Gc[i] = min(1.0, 2 * Gc[i] * g)
        Bc[i] = min(1.0, 2 * Bc[i] * b)


def draw_scene(frame, drawables):
    """Pass 1 (blend 0, 1), then pass 2 (blend >= 2) far to near by (priorityPlane, depth)."""
    cam = frame.cam
    for d in drawables:
        if d.blend <= 1:
            draw(frame, d)
    rest = [d for d in drawables if d.blend >= 2]

    def depth(d):
        if not d.pos:
            return 0.0
        c = [sum(p[k] for p in d.pos) / len(d.pos) for k in range(3)]
        return cam.view(c)[2]
    rest.sort(key=lambda d: (d.priority, -depth(d)))
    for d in rest:
        draw(frame, d, True)


# ------------------------------------------------------------------------------------------- particles

def particle_drawables(m, textures, xform=None, cam=None, stages=(0.15, 0.5, 0.85), per_stage=3):
    out = []
    if cam is None:
        return out
    for pi, p in enumerate(m["particles"]):
        if not p["flags"] & 0x60000:
            continue  # the client would divide by zero; nothing is drawn here
        t = p["tracks"]
        speed = t.get("speed") or 0.0
        life = t.get("life") or 1.0
        grav = t.get("gravity") or 0.0
        lat = t.get("latitude") or 0.0
        tinfo = m["textures"][p["textureIndex"]] if p["textureIndex"] < len(m["textures"]) else None
        tex = textures.get(tinfo["path"], tinfo["flags"]) if tinfo else None
        ptr = p["partTracks"]
        times = [x / 32767.0 for x in ptr["scale"]["times"]] or [0.0]
        lit_emitter = not (p["flags"] & 0x1)
        mflags = 0x04 | 0x10 | (0 if lit_emitter else 0x01) | (0x02 if p["flags"] & 0x8 else 0)
        up = G.norm(G.mat_apply_dir(G.mat_normal(xform), (0.0, 0.0, 1.0))) if xform else (0.0, 0.0, 1.0)
        for si, st in enumerate(stages):
            age = st * life
            for k in range(per_stage):
                a = 2 * math.pi * (k + 0.37 * si) / per_stage
                spread = math.sin(lat) * (0.4 + 0.6 * ((k * 7 + si * 3) % 5) / 4.0)
                dirv = G.norm((math.cos(a) * spread, math.sin(a) * spread, 1.0))
                pos = list(p["position"])
                for c in range(3):
                    pos[c] += dirv[c] * speed * age
                pos[2] += -0.5 * grav * age * age
                if xform:
                    pos = G.mat_apply(xform, pos)
                sc = _track_at(ptr["scale"], times, st)
                al = _track_at(ptr["alpha"], times, st)
                co = _track_at(ptr["color"], times, st)
                s = sc[0] if isinstance(sc, tuple) else sc
                alpha = (al[0] if isinstance(al, tuple) else al) / 32767.0
                col = tuple(c / 255.0 for c in co) if isinstance(co, tuple) else (1.0, 1.0, 1.0)
                q = _billboard(cam, pos, s)
                nrm = up if lit_emitter else G.mul(cam.zv, -1.0)
                out.append(Drawable(q, [nrm] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                    [(0, 2, 1), (0, 3, 2)], tex, p["blend"] if p["blend"] >= 2 else 2,
                                    mflags, False, col, priority=p.get("priorityPlane", 0),
                                    alpha=alpha, tag=3))
    return out


def _track_at(tr, times, t):
    vals = tr["values"]
    if not vals:
        return (0.0,)
    if len(vals) == 1 or t <= times[0]:
        return vals[0]
    for k in range(len(times) - 1):
        if times[k] <= t <= times[k + 1]:
            f = (t - times[k]) / ((times[k + 1] - times[k]) or 1)
            a, b = vals[k], vals[k + 1]
            return tuple(a[i] + (b[i] - a[i]) * f for i in range(len(a)))
    return vals[-1]


def _billboard(cam, c, s):
    x = G.mul(cam.xv, s)
    y = G.mul(cam.yv, s)
    return [G.sub(G.sub(c, x), G.mul(y, -1.0)), G.add(G.add(c, x), y), G.add(G.sub(c, y), x),
            G.sub(G.sub(c, x), y)]


# -------------------------------------------------------------------------------------------- overlays

def draw_line3d(frame, a, b, color, width=1):
    cam = frame.cam
    va, vb = cam.view(a), cam.view(b)
    if va[2] < cam.near or vb[2] < cam.near:
        return
    (x0, y0, _), (x1, y1, _) = cam.project(va), cam.project(vb)
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for k in range(n + 1):
        t = k / float(n)
        x = int(x0 + (x1 - x0) * t)
        y = int(y0 + (y1 - y0) * t)
        for dy in range(width):
            for dx in range(width):
                X, Y = x + dx, y + dy
                if 0 <= X < frame.w and 0 <= Y < frame.h:
                    i = Y * frame.w + X
                    frame.r[i], frame.g[i], frame.b[i] = color


def overlay_collision(frame, m, xform=None, color=(1.0, 0.15, 0.1)):
    col = m["collision"]
    pts = col["positions"]
    if xform:
        pts = [G.mat_apply(xform, p) for p in pts]
    ind = col["indices"]
    for k in range(0, len(ind) - 2, 3):
        a, b, c = pts[ind[k]], pts[ind[k + 1]], pts[ind[k + 2]]
        for p, q in ((a, b), (b, c), (c, a)):
            draw_line3d(frame, p, q, color, frame.cam.ss)


def overlay_bounds(frame, lo, hi, xform=None, color=(1.0, 0.9, 0.1)):
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    if xform:
        corners = [G.mat_apply(xform, p) for p in corners]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    for a, b in edges:
        draw_line3d(frame, corners[a], corners[b], color, frame.cam.ss)
