"""cafe.json: the catalogue's rules (cflib/catalog.py) on the real file, the design tables of the café spec held
number for number, and every rule broken on purpose. No game data is used.

    python3 -I -m unittest discover -s Tools/CafeForge/tests -p "test_*.py"
"""

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from cflib import REPO  # noqa: E402
from cflib import catalog as C  # noqa: E402

# Section 2.5: n -> (archetype, tier, unlock level, steps, checklist lines).
RECIPES = {
    1: ("C1", 1, 1, [1, 3, 4, 25], 4), 2: ("C2", 1, 1, [1, 3, 5, 25], 4), 3: ("C3", 2, 2, [1, 3, 6, 16, 25], 5),
    4: ("C4", 2, 3, [1, 3, 3, 19, 25], 4), 5: ("C5", 3, 4, [1, 3, 20, 5, 23, 25], 6),
    6: ("C6", 3, 5, [1, 3, 12, 13, 17, 25], 6), 7: ("C7", 5, 9, [1, 3, 3, 18, 5, 23, 25], 6),
    8: ("T1", 1, 1, [7, 8, 16, 25], 4), 9: ("T2", 1, 1, [7, 9, 14, 25], 4), 10: ("T3", 2, 3, [2, 7, 10, 16, 25], 5),
    11: ("T4", 3, 5, [7, 8, 22, 12, 25], 5), 12: ("T5", 3, 6, [7, 9, 19, 6, 25], 5),
    13: ("T6", 4, 8, [7, 8, 21, 16, 5, 25], 6), 14: ("M1", 1, 2, [11, 17, 15, 25], 4),
    15: ("M2", 2, 2, [11, 13, 21, 15, 25], 5), 16: ("M3", 3, 4, [11, 11, 20, 15, 23, 25], 5),
    17: ("M4", 3, 6, [11, 13, 22, 15, 12, 25], 6), 18: ("M5", 4, 7, [11, 11, 16, 14, 15, 23, 25], 6),
    19: ("M6", 5, 10, [11, 11, 11, 18, 20, 15, 23, 25], 6),
}
# Section 2.4: id -> (station, key, kind, durMs, gold, name, step spell).
ACTIONS = {
    1: ("G", 1, "T", 1500, None, "Grind Beans"), 2: ("G", 2, "T", 1200, None, "Crush Spices"),
    3: ("E", 1, "H", 3000, [700, 850], "Pull Shot"), 4: ("E", 2, "T", 1000, None, "Hot Water"),
    5: ("E", 3, "H", 2500, [650, 800], "Steam Milk"), 6: ("E", 4, "H", 2000, [400, 600], "Froth Foam"),
    7: ("K", 1, "T", 2000, None, "Boil Water"), 8: ("K", 2, "H", 3000, [350, 500], "Steep Light"),
    9: ("K", 3, "H", 3000, [700, 850], "Steep Strong"), 10: ("K", 4, "H", 3500, [550, 700], "Simmer Spiced"),
    11: ("C", 1, "T", 1000, None, "Scoop Ice Cream"), 12: ("C", 2, "T", 800, None, "Add Ice"),
    13: ("C", 3, "T", 1000, None, "Pour Cold Milk"), 14: ("C", 4, "T", 1000, None, "Pour Cream"),
    15: ("B", 1, "H", 2500, [550, 750], "Blend"), 16: ("S", 1, "T", 800, None, "Honey"),
    17: ("S", 2, "T", 800, None, "Vanilla"), 18: ("S", 3, "T", 800, None, "Caramel"),
    19: ("S", 4, "T", 800, None, "Cinnamon"), 20: ("S", 5, "T", 800, None, "Chocolate"),
    21: ("S", 6, "T", 800, None, "Elwynn Berry"), 22: ("S", 7, "T", 800, None, "Mint"),
    23: ("S", 8, "T", 1000, None, "Whipped Cream"), 24: ("V", 1, "T", 500, None, "Take Order"),
    25: ("V", 2, "T", 1000, None, "Serve"), 26: ("V", 3, "T", 500, None, "Bin"),
}
# Section 2.7: the display-gender table of the stock "[PH] Gossip NPC" rows.
GENDERS = {19175: "f", 19176: "m", 19177: "f", 19178: "m", 19181: "f", 19182: "m", 19183: "f", 19184: "m",
           19185: "f", 19186: "m", 19187: "f", 19188: "m", 19340: "f", 19343: "m"}
# Section 5.8: display -> W x D x H. ModelForge's tests hold every built model to cafe.json's size.
SIZES = {
    19300: [1.3, 0.7, 0.9], 19301: [1.4, 0.75, 0.95], 19302: [0.5, 0.5, 0.85], 19303: [0.55, 0.55, 0.9],
    19304: [0.35, 0.35, 0.7], 19305: [0.4, 0.4, 0.75], 19306: [0.8, 0.6, 1.1], 19307: [0.85, 0.65, 1.0],
    19308: [1.1, 0.7, 0.8], 19309: [1.1, 0.75, 0.85], 19310: [1.4, 0.4, 0.9], 19311: [1.45, 0.45, 0.9],
    19312: [5.0, 0.8, 1.05], 19313: [5.0, 0.85, 1.05], 19314: [6.0, 0.8, 1.05], 19315: [6.0, 0.85, 1.05],
    19316: [2.8, 2.8, 3.2], 19317: [2.8, 2.8, 3.3], 19318: [0.9, 0.5, 1.4], 19319: [0.95, 0.5, 1.45],
    19320: [0.22, 0.22, 0.15], 19321: [0.2, 0.2, 0.22], 19322: [0.16, 0.16, 0.5], 19323: [0.25, 0.25, 0.3],
}

DOC = C.load()


def problems_after(change):
    """The problems of a copy of cafe.json after change(doc)."""
    doc = copy.deepcopy(DOC)
    change(doc)
    return C.validate(doc)


def find(items, **kw):
    return next(i for i in items if all(i.get(k) == v for k, v in kw.items()))


def layout_row(doc, cafe, role):
    return next(r for r in doc["layout"] if r["role"] == role and r.get("cafe", cafe) == cafe)


class RealCatalogue(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(C.validate(DOC), [])

    def test_recipes_match_the_design(self):
        self.assertEqual(len(DOC["recipes"]), 19)
        for r in DOC["recipes"]:
            arch, tier, unlock, steps, lines = RECIPES[r["n"]]
            self.assertEqual((r["arch"], r["tier"], r["unlock"], r["steps"]), (arch, tier, unlock, steps), r["arch"])
            self.assertEqual(C.lines_of(r["steps"]), lines, r["arch"])
            self.assertEqual(r["family"], arch[0])

    def test_actions_match_the_design(self):
        self.assertEqual(len(DOC["actions"]), 26)
        for a in DOC["actions"]:
            st, key, kind, dur, gold, name = ACTIONS[a["id"]]
            self.assertEqual((a["station"], a["key"], a["kind"], a["durMs"], a.get("gold"), a["name"]),
                             (st, key, kind, dur, gold, name))
            self.assertEqual(a["spell"], 100900 + a["id"])
        self.assertEqual(find(DOC["actions"], id=21)["hordeName"], "Cactus Apple")

    def test_every_gold_zone_is_wide_enough(self):
        for a in DOC["actions"]:
            if a["kind"] == "H":
                lo, hi = a["gold"]
                self.assertGreaterEqual((hi - lo) * a["durMs"] / 1000, 375, a["name"])

    def test_every_ingredient_is_used(self):
        used = {s for r in DOC["recipes"] for s in r["steps"]}
        self.assertEqual(sorted(set(range(1, 24)) - used), [])
        self.assertNotIn(24, used)
        self.assertNotIn(26, used)

    def test_levels_and_tiers(self):
        self.assertEqual([lv["xp"] for lv in DOC["levels"]], [0, 120, 320, 620, 1040, 1600, 2320, 3220, 4320, 5640])
        self.assertEqual([lv["tickets"] for lv in DOC["levels"]], [1, 1, 1, 2, 2, 2, 2, 3, 3, 3])
        for lv in DOC["levels"]:
            unlocked = sorted(r["arch"] for r in DOC["recipes"] if r["unlock"] == lv["level"])
            self.assertEqual(unlocked, sorted(C.LEVELS[lv["level"]][2]))
        t = {int(k): v for k, v in DOC["tiers"].items()}
        self.assertEqual([t[i]["price80"] for i in range(1, 6)], [4000, 6000, 9000, 12000, 18000])
        self.assertEqual([t[i]["buffMin"] for i in range(1, 6)], [30, 35, 40, 45, 50])
        self.assertEqual([t[i]["xp"] for i in range(1, 6)], [8, 12, 18, 25, 35])
        self.assertEqual([t[i]["tip"] for i in range(1, 6)], [400, 600, 900, 1300, 1800])

    def test_walkthrough_numbers(self):
        """The section 1.2/1.3 examples come out of the tier numbers: a T1 Perfect fast drink is 14 XP and a level 34
        barista's tip 2s 55c; a level 40 customer pays 33s for the Honey Cappuccino with a 10% tip."""
        t = {int(k): v for k, v in DOC["tiers"].items()}
        self.assertEqual(int(t[1]["xp"] * 1.5 * 1.2), 14)
        self.assertEqual(int(t[1]["tip"] * 1.5 * 1.0 * 34 / 80), 255)
        c3 = find(DOC["recipes"], arch="C3")
        price = max(200, -(-int(t[c3["tier"]]["price80"] * max(0.10, 40 / 80)) // 100) * 100)
        self.assertEqual(price + price * 10 // 100, 3300)

    def test_gender_table(self):
        self.assertEqual({d: g for d, (_race, g) in C.DISPLAY_GENDER.items()}, GENDERS)
        for who in DOC["staff"] + [p for p in DOC["personas"] if p["kind"] == "named"]:
            d = who["displays"][0]
            if d in GENDERS:
                self.assertEqual(who["gender"], GENDERS[d], who["name"])

    def test_sizes_are_the_model_table(self):
        got = {g["display"]: g["size"] for g in DOC["gameobjects"] if "model" in g}
        self.assertEqual(got, SIZES)

    def test_sizes_agree_with_modelforge(self):
        cat = C.modelforge_catalogue(REPO)
        if cat is None:
            self.skipTest("Tools/ModelForge not found")
        self.assertEqual(C.modelforge_problems(DOC, cat), [])

    def test_ids_and_counts(self):
        self.assertEqual(len(DOC["personas"]), 50)
        self.assertEqual(sorted(p["entry"] for p in DOC["personas"] if p["cafe"] == 1),
                         list(range(909320, 909345)))
        self.assertEqual(sorted(p["entry"] for p in DOC["personas"] if p["cafe"] == 2),
                         list(range(909350, 909375)))
        self.assertEqual(sorted(s["entry"] for s in DOC["staff"]),
                         [909300, 909301, 909302, 909303, 909305, 909306, 909307, 909308, 909309, 909310])
        entries = sorted([g["entry"] for g in DOC["gameobjects"]] +
                         [g["standin"]["entry"] for g in DOC["gameobjects"] if "standin" in g])
        self.assertEqual(entries, list(range(909300, 909324)) + list(range(909330, 909354)) +
                         list(range(909360, 909380)))
        self.assertEqual([i["entry"] for i in DOC["items"]], list(range(909380, 909385)))
        self.assertEqual(sorted(w["spell"]["id"] for w in DOC["dbc"]["spells"]), C.CAFE_SPELLS)
        self.assertEqual([i["id"] for i in DOC["dbc"]["icons"]], list(range(19300, 19314)))

    def test_layout_of_both_cafes(self):
        for cafe in (1, 2):
            self.assertEqual(C.layout_problems(DOC, cafe), [])
            rows = C.cafe_layout(DOC, cafe)
            spots = {C.station_of(r): C.work_spots(r) for r in rows if C.station_of(r)}
            want = {"V": (1.6, 0.35), "B": (1.6, -1.65), "E": (4.0, 0.35), "G": (4.0, 2.35), "S": (4.0, -1.65),
                    "K": (2.75, 4.4), "C": (2.05, -4.4)}
            for st, (f, l) in want.items():
                self.assertAlmostEqual(spots[st][0][0], f, places=6, msg=st)
                self.assertAlmostEqual(spots[st][0][1], l, places=6, msg=st)
            self.assertEqual(len([r for r in rows if r["role"].startswith("chair_")]), 12)
            self.assertEqual(len([r for r in rows if r["role"].startswith("path_")]), 9)

    def test_rush_groups_and_children(self):
        for cafe in (1, 2):
            groups = [p for p in DOC["personas"] if p["cafe"] == cafe and p["kind"] == "group"]
            self.assertEqual(len(groups), 2)
            for g in groups:
                self.assertEqual((g["groupSize"], len(g["fav"])), (3, 3))
        children = sorted(p["name"] for p in DOC["personas"] if p["child"])
        self.assertEqual(children, ["Horde Child", "Little Grak", "Little Wendel", "Stormwind Child"])

    def test_named_order_lines_name_the_first_favourite(self):
        """Spot checks: the line is said only for the first favourite, so it must be about that drink."""
        sw = {r["arch"]: r["names"]["1"][0] for r in DOC["recipes"]}
        corwin = find(DOC["personas"], entry=909320)
        self.assertIn(sw[corwin["fav"][0]], corwin["order"])
        tilly = find(DOC["personas"], entry=909321)
        self.assertEqual(tilly["fav"][0], "M1")
        self.assertIn("vanilla", tilly["order"])

    def test_disabled_eredar(self):
        m = find(DOC["personas"], entry=909367)
        self.assertEqual((m["enabled"], m["displays"]), (False, [0]))


class BrokenOnPurpose(unittest.TestCase):
    def assertProblem(self, change, needle):
        got = problems_after(change)
        self.assertTrue(any(needle in p for p in got), "%r not in %s" % (needle, got))

    def test_duplicate_and_outside_ids(self):
        self.assertProblem(lambda d: d["personas"][1].update(entry=d["personas"][0]["entry"]), "entry used twice")
        self.assertProblem(lambda d: d["personas"][0].update(entry=909400), "outside the creatures block")
        self.assertProblem(lambda d: d["items"][0].update(entry=909390), "outside the items block")
        self.assertProblem(lambda d: d["ids"].update(spells=[100900, 100999]), "id registry")

    def test_recipe_rules(self):
        self.assertProblem(lambda d: d["recipes"][0].update(steps=[1, 4, 25]), "timed step")
        self.assertProblem(lambda d: d["recipes"][0].update(steps=[1, 3, 4]), "end with Serve")
        self.assertProblem(lambda d: d["recipes"][0].update(steps=[1, 3, 25, 4, 25]), "end with Serve")
        self.assertProblem(lambda d: d["recipes"][0].update(steps=[1, 3, 99, 25]), "unknown action")
        self.assertProblem(lambda d: d["recipes"][0].update(steps=[1, 3] + [4] * 11 + [25]), "more than 12")
        self.assertProblem(lambda d: d["recipes"][0].update(unlock=2), "barista level that unlocks it")
        self.assertProblem(lambda d: d["recipes"][1]["names"]["1"].__setitem__(0, "Cathedral Black"), "used twice")
        self.assertProblem(lambda d: d["tiers"]["1"].update(xp=9), "tiers.1")
        self.assertProblem(lambda d: d["levels"][3].update(tickets=3), "level 4")

    def test_action_rules(self):
        self.assertProblem(lambda d: find(d["actions"], id=5).update(gold=[650, 790]), "less than 375")
        self.assertProblem(lambda d: find(d["actions"], id=5).update(gold=[20, 700]), "never clamps")
        self.assertProblem(lambda d: find(d["actions"], id=4).update(gold=[100, 900]), "only a timed action")
        self.assertProblem(lambda d: find(d["actions"], id=4).update(key=1), "unique at station E")
        self.assertProblem(lambda d: find(d["actions"], id=4).update(spell=100999), "spell must be")
        self.assertProblem(lambda d: find(d["actions"], id=4).update(glyph="spoon"), "unknown glyph")
        self.assertProblem(lambda d: find(d["actions"], id=4).update(emote={"state": 1}), "known emote")

    def test_genders_and_lore(self):
        self.assertProblem(lambda d: find(d["personas"], entry=909328).update(gender="m"),
                           "does not match display 19177")
        self.assertProblem(lambda d: find(d["staff"], entry=909301).update(gender="f"), "does not match display")
        self.assertProblem(lambda d: find(d["personas"], entry=909342)["displays"].append(19340), "no goblins")
        self.assertProblem(lambda d: find(d["personas"], entry=909330).update(race="goblin"), "no goblins")
        self.assertProblem(lambda d: find(d["staff"], entry=909302).update(race="dwarf"), "all human")
        self.assertProblem(lambda d: find(d["personas"], entry=909342).update(gender="m"), "only named personas")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).pop("gender"), "gender must be")

    def test_persona_rules(self):
        self.assertProblem(lambda d: find(d["personas"], entry=909341).update(groupSize=4), "Rush group")
        self.assertProblem(lambda d: find(d["personas"], entry=909341)["fav"].pop(), "Rush group")
        self.assertProblem(lambda d: find(d["personas"], entry=909342).update(order="Hi."), "from its pool")
        self.assertProblem(lambda d: find(d["personas"], entry=909342).update(pool="H"), "pool must be")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).pop("thanks"), "own order, thanks")
        self.assertProblem(lambda d: find(d["personas"], entry=909343)["fav"].append("C1"), "only order milkshakes")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(fav=["X9"]), "archetype codes")
        self.assertProblem(lambda d: find(d["personas"], entry=909367).update(enabled=True), "display 0")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(displays=[0]), "display 0")

    def test_text_caps(self):
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(order="x" * 161), "more than 160")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(name="x" * 49), "more than 48")
        self.assertProblem(lambda d: d["recipes"][0]["names"]["2"].__setitem__(1, "é" * 81), "more than 160")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(thanks="Hot |cff00ff00tea"), "'|'")
        self.assertProblem(lambda d: find(d["personas"], entry=909320).update(thanks="One {drink}."),
                           "unknown placeholder")
        self.assertProblem(lambda d: d["linePools"]["A"]["order"].append("One coffee."), "{drink} once")
        self.assertProblem(lambda d: find(d["staff"], entry=909301)["lines"].update(levelUp="Well done."),
                           "{n} once")

    def test_staff_rules(self):
        self.assertProblem(lambda d: find(d["staff"], entry=909302).update(npcflag=1), "npcflag")
        self.assertProblem(lambda d: find(d["staff"], entry=909300)["lines"].pop("takeover"), "missing 'takeover'")
        self.assertProblem(lambda d: find(d["staff"], entry=909300).update(displays=[5444, 5445]),
                           "exactly one fixed display")
        self.assertProblem(lambda d: find(d["staff"], entry=909307).update(faction=12), "faction must be 29")
        # the owners and head baristas are friendly to both teams: the other team's click reaches the refusal gossip
        self.assertProblem(lambda d: find(d["staff"], entry=909305).update(faction=29), "faction must be 35")
        self.assertProblem(lambda d: find(d["staff"], entry=909301).update(faction=12), "faction must be 35")

    def test_gameobject_rules(self):
        self.assertProblem(lambda d: find(d["gameobjects"], entry=909300).update(display=19301), "entry - 890000")
        self.assertProblem(lambda d: find(d["gameobjects"], entry=909300)["standin"].update(entry=909331),
                           "entry + 30")
        self.assertProblem(lambda d: find(d["gameobjects"], entry=909362).pop("footprint"), "declared footprint")
        self.assertProblem(lambda d: find(d["gameobjects"], entry=909368).update(name="Marker"), "Café marker")
        self.assertProblem(lambda d: find(d["gameobjects"], entry=909360).update(data=[0, 1]), "CHAIR")
        cat = {k: v for k, v in (C.modelforge_catalogue(REPO) or {}).items()}
        if cat:
            doc = copy.deepcopy(DOC)
            find(doc["gameobjects"], entry=909300)["size"] = [1.3, 0.7, 1.0]
            self.assertTrue(any("ModelForge's table says" in p for p in C.modelforge_problems(doc, cat)))

    def test_layout_rules(self):
        def move(cafe, role, **kw):
            return lambda d: layout_row(d, cafe, role).update(**kw)
        self.assertProblem(move(1, "station_G", l=1.0), "first work spots of stations G and E")
        self.assertProblem(move(1, "station_G", l=1.0), "work spots of stations G and E are 0.30")
        self.assertProblem(move(2, "staff_head", f=2.8, l=4.6), "less than 0.8")
        self.assertProblem(move(1, "door", f=-10, l=0), "less than 25")
        self.assertProblem(move(1, "chalkboard", f=0.8, l=1.0), "overlap")
        self.assertProblem(move(1, "station_E", f=5.3), "not inside its parent's top")
        self.assertProblem(move(1, "queue_1", f=0.8, l=0.0), "stands inside the footprint")
        self.assertProblem(move(1, "chair_1", turn=0), "faces its table")
        self.assertProblem(move(1, "tipjar", snap=True), "not ground-snapped")
        self.assertProblem(lambda d: layout_row(d, 1, "counter")["work"].__setitem__(1, [-0.8, 0.5]),
                           "apart, not 0.7")
        self.assertProblem(lambda d: d["layout"].remove(layout_row(d, 2, "chair_12")), "missing chair_12")
        self.assertProblem(lambda d: d["counterCup"].update(f=0.2), "not on the counter top")
        # the rug is a floor decal: walking over it (and the busser standing on it) is fine
        self.assertEqual(C.layout_problems(DOC, 1), [])

    def test_dbc_rules(self):
        def spell(d, sid):
            return next(w for w in d["dbc"]["spells"] if w["spell"]["id"] == sid)
        self.assertProblem(lambda d: spell(d, 100903)["spell"].update(visual=3881), "never 3881")
        self.assertProblem(lambda d: spell(d, 100903).update(castMs=3000), "a timed step is a channel")
        self.assertProblem(lambda d: spell(d, 100901).update(castMs=0), "a tap step is a cast")
        self.assertProblem(lambda d: spell(d, 100901)["spell"]["fields"].update(castingTimeIndex=1),
                           "not a column the café spells set")
        self.assertProblem(lambda d: spell(d, 100901).update(icon=1), "unknown field 'icon'")
        self.assertProblem(lambda d: spell(d, 100901)["spell"].update(mana=5), "unknown field 'mana'")
        self.assertProblem(lambda d: d["dbc"]["spells"].pop(), "once each")
        self.assertProblem(lambda d: d["dbc"]["titles"][1].update(mask=162), "mask 161")

    def test_malformed_input_does_not_crash(self):
        for change in (lambda d: d.update(recipes=[{}]), lambda d: d.update(layout=[{"slot": "x"}]),
                       lambda d: d.update(personas=[None]), lambda d: d["dbc"].update(spells=[{}])):
            self.assertTrue(problems_after(change))
        self.assertEqual(C.validate([]), ["cafe.json must be a JSON object"])


class RaceForgeSpellFormat(unittest.TestCase):
    """CafeForge hands every dbc spell to RaceForge's parse_spell (section 6.3) after adding castingTimeIndex,
    durationIndex and rangeIndex: the spell part must already pass it, and every field must be a Spell column."""

    def test_parse_spell_accepts_every_cafe_spell(self):
        rf = os.path.join(REPO, "Tools", "RaceForge")
        if not os.path.isfile(os.path.join(rf, "rflib", "config.py")):
            self.skipTest("Tools/RaceForge not found")
        if rf not in sys.path:
            sys.path.insert(0, rf)
        from rflib import config, schemas  # noqa: E402
        columns = {c[0] for c in schemas.SCHEMAS["Spell"][4]}
        for i, w in enumerate(DOC["dbc"]["spells"]):
            s = config.parse_spell(w["spell"], i)
            self.assertEqual(s.cast_by, "server")
            for k in s.fields:
                self.assertIn(k, columns, s.name)
        self.assertTrue(set(C.SPELL_FIELDS) <= columns)


if __name__ == "__main__":
    unittest.main()
