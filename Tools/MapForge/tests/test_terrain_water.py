"""Lakes, rivers that step down at waterfalls, and several water bodies per map (spec `lakes`, `rivers`).

MH2O as both readers take it: the client walks every instance of a chunk (CMapChunk::CreateLiquids) and reads
vertex heights row by row with (width + 1) per row (CChunkLiquid::CreateVertXY, GetHeight); AzerothCore's
map_extractor takes the first instance only, copies its vertex grid into one tile-wide grid in chunk order, and the
server reads each cell's level at its top-left vertex (System.cpp, GridTerrainData::getLiquidLevel). `emulate_ac`
below follows that code, so per-chunk and per-reach levels are checked cell by cell without the binary.
"""

import copy
import os
import shutil
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import built, copy_output, map_folder, validate  # noqa: E402

from terrain import coords  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.placements import scatter_placements  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.water import ChunkWater, build_mh2o, water_bodies, water_for_chunk  # noqa: E402

RIVER = {"name": "run", "width": 12, "depth": 2.5, "bank": 10, "freeboard": 0.6, "fall_run": 4,
         "reaches": [{"level": 18, "path": [[-60, -100], [-140, -160]]},
                     {"level": 12, "path": [[-220, -220]]},
                     {"level": 6, "path": [[-300, -300], [-345, -345]]}],
         "waterfall": {"model": "World\\Made\\Up\\Fall.m2", "splash": "World\\Made\\Up\\Splash.m2", "height": 10,
                       "anchor": "top", "splash_offset": 4, "radius": 6}}

WATER_SPEC = {
    "map": {"directory": "WaterT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 31,
    "area_id": 1,
    "uid_base": 100,
    "heightmap": {"base": 20.0, "noise": [{"scale": 120, "amplitude": 1.0}], "features": []},
    "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\G.blp"}],
    "doodads": [{"model": "World\\Made\\Up\\Rock.m2", "position": [-30, -30], "radius": 3}],
    "lakes": [{"name": "pool", "level": 6, "depth": 6, "shelf": 25, "shore": 25,
               "shape": {"circle": {"center": [-380, -380], "radius": 80}},
               "islands": [{"center": [-400, -400], "radius": 18, "height": 5}]},
              {"name": "pond", "liquid_type": 5, "level": 17, "depth": 3, "shelf": 10, "shore": 10,
               "shape": {"circle": {"center": [-80, -420], "radius": 30}}}],
    "rivers": [RIVER],
}


def emulate_ac(info):
    """map_extractor's MH2O pass (System.cpp, 'Get liquid map for grid') and the server's per-cell level: {(row,
    col): level} for the cells it shows; the instance arrays come from validate.py's parse of the tile."""
    height = [[0.0] * 129 for _ in range(129)]
    show = set()
    for i in range(16):  # chunk row
        for j in range(16):  # chunk column
            inst = info.mh2o.get((j, i))
            if inst is None:
                continue
            mask = inst["bits"]
            for y in range(inst["h"]):
                for x in range(inst["w"]):
                    if mask & 1:
                        show.add((i * 8 + y + inst["y"], j * 8 + x + inst["x"]))
                    mask >>= 1
            pos = 0
            for y in range(inst["h"] + 1):
                for x in range(inst["w"] + 1):
                    height[i * 8 + y + inst["y"]][j * 8 + x + inst["x"]] = inst["heights"][pos]
                    pos += 1
    return {cell: height[cell[0]][cell[1]] for cell in show}


def expected_level(spec, r, c):
    """The build's rule for the cell whose top-left lattice point is (r, c): the lowest body level that holds the
    cell centre, where a river that misses the centre counts with its lowest level at one of the four corners."""
    levels = []
    for body in water_bodies(spec):
        level = body.probe(coords.lattice_x(r + 1), coords.lattice_y(c + 1))
        if level is None and body.kind == "river":
            corner = [body.probe(coords.lattice_x(rr), coords.lattice_y(cc))
                      for rr, cc in ((r, c), (r, c + 2), (r + 2, c), (r + 2, c + 2))]
            corner = [lv for lv in corner if lv is not None]
            level = min(corner) if corner else None
        if level is not None:
            levels.append(level)
    return min(levels) if levels else None


def sloped_cells(info):
    """Wet cells of the instances the server reads whose four corner vertices differ: the client interpolates the
    corners (CChunkLiquid::GetHeight), the server holds the top-left one over the whole cell."""
    out = []
    for (ix, iy), inst in sorted(info.mh2o.items()):
        w, hs = inst["w"], inst["heights"]
        for y in range(inst["h"]):
            for x in range(w):
                if inst["bits"] >> (y * w + x) & 1:
                    corners = {hs[y * (w + 1) + x], hs[y * (w + 1) + x + 1], hs[(y + 1) * (w + 1) + x],
                               hs[(y + 1) * (w + 1) + x + 1]}
                    if len(corners) > 1:
                        out.append((ix, iy, inst["x"] + x, inst["y"] + y, sorted(corners)))
    return out


class TestRiversAndLakes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("water", WATER_SPEC)
        cls.spec = cls.result.context.spec
        cls.rep = validate(cls.out)
        cls.info = cls.rep.adts[(32, 32)]
        cls.tile = cls.result.tiles[(32, 32)]

    def test_validator_clean(self):
        self.assertEqual(self.rep.errors, [])
        self.assertEqual(self.rep.warnings, [])

    def test_each_cell_keeps_its_own_level_on_the_server(self):
        server = emulate_ac(self.info)
        self.assertTrue(server)
        seen = set()
        for (row, col), level in server.items():
            want = expected_level(self.spec, 32 * 256 + 2 * row, 32 * 256 + 2 * col)
            self.assertEqual(level, want, (row, col))
            seen.add(level)
        self.assertEqual(seen, {18.0, 12.0, 6.0, 17.0})

    def test_every_wet_cell_is_flat_where_the_server_reads_it(self):
        # A cell with corners at two levels (next to higher water inside a chunk) would be drawn sloped by the
        # client, below the ground near the lip, while the server holds the upper level over the whole cell.
        self.assertEqual(sloped_cells(self.info), [])
        for cw in self.tile.water.values():
            for (cx, cy), level in cw.levels.items():
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        self.assertEqual(cw.levels.get((cx + dx, cy + dy), level), level, (cx, cy))

    def test_bank_cells_over_the_bed_are_wet(self):
        # The rounded bed stays under the water out to about 0.9 of the half width, so a cell centred just outside
        # the channel can have a corner well under the reach's level: it must hold water, or the surface ends in
        # mid-air over bare bed along the bank.
        server = emulate_ac(self.info)
        grid = self.result.context.grid
        river = next(b for b in water_bodies(self.spec) if b.kind == "river")
        falls = [(f["x"], f["y"]) for f in self.spec.rivers[0]["falls"]]
        bank = 0
        for row in range(128):
            for col in range(128):
                r, c = 32 * 256 + 2 * row, 32 * 256 + 2 * col
                x, y = coords.lattice_x(r + 1), coords.lattice_y(c + 1)
                if river.probe(x, y) is not None or min((x - fx) ** 2 + (y - fy) ** 2 for fx, fy in falls) < 20 ** 2:
                    continue
                corners = [(rr, cc, river.probe(coords.lattice_x(rr), coords.lattice_y(cc)))
                           for rr, cc in ((r, c), (r, c + 2), (r + 2, c), (r + 2, c + 2))]
                under = [lv for rr, cc, lv in corners if lv is not None and grid.get(rr, cc) < lv - river.min_depth]
                if not under:
                    continue
                bank += 1
                self.assertEqual(server.get((row, col)), expected_level(self.spec, r, c), (row, col))
        self.assertGreater(bank, 10)

    def test_client_vertex_layout_matches_the_writer(self):
        for (ix, iy), cw in self.tile.water.items():
            inst = self.info.mh2o[(ix, iy)]
            self.assertEqual((inst["x"], inst["y"], inst["w"], inst["h"]), (cw.x0, cw.y0, cw.w, cw.h))
            self.assertEqual(inst["heights"], [float(h) for h in cw.heights])
            self.assertEqual((inst["min"], inst["max"]), (min(cw.heights), max(cw.heights)))
            for (cx, cy), level in cw.levels.items():
                # The client reads row-major vertices with width + 1 per row; a cell's top-left vertex is its own.
                self.assertEqual(inst["heights"][(cy - cw.y0) * (cw.w + 1) + (cx - cw.x0)], level)

    def test_a_chunk_holds_two_levels_at_a_fall(self):
        mixed = [cw for cw in self.tile.water.values() if cw.min_height != cw.max_height]
        self.assertTrue(mixed)
        self.assertTrue(any({18.0, 12.0} <= set(cw.levels.values()) for cw in mixed))

    def test_partial_chunks_along_the_banks(self):
        partial = [inst for inst in self.info.mh2o.values()
                   if inst["w"] * inst["h"] < 64 or inst["bits"] != (1 << (inst["w"] * inst["h"])) - 1]
        self.assertGreater(len(partial), 5)

    def test_liquid_types_per_body(self):
        types = {}
        for inst in self.info.mh2o.values():
            types.setdefault(inst["type"], set()).update(set(inst["heights"]))
        self.assertEqual(set(types), {1, 5})
        self.assertEqual(types[5], {17.0})

    def test_lake_and_river_merge_at_the_mouth(self):
        self.assertGreaterEqual(self.result.manifest["water_merged_chunks"], 1)
        self.assertEqual(self.result.manifest["water_dropped_cells"], 0)
        merged = [cw for cw in self.tile.water.values() if len(cw.bodies) > 1]
        self.assertTrue(merged)
        self.assertTrue(all(set(cw.levels.values()) == {6.0} for cw in merged))

    def test_terrain_follows_the_reaches(self):
        field = self.result.context.field
        path = self.spec.rivers[0]["path"]
        # The bed lies `depth` under each reach's water on the centre line, away from the falls.
        for (x, y), level in (((-90, -122.5), 18.0), ((-180, -190), 12.0), ((-260, -260), 6.0)):
            self.assertAlmostEqual(field.raw(x, y), level - 2.5, delta=0.05, msg=(x, y))
        # Across a fall the bed drops by the step within fall_run.
        joint = (-140.0, -160.0)
        up = field.raw(joint[0] + 8 * 0.8, joint[1] + 8 * 0.6)
        down = field.raw(joint[0] - 8 * 0.707, joint[1] - 8 * 0.707)
        self.assertAlmostEqual(up - down, 6.0, delta=0.3)
        # The bank lip stands above the water at the channel edge, and the edge has no step.
        for t in (0.25, 0.5, 0.75):
            ax, ay = -180 + (-220 + 180) * t, -190 + (-220 + 190) * t
            nx, ny = 0.707, -0.707
            inner = field.raw(ax + nx * 5.95, ay + ny * 5.95)
            outer = field.raw(ax + nx * 6.05, ay + ny * 6.05)
            self.assertGreaterEqual(outer, 12.0 + 0.5)
            self.assertLess(abs(outer - inner), 0.2)
        self.assertEqual(path.level_at(-90, -122.5), 18.0)

    def test_lake_basin_shore_and_island(self):
        field = self.result.context.field
        self.assertAlmostEqual(field.raw(-330.0, -380.0), 0.0, delta=0.6)  # level 6 - depth 6 past the shelf
        self.assertAlmostEqual(field.raw(-400.0, -400.0), 11.0, delta=0.05)  # island top: level + 5
        self.assertAlmostEqual(field.raw(-380.0 + 80.0, -380.0 - 0.001), 6.8, delta=0.3)  # shore: freeboard

    def test_waterfalls_at_the_steps(self):
        gen = self.spec.generated
        self.assertEqual([p.label for p in gen], ["run fall 1", "run splash 1", "run fall 2", "run splash 2"])
        fall, splash = gen[0], gen[1]
        self.assertEqual((fall.x, fall.y, fall.z), (-140.0, -160.0, 18.0))  # anchor top: the upper level
        self.assertAlmostEqual(fall.scale, 6.0 / 10.0)  # the drop over the model's own height
        facing = coords.datan2(-60.0, -80.0) % 360.0  # downstream: toward (-220, -220)
        self.assertAlmostEqual(fall.rotation[1], (facing - 180.0) % 360.0, places=6)
        self.assertEqual(splash.z, 12.0)
        self.assertAlmostEqual(splash.x, -140.0 + coords.dcos(facing) * 4.0, places=6)
        self.assertAlmostEqual(splash.y, -160.0 + coords.dsin(facing) * 4.0, places=6)
        uids = {p.label: p.uid for p in self.result.context.doodads}
        self.assertLess(uids[""], uids["run fall 1"])  # the spec's own doodad keeps the first id
        names = {e["name"] for e in self.info.mddf}
        self.assertIn("World\\Made\\Up\\Fall.m2", names)
        self.assertIn("World\\Made\\Up\\Splash.m2", names)
        self.assertEqual(self.result.manifest["rivers"][0]["waterfall_doodads"], 4)


class TestWaterBodiesMeeting(unittest.TestCase):
    def chunk(self, water, ground=0.0):
        data = {"map": {"directory": "MeetT", "tiles": {"x": [32, 32], "y": [32, 32]}},
                "heightmap": {"base": ground}, "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\G.blp"}],
                "water": water}
        spec = parse_spec(data)
        grid = LatticeGrid(spec, HeightField(spec))
        warnings = []
        stats = {}
        cw = water_for_chunk(spec, grid, 32, 32, 3, 3, warnings, stats)
        return cw, warnings, stats

    def test_lower_water_wins_where_two_overlap(self):
        x0, y0 = coords.chunk_top_left(32, 32, 3, 3)
        a = {"height": 5.0, "shape": {"rect": {"min": [x0 - 33.4, y0 - 20], "max": [x0, y0]}}}
        b = {"height": 2.0, "shape": {"rect": {"min": [x0 - 33.4, y0 - 33.4], "max": [x0, y0 - 12]}}}
        cw, warnings, stats = self.chunk([a, b])
        self.assertEqual(warnings, [])
        self.assertEqual(stats["merged_chunks"], 1)
        self.assertEqual(set(cw.levels.values()), {5.0, 2.0})
        both = 0
        for (cx, cy), level in cw.levels.items():
            x = x0 - (2 * cy + 1) * coords.HALF_UNIT
            y = y0 - (2 * cx + 1) * coords.HALF_UNIT
            in_a = x0 - 33.4 <= x <= x0 and y0 - 20 <= y <= y0
            in_b = x0 - 33.4 <= x <= x0 and y0 - 33.4 <= y <= y0 - 12
            both += in_a and in_b
            self.assertEqual(level, 2.0 if in_b else 5.0, (cx, cy))  # the lower water wins where both hold
        self.assertGreater(both, 0)
        # Column 3 (lower water next to the higher) stays dry, so every wet cell has its four corners at its level.
        self.assertEqual(sorted({cx for cx, _ in cw.levels}), [0, 1, 2, 4, 5, 6, 7])
        for (cx, cy), level in cw.levels.items():
            corners = [cw.heights[(cy - cw.y0 + dy) * (cw.w + 1) + (cx - cw.x0 + dx)] for dy in (0, 1) for dx in (0, 1)]
            self.assertEqual(set(corners), {level}, (cx, cy))

    def test_another_liquid_type_is_dropped_with_a_warning(self):
        x0, y0 = coords.chunk_top_left(32, 32, 3, 3)
        a = {"height": 5.0, "shape": {"rect": {"min": [x0 - 33.4, y0 - 15], "max": [x0, y0]}}}
        b = {"height": 5.0, "liquid_type": 3, "shape": {"rect": {"min": [x0 - 33.4, y0 - 33.4],
                                                                  "max": [x0, y0 - 18]}}}
        cw, warnings, stats = self.chunk([a, b])
        self.assertEqual(cw.liquid_type, 1)
        self.assertGreater(stats["dropped_cells"], 0)
        self.assertTrue(any("one liquid instance" in w for w in warnings))

    def test_flat_water_writes_the_same_bytes_as_before(self):
        # One level everywhere: min == max == the level, every vertex at the level (the v1 layout).
        cw = ChunkWater(1, 3.0, 1, 2, 3, 2, {(1, 2), (3, 3)}, [8] * 12)
        payload = build_mh2o([cw] + [None] * 255)
        inst = struct.unpack_from("<HHffBBBBII", payload, 3072)
        self.assertEqual(inst[:8], (1, 0, 3.0, 3.0, 1, 2, 3, 2))
        heights = struct.unpack_from("<12f", payload, inst[9])
        self.assertEqual(set(heights), {3.0})


class TestWaterScatterAndErrors(unittest.TestCase):
    def test_scatter_stays_dry(self):
        data = copy.deepcopy(WATER_SPEC)
        data["scatter"] = [{"name": "t", "seed": 3, "density": 40, "models": [{"model": "World\\X\\T.m2"}]}]
        spec = parse_spec(data)
        field = HeightField(spec)
        grid = LatticeGrid(spec, field)
        placed, stats = scatter_placements(spec, grid)
        self.assertGreater(stats[0]["rejected"]["wet"], 0)
        for p in placed:
            ground = grid.ground_height(p.x, p.y)
            self.assertFalse(any((lv := b.probe(p.x, p.y)) is not None and ground < lv for b in water_bodies(spec)))

    def bad(self, changes, text):
        data = copy.deepcopy(WATER_SPEC)
        data.update(changes)
        with self.assertRaisesRegex(SpecError, text):
            parse_spec(data)

    def test_rejects(self):
        rising = copy.deepcopy(RIVER)
        rising["reaches"][1]["level"] = 25
        self.bad({"rivers": [rising]}, "only steps down")
        outside = copy.deepcopy(RIVER)
        outside["reaches"][0]["path"][0] = [100, -100]
        self.bad({"rivers": [outside]}, "outside the map")
        same = copy.deepcopy(RIVER)
        same["name"] = "pool"
        self.bad({"rivers": [same]}, "unique name")
        self.bad({"lakes": [{"name": "l", "level": 1}]}, "missing keys")
        twice = copy.deepcopy(WATER_SPEC["heightmap"])
        twice["features"] = [{"type": "water_bodies"}, {"type": "water_bodies"}]
        self.bad({"heightmap": twice}, "at most one")
        anchor = copy.deepcopy(RIVER)
        anchor["waterfall"]["anchor"] = "middle"
        self.bad({"rivers": [anchor]}, "anchor")

    def test_marker_places_the_carving(self):
        # Features after {"type": "water_bodies"} apply on top of the carved water (an island built later).
        data = copy.deepcopy(WATER_SPEC)
        data["heightmap"]["features"] = [{"type": "water_bodies"},
                                         {"type": "hill", "center": [-340, -380], "radius": 15, "height": 12}]
        spec = parse_spec(data)
        kinds = [f["type"] for f in spec.features]
        self.assertEqual(kinds[:4], ["lake", "lake", "river_reaches", "hill"])
        self.assertGreater(HeightField(spec).raw(-340.0, -380.0), 6.0)


class TestWaterValidatorRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.good = built("water", WATER_SPEC)

    def setUp(self):
        self.out = copy_output(self.good)
        self.path = os.path.join(map_folder(self.out, "WaterT"), "WaterT_32_32.adt")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def corrupt(self, fn):
        with open(self.path, "rb") as f:
            data = bytearray(f.read())
        pos = 0
        while data[pos:pos + 4] != b"O2HM":
            pos += 8 + struct.unpack_from("<I", data, pos + 4)[0]
        base = pos + 8
        for i in range(256):
            inst, layers, _ = struct.unpack_from("<3I", data, base + 12 * i)
            if layers:
                fn(data, base, base + 12 * i, base + inst)
                break
        with open(self.path, "wb") as f:
            f.write(bytes(data))
        return validate(self.out)

    def test_vertex_above_max_height(self):
        def fn(d, base, header, inst):
            ofs_verts = struct.unpack_from("<I", d, inst + 20)[0]
            struct.pack_into("<f", d, base + ofs_verts, 99.0)
        rep = self.corrupt(fn)
        self.assertTrue(any("outside [minHeight, maxHeight]" in e for e in rep.errors))

    def test_wet_cell_with_corners_at_two_heights(self):
        def fn(d, base, header, inst):
            hmin = struct.unpack_from("<f", d, inst + 4)[0]
            w, h, ofs_bits, ofs_verts = struct.unpack_from("<BBII", d, inst + 14)
            bits = int.from_bytes(d[base + ofs_bits:base + ofs_bits + 8], "little")
            cell = next(i for i in range(w * h) if bits >> i & 1)
            vertex = (cell // w + 1) * (w + 1) + cell % w + 1  # the wet cell's bottom-right corner
            struct.pack_into("<f", d, base + ofs_verts + 4 * vertex, hmin - 1.0)
            struct.pack_into("<f", d, inst + 4, hmin - 1.0)  # still inside [minHeight, maxHeight]
        rep = self.corrupt(fn)
        self.assertTrue(any("corners at different heights" in e for e in rep.errors), rep.errors)
        self.assertFalse(any("outside [minHeight, maxHeight]" in e for e in rep.errors))

    def test_empty_exists_bitmap(self):
        def fn(d, base, header, inst):
            ofs_bits = struct.unpack_from("<I", d, inst + 16)[0]
            d[base + ofs_bits:base + ofs_bits + 8] = bytes(8)
        rep = self.corrupt(fn)
        self.assertTrue(any("Wrong liquid detect" in e for e in rep.errors))

    def test_second_instance_warns(self):
        def fn(d, base, header, inst):
            struct.pack_into("<I", d, header + 4, 2)
        rep = self.corrupt(fn)
        self.assertTrue(any("reads only the first" in w for w in rep.warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
