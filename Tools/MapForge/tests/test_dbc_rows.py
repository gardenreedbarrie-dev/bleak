"""The map's rows: the forge adds exactly the configured rows and touches nothing else."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from dbc import config as configmod  # noqa: E402
from dbc import forge as forgemod  # noqa: E402
from dbc import layout  # noqa: E402
from tests import synth_dbc  # noqa: E402
from tests.synth_dbc import run_forge  # noqa: E402

from rflib.dbc import DbcTable, to_signed  # noqa: E402


class ForgeTests(unittest.TestCase):
    def test_rows_added_and_inputs_untouched(self):
        cfg, tables, result, raw = run_forge()
        output = {name: tables[name].to_bytes() for name in result.changes}
        problems = forgemod.check({n: raw[n] for n in output}, output, cfg, result)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(result.changes), ["AreaTable", "BattlemasterList", "Light", "Map", "PvpDifficulty",
                                                  "WorldMapArea"])

        for name in result.changes:
            before = DbcTable.from_bytes(raw[name], layout.get(name))
            after = tables[name]
            # Every input row is still there, byte for byte, and the string block only grew.
            by_id = after.by_id()

            for row in before.rows:
                self.assertEqual(by_id[to_signed(row[0])], row, name)

            self.assertEqual(bytes(after.strings[:len(before.strings)]), bytes(before.strings), name)

    def test_map_row(self):
        cfg, tables, result, _ = run_forge()
        maps = tables["Map"]
        row = maps.by_id()[901]
        self.assertEqual(maps.get_str(row, "directory"), "BleakholdRoyale")
        self.assertEqual(maps.get(row, "instanceType"), 3)
        self.assertEqual(maps.get(row, "areaTableID"), 5100)
        self.assertEqual(maps.get(row, "maxPlayers"), 40)
        self.assertEqual(maps.get(row, "expansionID"), 0)
        self.assertEqual(maps.get_loc(row, "mapName"), ["Bleakhold Royale"] * 9 + [""] * 7)
        # Values the config leaves out are the template's (Warsong Gulch).
        template = maps.by_id()[489]
        self.assertEqual(maps.get(row, "loadingScreenID"), maps.get(template, "loadingScreenID"))
        self.assertEqual(maps.get(row, "minimapIconScale"), maps.get(template, "minimapIconScale"))
        self.assertEqual(row[maps.col("mapName_flags")], template[maps.col("mapName_flags")])

    def test_zone_is_ffa(self):
        cfg, tables, result, _ = run_forge()
        areas = tables["AreaTable"]
        row = areas.by_id()[5100]
        self.assertEqual(areas.get(row, "continentID"), 901)
        self.assertEqual(areas.get(row, "parentAreaID"), 0)
        flags = areas.get(row, "flags")
        self.assertTrue(flags & 0x80, "AREA_FLAG_ARENA (FFA PvP) must be set")
        self.assertFalse(flags & 0x800, "SANCTUARY must be cleared")
        # The template's sounds are kept.
        template = areas.by_id()[3277]
        self.assertEqual(areas.get(row, "ambienceID"), areas.get(template, "ambienceID"))
        self.assertEqual(areas.get(row, "zoneMusic"), areas.get(template, "zoneMusic"))
        # A fresh exploration bit, unique over the whole table.
        bits = [areas.get(r, "areaBit") for r in areas.rows]
        self.assertEqual(bits.count(areas.get(row, "areaBit")), 1)
        self.assertEqual(result.area_bits[5100], areas.get(row, "areaBit"))

    def test_subzones_point_at_the_zone(self):
        data = synth_dbc.default_config()
        data["zone"]["subzones"] = [{"id": 5101, "name": "The Crater"}, {"id": 5102, "name": "Storm's Eye"}]
        cfg, tables, result, _ = run_forge(data)
        areas = tables["AreaTable"]

        for area_id in (5101, 5102):
            row = areas.by_id()[area_id]
            self.assertEqual(areas.get(row, "parentAreaID"), 5100)
            self.assertEqual(areas.get(row, "continentID"), 901)

        bits = {result.area_bits[i] for i in (5100, 5101, 5102)}
        self.assertEqual(len(bits), 3)

    def test_inherited_zone_flags_must_be_harmless(self):
        # Template 12 (synthetic "Elwynn Fjord") carries ALLOW_DUELS; subzones copy the row, so they would too.
        data = synth_dbc.default_config()
        data["zone"]["template"] = 12
        data["zone"]["set_flags"] = ["ARENA", "NO_FLY_ZONE"]
        data["zone"]["clear_flags"] = ["SANCTUARY"]
        data["zone"]["subzones"] = [{"id": 5101, "name": "The Bleak Hold"}]
        cfg, tables, result, raw = run_forge(data)
        output = {name: tables[name].to_bytes() for name in result.changes}
        problems = forgemod.check({n: raw[n] for n in output}, output, cfg, result)
        self.assertEqual(len([p for p in problems if "keeps ALLOW_DUELS from template 12" in p]), 2, problems)

        data["zone"]["clear_flags"] = synth_dbc.default_config()["zone"]["clear_flags"]
        cfg, tables, result, raw = run_forge(data)
        output = {name: tables[name].to_bytes() for name in result.changes}
        self.assertEqual(forgemod.check({n: raw[n] for n in output}, output, cfg, result), [])
        row = tables["AreaTable"].by_id()[5101]
        self.assertEqual(tables["AreaTable"].get(row, "flags"), 0x80 | 0x20000000)  # ARENA | NO_FLY_ZONE only
        note = next(n for n in result.notes if n.startswith("zone 5100"))
        self.assertIn("ARENA | NO_FLY_ZONE", note)
        self.assertIn("kept from template 12: none", note)

    def test_harmless_template_flags_stay(self):
        # The default template (3277) has OUTSIDE | OUTLAND: OUTLAND is cleared, OUTSIDE is harmless and stays.
        cfg, tables, result, _ = run_forge()
        flags = tables["AreaTable"].get(tables["AreaTable"].by_id()[5100], "flags")
        self.assertEqual(flags, 0x80 | 0x4000000)
        self.assertEqual(configmod.flag_names(flags), ["ARENA", "OUTSIDE"])
        self.assertTrue(configmod.HARMLESS_TEMPLATE_FLAGS & configmod.AREA_FLAGS["OUTSIDE"])
        self.assertFalse(configmod.HARMLESS_TEMPLATE_FLAGS & configmod.AREA_FLAGS["ALLOW_DUELS"])
        self.assertEqual(configmod.flag_names(0x40000000), ["0x40000000"])

    def test_time_of_day_override(self):
        data = synth_dbc.default_config()
        data["map"]["time_of_day_override"] = 1050
        cfg, tables, result, _ = run_forge(data)
        maps = tables["Map"]
        self.assertEqual(maps.get(maps.by_id()[901], "timeOfDayOverride"), 1050)

    def test_light_from_skybox(self):
        cfg, tables, result, _ = run_forge()
        light = tables["Light"]
        row = light.by_id()[result.light_id]
        self.assertEqual(light.get(row, "continentID"), 901)
        # LightParams 55 is the synthetic row showing WintergraspSmokySky.M2.
        self.assertEqual([light.get(row, f"lightParamsID[{i}]") for i in range(8)], [55] * 8)
        # The default light sits at coordinates (0, 0, 0): DayNight::LightLoad takes it for the whole map.
        self.assertEqual(light.float_value(row, "gameCoords[0]"), 0.0)

    def test_skybox_matches_mdx_rows(self):
        # The stock rows say .mdx; configs name the .M2 (v1's bleakhold_royale.json does). Case, extension (.m2 or
        # .mdx) and slashes do not matter.
        with open(os.path.join(TOOL_DIR, "bleakhold_royale.json"), encoding="utf-8") as f:
            v1 = json.load(f)
        self.assertTrue(v1["light"]["skybox"].endswith(".M2"))
        for name in (v1["light"]["skybox"], "Environments\\Stars\\WintergraspSmokySky.mdx",
                     "ENVIRONMENTS/STARS/WINTERGRASPSMOKYSKY.MDX", "environments\\stars\\wintergraspsmokysky.m2"):
            data = synth_dbc.default_config()
            data["light"] = {"skybox": name}
            _, tables, result, _ = run_forge(data)
            light = tables["Light"]
            row = light.by_id()[result.light_id]
            self.assertEqual([light.get(row, f"lightParamsID[{i}]") for i in range(8)], [55] * 8, name)
        data = synth_dbc.default_config()
        data["light"] = {"skybox": "Environments\\Stars\\WintergraspSmokySky.blp"}
        with self.assertRaisesRegex(forgemod.ForgeError, "no LightSkybox row"):
            run_forge(data)

    def test_time_of_day_off_and_range(self):
        for value, want in (("off", -1), (-1, -1), (0, 0), (1440, 1440)):
            data = synth_dbc.default_config()
            data["map"]["time_of_day_override"] = value
            _, tables, _, _ = run_forge(data)
            maps = tables["Map"]
            self.assertEqual(maps.get_signed(maps.by_id()[901], "timeOfDayOverride"), want, value)
        for bad in (1441, -2, "noon", True, 12.5):
            data = synth_dbc.default_config()
            data["map"]["time_of_day_override"] = bad
            with self.assertRaises(configmod.ConfigError, msg=bad):
                configmod.parse(data)

    def test_light_from_another_map(self):
        data = synth_dbc.default_config()
        data["light"] = {"params_from_map": 532}
        cfg, tables, result, _ = run_forge(data)
        light = tables["Light"]
        row = light.by_id()[result.light_id]
        self.assertEqual([light.get(row, f"lightParamsID[{i}]") for i in range(8)],
                         [55, 55, 55, 55, 60, 55, 55, 55])

    def test_world_map_area_bounds_from_tiles(self):
        cfg, tables, result, _ = run_forge()
        wma = tables["WorldMapArea"]
        row = wma.by_id()[result.world_map_area_id]
        self.assertEqual(wma.get(row, "mapID"), 901)
        self.assertEqual(wma.get(row, "areaID"), 5100)
        left, right = wma.float_value(row, "locLeft"), wma.float_value(row, "locRight")
        top, bottom = wma.float_value(row, "locTop"), wma.float_value(row, "locBottom")
        self.assertGreater(left, right)
        self.assertGreater(top, bottom)
        # Tiles 31-32 both axes: 2 x 533.33 yards around the center, widened to the 1002:668 world map frame.
        self.assertAlmostEqual((top - bottom) / (left - right), 668 / 1002, places=3)
        self.assertGreaterEqual(top - bottom, 2 * 1600 / 3 - 0.01)

    def test_battleground_rows(self):
        cfg, tables, result, _ = run_forge()
        bml = tables["BattlemasterList"]
        row = bml.by_id()[12]
        self.assertEqual(bml.get(row, "mapID[0]"), 901)
        self.assertEqual([bml.get_signed(row, f"mapID[{i}]") for i in range(1, 8)], [-1] * 7)
        self.assertEqual(bml.get(row, "instanceType"), 3)
        self.assertEqual(bml.get(row, "maxGroupSize"), 0)
        self.assertEqual((bml.get(row, "minLevel"), bml.get(row, "maxLevel")), (80, 80))

        pvp = tables["PvpDifficulty"]
        ours = [r for r in pvp.rows if pvp.get(r, "mapID") == 901]
        self.assertEqual(len(ours), 1)
        self.assertEqual(pvp.get(ours[0], "rangeIndex"), 7)
        self.assertEqual((pvp.get(ours[0], "minLevel"), pvp.get(ours[0], "maxLevel")), (80, 80))
        self.assertNotIn(to_signed(ours[0][0]), {100, 101})  # fresh id, not Warsong's brackets

    def test_id_collisions_are_refused(self):
        data = synth_dbc.default_config()
        data["map"]["id"] = 532  # Karazhan's id

        with self.assertRaisesRegex(forgemod.ForgeError, "not this map's"):
            run_forge(data)

        data = synth_dbc.default_config()
        data["zone"]["id"] = 3457  # Karazhan's zone

        with self.assertRaisesRegex(forgemod.ForgeError, "not this map's"):
            run_forge(data)

        data = synth_dbc.default_config()
        data["map"]["directory"] = "WarsongGulch"

        with self.assertRaisesRegex(forgemod.ForgeError, "already uses the directory"):
            run_forge(data)

    def test_server_sql_ids_are_reserved(self):
        with self.assertRaisesRegex(forgemod.ForgeError, "already exists in the server's SQL"):
            run_forge(reserved={"Map": {901: "updates/pending_db_world/rev_1.sql"}})

    def test_second_run_replaces_in_place(self):
        cfg, tables, result, raw = run_forge()
        once = {name: tables[name].to_bytes() for name in tables}

        # Forge again over the output (a rebuild on the realm's then-current DBCs).
        cfg2 = configmod.parse(synth_dbc.default_config())
        tables2 = {name: DbcTable.from_bytes(data, layout.get(name), name) for name, data in once.items()}
        result2 = forgemod.Forge(tables2, cfg2, None, synth_dbc.TILES).run()

        for name in result2.changes:
            self.assertEqual(len(tables2[name].rows), len(tables[name].rows), name)
            self.assertFalse(result2.changes[name].added, name)
            self.assertTrue(result2.changes[name].replaced, name)

        self.assertEqual(result2.area_bits, result.area_bits)
        self.assertEqual(result2.light_id, result.light_id)

    def test_dropped_subzone_is_removed_on_rebuild(self):
        data = synth_dbc.default_config()
        data["zone"]["subzones"] = [{"id": 5101, "name": "The Crater"}]
        cfg, tables, result, _ = run_forge(data)
        once = {name: tables[name].to_bytes() for name in tables}

        data["zone"]["subzones"] = []
        cfg2 = configmod.parse(data)
        tables2 = {name: DbcTable.from_bytes(bytes_, layout.get(name), name) for name, bytes_ in once.items()}
        result2 = forgemod.Forge(tables2, cfg2, None, synth_dbc.TILES).run()
        self.assertNotIn(5101, tables2["AreaTable"].ids())
        self.assertIn(5101, result2.changes["AreaTable"].removed)

    def test_missing_template_is_an_error(self):
        data = synth_dbc.default_config()
        data["map"]["template"] = 998

        with self.assertRaisesRegex(forgemod.ForgeError, "template 998 is not in Map.dbc"):
            run_forge(data)

    def test_unknown_skybox_is_an_error(self):
        data = synth_dbc.default_config()
        data["light"] = {"skybox": "Environments\\Stars\\NoSuchSky.M2"}

        with self.assertRaisesRegex(forgemod.ForgeError, "no LightSkybox row"):
            run_forge(data)


if __name__ == "__main__":
    unittest.main()
