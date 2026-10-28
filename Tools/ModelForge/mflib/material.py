"""Material presets (CAFE.SPEC.md section 5.2.5).

blendMode is M2Material.m_blendMode, mapped by the client through s_blendModes (M2Scene.cpp:30) to
Opaque, AlphaKey, Alpha, NoAlphaAdd, Add, Mod, Mod2x. Material flags (CM2SceneRender.cpp:204, 296-311):
0x01 unlit, 0x02 unfogged, 0x04 two-sided (no culling), 0x08 no depth test, 0x10 no depth write.

`coord` is the batch's textureCoordComboIndex: 0 = UV set 0 (textureCoordCombos[0] = 0), 1 = the sphere-map env
slot (textureCoordCombos[1] = 0xFFFF; SubstituteSimpleShaders turns a coord combo > 2 into the env shader,
M2Shared.cpp:638-662).
"""

PRESETS = {
    # name: blend, flags, priorityPlane, coord
    "opaque": (0, 0x00, 0, 0),
    "cutout": (1, 0x04, 0, 0),
    "glass": (2, 0x10, 1, 0),
    "glass1": (2, 0x10 | 0x04, 1, 0),   # single-shell glass: both sides drawn
    "glow": (4, 0x01 | 0x10 | 0x04, 0, 0),
    "chrome": (0, 0x00, 0, 1),
}

UNLIT = 0x01
UNFOGGED = 0x02
TWO_SIDED = 0x04
NO_DEPTH_TEST = 0x08
NO_DEPTH_WRITE = 0x10


def preset(name):
    if name not in PRESETS:
        raise KeyError("unknown material preset %r (known: %s)" % (name, ", ".join(sorted(PRESETS))))
    blend, flags, prio, coord = PRESETS[name]
    return {"blend": blend, "flags": flags, "priority": prio, "coord": coord}


def is_alpha(name):
    return PRESETS[name][0] >= 1
