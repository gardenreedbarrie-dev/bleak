"""The lettered test cube (M2 art smoke test, V30): 1 yd, base at the origin, every face named after its axis
with a yellow dot at the face's UV (0, 0) corner, a steam emitter (head quads, lit) and an ember emitter (head
quads, flag 0x1 unlit, V33) on top. Not a café piece: no display id."""

from .. import build as B
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "Cube"
DISPLAY = None

FACES = {
    "+x": ("FRONT", "+X", T.hexc("C83A28")),
    "-x": ("BACK", "-X", T.hexc("6A2A20")),
    "+y": ("LEFT", "+Y", T.hexc("3A9A48")),
    "-y": ("RIGHT", "-Y", T.hexc("1E5A2A")),
    "+z": ("TOP", "+Z", T.hexc("3A6AC8")),
    "-z": ("BOTTOM", "-Z", T.hexc("1E2E6A")),
}


def _face_decal(name):
    label, sub, col = FACES[name]

    def f(w, h):
        return P2.cube_face(w, h, {"color": col, "name": label, "sub": sub})
    return f


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (1.0, 1.0, 1.0)
    d.budget = 200
    d.kind = "test"
    d.max_height = 1.0
    d.atlas = {"atlas": 256}
    mesh = G.box(1.0, 1.0, 1.0)
    d.add(B.Part("cube", mesh, "opaque", "atlas", ("flat", {"color": (1.0, 1.0, 1.0)}),
                 decals={k: _face_decal(k) for k in FACES}))
    h = 0.5
    pos = [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0), (-h, -h, 1), (h, -h, 1), (h, h, 1), (-h, h, 1)]
    tris = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7),
            (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    d.collision = (pos, tris)
    d.particles = [
        B.ParticleDef((0.2, 0.0, 1.0), "Steam"),
        B.ParticleDef((-0.2, 0.0, 1.0), "Steam", flags=0x20001, blend=4, colors=((255.0, 140.0, 40.0),) * 3,
                      scales=((0.03, 0.03), (0.02, 0.02), (0.0, 0.0)), emission_rate=10.0, life=1.0, speed=0.5,
                      gravity=-0.2),
    ]
    d.model_frame = {"position": [0, 0, -0.5], "scale": 1.0, "facing": 0.6}
    return d
