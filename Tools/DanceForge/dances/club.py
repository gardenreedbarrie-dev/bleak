"""Club and party dances: the big, catchy dance-floor moves everybody joins in on, choreographed for Bleakhold."""

import math

from dflib.choreo import Dance

from moves import arms_fk, feet, groove, hands, hips, merge, sway, STANCE, ANKLE_Z

TOUCH_Z = ANKLE_Z + 0.03     # a foot tapping the floor with the toes, heel up


def _y(v, s):
    """A left-side position or direction moved to the side `s` (+1 left, -1 the right-side mirror)."""
    return (v[0], v[1] * s, v[2])


def _step_touch(d, width=0.21, inner=0.05, lift=0.07, hip=0.11, touch_pitch=16.0):
    """Keys a travelling step touch on every beat: step right, touch left in, step left, touch right in. The
    stepping foot lands wide on the beat, the tapping foot comes in next to it on its toes, and the hips ride over
    the foot that carries the weight."""
    for k in range(int(d.beats)):
        b = float(k)
        phase = k % 4
        if phase == 0:      # step right: wide stance, weight travelling right
            moved, pos, other, opos, y = "r", (0.0, -width, ANKLE_Z), "l", (0.0, width, ANKLE_Z), 0.0
        elif phase == 1:    # touch left next to the right foot
            moved, pos, other, opos, y = "l", (0.0, -inner, TOUCH_Z), "r", (0.0, -width, ANKLE_Z), -hip
        elif phase == 2:    # step left
            moved, pos, other, opos, y = "l", (0.0, width, ANKLE_Z), "r", (0.0, -width, ANKLE_Z), 0.0
        else:               # touch right next to the left foot
            moved, pos, other, opos, y = "r", (0.0, inner, TOUCH_Z), "l", (0.0, width, ANKLE_Z), hip
        touching = pos[2] > ANKLE_Z
        d.key(b, ease="inout", lift=lift, **{"foot_" + moved: pos})
        d.key(b, ease="inout", **{"foot_" + other: opos, "foot_pitch_" + other: 0.0, "toe_" + other: 0.0,
                                  "foot_pitch_" + moved: touch_pitch if touching else 0.0,
                                  "toe_" + moved: touch_pitch if touching else 0.0})
        side = -y / hip if y else 0.0      # +1 with the weight on the right foot
        d.key(b, hips=(0.0, y, -0.05), hips_roll=4.0 * side)


def party_starter():
    """The go-to party dance: a step touch from side to side with a knee bounce while the arms row in turn, each
    one punching forward across the body and pulling back past the hip while the other swings round to take over,
    the shoulders rolling into every punch and the head bobbing; the eight-count phrase ends on a point up and out
    to the crowd."""
    d = Dance(bpm=120, beats=8)
    _step_touch(d)
    # one arm's rowing loop (left side; the right is the mirror, one beat later): punch across, pull down past the
    # hip close to the body, back, then swing round wide and high to the next punch
    loop = [((0.56, 0.0, 0.14), (-0.2, 1.0, -0.5)),
            ((0.18, 0.40, -0.24), (-1.0, 0.5, -0.3)),
            ((-0.14, 0.35, -0.20), (-1.0, 0.3, 0.1)),
            ((0.20, 0.42, 0.06), (-0.8, 0.6, -0.4))]
    for k in range(16):
        b = k * 0.5
        hl, el = loop[k % 4]
        d.key(b, ease="in" if k % 4 == 0 else "smooth", **hands(left=hl, elbow_l=el))
        if b < 7.0:
            hr, er = loop[(k + 2) % 4]
            d.key(b, ease="in" if k % 4 == 2 else "smooth", **hands(right=_y(hr, -1), elbow_r=_y(er, -1)))
    for k in range(7):
        s = 1.0 if k % 2 == 0 else -1.0      # +1: the left arm punches across to the right
        d.key(float(k), ease="in", **merge(
            hips_yaw=10.0 * s, spine_twist=-30.0 * s, clav_fwd_l=20.0 if s > 0 else -6.0,
            clav_fwd_r=-6.0 if s > 0 else 20.0, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0)))
    # the point on the last count: the right arm shoots forward and up to the crowd on the right and holds
    point = merge(hands(right=(0.44, -0.40, 0.42), elbow_r=(-0.3, -1.0, -0.4)),
                  hips_yaw=-4.0, spine_twist=10.0, clav_fwd_l=-6.0, clav_fwd_r=18.0)
    d.key(7.0, ease="in", **point)
    d.key(7.25, ease="hold", **point)
    d.key(7.62, **hands(right=_y(loop[1][0], -1), elbow_r=_y(loop[1][1], -1)))
    d.key(0, hips_pitch=6.0, spine_bend=5.0)
    d.key(6.5, head_nod=0.0)
    d.key(7.0, ease="in", head_nod=-8.0)
    d.key(7.25, ease="hold", head_nod=-8.0)
    d.key(7.8, head_nod=0.0)
    d.overlay(groove(depth=0.04, per_beat=1, chest=3.0, nod=5.0))
    d.follow("head_turn", "spine_twist", gain=0.4)
    d.follow("head_tilt", "hips_roll", gain=-0.6)
    return d


def _smoothstep(e0, e1, x):
    u = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return u * u * (3.0 - 2.0 * u)


def _window(beat, start, end, ramp=0.4):
    """0..1 envelope: rises over `ramp` beats from `start`, falls over `ramp` beats to `end`."""
    return _smoothstep(start, start + ramp, beat) * (1.0 - _smoothstep(end - ramp, end, beat))


def prep_swing():
    """The preppy sitcom swing: a step touch from side to side while both arms swing together across the front of
    the body on every beat, elbows bent and wrists loose, the hips twisting the other way and the head cocked; then
    both arms fly up overhead and come down slowly while the shoulders shake. Goofy and very pleased with itself."""
    d = Dance(bpm=116, beats=8)
    _step_touch(d, width=0.19, hip=0.10)
    # both arms swing to the left (out wide and across the front), dip through the middle, then to the right
    wide, cross, low = (0.18, 0.55, 0.18), (0.46, 0.06, 0.08), (0.40, 0.22, -0.06)
    el_wide, el_cross = (-0.6, 0.8, -0.6), (-0.4, 0.5, -1.0)
    to_left = merge(hands(wide, _y(cross, 1), el_wide, _y(el_cross, -1)),
                    spine_twist=16.0, spine_side=6.0, hips_yaw=-10.0, head_tilt=10.0, head_turn=6.0)
    to_right = merge(hands(cross, _y(wide, -1), el_cross, _y(el_wide, -1)),
                     spine_twist=-16.0, spine_side=-6.0, hips_yaw=10.0, head_tilt=-10.0, head_turn=-6.0)
    middle = merge(hands(low, _y(low, -1), el_cross, _y(el_cross, -1)),
                   spine_twist=0.0, spine_side=0.0, hips_yaw=0.0, head_tilt=0.0, head_turn=0.0)
    for k in range(4):
        b = float(k)
        left = k % 2 == 0
        d.key(b, ease="out", **(to_left if left else to_right))
        if k < 3:
            w = -30.0 if left else 30.0     # the loose hands trail the swing
            d.key(b + 0.5, ease="in", **merge(middle, wrist_l=(w, 0.0, 0.0), wrist_r=(-w, 0.0, 0.0)))
        d.key(b, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0))
    # both arms fly up overhead, hold, and come down slowly while the shoulders shake
    up = merge(hands((0.08, 0.40, 0.78), (0.08, -0.40, 0.78), (-0.3, 1.0, 0.0), (-0.3, -1.0, 0.0)),
               spine_twist=0.0, spine_side=0.0, hips_yaw=0.0, head_tilt=-6.0, head_turn=0.0)
    d.key(4.0, ease="out", **merge(up, head_nod=-12.0, wrist_l=(-20.0, 0.0, 0.0), wrist_r=(-20.0, 0.0, 0.0)))
    d.key(4.6, ease="inout", **merge(hands((0.10, 0.42, 0.74), (0.10, -0.42, 0.74)), head_nod=-8.0))
    d.key(5.6, ease="inout", **merge(hands((0.20, 0.48, 0.28), (0.20, -0.48, 0.28), (-0.4, 1.0, -0.6),
                                           (-0.4, -1.0, -0.6)), head_tilt=6.0, head_nod=0.0,
                                     wrist_l=(30.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 0.0)))
    d.key(7.2, ease="inout", **merge(hands((0.34, 0.36, 0.10), (0.34, -0.36, 0.10)), head_tilt=-4.0,
                                     wrist_l=(20.0, 0.0, 0.0), wrist_r=(20.0, 0.0, 0.0)))
    d.key(0.0, head_nod=0.0)
    d.key(3.0, head_nod=0.0)

    def shake(beat):
        e = _window(beat, 5.0, 7.7, 0.4)
        v = math.sin(2.0 * math.pi * 2.0 * beat) * e
        return {"clav_up_l": 12.0 * v, "clav_up_r": -12.0 * v, "clav_fwd_l": 8.0 * v, "clav_fwd_r": -8.0 * v,
                "spine_twist": 5.0 * v}
    d.overlay(shake)
    d.key(0, hips_pitch=5.0)
    d.overlay(groove(depth=0.035, per_beat=1, chest=2.5, nod=4.0))
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def sidekick_pump():
    """The kid's kick dance: bouncing on every count, a knee pops up and kicks out to the side while both arms swing
    low across the front of the hips the other way and the body leans into it, then the other side; the second bar
    pumps the arms up higher and leans harder."""
    d = Dance(bpm=126, beats=8)
    for cell in range(4):
        b = cell * 2.0
        sk = -1.0 if cell % 2 == 0 else 1.0     # the kicking side: right, left, right, left
        a = -sk                                   # the arms and the lean go the other way
        big = cell >= 2
        kick, sup = ("r", "l") if sk < 0 else ("l", "r")
        stance = (0.0, sk * STANCE, ANKLE_Z)
        d.key(b, ease="inout", **{"foot_" + kick: stance, "foot_" + sup: (0.0, a * STANCE, ANKLE_Z),
                                  "foot_pitch_" + kick: 0.0, "knee_" + kick: (1.0, sk * 0.14, 0.0)})
        d.key(b + 0.5, ease="out", **{"foot_" + kick: (0.12, sk * 0.17, 0.36), "foot_pitch_" + kick: 10.0,
                                      "knee_" + kick: (1.0, sk * 0.3, 0.1)})
        d.key(b + 1.0, ease="out", **{"foot_" + kick: (0.04, sk * (0.52 if big else 0.48), 0.30),
                                      "foot_pitch_" + kick: -15.0, "knee_" + kick: (0.5, sk * 0.3, 0.8)})
        d.key(b + 1.5, ease="in", **{"foot_" + kick: stance, "foot_" + sup: (0.0, a * STANCE, ANKLE_Z),
                                     "foot_pitch_" + kick: 0.0, "knee_" + kick: (1.0, sk * 0.14, 0.0)})
        # the arms: from low in the middle to low at the side (or up at chest height in the second bar)
        z = -0.02 if big else -0.22
        near, far = (0.26, a * 0.50, z), (0.46, a * 0.08, z + 0.02)
        hl, hr = (near, far) if a > 0 else (far, near)
        lean = 14.0 if big else 10.0
        d.key(b, ease="inout", **merge(
            hips(y=0.0, z=-0.07, roll=0.0, pitch=6.0), spine_side=0.0, spine_twist=0.0, spine_bend=8.0))
        d.key(b + 1.0, **hands(hl, hr, (-0.5, 0.6, -1.0), (-0.5, -0.6, -1.0)))
        d.key(b + 1.0, ease="out", **merge(
            hips(y=a * 0.07, z=-0.05, roll=-a * 5.0, pitch=6.0),
            spine_side=a * lean, spine_twist=a * 14.0, spine_bend=6.0 if big else 10.0))
        d.key(b + 1.5, ease="inout", **merge(hips(y=a * 0.03, z=-0.08, roll=-a * 2.0, pitch=6.0)))
        d.key(b, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0))
        d.key(b + 1.0, wrist_l=(-25.0 * a, 0.0, 0.0), wrist_r=(25.0 * a, 0.0, 0.0))
    d.overlay(groove(depth=0.03, per_beat=1, chest=2.0, nod=4.0))
    d.overlay(groove(depth=0.015, per_beat=2, chest=1.0, nod=0.0))
    d.follow("head_tilt", "spine_side", gain=0.6)
    d.follow("head_turn", "spine_twist", gain=0.3)
    return d


def _hop(d, beat, height=0.06, z=0.04, width=STANCE, pitch=25.0):
    """Both feet off the floor at `beat` (toes pointed), the hips up with them."""
    d.key(beat, ease="out", **merge(feet(width, z_l=ANKLE_Z + height, z_r=ANKLE_Z + height),
                                    foot_pitch_l=pitch, foot_pitch_r=pitch))
    d.key(beat, ease="out", hips=(0.0, 0.0, z))


def _land(d, beat, z=-0.10, width=STANCE, y=0.0):
    """Both feet back on the floor at `beat`, the knees soaking it up."""
    d.key(beat, ease="in", **merge(feet(width), foot_pitch_l=0.0, foot_pitch_r=0.0))
    d.key(beat, ease="in", hips=(0.0, y, z))


def hands_up():
    """Rave hands: the drop hits with a finger pointing at the sky, then both hands go up and pump on every beat
    with little jumps, the arms wave over the head from side to side, and the body crouches low for the build
    before springing up into the next drop."""
    d = Dance(bpm=128, beats=8)
    wide = STANCE + 0.05
    point = merge(hands((0.16, 0.40, -0.06), (0.10, -0.34, 0.80), (-0.6, 1.0, -0.3), (-0.3, -1.0, 0.0)),
                  spine_side=4.0, spine_twist=8.0, spine_bend=-2.0, head_nod=-16.0, head_turn=-6.0)
    v_up = merge(hands((0.10, 0.42, 0.78), (0.10, -0.42, 0.78), (-0.3, 1.0, 0.0), (-0.3, -1.0, 0.0)),
                 spine_side=0.0, spine_twist=0.0, spine_bend=-2.0, head_nod=-10.0, head_turn=0.0)
    v_bent = hands((0.20, 0.50, 0.50), (0.20, -0.50, 0.50))
    # the drop and the pumps
    d.key(0.0, ease="in", **point)
    _land(d, 0.0, z=-0.12, width=wide)
    d.key(0.35, ease="hold", **point)
    d.key(0.5, ease="out", hips=(0.0, 0.0, -0.04))
    d.key(0.68, **hands(left=(0.16, 0.62, 0.32)))
    for k in range(4):
        b = 1.0 + k
        d.key(b, ease="inout" if k == 0 else "in", **v_up)
        if k == 0:
            _land(d, b, z=-0.10, width=wide)
        else:
            _land(d, b)
        if k < 3:
            d.key(b + 0.5, ease="out", **v_bent)
            _hop(d, b + 0.5)
    # waving over the head from side to side
    lean_l = merge(hands((0.10, 0.62, 0.58), (0.08, -0.30, 0.80)), spine_side=14.0, head_nod=-8.0, head_tilt=6.0)
    lean_r = merge(hands((0.08, 0.30, 0.80), (0.10, -0.62, 0.58)), spine_side=-14.0, head_nod=-8.0, head_tilt=-6.0)
    d.key(4.6, **lean_l)
    d.key(4.6, hips=(0.0, -0.06, -0.06))
    d.key(5.6, **lean_r)
    d.key(5.6, hips=(0.0, 0.06, -0.06))
    # the build: down low, hands on the knees, then spring up
    crouch = merge(hands((0.42, 0.24, -0.30), (0.42, -0.24, -0.30), (-0.6, 0.7, -0.5), (-0.6, -0.7, -0.5)),
                   spine_side=0.0, spine_twist=0.0, spine_bend=22.0, head_nod=6.0, head_tilt=0.0, head_turn=0.0)
    d.key(6.1, **merge(hands((0.22, 0.56, 0.30), (0.22, -0.56, 0.30)), spine_side=0.0, head_tilt=0.0))
    d.key(6.6, ease="inout", **crouch)
    d.key(6.6, ease="inout", hips=(0.0, 0.0, -0.18))
    d.key(7.0, ease="inout", **merge(crouch, spine_bend=28.0, head_nod=10.0))
    d.key(7.0, ease="inout", **merge(feet(STANCE), foot_pitch_l=0.0, foot_pitch_r=0.0))
    d.key(7.0, ease="inout", hips=(0.0, 0.0, -0.24))
    d.key(7.3, **hands((0.40, 0.36, -0.10), (0.42, -0.40, 0.08)))
    d.key(7.6, **merge(hands((0.24, 0.46, 0.02), (0.20, -0.50, 0.52)), spine_bend=0.0, head_nod=-8.0))
    _hop(d, 7.55, height=0.12, z=0.10, width=(STANCE + wide) / 2.0)
    d.key(0, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0))
    d.key(4.6, wrist_l=(-20.0, 0.0, 0.0), wrist_r=(-20.0, 0.0, 0.0))
    d.key(5.6, wrist_l=(-20.0, 0.0, 0.0), wrist_r=(-20.0, 0.0, 0.0))
    d.key(6.6, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0))
    d.key(0, hips_pitch=4.0)
    d.overlay(groove(depth=0.02, per_beat=1, chest=2.0, nod=4.0))
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def snap_groove():
    """Cool and laid back: an easy step touch from side to side with a lean, the fingers snapping out at shoulder
    height on two and four (right, then left, then both together in the second bar), the shoulders rolling and the
    head bobbing along."""
    d = Dance(bpm=100, beats=8)
    _step_touch(d, width=0.17, inner=0.07, lift=0.04, hip=0.09)
    rest = ((0.27, 0.32, -0.16), (-0.5, 0.6, -1.0))
    snap = ((0.30, 0.64, 0.14), (-0.4, 0.4, -1.0))
    gather = ((0.28, 0.32, -0.18), (-0.6, 0.5, -1.0))
    for bar in range(2):
        b = bar * 4.0
        both = bar == 1
        # beat 1 and 3: step (the hands gather in front); beat 2 and 4: snap
        for k, side in ((0, -1.0), (2, 1.0)):
            d.key(b + k, ease="inout", **merge(
                hands(gather[0], _y(gather[0], -1), gather[1], _y(gather[1], -1)),
                spine_side=0.0, spine_bend=2.0, head_turn=0.0, head_nod=0.0, spine_twist=0.0,
                wrist_l=(30.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 0.0)))
            out_l = snap if (both or side > 0) else rest
            out_r = snap if (both or side < 0) else rest
            pose = merge(hands(out_l[0], _y(out_r[0], -1), out_l[1], _y(out_r[1], -1)),
                         spine_side=-side * (8.0 if both else 6.0), spine_bend=-6.0 if both else -2.0,
                         spine_twist=0.0 if both else side * 10.0, head_turn=0.0 if both else side * 14.0,
                         head_nod=-6.0 if both else 0.0,
                         wrist_l=(-25.0, 0.0, 0.0) if out_l is snap else (20.0, 0.0, 0.0),
                         wrist_r=(-25.0, 0.0, 0.0) if out_r is snap else (20.0, 0.0, 0.0))
            d.key(b + k + 1.0, ease="in", **pose)
            d.key(b + k + 1.3, ease="out", **merge(pose, spine_side=pose["spine_side"] * 1.2))

    def roll(beat):
        a = math.pi * beat
        return {"clav_up_l": 5.0 * math.sin(a), "clav_fwd_l": 6.0 * math.cos(a),
                "clav_up_r": -5.0 * math.sin(a), "clav_fwd_r": -6.0 * math.cos(a)}
    d.overlay(roll)
    d.key(0, hips_pitch=3.0)
    d.overlay(groove(depth=0.03, per_beat=1, chest=2.0, nod=5.0, lag=0.15))
    d.follow("head_tilt", "spine_side", gain=-0.4)
    return d


def clap_along():
    """Happy crowd clapping: a step touch with the hands clapping high over the head on two and four, then the claps
    drop low and out to the side, the torso spinning round to meet them, right then left."""
    d = Dance(bpm=120, beats=8)
    _step_touch(d, width=0.19, hip=0.10)
    palms = {"wrist_l": (0.0, 0.0, -90.0), "wrist_r": (0.0, 0.0, -90.0)}
    open_up = merge(hands((0.12, 0.62, 0.50), (0.12, -0.62, 0.50), (-0.3, 1.0, -0.2), (-0.3, -1.0, -0.2)),
                    spine_twist=0.0, spine_side=0.0, head_nod=-6.0, head_tilt=0.0, wrist_l=(-20.0, 0.0, -60.0),
                    wrist_r=(-20.0, 0.0, -60.0))
    clap_up = merge(hands((0.28, 0.035, 0.72), (0.28, -0.035, 0.72), (-0.2, 1.0, 0.0), (-0.2, -1.0, 0.0)),
                    spine_twist=0.0, spine_side=0.0, head_nod=-10.0, head_tilt=0.0, **palms)
    for k in (0, 2):
        d.key(float(k), **open_up)
        d.key(k + 1.0, ease="in", **merge(clap_up, head_tilt=8.0 if k == 0 else -8.0))
        d.key(k + 1.2, ease="out", **merge(hands((0.28, 0.06, 0.71), (0.28, -0.06, 0.71)),
                                           head_tilt=8.0 if k == 0 else -8.0))
    # the arms open out wide on the way down to the low claps
    d.key(3.6, **merge(hands((0.22, 0.58, 0.36), (0.22, -0.58, 0.36)), wrist_l=(-20.0, 0.0, -60.0),
                       wrist_r=(-20.0, 0.0, -60.0)))
    # low claps out to the side, the torso spinning round to them
    for k, side in ((4, -1.0), (6, 1.0)):
        out = merge(hands((0.30, 0.48, 0.04), (0.30, -0.48, 0.04), (-0.5, 1.0, -0.5), (-0.5, -1.0, -0.5)),
                    spine_twist=-side * 8.0, spine_side=0.0, head_nod=0.0, head_tilt=0.0,
                    wrist_l=(-20.0, 0.0, -60.0), wrist_r=(-20.0, 0.0, -60.0))
        clap = merge(hands((0.42, side * 0.10 + 0.035, -0.12), (0.42, side * 0.10 - 0.035, -0.12),
                           (-0.6, 1.0, -0.6), (-0.6, -1.0, -0.6)),
                     spine_twist=side * 32.0, spine_side=-side * 6.0, head_nod=8.0, head_tilt=side * 8.0,
                     hips_yaw=side * 8.0, **palms)
        d.key(float(k), **out)
        d.key(k + 1.0, ease="in", **clap)
        d.key(k + 1.2, ease="out", **merge(clap, hands((0.42, side * 0.10 + 0.06, -0.10),
                                                       (0.42, side * 0.10 - 0.06, -0.10))))
    d.key(0, hips_yaw=0.0)
    d.key(4, hips_yaw=0.0)
    d.key(6, hips_yaw=0.0)
    d.key(7.6, hips_yaw=0.0)
    d.key(0, hips_pitch=4.0)
    d.overlay(groove(depth=0.035, per_beat=1, chest=2.5, nod=4.0))
    d.follow("head_turn", "spine_twist", gain=0.4)
    return d


def step_touch():
    """The classic step touch with style: step out, touch in, the arms swinging forward and back in opposition to
    the feet, a body roll rippling down from the chest to the hips on every step and the hips popping out to the
    side on every touch; the second bar swings the arms higher."""
    d = Dance(bpm=116, beats=8)
    _step_touch(d, width=0.20, hip=0.09, lift=0.06)
    for k in range(8):
        b = float(k)
        big = k >= 4
        s = 1.0 if k % 2 == 0 else -1.0       # +1: the left arm swings forward
        fwd = (68.0, 18.0, 16.0, 0.0) if big else (76.0, -8.0, 26.0, 0.0)
        back = (-48.0, -48.0, 14.0, 0.0)
        arm_l, arm_r = (fwd, back) if s > 0 else (back, fwd)
        d.key(b, ease="out", **merge(arms_fk(arm_l, arm_r), spine_twist=-14.0 * s, clav_fwd_l=10.0 * s,
                                     clav_fwd_r=-10.0 * s, wrist_l=(-15.0, 0.0, 0.0), wrist_r=(-15.0, 0.0, 0.0)))
        d.key(b + 0.5, ease="in", **arms_fk((18.0, -78.0, 10.0, 0.0), (18.0, -78.0, 10.0, 0.0)))
    # the hips pop out over the standing foot on every touch
    for k in range(8):
        b = float(k)
        phase = k % 4
        y = (0.0, -0.13, 0.0, 0.13)[phase]
        d.key(b, ease="pop" if phase % 2 else "inout", hips=(0.0, y, -0.05),
              hips_roll=(0.0, 7.0, 0.0, -7.0)[phase], spine_side=(0.0, -5.0, 0.0, 5.0)[phase])

    def body_roll(beat):
        # a wave over the first beat of every pair: head, then chest, then hips
        t = beat % 2.0
        if t >= 1.0:
            return {}
        env = math.sin(math.pi * t)
        w = 2.0 * math.pi * t
        return {"head_nod": -7.0 * math.sin(w) * env, "spine_bend": 9.0 * math.sin(w - 0.9) * env,
                "hips_pitch": -7.0 * math.sin(w - 1.8) * env, "hips": (0.035 * math.sin(w - 1.8) * env, 0.0, 0.0)}
    d.overlay(body_roll)
    d.key(0, hips_pitch=5.0, spine_bend=3.0)
    d.overlay(groove(depth=0.03, per_beat=1, chest=2.0, nod=3.0))
    d.follow("head_tilt", "spine_side", gain=-0.5)
    d.follow("head_turn", "spine_twist", gain=0.3)
    return d


def shoulder_bounce():
    """The hip-hop shoulder bounce: the shoulders pop up in turn on every beat with the arms bent and loose, the body
    rocking forward and back over a wide bouncing stance and the head nodding, cocky; the second bar goes double
    time turned to one side, then the other, and ends on a big shrug."""
    d = Dance(bpm=98, beats=8)
    hits = [(0.0, 1.0), (1.0, -1.0), (2.0, 1.0), (3.0, -1.0)]
    hits += [(4.0 + 0.5 * k, 1.0 if k % 2 == 0 else -1.0) for k in range(4)]
    hits += [(6.0, 1.0), (6.5, -1.0)]
    for b, side in hits:
        up, down = 20.0, -3.0
        l, r = (up, down) if side > 0 else (down, up)
        big = b >= 4.0
        hl = (0.24, 0.42, 0.10) if side > 0 else (0.28, 0.35, 0.0)
        hr = (0.28, -0.35, 0.0) if side > 0 else (0.24, -0.42, 0.10)
        d.key(b, ease="pop", **merge(
            hands(hl, hr, (-0.6, 1.0, -0.4), (-0.6, -1.0, -0.4)), clav_up_l=l, clav_up_r=r,
            clav_fwd_l=6.0 if side > 0 else -2.0, clav_fwd_r=-2.0 if side > 0 else 6.0,
            spine_side=-side * (3.0 if big else 5.0), head_tilt=side * 6.0))
    # the double-time bar turns to the left, then to the right
    for b, facing in ((0.0, 0.0), (3.6, 0.0), (4.0, 1.0), (5.5, 1.0), (6.0, -1.0), (6.8, -1.0), (7.0, 0.0)):
        d.key(b, ease="inout", spine_twist=facing * 22.0, hips_yaw=facing * 10.0, head_turn=facing * 10.0)
    # the shrug: both shoulders up and hold, then drop
    shrug = merge(hands((0.24, 0.44, 0.10), (0.24, -0.44, 0.10)), clav_up_l=26.0, clav_up_r=26.0,
                  clav_fwd_l=8.0, clav_fwd_r=8.0, spine_side=0.0, head_tilt=10.0)
    d.key(7.0, ease="pop", **shrug)
    d.key(7.5, ease="hold", **shrug)
    d.key(7.75, ease="inout", **merge(hands((0.27, 0.37, 0.02), (0.27, -0.37, 0.02)), clav_up_l=0.0,
                                      clav_up_r=0.0, head_tilt=0.0))
    # rocking forward and back over two beats
    for b, lean in ((0.0, 8.0), (1.0, -3.0), (2.0, 8.0), (3.0, -3.0), (4.0, 6.0), (5.0, 1.0), (6.0, 6.0),
                    (7.0, -6.0)):
        d.key(b, spine_bend=lean, hips=(0.0, 0.0, -0.10 if lean > 5.0 else -0.06),
              hips_pitch=8.0 if lean > 5.0 else 3.0, head_nod=-lean * 0.6)
    d.key(0, **merge(feet(STANCE + 0.06), foot_yaw_l=18.0, foot_yaw_r=-18.0))
    d.key(0, knee_l=(1.0, 0.35, 0.0), knee_r=(1.0, -0.35, 0.0))
    d.key(0, wrist_l=(8.0, 0.0, 0.0), wrist_r=(8.0, 0.0, 0.0))
    d.overlay(groove(depth=0.035, per_beat=1, chest=4.0, nod=6.0, lag=0.15))
    d.overlay(sway(amount=0.03, period=2.0, roll=3.0))
    d.follow("head_turn", "spine_twist", gain=0.3)
    return d


def club_bounce():
    """The dance-floor bounce: the knees bounce on every beat while bent arms pump in turn in front of the chest,
    the body turned a little to the left for one bar and to the right for the next, the head nodding along; the end
    of the second bar pumps in double time."""
    d = Dance(bpm=126, beats=8)
    pumps = [float(k) for k in range(6)] + [6.0, 6.5, 7.0, 7.5]
    for i, b in enumerate(pumps):
        s = 1.0 if i % 2 == 0 else -1.0       # +1: the left hand pumps down
        low, high = (0.46, 0.25, -0.04), (0.34, 0.36, 0.18)
        hl, hr = (low, _y(high, -1)) if s > 0 else (high, _y(low, -1))
        d.key(b, ease="in", **merge(hands(hl, hr, (-0.4, 1.0, -0.8), (-0.4, -1.0, -0.8)),
                                    clav_fwd_l=8.0 * s, clav_fwd_r=-8.0 * s, spine_side=-3.0 * s,
                                    wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0)))
    for b, facing in ((0.0, 1.0), (3.4, 1.0), (4.0, -1.0), (7.4, -1.0)):
        d.key(b, ease="inout", hips_yaw=facing * 14.0, spine_twist=facing * 8.0, head_turn=facing * 6.0,
              foot_yaw_l=8.0 + facing * 8.0, foot_yaw_r=-8.0 + facing * 8.0)
    d.key(0, **feet(STANCE + 0.04))
    d.key(0, hips=(0.0, 0.0, -0.05), hips_pitch=5.0, spine_bend=4.0)
    d.overlay(groove(depth=0.05, per_beat=1, chest=3.0, nod=7.0, lag=0.12))
    d.overlay(sway(amount=0.035, period=2.0, roll=3.0))
    d.follow("head_tilt", "spine_side", gain=-0.5)
    return d


def hip_roll():
    """Big slow hip circles, one every two beats, the upper body rolling against them so the whole body undulates,
    while the arms flow up the front of the body to over the head, sway there, and pour back down the sides like
    water, the right arm a moment behind the left."""
    d = Dance(bpm=96, beats=8)

    def circle(beat):
        a = math.pi * beat               # one full circle every two beats
        c, sn = math.cos(a), math.sin(a)
        return {"hips": (0.05 * c, 0.10 * sn, -0.03 * (1.0 - c)), "hips_pitch": -6.0 * c, "hips_roll": -9.0 * sn,
                "spine_side": 12.0 * math.sin(a - 0.6), "spine_bend": 5.0 * math.cos(a - 0.6),
                "head_tilt": -4.0 * math.sin(a - 1.2), "head_nod": -3.0 * math.cos(a - 1.2)}
    d.overlay(circle)
    # the left arm's path (the right follows it half a beat later, mirrored)
    path = [(0.0, (0.16, 0.40, -0.26), (-0.5, 1.0, -0.6), 30.0),
            (1.4, (0.36, 0.36, 0.04), (-0.4, 1.0, -0.8), -20.0),
            (2.2, (0.26, 0.52, 0.40), (-0.4, 1.0, -0.4), 0.0),
            (3.0, (0.08, 0.46, 0.72), (-0.3, 1.0, 0.0), 30.0),
            (4.0, (0.04, 0.40, 0.78), (-0.3, 1.0, 0.0), -10.0),
            (5.0, (0.10, 0.52, 0.64), (-0.3, 1.0, 0.0), 20.0),
            (6.3, (0.16, 0.62, 0.20), (-0.4, 1.0, -0.4), -25.0),
            (7.3, (0.12, 0.48, -0.16), (-0.5, 1.0, -0.6), 15.0)]
    for b, hand, elbow, wrist in path:
        d.key(b, **merge(hands(left=hand, elbow_l=elbow), wrist_l=(wrist, 0.0, 0.0)))
        br = (b + 0.5) % 8.0
        d.key(br, **merge(hands(right=_y(hand, -1), elbow_r=_y(elbow, -1)), wrist_r=(wrist, 0.0, 0.0)))
    d.key(0, **merge(feet(STANCE + 0.05), hips_yaw=0.0))
    d.key(0, knee_l=(1.0, 0.3, 0.0), knee_r=(1.0, -0.3, 0.0))
    d.key(0, hips=(0.0, 0.0, -0.08))
    d.overlay(groove(depth=0.015, per_beat=1, chest=1.0, nod=2.0))
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def hula_hoop():
    """Keeping an invisible hula hoop up: quick hip circles, one on every beat, pushing forward, side, back and side
    while the chest stays quiet and the knees give a little; the arms are bent up over the head for one bar and held
    out to the sides for balance for the next."""
    d = Dance(bpm=132, beats=8)

    def hoop(beat):
        a = 2.0 * math.pi * beat         # a full circle on every beat
        c, sn = math.cos(a), math.sin(a)
        return {"hips": (0.075 * c, 0.065 * sn, -0.015 * (1.0 + sn)), "hips_pitch": -9.0 * c, "hips_roll": -8.0 * sn,
                "spine_bend": 8.0 * math.cos(a - 0.4), "spine_side": 8.0 * math.sin(a - 0.4),
                "head_nod": -2.0 * math.cos(a - 0.9), "head_tilt": -2.0 * math.sin(a - 0.9)}
    d.overlay(hoop)
    up = merge(hands((0.04, 0.44, 0.66), (0.04, -0.44, 0.66), (-0.2, 1.0, 0.2), (-0.2, -1.0, 0.2)),
               wrist_l=(-20.0, 0.0, 0.0), wrist_r=(-20.0, 0.0, 0.0))
    out = merge(hands((0.12, 0.72, 0.12), (0.12, -0.72, 0.12), (-0.4, 1.0, -0.4), (-0.4, -1.0, -0.4)),
                wrist_l=(-35.0, 0.0, 0.0), wrist_r=(-35.0, 0.0, 0.0))
    d.key(0.0, **up)
    d.key(3.3, ease="inout", **up)
    d.key(4.3, ease="inout", **out)
    d.key(7.3, ease="inout", **out)
    # the arms float a little with the hoop
    d.key(1.5, **hands((0.06, 0.46, 0.68), (0.06, -0.42, 0.64)))
    d.key(5.5, **hands((0.14, 0.72, 0.16), (0.14, -0.70, 0.08)))
    d.key(0, **feet(STANCE, x_l=0.08, x_r=-0.06))
    d.key(0, foot_yaw_l=4.0, foot_yaw_r=-20.0, hips_yaw=-6.0)
    d.key(0, hips=(0.0, 0.0, -0.07))
    d.overlay(groove(depth=0.02, per_beat=1, chest=0.0, nod=0.0))
    return d


def slow_sway():
    """The slow dance: rocking gently from foot to foot, the free heel lifting off the floor, with the arms up as if
    resting on a partner's shoulders, the head tilting softly, the couple turning slowly one way and back; half way
    the left hand drifts to the heart and returns."""
    d = Dance(bpm=90, beats=8)
    # small steps in place: the weight rocks onto one foot and the other lifts its heel and settles again
    st = STANCE + 0.02
    for k in range(4):
        b = k * 2.0
        free = "l" if k % 2 == 0 else "r"      # the foot without the weight
        y = st if free == "l" else -st
        d.key(b + 0.2, ease="inout", **{"foot_" + free: (0.0, y, ANKLE_Z), "foot_pitch_" + free: 0.0})
        d.key(b + 1.0, ease="inout", **{"foot_" + free: (0.02, y, ANKLE_Z + 0.03), "foot_pitch_" + free: 14.0})
        d.key(b + 1.8, ease="inout", **{"foot_" + free: (0.0, y, ANKLE_Z), "foot_pitch_" + free: 0.0})
    for k in range(4):
        b = k * 2.0
        side = -1.0 if k % 2 == 0 else 1.0       # rock onto the right, then the left
        d.key(b + 1.0, hips=(0.0, side * 0.075, -0.06), hips_roll=-side * 5.0, spine_side=side * 4.0,
              head_tilt=side * 9.0)
        d.key(b, hips=(0.0, 0.0, -0.08), hips_roll=0.0, spine_side=0.0, head_tilt=side * 3.0)
    # a gentle turn one way and back over the two bars
    for b, turn in ((0.0, -1.0), (4.0, 1.0)):
        d.key(b, ease="inout", hips_yaw=turn * 14.0, spine_twist=-turn * 4.0, head_turn=turn * 6.0,
              foot_yaw_l=8.0 + turn * 10.0, foot_yaw_r=-8.0 + turn * 10.0)
    # the arms rest on the partner's shoulders; the left hand drifts to the heart and back
    partner = merge(hands((0.44, 0.40, 0.28), (0.44, -0.40, 0.28), (-0.2, 1.0, -0.7), (-0.2, -1.0, -0.7)),
                    wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0))
    d.key(0.0, **partner)
    d.key(3.4, ease="inout", **partner)
    d.key(4.6, ease="inout", **merge(hands(left=(0.30, 0.12, 0.10), elbow_l=(-0.6, 1.0, -0.6)),
                                     wrist_l=(10.0, 0.0, -30.0)))
    d.key(6.6, ease="inout", **merge(hands(left=(0.29, 0.13, 0.09)), wrist_l=(10.0, 0.0, -30.0)))
    d.key(7.6, ease="inout", **merge(hands(left=(0.44, 0.40, 0.28), elbow_l=(-0.2, 1.0, -0.7)),
                                     wrist_l=(10.0, 0.0, 0.0)))
    d.key(0, hips_pitch=4.0, spine_bend=5.0, head_nod=3.0)
    d.overlay(groove(depth=0.012, per_beat=1, chest=0.8, nod=1.5, lag=0.2))
    d.follow("head_tilt", "spine_side", gain=0.4, hz=1.5)
    return d


DANCES = {
    "party_starter": party_starter,
    "prep_swing": prep_swing,
    "sidekick_pump": sidekick_pump,
    "hands_up": hands_up,
    "snap_groove": snap_groove,
    "clap_along": clap_along,
    "step_touch": step_touch,
    "shoulder_bounce": shoulder_bounce,
    "club_bounce": club_bounce,
    "hip_roll": hip_roll,
    "hula_hoop": hula_hoop,
    "slow_sway": slow_sway,
}
