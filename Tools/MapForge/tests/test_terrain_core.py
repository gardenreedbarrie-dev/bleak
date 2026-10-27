"""Terrain core units: coordinates, deterministic math, noise, shapes, height field, texturing."""

import math
import os
import struct
import sys
import unittest

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from terrain import coords  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.noise import Fbm, GradientNoise, hash32  # noqa: E402
from terrain.shapes import Circle, Polygon, Polyline, Rect, RiverPath, parse_shape  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.texturing import TexturePainter, pack_alpha_4bit, texture_chunk  # noqa: E402


def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def tiny_spec(**overrides):
    data = {
        "map": {"directory": "CoreT", "tiles": {"x": [32, 32], "y": [32, 32]}},
        "seed": 11,
        "heightmap": {"base": 4.0, "noise": [{"scale": 90, "amplitude": 5, "octaves": 2}]},
        "textures": [{"name": "a", "path": "Tileset\\X\\A.blp"}, {"name": "b", "path": "Tileset\\X\\B.blp"}],
    }
    data.update(overrides)
    return parse_spec(data)


class TestCoords(unittest.TestCase):
    def test_constants(self):
        self.assertAlmostEqual(coords.TILE_SIZE, 533.33333, places=4)
        self.assertAlmostEqual(coords.ZERO, 17066.666, places=2)
        self.assertAlmostEqual(coords.UNIT_SIZE, 4.1666665, places=5)

    def test_lattice_matches_client_chunk_corners(self):
        # CMapChunk::Create: top.x = 17066.666f - cOffset.y * 33.333332f.
        for tile_chunk in (0, 512, 515, 1023):
            top = f32(coords.ZERO) - tile_chunk * f32(coords.CHUNK_SIZE)
            ours = coords.lattice_x(tile_chunk * coords.LATTICE_PER_CHUNK)
            self.assertLess(abs(top - ours), 0.01)

    def test_tile_of_and_bounds(self):
        self.assertEqual(coords.tile_of(-1.0, -1.0), (32, 32))
        self.assertEqual(coords.tile_of(1.0, 1.0), (31, 31))
        x0, x1, y0, y1 = coords.tile_bounds(32, 32)
        self.assertAlmostEqual(x1, 0.0)
        self.assertAlmostEqual(x0, -coords.TILE_SIZE)
        self.assertAlmostEqual(y1, 0.0)

    def test_world_file_round_trip(self):
        w = (-123.25, 456.5, 33.125)
        self.assertEqual(coords.file_to_world(*coords.world_to_file(*w)), w)

    def test_quantized_heights_are_exact_in_float32(self):
        # base + (h - base) must give back h in the client's float32 arithmetic for any two lattice heights.
        for h in (0.0, 1.015625, -77.328125, 912.5, -1533.984375):
            q = coords.quantize_height(h)
            for base in (0.0, coords.quantize_height(-40.546875), coords.quantize_height(333.33)):
                rel = f32(q - base)
                self.assertEqual(f32(base + rel), f32(q))

    def test_dsin_dcos_match_libm(self):
        for deg in (-725.0, -90.0, -1.0, 0.0, 29.37, 45.0, 90.0, 135.5, 180.0, 269.9, 360.0, 1234.56):
            self.assertLess(abs(coords.dsin(deg) - math.sin(math.radians(deg))), 1e-9, deg)
            self.assertLess(abs(coords.dcos(deg) - math.cos(math.radians(deg))), 1e-9, deg)


    def test_datan2_matches_libm(self):
        for y, x in ((0.0, 1.0), (1.0, 0.0), (0.0, -1.0), (-1.0, 0.0), (3.0, 4.0), (-60.0, -80.0), (1e-9, -5.0),
                     (7.25, -0.125), (-0.5, 0.75)):
            self.assertLess(abs(coords.datan2(y, x) - math.degrees(math.atan2(y, x))), 1e-9, (y, x))
        self.assertEqual(coords.datan2(0.0, 0.0), 0.0)


class TestNoise(unittest.TestCase):
    def test_hash_deterministic(self):
        self.assertEqual(hash32(12, -7, 99), hash32(12, -7, 99))
        self.assertNotEqual(hash32(12, -7, 99), hash32(12, -7, 100))

    def test_gradient_noise_range_and_determinism(self):
        n1 = GradientNoise(5)
        n2 = GradientNoise(5)
        for i in range(200):
            x = (i * 37 % 101) * 0.173 - 5.0
            y = (i * 53 % 97) * 0.219 - 7.0
            v = n1(x, y)
            self.assertEqual(v, n2(x, y))
            self.assertLessEqual(abs(v), 1.5)

    def test_fbm_amplitude(self):
        f = Fbm(3, 50.0, 10.0, octaves=3)
        values = [f(x * 7.1, x * -3.3) for x in range(300)]
        self.assertLessEqual(max(abs(v) for v in values), 15.0)
        self.assertGreater(max(values) - min(values), 1.0)


class TestShapes(unittest.TestCase):
    def test_circle(self):
        c = Circle((10.0, -5.0), 4.0)
        self.assertEqual(c.distance(10.0, -5.0), 0.0)
        self.assertAlmostEqual(c.distance(10.0, 1.0), 2.0)
        self.assertTrue(c.contains(13.9, -5.0))

    def test_rect(self):
        r = Rect((0.0, 0.0), (10.0, 4.0))
        self.assertEqual(r.distance(5.0, 2.0), 0.0)
        self.assertAlmostEqual(r.distance(13.0, 2.0), 3.0)
        self.assertAlmostEqual(r.distance(13.0, 8.0), 5.0)

    def test_polygon(self):
        p = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
        self.assertEqual(p.distance(5.0, 5.0), 0.0)
        self.assertAlmostEqual(p.distance(-3.0, 5.0), 3.0)

    def test_polyline(self):
        line = Polyline([(0.0, 0.0), (10.0, 0.0)], 4.0)
        self.assertEqual(line.distance(5.0, 1.9), 0.0)
        self.assertAlmostEqual(line.distance(5.0, 5.0), 3.0)

    def test_inside_distance(self):
        self.assertAlmostEqual(Circle((0.0, 0.0), 10.0).inside_distance(3.0, 4.0), 5.0)
        self.assertEqual(Circle((0.0, 0.0), 10.0).inside_distance(30.0, 0.0), 0.0)
        self.assertAlmostEqual(Rect((0.0, 0.0), (10.0, 4.0)).inside_distance(5.0, 1.0), 1.0)
        square = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
        self.assertAlmostEqual(square.inside_distance(5.0, 2.0), 2.0)
        self.assertEqual(square.inside_distance(-1.0, 5.0), 0.0)
        self.assertAlmostEqual(Polyline([(0.0, 0.0), (10.0, 0.0)], 4.0).inside_distance(5.0, 0.5), 1.5)

    def test_river_path_reaches(self):
        path = RiverPath([(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)], [0, 1, 1], [9.0, 5.0], 4.0, 2.0)
        self.assertEqual(path.joints, [(10.0, 1)])
        self.assertEqual(path.level_at(5.0, 1.0), 9.0)
        self.assertEqual(path.level_at(25.0, -1.0), 5.0)
        self.assertEqual(path.level_at(10.0, 1.0), 9.0)  # a tie at the joint belongs upstream
        self.assertEqual(path.terrain_level(8.0), 9.0)
        self.assertEqual(path.terrain_level(10.0), 7.0)  # halfway down the step, spread over fall_run
        self.assertEqual(path.terrain_level(12.0), 5.0)
        dist, seg, t = path.nearest(15.0, 3.0)
        self.assertEqual((dist, seg, path.arc(seg, t)), (3.0, 1, 15.0))

    def test_parse_rejects_unknown(self):
        with self.assertRaises(SpecError):
            parse_shape({"blob": {}}, "t")
        with self.assertRaises(SpecError):
            parse_shape({"circle": {"center": [0, 0]}}, "t")
        with self.assertRaises(SpecError):
            parse_shape({"circle": {"center": [0, 0], "radius": 1, "extra": 2}}, "t")


class TestHeightField(unittest.TestCase):
    def test_flatten_sets_height(self):
        spec = tiny_spec(heightmap={"base": 10.0, "features": [
            {"type": "flatten", "shape": {"circle": {"center": [-100, -100], "radius": 30}}, "height": 55.0},
        ]})
        field = HeightField(spec)
        self.assertAlmostEqual(field.raw(-100.0, -100.0), 55.0)
        self.assertAlmostEqual(field.raw(-300.0, -300.0), 10.0)

    def test_river_carves_and_banks_blend(self):
        spec = tiny_spec(heightmap={"base": 10.0, "features": [
            {"type": "river", "path": [[-50, -400], [-50, -100]], "width": 10, "bank": 20, "bed": 1.0},
        ]})
        field = HeightField(spec)
        self.assertAlmostEqual(field.raw(-50.0, -250.0), 1.0)
        self.assertAlmostEqual(field.raw(-50.0 + 40.0, -250.0), 10.0)
        mid = field.raw(-50.0 + 15.0, -250.0)
        self.assertTrue(1.0 < mid < 10.0)

    def test_ramp_null_heights_resolve_to_terrain(self):
        spec = tiny_spec(heightmap={"base": 6.0, "features": [
            {"type": "hill", "center": [-100, -100], "radius": 60, "height": 20},
            {"type": "ramp", "from": [-300, -100, None], "to": [-100, -100, None], "width": 10},
        ]})
        field = HeightField(spec)
        self.assertAlmostEqual(field.raw(-300.0, -100.0), 6.0, places=3)
        self.assertAlmostEqual(field.raw(-100.0, -100.0), 26.0, places=3)

    def test_border_raises_edges_only(self):
        spec = tiny_spec(heightmap={"base": 5.0, "features": [
            {"type": "border", "inset": 10, "width": 50, "height": 40},
        ]})
        field = HeightField(spec)
        self.assertAlmostEqual(field.raw(-266.0, -266.0), 5.0)
        self.assertAlmostEqual(field.raw(-5.0, -266.0), 45.0)

    def test_clamp(self):
        spec = tiny_spec(heightmap={"base": 500.0, "features": [{"type": "clamp", "min": -10, "max": 90}]})
        self.assertEqual(HeightField(spec).raw(-50.0, -50.0), 90.0)

    def test_ground_height_interpolates_triangles(self):
        spec = tiny_spec()
        grid = LatticeGrid(spec, HeightField(spec))
        r = 32 * coords.LATTICE_PER_TILE + 40
        c = 32 * coords.LATTICE_PER_TILE + 56
        x = coords.lattice_x(r)
        y = coords.lattice_y(c)
        self.assertAlmostEqual(grid.ground_height(x, y), grid.get(r, c), places=5)
        self.assertAlmostEqual(grid.ground_height(coords.lattice_x(r + 1), coords.lattice_y(c + 1)),
                               grid.get(r + 1, c + 1), places=5)

    def test_normals_unit_up(self):
        spec = tiny_spec()
        grid = LatticeGrid(spec, HeightField(spec))
        r0 = 32 * coords.LATTICE_PER_TILE
        for d in range(0, 250, 17):
            n = grid.normal(r0 + d, r0 + d // 2)
            self.assertAlmostEqual(n[0] ** 2 + n[1] ** 2 + n[2] ** 2, 1.0, places=6)
            self.assertGreater(n[2], 0.0)


class TestBorderCheck(unittest.TestCase):
    """build.border_check: can a player walk (slopes <= 50 degrees) from the centre to the tile edge?"""

    def check(self, border):
        from terrain.build import border_check
        spec = tiny_spec(heightmap={"base": 5.0, "features": [dict(border, type="border")]})
        return border_check(spec, LatticeGrid(spec, HeightField(spec)))

    def test_flat_map_is_open(self):
        from terrain.build import border_check
        spec = tiny_spec(heightmap={"base": 5.0})
        self.assertFalse(border_check(spec, LatticeGrid(spec, HeightField(spec)))["closed"])

    def test_gentle_ridge_is_open(self):
        # Peak slope of a smoothstep rise is 1.5 * height / width = 0.6, about 31 degrees: walkable.
        self.assertFalse(self.check({"inset": 20, "width": 100, "height": 40})["closed"])

    def test_cliff_is_closed(self):
        # 1.5 * 50 / 25 = 3, about 72 degrees.
        result = self.check({"inset": 10, "width": 25, "height": 50})
        self.assertTrue(result["closed"])
        self.assertGreater(result["closest_walkable_to_edge_yards"], 10.0)


class TestTexturing(unittest.TestCase):
    def test_pack_alpha_sizes_and_nibble_order(self):
        flat = [[1.0] * 17 for _ in range(17)]
        packed = pack_alpha_4bit(flat)
        self.assertEqual(len(packed), 2048)
        self.assertEqual(packed, b"\xff" * 2048)
        # Left half 0, right half 1: the first texel sits in the LOW nibble (UnpackAlphaShadowBitsFixed4444).
        split = [[0.0] * 8 + [1.0] * 9 for _ in range(17)]
        packed = pack_alpha_4bit(split)
        self.assertEqual(len(packed), 2048)
        self.assertEqual(packed[0], 0x00)
        self.assertEqual(packed[31], 0xFF)

    def test_chunk_layer_selection(self):
        spec = tiny_spec(textures=[{"name": f"t{i}", "path": f"Tileset\\X\\T{i}.blp"} for i in range(6)],
                         texture_rules=[
                             {"texture": "t1", "shape": {"rect": {"min": [-533, -533], "max": [0, 0]}}},
                             {"texture": "t2", "strength": 0.5,
                              "shape": {"rect": {"min": [-533, -533], "max": [0, 0]}}},
                         ])
        grid = LatticeGrid(spec, HeightField(spec))
        painter = TexturePainter(spec, grid)
        weights = painter.weights_for_tile(32, 32)
        chunk = texture_chunk(weights, 4, 4)
        self.assertLessEqual(len(chunk.layers), 4)
        self.assertEqual(len(chunk.alpha), len(chunk.layers) - 1)
        for a in chunk.alpha:
            self.assertEqual(len(a), 2048)
        # t1 and t2 end at 0.5 each (t2 painted 0.5 over t1); the tie goes to spec order, so t1 is the base.
        self.assertEqual(chunk.layers, [1, 2])
        self.assertEqual(len(chunk.low_quality), 16)

    def test_weights_sum_to_one(self):
        spec = tiny_spec(texture_rules=[{"texture": "b", "noise": {"scale": 40, "threshold": 0.0, "fade": 0.4}}])
        grid = LatticeGrid(spec, HeightField(spec))
        weights = TexturePainter(spec, grid).weights_for_tile(32, 32)
        size = coords.LATTICE_PER_TILE + 1
        for i in range(0, size * size, 997):
            self.assertAlmostEqual(sum(w[i] for w in weights), 1.0, places=9)


class TestSpecErrors(unittest.TestCase):
    def test_unknown_key(self):
        with self.assertRaises(SpecError):
            tiny_spec(bogus=1)

    def test_bad_directory(self):
        for bad in ("", "9Start", "a b", "x" * 64):
            with self.assertRaises(SpecError):
                tiny_spec(map={"directory": bad, "tiles": {"x": [32, 32], "y": [32, 32]}})

    def test_duplicate_uid(self):
        with self.assertRaises(SpecError):
            spec = tiny_spec(doodads=[
                {"model": "a\\b.m2", "position": [-10, -10], "uid": 7},
                {"model": "a\\c.m2", "position": [-20, -20], "uid": 7},
            ])
            from terrain.placements import resolve_placements
            resolve_placements(spec, LatticeGrid(spec, HeightField(spec)))

    def test_placement_outside_tiles(self):
        from terrain.placements import resolve_placements
        spec = tiny_spec(doodads=[{"model": "a\\b.m2", "position": [900, -10]}])
        with self.assertRaises(SpecError):
            resolve_placements(spec, LatticeGrid(spec, HeightField(spec)))

    def test_wmo_group_file_rejected(self):
        with self.assertRaises(SpecError):
            tiny_spec(wmos=[{"model": "w\\t_000.wmo", "position": [-10, -10]}])

    def test_destructible_flag_rejected(self):
        with self.assertRaises(SpecError):
            tiny_spec(wmos=[{"model": "w\\t.wmo", "position": [-10, -10], "flags": 1}])

    def test_non_ascii_path_rejected(self):
        with self.assertRaises(SpecError):
            tiny_spec(textures=[{"name": "a", "path": "Tileset\\Grün.blp"}])

    def test_flattened_poi_needs_radius(self):
        with self.assertRaises(SpecError):
            tiny_spec(pois=[{"name": "p", "position": [-10, -10], "flatten": True}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
