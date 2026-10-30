"""One module per model (CAFE.SPEC.md section 5.8). Each defines NAME and build(opts) -> build.PropDef.

The registry is discovered: every module of this package that defines a string NAME and a callable build is a
model, so adding a model is adding its file, with no edit here. Conventions (tests/test_props.py holds them):
- the module is named after the model in snake case (GrinderOrg -> grinder_org.py, BackBarSW -> back_bar_sw.py),
  so a test run limited to some models (MF_MODELS) can tell which broken module is whose;
- NAME is a CATALOGUE name (or a test model such as the cube, with DISPLAY None) and DISPLAY its display id;
- helper modules (no NAME) and modules starting with "_" are skipped.

A module that fails to import does not take the others down (several people add models at once): it is left
out of REGISTRY and its traceback is kept in BROKEN, which `modelforge.py build` and the tests report.

REGISTRY order (the build and manifest order) is deterministic: test models first, by name, then the section 5.8
order of CATALOGUE.
"""

import importlib
import pkgutil
import re
import traceback

# Section 5.8: every model of the café (name, display, size W(Y) x D(X) x H, triangle budget). The tests hold
# every registered model to its row (sizes within 2 cm unless cafe.json says otherwise, the budget, the display).
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
CATALOGUE_NAMES = [row[0] for row in CATALOGUE]


def module_name(name):
    """The module a model lives in: EspressoSW -> espresso_sw, KettleStoveOrg -> kettle_stove_org."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _discover():
    found = {}
    broken = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_") or info.ispkg:
            continue
        try:
            mod = importlib.import_module("." + info.name, __name__)
        except Exception:  # noqa: BLE001  one broken model must not hide the others
            broken[info.name] = traceback.format_exc()
            continue
        name = getattr(mod, "NAME", None)
        if not isinstance(name, str) or not callable(getattr(mod, "build", None)):
            continue
        if name in found:
            broken[info.name] = "NAME %r is already defined by %s" % (name, found[name].__name__)
            continue
        found[name] = mod
    rank = {n: k for k, n in enumerate(CATALOGUE_NAMES)}
    order = sorted(found, key=lambda n: (n in rank, rank.get(n, 0), n))
    return {n: found[n] for n in order}, broken


REGISTRY, BROKEN = _discover()


def broken_for(names):
    """{module: traceback} of the broken modules that would hold any of the given model names."""
    want = {module_name(n) for n in names}
    return {m: tb for m, tb in BROKEN.items() if m in want}
