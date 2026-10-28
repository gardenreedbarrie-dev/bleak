"""The preview rasterizer: lighting, culling, blending, orientation (section 5.6)."""

import unittest

import common as CM
from mflib import geom as G
from mflib import preview as P
from mflib import render as RD


def lum(frame, x, y):
    i = y * frame.w + x
    return 0.299 * frame.r[i] + 0.587 * frame.g[i] + 0.114 * frame.b[i]


class Lighting(unittest.TestCase):
    def _render(self, eye):
        cam = RD.Camera(eye, (0.0, 0.0, 0.5), 40.0, 96, 96, 1)
        fr = RD.Frame(cam, RD.PRESETS["neutral"], "flat")
        RD.draw(fr, RD.mesh_drawable(G.box(1.0, 1.0, 1.0), (0.8, 0.8, 0.8)))
        return fr, cam

    def _face_lum(self, eye, centre):
        fr, cam = self._render(eye)
        x, y, _z = cam.project(cam.view(centre))
        return lum(fr, int(x), int(y))

    def test_top_brighter_than_bottom_and_front_than_back(self):
        """A unit cube's top face is brighter than its bottom face, its +X face brighter than its -X face."""
        top = self._face_lum((2.5, 1.0, 3.0), (0.0, 0.0, 1.0))
        bottom = self._face_lum((2.5, 1.0, -2.0), (0.0, 0.0, 0.0))
        self.assertGreater(top, bottom + 0.1)
        front = self._face_lum((3.0, 0.4, 0.8), (0.5, 0.0, 0.5))
        back = self._face_lum((-3.0, 0.4, 0.8), (-0.5, 0.0, 0.5))
        self.assertGreater(front, back + 0.1)


class Raster(unittest.TestCase):
    def test_backface_culled_unless_two_sided(self):
        cam = RD.Camera((3.0, 0.0, 0.0), (0.0, 0.0, 0.0), 40.0, 64, 64, 1)
        # a triangle in the YZ plane whose outward side (CCW) faces -X: away from the camera
        tri_pos = [(0.0, 0.5, -0.5), (0.0, -0.5, -0.5), (0.0, 0.0, 0.6)]
        n = G.norm(G.cross(G.sub(tri_pos[1], tri_pos[0]), G.sub(tri_pos[2], tri_pos[0])))
        self.assertLess(n[0], 0)
        d = RD.Drawable(tri_pos, [n] * 3, [(0, 0)] * 3, [(0, 1, 2)], None, 0, 0, False, (1.0, 0.0, 0.0))
        fr = RD.Frame(cam, RD.PRESETS["neutral"], (0.0, 0.0, 0.0))
        RD.draw(fr, d)
        self.assertEqual(sum(fr.mask), 0, "back face drawn")
        d2 = RD.Drawable(tri_pos, [n] * 3, [(0, 0)] * 3, [(0, 1, 2)], None, 0, 0x04, False, (1.0, 0.0, 0.0))
        RD.draw(fr, d2)
        self.assertGreater(sum(fr.mask), 50, "two-sided material not drawn")
        # the same triangle wound the other way is a front face
        fr2 = RD.Frame(cam, RD.PRESETS["neutral"], (0.0, 0.0, 0.0))
        d3 = RD.Drawable(tri_pos, [G.mul(n, -1)] * 3, [(0, 0)] * 3, [(0, 2, 1)], None, 0, 0, False, (1, 0, 0))
        RD.draw(fr2, d3)
        self.assertGreater(sum(fr2.mask), 50)

    def test_glass_blend(self):
        """Blend mode 2 composites src*a + dst*(1-a) over what pass 1 drew."""
        cam = RD.Camera((3.0, 0.0, 0.0), (0.0, 0.0, 0.0), 40.0, 32, 32, 1)
        fr = RD.Frame(cam, RD.PRESETS["neutral"], (0.0, 0.0, 1.0))
        quad = G.box(2.0, 0.01, 2.0, z0=-1.0)
        RD.draw_scene(fr, [RD.mesh_drawable(quad, (1.0, 0.0, 0.0), G.mat_translate(-0.5, 0, 0), blend=2, alpha=0.5,
                                            flags=0x01)])
        i = 16 * 32 + 16
        self.assertAlmostEqual(fr.r[i], 0.5, 2)
        self.assertAlmostEqual(fr.b[i], 0.5, 2)

    def test_screen_right_is_minus_y_looking_along_plus_x(self):
        """GxuXformCreateLookAtSgCompat: looking along +X, screen right is -Y."""
        cam = RD.Camera((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 60.0, 100, 100, 1)
        x_left, _y, _z = cam.project(cam.view((5.0, 1.0, 0.0)))
        x_right, _y, _z = cam.project(cam.view((5.0, -1.0, 0.0)))
        self.assertLess(x_left, 50)
        self.assertGreater(x_right, 50)
        _x, y_up, _z = cam.project(cam.view((5.0, 0.0, 1.0)))
        self.assertLess(y_up, 50)

    def test_particles_without_quad_flags_draw_nothing(self):
        m2, skin, mod, _sk = CM.tiny_model()
        from mflib import m2check as C
        m, f = C.parse(m2, skin, "x.m2")
        cam = RD.Camera((3, 0, 1), (0, 0, 1), 45.0, 32, 32, 1)
        self.assertEqual(len(RD.particle_drawables(m, RD.TextureSet("/nonexistent"), None, cam)), 9)
        m["particles"][0]["flags"] = 0
        self.assertEqual(RD.particle_drawables(m, RD.TextureSet("/nonexistent"), None, cam), [])

    def test_particle_lighting_follows_flag_0x1(self):
        """An emitter without flag 0x1 is lit (M2Model.cpp:7453 -> the lit Particle effect) with the world-up
        normal; with 0x1 it is unlit. At night the lit steam is darker than the unlit embers."""
        m2, skin, _mod, _sk = CM.tiny_model()
        from mflib import m2check as C
        m, _f = C.parse(m2, skin, "x.m2")
        cam = RD.Camera((3, 0, 1), (0, 0, 1), 45.0, 32, 32, 1)
        tx = RD.TextureSet("/nonexistent")
        lit = RD.particle_drawables(m, tx, None, cam)
        self.assertTrue(lit and all(not (d.flags & 1) for d in lit), "0x20000 steam is lit")
        self.assertTrue(all(d.nrm[0] == (0.0, 0.0, 1.0) for d in lit), "lit particles use the world-up normal")
        night = RD.PRESETS["sw_night"]
        self.assertLess(max(RD._vertex_light(lit[0].nrm[0], night, False)), 0.95)
        m["particles"][0]["flags"] |= 0x1
        unlit = RD.particle_drawables(m, tx, None, cam)
        self.assertTrue(all(d.flags & 1 for d in unlit), "flag 0x1 draws unlit")
        m["particles"][0]["flags"] |= 0x8
        self.assertTrue(all(d.flags & 2 for d in RD.particle_drawables(m, tx, None, cam)), "flag 0x8: no fog")


class Previews(unittest.TestCase):
    def test_cube_previews_render(self):
        """The orbit view of the lettered cube shows the FRONT (+X, red) face on the left and the LEFT (+Y, green)
        face on the right when seen from front-left (section 5.2.1 conventions)."""
        res = CM.built("Cube")
        m = P.load(res.m2)
        tx = RD.TextureSet(CM.workdir() + "/files")
        fr = P.orbit_view(m, tx, 30, 10, 96, 1, particles=False)
        img = fr.to_image()
        def px(x, y):
            o = 4 * (y * img.width + x)
            return tuple(img.data[o:o + 3])
        left = px(30, 56)
        right = px(70, 56)
        self.assertGreater(left[0], left[1], "front face (red) on the left: %r" % (left,))
        self.assertGreater(right[1], right[0], "left face (green) on the right: %r" % (right,))


if __name__ == "__main__":
    unittest.main()
