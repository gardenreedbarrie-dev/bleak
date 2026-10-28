"""One module per model (CAFE.SPEC.md section 5.8). Each defines NAME and build(opts) -> build.PropDef."""

from . import cube, espresso_sw

REGISTRY = {
    cube.NAME: cube,
    espresso_sw.NAME: espresso_sw,
}

# Section 5.8: every model of the café (name, display, size W(Y) x D(X) x H, triangle budget). Only the ones in
# REGISTRY are built in M1; the rest come in M5 after the in-game look at the M2 art smoke test (section 7.4).
CATALOGUE = [
    ("EspressoSW", 19300, (1.3, 0.7, 0.9), 4000), ("EspressoOrg", 19301, (1.4, 0.75, 0.95), 4500),
    ("GrinderSW", 19302, (0.5, 0.5, 0.85), 1200), ("GrinderOrg", 19303, (0.55, 0.55, 0.9), 1200),
    ("BlenderSW", 19304, (0.35, 0.35, 0.7), 800), ("BlenderOrg", 19305, (0.4, 0.4, 0.75), 900),
    ("KettleStoveSW", 19306, (0.8, 0.6, 1.1), 1600), ("KettleStoveOrg", 19307, (0.85, 0.65, 1.0), 1600),
    ("ColdBoxSW", 19308, (1.1, 0.7, 0.8), 1200), ("ColdBoxOrg", 19309, (1.1, 0.75, 0.85), 1200),
    ("SyrupRackSW", 19310, (1.4, 0.4, 0.9), 1600), ("SyrupRackOrg", 19311, (1.45, 0.45, 0.9), 1600),
    ("CounterSW", 19312, (5.0, 0.8, 1.05), 1000), ("CounterOrg", 19313, (5.0, 0.85, 1.05), 1000),
    ("BackBarSW", 19314, (6.0, 0.8, 1.05), 900), ("BackBarOrg", 19315, (6.0, 0.85, 1.05), 900),
    ("ParasolSW", 19316, (2.8, 2.8, 3.2), 700), ("ParasolOrg", 19317, (2.8, 2.8, 3.3), 800),
    ("ChalkboardSW", 19318, (0.9, 0.5, 1.4), 300), ("ChalkboardOrg", 19319, (0.95, 0.5, 1.45), 300),
    ("CupSW", 19320, (0.22, 0.22, 0.15), 200), ("MugOrg", 19321, (0.2, 0.2, 0.22), 200),
    ("ShakeGlass", 19322, (0.16, 0.16, 0.5), 300), ("TipJar", 19323, (0.25, 0.25, 0.3), 300),
]
