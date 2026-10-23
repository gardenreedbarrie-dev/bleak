"""Street and hip-hop dances: b-boy toprock, popping, locking, krump, shuffle and party moves, choreographed for
Bleakhold."""

import math

from dflib import rig
from dflib.choreo import Dance

from moves import arms_fk, feet, groove, hands, hips, merge, ANKLE_Z


def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def ball(pitch):
    """Ankle height that keeps the ball of the foot on the ground with the heel up by `pitch` degrees."""
    a = math.radians(pitch)
    return 0.02 + 0.085 * math.cos(a) + 0.21 * math.sin(a)


def knee(yaw):
    """A knee pointing forward, turned `yaw` degrees to the left."""
    return (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0)


def mirrored(pose):
    """A pose mirrored left to right."""
    return dict(rig.mirror_control(k, v) for k, v in pose.items())


def calm(fn, windows, ramp=0.15):
    """An overlay that fades out inside the (start, end) beat windows: a freeze holds still."""
    def out(beat):
        m = 1.0
        for a, b in windows:
            if a - ramp < beat < b + ramp:
                m = min(m, max(0.0, (a - beat) / ramp, (beat - b) / ramp))
        return {k: tuple(x * m for x in v) if isinstance(v, tuple) else v * m for k, v in fn(beat).items()}
    return out


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)


def tut(side, elbow, fore):
    """An arm placed by where the upper arm and the forearm point (chest frame, given for the left side; the right
    is mirrored), so the forearms make exact lines and right angles."""
    sg = 1.0 if side == "l" else -1.0
    e = _unit((elbow[0], sg * elbow[1], elbow[2]))
    f = _unit((fore[0], sg * fore[1], fore[2]))
    sh = (0.0, sg * 0.25, 0.20)
    el = tuple(a + 0.355 * b for a, b in zip(sh, e))
    hand = tuple(a + 0.29 * b for a, b in zip(el, f))
    # the pole: the elbow's offset from the shoulder-to-hand line, which keeps the bend side steady in between
    reach = tuple(h - a for h, a in zip(hand, sh))
    k = sum(x * y for x, y in zip(e, reach)) / sum(x * x for x in reach)
    pole = _unit(tuple(x - k * y for x, y in zip(e, reach)))
    return {"hand_" + side: hand, "elbow_" + side: pole, "ik_" + side: 1.0}


def toprock():
    """B-boy toprock: the Indian step. The right foot crosses in front of the left while the arms swing open, steps
    back as the arms close across the chest, then the left; the second bar kicks out before each cross. Crouched,
    bouncing on every beat, the shoulders swaggering."""
    d = Dance(bpm=112, beats=8)
    home = 0.15
    # the right foot leads every pose; the left-foot moves are the mirror
    cross = {"foot_r": (0.22, 0.05, ball(12.0)), "foot_pitch_r": 12.0, "toe_r": 12.0, "foot_yaw_r": 16.0,
             "knee_r": knee(32.0)}
    back = {"foot_r": (0.0, -home, ANKLE_Z), "foot_pitch_r": 0.0, "toe_r": 0.0, "foot_yaw_r": -8.0,
            "knee_r": knee(-8.0)}
    kick = {"foot_r": (0.52, -0.10, 0.30), "foot_pitch_r": 25.0, "toe_r": 0.0, "foot_yaw_r": -4.0,
            "knee_r": (1.0, -0.1, 0.6)}
    open_up = merge(
        hips(x=0.04, y=0.03, z=-0.09, yaw=16.0, roll=-3.0), spine_bend=-2.0, spine_twist=-10.0, spine_side=-5.0,
        head_nod=-4.0, clav_up_l=8.0, clav_up_r=8.0, clav_fwd_l=-6.0, clav_fwd_r=-6.0,
        wrist_l=(-25.0, 0.0, 20.0), wrist_r=(-25.0, 0.0, 20.0),
        **hands((0.14, 0.60, 0.02), (0.18, -0.58, -0.02), (-0.4, 0.3, -1.0), (-0.4, -0.3, -1.0)))
    close = merge(
        hips(x=0.0, y=0.0, z=-0.15, yaw=-6.0, roll=0.0), spine_bend=22.0, spine_twist=6.0, spine_side=2.0,
        head_nod=-21.0, clav_up_l=0.0, clav_up_r=0.0, clav_fwd_l=12.0, clav_fwd_r=12.0,
        wrist_l=(20.0, 0.0, 0.0), wrist_r=(20.0, 0.0, 0.0),
        **hands((0.56, -0.06, 0.30), (0.52, 0.07, 0.20), (-0.2, 1.0, -0.6), (-0.2, -1.0, -0.6)))
    chamber = merge(
        hips(x=-0.05, y=0.02, z=-0.08, yaw=10.0, roll=2.0), spine_bend=-4.0, spine_twist=-14.0, spine_side=4.0,
        head_nod=2.0, clav_up_l=4.0, clav_up_r=0.0, clav_fwd_l=10.0, clav_fwd_r=-4.0,
        wrist_l=(10.0, 0.0, 0.0), wrist_r=(-10.0, 0.0, 0.0),
        **hands((0.50, 0.26, 0.04), (-0.04, -0.40, -0.24), (-0.6, 0.6, -0.6), (-0.6, -0.4, -0.8)))
    half_open = merge(open_up, wrist_l=(-10.0, 0.0, 10.0), wrist_r=(-10.0, 0.0, 10.0),
                      **hands((0.26, 0.52, 0.06), (0.28, -0.50, 0.02)))
    # (beat, right-leading?, foot pose, upper body, the foot's lift on the way)
    phrase = [
        (0.0, True, cross, open_up, 0.08), (1.0, True, back, close, 0.06),
        (2.0, False, cross, open_up, 0.08), (3.0, False, back, close, 0.06),
        (4.0, True, kick, chamber, 0.0), (4.5, True, cross, half_open, 0.04), (5.0, True, back, close, 0.06),
        (6.0, False, kick, chamber, 0.0), (6.5, False, cross, half_open, 0.04), (7.0, False, back, close, 0.06),
    ]
    for beat, right, foot, body, lift in phrase:
        f = foot if right else mirrored(foot)
        b = body if right else mirrored(body)
        moving = "foot_r" if right else "foot_l"
        d.key(beat, ease="inout", lift=lift, **{moving: f[moving]})
        d.key(beat, ease="inout", **{k: v for k, v in f.items() if k != moving})
        d.key(beat, ease="inout" if beat % 1.0 else "out", **b)
    # the standing foot stays planted at home while the other one works
    for beat, right in ((0.0, True), (1.0, True), (2.0, False), (3.0, False), (4.0, True), (4.5, True),
                        (5.0, True), (6.0, False), (6.5, False), (7.0, False)):
        rest = mirrored(back) if right else back
        d.key(beat, ease="inout", **rest)
    d.overlay(groove(depth=0.04, per_beat=1, chest=4.0, nod=5.0))
    d.follow("head_tilt", "spine_side", gain=0.5)
    d.follow("head_turn", "spine_twist", gain=0.4)
    return d


def _wave_bump(x, width):
    """1 at the crest of a travelling wave, falling smoothly to 0 at `width` either side."""
    if abs(x) >= width:
        return 0.0
    return math.cos(0.5 * math.pi * x / width) ** 2


def arm_wave():
    """The popping arm wave: arms out to the sides, palms down, a wave rolls in from the left fingertips through the
    wrist, the elbow and the shoulder, pops the chest, and runs out along the right arm to the right hand, then
    back. The head watches the wave go by and the knees bounce on every beat; the second bar rides higher."""
    d = Dance(bpm=100, beats=8)
    upper, fore, palm, clav = 0.355, 0.29, 0.12, 0.21
    # where each joint sits along the chain from the left fingertips (0) to the right fingertips (1)
    total = 2.0 * (palm + fore + upper + clav + 0.04)
    at_l = {"tip": 0.0, "wrist": palm, "elbow": palm + fore, "shoulder": palm + fore + upper}
    at_l = {k: v / total for k, v in at_l.items()}
    amp, width = 0.17, 0.14
    steps = 12
    for k in range(8 * steps):
        t = k / float(steps)
        q = (t % 2.0) / 2.0
        q = 0.5 * (q + q * q * (3.0 - 2.0 * q))
        p = q if int(t // 2.0) % 2 == 0 else 1.0 - q      # left to right, then back
        high = _ease(t - 3.5) - _ease(t - 7.0)            # the arms ride higher in the second bar
        pose = {}
        sh = {}
        for side in ("l", "r"):
            h = {j: amp * _wave_bump((s if side == "l" else 1.0 - s) - p, width) for j, s in at_l.items()}
            sh[side] = h["shoulder"]
            up = math.degrees(math.atan2(h["elbow"] - h["shoulder"], upper))
            fa = math.degrees(math.atan2(h["wrist"] - h["elbow"], fore))
            hand = math.degrees(math.atan2(h["tip"] - h["wrist"], palm))
            pose["arm_" + side] = (4.0, -4.0 + 14.0 * high + up, fa - up, -59.0)
            pose["ik_" + side] = 0.0
            pose["wrist_" + side] = (-(hand - fa), 0.0, -90.0)
            pose["clav_up_" + side] = math.degrees(math.asin(min(1.0, sh[side] / clav)))
        chest = _wave_bump(0.5 - p, width * 1.2)
        pose.update(hips(y=0.035 * (1.0 - 2.0 * p), z=-0.06 - 0.05 * high, roll=-3.0 * (1.0 - 2.0 * p)))
        pose["spine_bend"] = -8.0 * chest
        pose["spine_side"] = -60.0 * (sh["l"] - sh["r"])
        pose["head_turn"] = 32.0 * (1.0 - 2.0 * p)
        d.key(t, **pose)
    d.key(0, **feet(0.17))
    d.overlay(groove(depth=0.035, per_beat=1, chest=2.0, nod=3.0))
    d.follow("head_tilt", "spine_side", gain=0.6)
    d.follow("head_turn", "head_turn", gain=0.3)
    return d


def lock_it_up():
    """Locking: a big point to the right, then the left, the wrists roll round each other and the whole body locks
    in a freeze on the beat; a sudden knee drop, up into two claps, and a last lock with the wrists hanging. Every
    hit lands sharp and holds, the knees bounce in between."""
    d = Dance(bpm=108, beats=8)
    stance = feet(0.15)
    flat = {"foot_pitch_r": 0.0, "toe_r": 0.0, "foot_pitch_l": 0.0, "toe_l": 0.0}
    point_r = merge(
        hips(z=-0.07, yaw=-14.0, roll=3.0), spine_twist=-12.0, spine_side=-8.0, spine_bend=-2.0,
        head_turn=-28.0, head_nod=-6.0, clav_up_l=0.0, clav_up_r=6.0,
        wrist_l=(10.0, 0.0, 0.0), wrist_r=(-5.0, 0.0, 0.0),
        **hands((0.44, 0.16, 0.04), (0.30, -0.64, 0.56), (-0.3, 1.0, -0.6), (-0.6, -0.2, -1.0)))
    point_l = mirrored(point_r)
    lock = merge(
        hips(z=-0.13, yaw=0.0, roll=0.0), spine_twist=0.0, spine_side=0.0, spine_bend=-6.0,
        head_turn=0.0, head_nod=-8.0, clav_up_l=18.0, clav_up_r=18.0,
        wrist_l=(35.0, 0.0, 0.0), wrist_r=(35.0, 0.0, 0.0),
        **hands((0.36, 0.36, 0.20), (0.36, -0.36, 0.20), (-0.1, 1.0, -0.2), (-0.1, -1.0, -0.2)))
    drop = merge(
        hips(x=0.02, z=-0.29, yaw=8.0, roll=0.0, pitch=4.0), spine_twist=-4.0, spine_side=0.0, spine_bend=2.0,
        head_turn=0.0, head_nod=4.0, clav_up_l=0.0, clav_up_r=0.0,
        wrist_l=(-20.0, 0.0, 0.0), wrist_r=(-20.0, 0.0, 0.0),
        **hands((0.20, 0.56, -0.16), (0.20, -0.56, -0.16), (-0.3, 0.4, -1.0), (-0.3, -0.4, -1.0)))
    clap = merge(
        hips(x=0.0, z=-0.08, yaw=0.0, roll=0.0, pitch=0.0), spine_twist=0.0, spine_side=0.0, spine_bend=6.0,
        head_turn=0.0, head_nod=-4.0, clav_up_l=4.0, clav_up_r=4.0,
        wrist_l=(0.0, -15.0, 65.0), wrist_r=(0.0, -15.0, 65.0),
        **hands((0.47, 0.08, 0.07), (0.47, -0.08, 0.07), (-0.6, 0.4, -1.0), (-0.6, -0.4, -1.0)))
    apart = merge(clap, spine_bend=0.0, head_nod=-8.0,
                  **hands((0.30, 0.34, 0.22), (0.30, -0.34, 0.22), (-0.4, 0.8, -1.0), (-0.4, -0.8, -1.0)))
    hang = merge(
        hips(z=-0.10, yaw=-10.0, roll=0.0), spine_twist=8.0, spine_side=4.0, spine_bend=-4.0,
        head_turn=22.0, head_nod=-6.0, clav_up_l=14.0, clav_up_r=14.0,
        wrist_l=(65.0, 0.0, 0.0), wrist_r=(65.0, 0.0, 0.0),
        **hands((0.56, 0.24, 0.18), (0.56, -0.24, 0.18), (-0.4, 1.0, -0.6), (-0.4, -1.0, -0.6)))
    # the hits: snap into the pose on the beat, hold it
    for beat, pose, hold, ease in ((0.0, point_r, 0.4, "in"), (1.0, point_l, 0.15, "in"), (3.0, lock, 0.6, "in"),
                                   (4.0, drop, 0.5, "in"), (5.0, clap, 0.0, "in"), (6.0, clap, 0.0, "in"),
                                   (7.0, hang, 0.5, "in")):
        d.key(beat, ease=ease, **pose)
        if hold:
            d.key(beat + hold, ease="linear", **pose)
    d.key(5.5, ease="out", **apart)
    d.key(6.5, ease="out", **merge(apart, wrist_l=(30.0, 0.0, 20.0), wrist_r=(30.0, 0.0, 20.0)))
    # the wrist roll: the forearms circle round each other in front of the chest, two turns
    for k in range(11):
        t = 1.6 + k * 0.115
        a = 2.0 * math.pi * k / 5.0
        dx, dz = 0.09 * math.cos(a), 0.09 * math.sin(a)
        d.key(t, ease="smooth" if 0 < k < 10 else "inout", **merge(
            hips(z=-0.09, yaw=6.0 * math.sin(a), roll=0.0), spine_twist=-5.0 * math.sin(a), spine_side=0.0,
            spine_bend=4.0, head_turn=0.0, head_nod=2.0, clav_up_l=4.0, clav_up_r=4.0,
            wrist_l=(30.0 * math.sin(a), 0.0, 0.0), wrist_r=(-30.0 * math.sin(a), 0.0, 0.0),
            **hands((0.56 + dx, 0.10, 0.14 + dz), (0.56 - dx, -0.10, 0.14 - dz),
                    (-0.3, 1.0, -0.6), (-0.3, -1.0, -0.6))))
    # the feet stay put, except for the knee drop: the right foot steps back onto its toes
    d.key(0, ease="inout", **merge(stance, flat, knee_r=knee(-8.0)))
    d.key(3.6, ease="inout", **merge(stance, flat, knee_r=knee(-8.0)))
    d.key(4.0, ease="in", **{"foot_l": (0.16, 0.15, ANKLE_Z), "foot_r": (-0.30, -0.13, ball(45.0)),
                             "foot_pitch_r": 45.0, "toe_r": 45.0, "knee_r": (0.3, -0.1, -1.0)})
    d.key(4.5, ease="inout", **{"foot_l": (0.16, 0.15, ANKLE_Z), "foot_r": (-0.30, -0.13, ball(45.0)),
                                "foot_pitch_r": 45.0, "toe_r": 45.0, "knee_r": (0.3, -0.1, -1.0)})
    d.key(5.0, ease="out", **merge(stance, flat, knee_r=knee(-8.0)))
    bounce_ = groove(depth=0.035, per_beat=2, chest=2.0, nod=3.0)
    d.overlay(calm(bounce_, [(0.0, 0.4), (1.0, 1.15), (3.0, 3.6), (4.0, 4.5), (7.0, 7.5)]))
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def krump_stomp():
    """Krump: bent over and fierce, the feet stomp down hard on the beat, the chest pops, the fists jab and the arms
    swing big from behind and crash down across the body; a chest pop with the arms flung back, a double pop, and
    both fists hammer down with the last stomp."""
    d = Dance(bpm=96, beats=8)
    width = 0.18

    def plant(beat, side, ease="in"):
        sg = 1.0 if side == "l" else -1.0
        d.key(beat, ease=ease, **{"foot_" + side: (0.0, sg * width, ANKLE_Z), "foot_pitch_" + side: 0.0,
                                  "knee_" + side: knee(10.0 * sg)})

    def lift(beat, side):
        sg = 1.0 if side == "l" else -1.0
        d.key(beat, ease="out", **{"foot_" + side: (0.10, sg * (width + 0.02), 0.34), "foot_pitch_" + side: 12.0,
                                   "knee_" + side: (1.0, 0.3 * sg, 0.25)})

    # (side, lifted, slammed down)
    for side, up, down in (("r", 7.5, 0.0), ("l", 0.5, 1.0), ("r", 3.5, 4.0), ("l", 4.5, 5.0), ("l", 6.5, 7.0)):
        plant((up - 0.4) % 8.0, side, ease="inout")
        lift(up, side)
        plant(down, side)
    body = {"spine_bend": 20.0, "hips_pitch": 8.0, "head_nod": -16.0, "spine_twist": 0.0, "spine_side": 0.0,
            "head_turn": 0.0, "clav_fwd_l": 10.0, "clav_fwd_r": 10.0, "clav_up_l": 6.0, "clav_up_r": 6.0}
    fist = {"wrist_l": (15.0, 0.0, 0.0), "wrist_r": (15.0, 0.0, 0.0)}
    el_l, el_r = (-0.4, 1.0, -0.6), (-0.4, -1.0, -0.6)
    # stomp R / L: the arms swing down hard with the stomp, the chest pops
    stomp = merge(body, fist, hips(z=-0.16), spine_bend=26.0, head_nod=-26.0, clav_up_l=12.0, clav_up_r=12.0,
                  **hands((0.40, 0.40, -0.10), (0.40, -0.40, -0.10), (-0.1, 1.0, 0.0), (-0.1, -1.0, 0.0)))
    recoil = merge(body, fist, hips(z=-0.08), spine_bend=12.0, clav_up_l=14.0, clav_up_r=14.0,
                   **hands((0.34, 0.40, 0.04), (0.34, -0.40, 0.04), el_l, el_r))
    jab_r = merge(body, fist, hips(z=-0.12, yaw=18.0), spine_twist=22.0, spine_bend=16.0, head_turn=-14.0,
                  clav_fwd_r=22.0, clav_fwd_l=0.0,
                  **hands((0.44, 0.22, 0.24), (0.66, -0.14, 0.24), (-0.3, 1.0, -0.8), (-0.4, -0.3, -1.0)))
    jab_l = mirrored(jab_r)
    guard = merge(body, hips(z=-0.12, yaw=0.0), spine_twist=0.0, spine_bend=14.0, head_turn=0.0,
                  clav_fwd_l=6.0, clav_fwd_r=6.0, wrist_l=(-5.0, 0.0, 0.0), wrist_r=(-5.0, 0.0, 0.0),
                  **hands((0.28, 0.42, 0.06), (0.28, -0.42, 0.06), (-0.6, 0.7, -0.8), (-0.6, -0.7, -0.8)))
    pop_back = merge(body, hips(z=-0.10, pitch=2.0), spine_bend=-4.0, head_nod=-4.0, clav_fwd_l=-14.0,
                     clav_fwd_r=-14.0, clav_up_l=10.0, clav_up_r=10.0, wrist_l=(-30.0, 0.0, 0.0),
                     wrist_r=(-30.0, 0.0, 0.0),
                     **hands((-0.12, 0.58, 0.0), (-0.12, -0.58, 0.0), (-0.6, 0.3, -1.0), (-0.6, -0.3, -1.0)))
    wind_r = merge(body, fist, hips(z=-0.07, yaw=-16.0), spine_twist=-20.0, spine_bend=10.0, head_turn=10.0,
                   **hands((0.12, 0.50, -0.06), (-0.02, -0.52, 0.42), (-0.6, 0.5, -1.0), (-0.4, -1.0, -0.5)))
    crash_r = merge(body, fist, hips(z=-0.17, yaw=14.0), spine_twist=20.0, spine_bend=22.0, head_turn=-8.0,
                    head_nod=-24.0,
                    **hands((0.20, 0.42, -0.06), (0.46, -0.06, -0.30), el_l, (-0.3, -1.0, -0.5)))
    swing_mid_r = merge(wind_r, **hands(right=(0.40, -0.50, 0.12)))
    buck = merge(body, fist, hips(z=-0.12, yaw=0.0), spine_bend=14.0, clav_up_l=12.0, clav_up_r=12.0,
                 **hands((0.44, 0.34, -0.06), (0.44, -0.34, -0.06), (-0.2, 1.0, -0.4), (-0.2, -1.0, -0.4)))
    buck_pop = merge(buck, spine_bend=2.0, head_nod=-8.0, clav_fwd_l=-8.0, clav_fwd_r=-8.0, hips=(0.0, 0.0, -0.08))
    hammer = merge(body, hips(z=-0.20), spine_bend=18.0, head_nod=-22.0, clav_up_l=14.0, clav_up_r=14.0,
                   wrist_l=(30.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 0.0),
                   **hands((0.52, 0.20, -0.08), (0.52, -0.20, -0.08), (-0.2, 1.0, -0.2), (-0.2, -1.0, -0.2)))
    hammer_up = merge(hammer, hips(z=-0.07), spine_bend=4.0, head_nod=-12.0, clav_up_l=16.0, clav_up_r=16.0,
                      **hands((0.24, 0.40, 0.56), (0.24, -0.40, 0.56), (-0.4, 1.0, -0.4), (-0.4, -1.0, -0.4)))
    for beat, pose, ease in (
            (0.0, stomp, "in"), (0.5, recoil, "out"), (1.0, stomp, "in"), (1.5, recoil, "out"),
            (2.0, jab_r, "in"), (2.5, jab_l, "in"), (2.72, guard, "inout"), (3.0, pop_back, "in"),
            (3.15, pop_back, "linear"),
            (3.35, wind_r, "inout"), (3.68, swing_mid_r, "smooth"), (4.0, crash_r, "in"),
            (4.5, mirrored(swing_mid_r), "inout"), (5.0, mirrored(crash_r), "in"),
            (5.5, buck, "inout"), (6.0, buck_pop, "pop"), (6.2, buck, "inout"),
            (6.5, hammer_up, "out"), (7.0, hammer, "in"), (7.4, hammer, "linear"), (7.75, recoil, "inout")):
        d.key(beat, ease=ease, **pose)
    d.overlay(groove(depth=0.025, per_beat=1, chest=3.0, nod=3.0))
    d.follow("head_tilt", "spine_side", gain=0.5)
    d.follow("head_turn", "spine_twist", gain=0.4)
    return d


def neon_shuffle():
    """The electro shuffle: four running-man steps (a knee pops up while the standing foot slides back), then the
    T-step, the standing foot swivelling heel and toe to glide sideways while the free leg kicks out and in, to
    the right and back to the left. The fists pump up and down in front like a rave, fast."""
    d = Dance(bpm=128, beats=8)
    w = 0.13

    def foot(beat, side, x, y, z, ease="inout", pitch=0.0, yaw=None, kn=None):
        sg = 1.0 if side == "l" else -1.0
        c = {"foot_" + side: (x, y, z), "foot_pitch_" + side: pitch, "toe_" + side: max(0.0, pitch),
             "foot_yaw_" + side: 8.0 * sg if yaw is None else yaw, "knee_" + side: kn or knee(8.0 * sg)}
        d.key(beat, ease=ease, **c)

    def front(beat, side):
        foot(beat, side, 0.08, w if side == "l" else -w, ANKLE_Z, ease="in")

    def centre(beat, side):
        foot(beat, side, -0.04, w if side == "l" else -w, ANKLE_Z, ease="linear")

    def back(beat, side):
        foot(beat, side, -0.18, w if side == "l" else -w, ball(22.0), ease="linear", pitch=22.0)

    def knee_up(beat, side):
        sg = 1.0 if side == "l" else -1.0
        foot(beat, side, 0.06, sg * w, 0.32, ease="out", pitch=25.0, kn=(1.0, 0.1 * sg, 0.3))

    # running man: R in front and L behind on the count, the back knee pops up on the "and"
    for k in range(4):
        a, b = ("r", "l") if k % 2 == 0 else ("l", "r")
        front(float(k), a)
        back(float(k), b)
        knee_up(k + 0.5, b)
        centre(k + 0.5, a)
    # T-step: standing on the left foot, gliding right; then on the right foot, gliding left
    step = 0.05
    for part, (stand, free, y0, sg) in enumerate((("l", "r", w, -1.0), ("r", "l", -0.34, 1.0))):
        for k in range(4):
            t = 4.0 + 2.0 * part + 0.5 * k
            y = y0 + sg * step * k
            toe_out = k % 2 == 0
            yaw = (-35.0 if toe_out else 20.0) * (-sg)
            foot(t, stand, 0.0, y, ANKLE_Z, ease="inout", yaw=yaw)
            fy = y + sg * (0.44 if toe_out else 0.13)
            fz = 0.25 if toe_out else 0.34
            foot(t, free, 0.04 if toe_out else 0.02, fy, fz, ease="out" if toe_out else "inout",
                 pitch=10.0, yaw=55.0 * sg, kn=(0.5, 1.0 * sg, 0.15))
    for k in range(4):
        d.key(float(k), ease="in", **hips(x=-0.03, z=-0.10, pitch=6.0, roll=0.0))
        d.key(k + 0.5, ease="out", **hips(x=-0.03, z=-0.04, pitch=6.0, roll=0.0))
    for part, (y0, sg) in enumerate(((w - 0.07, -1.0), (-0.34 + 0.07, 1.0))):
        for k in range(4):
            t = 4.0 + 2.0 * part + 0.5 * k
            y = y0 + sg * step * k
            d.key(t, ease="inout", **hips(x=-0.02, y=y, z=-0.08 if k % 2 == 0 else -0.05, pitch=4.0,
                                          roll=4.0 * sg))
    # the arms: both fists pump down on the count during the running man, then piston in turn
    lo, hi = -0.10, 0.26
    for k in range(4):
        d.key(float(k), ease="in", **hands((0.48, 0.30, lo), (0.48, -0.30, lo), (-0.6, 0.5, -1.0),
                                           (-0.6, -0.5, -1.0)))
        d.key(k + 0.5, ease="out", **hands((0.46, 0.30, hi), (0.46, -0.30, hi)))
    for k in range(8):
        t = 4.0 + 0.5 * k
        up_l = k % 2 == 0
        d.key(t, ease="inout", **hands((0.47, 0.30, hi if up_l else lo), (0.47, -0.30, lo if up_l else hi)))
    d.key(0, wrist_l=(10.0, -15.0, 20.0), wrist_r=(10.0, -15.0, 20.0), spine_bend=8.0, head_nod=-6.0)
    d.overlay(groove(depth=0.0, per_beat=1, chest=3.0, nod=4.0))
    d.follow("spine_side", "hips_roll", gain=-0.6)
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def two_step():
    """The hip-hop two-step: step out to the right and bring the left foot in, then out to the left and bring the
    right in, the shoulders rocking with the weight, the arms swinging loose against the feet and the head nodding
    on every beat; in the second bar the body turns into the steps and the fingers snap on the close. Laid back."""
    d = Dance(bpm=92, beats=8)
    out_w, in_w = 0.21, -0.07
    moves = {"r": [(0.0, -out_w), (3.0, -in_w), (4.0, -out_w), (7.0, -in_w)],
             "l": [(1.0, in_w), (2.0, out_w), (5.0, in_w), (6.0, out_w)]}
    for side, steps in moves.items():
        sg = 1.0 if side == "l" else -1.0
        for i, (t, y) in enumerate(steps):
            closing = abs(y) < 0.1
            x = 0.03 if closing else 0.0
            d.key(t, ease="inout", lift=0.05, **{"foot_" + side: (x, y, ANKLE_Z)})
            d.key(t, ease="inout", **{"foot_yaw_" + side: (8.0 if closing else 14.0) * sg})
            nxt = steps[(i + 1) % len(steps)][0]
            hold = (nxt - 0.55) % 8.0
            d.key(hold, ease="linear", **{"foot_" + side: (x, y, ANKLE_Z)})
    # the weight goes with the step: right on 0-1, left on 2-3
    for bar in range(2):
        turn = 8.0 + 10.0 * bar
        for k, (hy, roll) in enumerate(((-0.08, 5.0), (-0.13, 7.0), (0.08, -5.0), (0.13, -7.0))):
            t = 4.0 * bar + k
            right = k < 2
            sg = -1.0 if right else 1.0
            d.key(t, ease="inout", **merge(
                hips(y=hy, z=-0.11 - 0.02 * bar, roll=roll, yaw=turn * sg),
                spine_side=-roll * 1.9, spine_twist=-turn * sg * 0.4 + 12.0 * sg))
    swing_f, swing_b, hang = (74.0, -46.0, 52.0, 0.0), (-44.0, -64.0, 18.0, 0.0), (10.0, -76.0, 20.0, 0.0)
    for bar in range(2):
        big = 1.0 + 0.2 * bar
        for k in range(4):
            t = 4.0 * bar + k
            right = k < 2              # weight right: the left arm swings forward
            f = (swing_f[0] * big, swing_f[1], swing_f[2] * big, 0.0)
            b = (swing_b[0] * big, swing_b[1], swing_b[2], 0.0)
            arm_l, arm_r = (f, b) if right else (b, f)
            if k % 2 == 1:             # on the close the swing settles a little
                arm_l = tuple(0.7 * a + 0.3 * h for a, h in zip(arm_l, hang))
                arm_r = tuple(0.7 * a + 0.3 * h for a, h in zip(arm_r, hang))
            snap = bar == 1 and k % 2 == 1
            d.key(t, ease="out", **merge(arms_fk(arm_l, arm_r),
                                         wrist_l=(35.0 if snap else 10.0, 0.0, -35.0),
                                         wrist_r=(35.0 if snap else 10.0, 0.0, -35.0),
                                         clav_up_l=10.0 if not right else 0.0, clav_up_r=10.0 if right else 0.0))
            d.key(t + 0.5, ease="inout", **{"wrist_l": (-10.0, 0.0, -35.0), "wrist_r": (-10.0, 0.0, -35.0)})
    d.key(0, spine_bend=2.0)
    d.overlay(groove(depth=0.055, per_beat=1, chest=3.5, nod=8.0, lag=0.15))
    d.follow("head_tilt", "spine_side", gain=0.5)
    d.follow("head_turn", "spine_twist", gain=0.4)
    return d


def heel_toe():
    """The shuffle heel-toe: hopping from foot to foot, the free foot taps its heel out in front on the count and
    its toe behind on the "and", right then left; the second bar taps the toe out to the side with the knee turned
    in. The hips bounce on every half beat and the bent arms pump, the eyes on the feet."""
    d = Dance(bpm=124, beats=8)
    w = 0.12

    def put(beat, side, where, ease):
        sg = 1.0 if side == "l" else -1.0
        if where == "stand":
            c = {"foot_" + side: (0.0, sg * w, ANKLE_Z), "foot_pitch_" + side: 0.0, "toe_" + side: 0.0,
                 "foot_yaw_" + side: 8.0 * sg, "knee_" + side: knee(8.0 * sg)}
        elif where == "heel":
            c = {"foot_" + side: (0.24, sg * (w - 0.02), 0.12), "foot_pitch_" + side: -28.0, "toe_" + side: 0.0,
                 "foot_yaw_" + side: 14.0 * sg, "knee_" + side: knee(10.0 * sg)}
        elif where == "behind":
            c = {"foot_" + side: (-0.17, sg * (w + 0.05), ball(45.0) + 0.01), "foot_pitch_" + side: 45.0,
                 "toe_" + side: 20.0, "foot_yaw_" + side: 8.0 * sg, "knee_" + side: knee(8.0 * sg)}
        else:  # out to the side, the knee and toes turned in
            c = {"foot_" + side: (0.03, sg * (w + 0.20), ball(40.0) + 0.01), "foot_pitch_" + side: 40.0,
                 "toe_" + side: 18.0, "foot_yaw_" + side: -22.0 * sg, "knee_" + side: knee(-35.0 * sg)}
        d.key(beat, ease=ease, **c)

    for k in range(8):
        t = float(k)
        tap, stand = ("r", "l") if k % 2 == 0 else ("l", "r")
        second = "behind" if k < 4 else "out"
        put(t, tap, "heel", "out")
        put(t + 0.5, tap, second, "inout")
        put(t, stand, "stand", "in")
        put(t + 0.5, stand, "stand", "linear")
        sg = 1.0 if stand == "l" else -1.0
        # the weight sits over the standing foot, a little hop between counts
        d.key(t, ease="in", **hips(x=-0.02, y=0.035 * sg, z=-0.10, roll=-3.0 * sg, yaw=-6.0 * sg))
        d.key(t + 0.5, ease="out", **hips(x=-0.03, y=0.03 * sg, z=-0.06, roll=-2.0 * sg, yaw=-3.0 * sg))
        d.key(t + 0.75, ease="out", **hips(x=-0.03, y=0.0, z=-0.04, roll=0.0, yaw=0.0))
        if k < 4:
            # bent arms pump forward and back against the feet
            fwd, bck = (0.42, 0.26, 0.06), (0.02, 0.32, -0.18)
            arm_l = fwd if tap == "r" else bck
            arm_r = bck if tap == "r" else fwd
            d.key(t, ease="out", **hands(arm_l, (arm_r[0], -arm_r[1], arm_r[2]),
                                         (-1.0, 0.4, -0.4), (-1.0, -0.4, -0.4)))
            d.key(t + 0.5, ease="inout", **hands((0.24, 0.30, -0.06), (0.24, -0.30, -0.06)))
        else:
            # both fists punch down on the count, come up on the "and"
            d.key(t, ease="in", **hands((0.44, 0.27, -0.12), (0.44, -0.27, -0.12), (-0.8, 0.6, -0.6),
                                        (-0.8, -0.6, -0.6)))
            d.key(t + 0.5, ease="out", **hands((0.44, 0.27, 0.14), (0.44, -0.27, 0.14)))
    d.key(0, wrist_l=(15.0, 0.0, -20.0), wrist_r=(15.0, 0.0, -20.0), spine_bend=12.0, head_nod=8.0)
    d.overlay(groove(depth=0.0, per_beat=2, chest=2.0, nod=3.0))
    d.follow("spine_side", "hips_roll", gain=-0.8)
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def moon_glide():
    """The backslide, on the spot: one foot up on its toes with the knee bent like a walking step while the other
    slides back flat along the floor, then the heels swap and the other foot slides; the feet scissor under a
    level body so it looks like walking forward while gliding back. The arms swing like a walk, the head stays
    level; the second bar leans into it with bigger swings."""
    d = Dance(bpm=104, beats=8)
    reach, w = 0.18, 0.10
    toe_up = 52.0

    def flat(beat, side, x, ease):
        sg = 1.0 if side == "l" else -1.0
        d.key(beat, ease=ease, **{"foot_" + side: (x, sg * w, ANKLE_Z), "foot_pitch_" + side: 0.0,
                                  "toe_" + side: 0.0, "knee_" + side: knee(6.0 * sg)})

    def toes(beat, side, x, ease):
        sg = 1.0 if side == "l" else -1.0
        d.key(beat, ease=ease, **{"foot_" + side: (x, sg * w, ball(toe_up)), "foot_pitch_" + side: toe_up,
                                  "toe_" + side: toe_up, "knee_" + side: knee(4.0 * sg)})

    for k in range(8):
        t = float(k)
        slide, glide = ("l", "r") if k % 2 == 0 else ("r", "l")
        # on the count the front foot drops its heel and the back foot pops onto its toes
        flat(t, slide, reach, "inout")
        toes(t, glide, -reach, "inout")
        # then the flat foot slides back while the toes glide forward under the body
        flat(t + 0.78, slide, -reach, "inout")
        toes(t + 0.78, glide, reach, "inout")
        lean = 1.0 if k >= 4 else 0.0
        sg = 1.0 if slide == "l" else -1.0
        d.key(t, ease="inout", **merge(
            hips(x=0.0, y=0.025 * sg, z=-0.11 - 0.02 * lean, yaw=7.0 * sg, roll=-2.0 * sg),
            spine_twist=-9.0 * sg, spine_bend=6.0 + 6.0 * lean, head_nod=-5.0 - 6.0 * lean, head_turn=4.0 * sg))
        big = 1.0 + 0.4 * lean
        fwd, bck = (44.0 * big, -68.0 + 6.0 * lean, 30.0 * big, 0.0), (-34.0 * big, -72.0, 10.0, 0.0)
        # the toes come forward like a step: the opposite arm swings forward with them
        arm_l, arm_r = (fwd, bck) if glide == "r" else (bck, fwd)
        d.key(t + 0.78, ease="inout", **merge(arms_fk(arm_l, arm_r), wrist_l=(10.0, 0.0, -20.0),
                                              wrist_r=(10.0, 0.0, -20.0)))
    d.overlay(groove(depth=0.015, per_beat=1, chest=1.0, nod=1.5))
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def dab_drop():
    """The dab: on the beat the head ducks into the crook of the bent left arm while the right arm shoots up and
    out, then the other way, with a loose bounce in between; the second bar dabs on every beat and the last one
    drops low into the knees before bouncing back up."""
    d = Dance(bpm=100, beats=8)
    dab_r = merge(
        hips(z=-0.13, yaw=-8.0, roll=2.0), spine_side=-10.0, spine_twist=-10.0, spine_bend=8.0,
        head_nod=20.0, head_turn=-28.0, head_tilt=-12.0, clav_up_l=8.0, clav_up_r=10.0,
        wrist_l=(0.0, 0.0, 0.0), wrist_r=(-10.0, 0.0, 0.0),
        **hands((0.48, -0.30, 0.38), (0.22, -0.68, 0.52), (0.4, 1.0, 0.6), (-0.3, -0.2, -1.0)))
    dab_l = mirrored(dab_r)
    drop_r = merge(dab_r, hips(z=-0.26, yaw=-10.0, roll=2.0, pitch=6.0), spine_bend=12.0)
    loose = merge(
        hips(z=-0.07, yaw=0.0, roll=0.0, pitch=0.0), spine_side=0.0, spine_twist=0.0, spine_bend=4.0,
        head_nod=0.0, head_turn=0.0, head_tilt=0.0, clav_up_l=6.0, clav_up_r=6.0,
        wrist_l=(20.0, 0.0, -20.0), wrist_r=(20.0, 0.0, -20.0),
        **hands((0.30, 0.32, -0.16), (0.30, -0.32, -0.16), (-0.5, 1.0, -0.4), (-0.5, -1.0, -0.4)))
    loose_r = merge(loose, hips(z=-0.07, yaw=8.0, roll=-3.0), spine_twist=8.0, spine_side=4.0, head_turn=10.0,
                    **hands((0.36, 0.26, -0.10), (0.18, -0.36, -0.20)))
    loose_l = mirrored(loose_r)
    open_ = merge(loose, hips(z=-0.06), clav_up_l=12.0, clav_up_r=12.0, wrist_l=(-5.0, 0.0, 0.0),
                  wrist_r=(-5.0, 0.0, 0.0),
                  **hands((0.30, 0.44, 0.10), (0.30, -0.44, 0.10), (0.05, 1.0, -0.15), (0.05, -1.0, -0.15)))
    for beat, pose, ease in (
            (0.0, dab_r, "in"), (0.45, dab_r, "linear"), (1.0, loose_l, "inout"), (1.5, loose, "inout"),
            (2.0, dab_l, "in"), (2.45, dab_l, "linear"), (3.0, loose_r, "inout"), (3.5, loose, "inout"),
            (4.0, dab_r, "in"), (4.3, dab_r, "linear"), (4.65, open_, "inout"),
            (5.0, dab_l, "in"), (5.3, dab_l, "linear"), (5.65, open_, "inout"),
            (6.0, drop_r, "in"), (6.5, drop_r, "linear"), (7.0, loose_l, "inout"), (7.5, loose, "inout")):
        d.key(beat, ease=ease, **pose)
    d.key(0, **feet(0.16))
    holds = [(0.0, 0.45), (2.0, 2.45), (4.0, 4.3), (5.0, 5.3), (6.0, 6.5)]
    d.overlay(calm(groove(depth=0.04, per_beat=2, chest=3.0, nod=4.0), holds, ramp=0.12))
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def _hit(beat, rise=0.08, decay=0.22):
    """0..1 muscle pop on every beat: tightens in a couple of frames up to the count, then lets go."""
    ph = beat - math.floor(beat + rise)
    if ph < 0.0:
        u = 1.0 + ph / rise
        return u * u * (3.0 - 2.0 * u)
    return math.exp(-ph / decay)


def pop_circuit():
    """Popping: every beat a hit tightens the chest, the shoulders and the neck, and the arms land in a new angular
    shape (goal posts, a marionette, an arm out with a forearm across and back, a stacked box, a zombie reach, an
    L, a diagonal line), gliding smoothly from one to the next while the chest and the head isolate side to
    side."""
    d = Dance(bpm=104, beats=8)
    out_l, out_r, up_l, up_r = (0.0, 1.0, -0.6), (0.0, -1.0, -0.6), (0.0, 1.0, 0.8), (0.0, -1.0, 0.8)
    back_l, back_r = (-1.0, 0.3, -0.4), (-1.0, -0.3, -0.4)
    shapes = [
        # (left hand, right hand, left elbow, right elbow, chest side, head turn, head tilt)
        ((0.04, 0.60, 0.50), (0.04, -0.60, 0.50), out_l, out_r, 0.0, 0.0, 0.0),
        ((0.54, -0.04, 0.20), (0.06, -0.84, 0.20), (0.0, 1.0, -0.2), back_r, -8.0, -28.0, 0.0),
        ((0.06, 0.84, 0.20), (0.54, 0.04, 0.20), back_l, (0.0, -1.0, -0.2), 8.0, 28.0, 0.0),
        ((0.54, -0.14, 0.32), (0.54, 0.14, 0.14), (0.0, 1.0, -0.2), (0.0, -1.0, -0.2), 0.0, 0.0, 10.0),
        ((0.16, 0.54, -0.30), (0.16, -0.58, 0.58), back_l, back_r, -10.0, -20.0, -10.0),
        ((0.60, 0.22, 0.18), (0.60, -0.22, 0.18), (-0.3, 1.0, -0.8), (-0.3, -1.0, -0.8), 0.0, 0.0, 0.0),
        ((0.04, 0.60, -0.08), (0.04, -0.60, 0.50), up_l, out_r, 8.0, 22.0, 8.0),
        ((0.26, 0.46, -0.04), (0.26, -0.46, -0.04), up_l, up_r, 0.0, 0.0, -6.0),
    ]
    wrists = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-10.0, 0.0, 0.0),
              (70.0, 0.0, 0.0), (0.0, 0.0, 0.0), (60.0, 0.0, 0.0)]
    order = [0, 7, 1, 2, 3, 5, 6, 4]     # each change keeps the hands clear of the face and of each other
    for k, i in enumerate(order):
        hl, hr, el, er, side, turn, tilt = shapes[i]
        w = wrists[i]
        d.key(float(k), ease="inout", **merge(
            hands(hl, hr, el, er), wrist_l=w, wrist_r=w, spine_side=side, head_turn=turn,
            head_tilt=tilt - side * 0.6, hips=(0.0, -0.012 * side, -0.07 if k % 2 == 0 else -0.10),
            hips_roll=0.3 * side))
    d.key(0, **feet(0.16))

    def pops(beat):
        h = _hit(beat)
        late = _hit(beat - 0.06)
        return {"spine_bend": -5.0 * h, "clav_up_l": 7.0 * h, "clav_up_r": 7.0 * h, "head_nod": -5.0 * late,
                "hips": (0.0, 0.0, -0.025 * h)}
    d.overlay(pops)
    return d


def tut_box():
    """Tutting: the forearms and hands build right-angled shapes in front of the chest and face, a new one on every
    beat, each forearm swinging one clean quarter round its elbow: a zigzag, an arm out over a forearm across, a
    stacked shelf, an L, the arms opening out one and then the other. The head follows each frame and the feet tap
    lightly from side to side."""
    d = Dance(bpm=104, beats=8)
    hi, top, mid, lo = (0.75, 0.68, 0.05), (1.0, 0.4, 0.12), (1.0, 0.38, -0.25), (0.85, 0.55, 0.35)
    up, down, across, out = (0.3, 0.22, 1.0), (0.3, 0.0, -1.0), (0.45, -1.0, 0.0), (0.3, 1.0, 0.0)
    # each forearm turns one quarter at most per beat, and only between up and out, out and down, down and across,
    # so a hand never sweeps across the face
    shapes = [
        # (left elbow, left forearm, right elbow, right forearm, head turn, head tilt)
        (hi, up, lo, down, 12.0, 6.0),
        (hi, out, mid, across, -10.0, -4.0),
        (lo, down, mid, across, 8.0, 6.0),
        (top, across, mid, across, 0.0, -8.0),
        (top, across, lo, down, -14.0, 4.0),
        (lo, down, hi, out, 16.0, -6.0),
        (hi, out, hi, up, -12.0, -6.0),
        (hi, up, hi, out, 18.0, 6.0),
    ]

    def arms(shape, prev=None):
        """The arms of a shape, or half way to it from prev: the forearms swing round the elbows, they do not cut
        across."""
        el, fl, er, fr = shape[:4]
        if prev is not None:
            el, fl, er, fr = (_unit(tuple(a + b for a, b in zip(u, v))) for u, v in zip(shape[:4], prev[:4]))
        return merge(tut("l", el, fl), tut("r", er, fr))

    tick = 0.34
    for k, shape in enumerate(shapes):
        prev = shapes[k - 1]
        t = float(k)
        d.key((t - tick) % 8.0, ease="linear", **arms(prev))
        d.key(t - tick / 2.0 if k else 8.0 - tick / 2.0, ease="in", **arms(shape, prev))
        d.key(t, ease="out", **arms(shape))
        d.key(t, ease="snap", head_turn=shape[4], head_tilt=shape[5])
    d.key(0, clav_fwd_l=10.0, clav_fwd_r=10.0)
    # light feet: the weight rocks side to side and the free heel lifts on every beat
    for k in range(8):
        t = float(k)
        free, sg = ("l", 1.0) if k % 2 == 0 else ("r", -1.0)
        stand = "r" if free == "l" else "l"
        d.key(t, ease="inout", **{"foot_pitch_" + free: 30.0, "toe_" + free: 30.0,
                                  "foot_" + free: (0.04, sg * 0.14, ball(30.0)),
                                  "foot_pitch_" + stand: 0.0, "toe_" + stand: 0.0,
                                  "foot_" + stand: (0.0, -sg * 0.14, ANKLE_Z)})
        d.key(t, ease="inout", **hips(y=-0.035 * sg, z=-0.08, roll=3.0 * sg, yaw=4.0 * sg))
    d.key(0, spine_bend=4.0)
    d.overlay(groove(depth=0.025, per_beat=1, chest=1.5, nod=2.0))
    d.follow("spine_side", "hips_roll", gain=-0.5)
    return d


def freeze_frame():
    """Bounce, bounce, freeze: two loose bouncing beats and then a hard hit into a cool pose, held dead still for two
    beats. Four different freezes: a fist up by the face with the other arm across, arms folded leaning back on a
    heel, a point straight out with a hand on the hip, and a low crouch with a fist up."""
    d = Dance(bpm=128, beats=16)
    w = 0.14
    flat_feet = {"foot_pitch_l": 0.0, "foot_pitch_r": 0.0, "toe_l": 0.0, "toe_r": 0.0,
                 "knee_l": knee(8.0), "knee_r": knee(-8.0)}
    loose = merge(
        hips(x=0.0, y=0.0, z=-0.07, yaw=0.0, roll=0.0, pitch=0.0), spine_bend=6.0, spine_twist=0.0, spine_side=0.0,
        head_nod=0.0, head_turn=0.0, head_tilt=0.0, clav_up_l=4.0, clav_up_r=4.0,
        wrist_l=(15.0, 0.0, -20.0), wrist_r=(15.0, 0.0, -20.0),
        **hands((0.24, 0.32, -0.22), (0.24, -0.32, -0.22), (-0.6, 0.8, -0.6), (-0.6, -0.8, -0.6)))
    freezes = [
        # a fist up by the face, the other forearm across, turned away and looking back over the shoulder
        (merge(hips(x=0.0, y=0.02, z=-0.09, yaw=16.0, roll=-3.0), spine_bend=-4.0, spine_twist=6.0,
               spine_side=-4.0, head_nod=-6.0, head_turn=-22.0, head_tilt=8.0, clav_up_l=0.0, clav_up_r=10.0,
               wrist_l=(10.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 60.0),
               **hands((0.46, -0.04, -0.04), (0.28, -0.52, 0.32), (-0.2, 1.0, -0.3), (0.0, -0.6, -1.0))),
         merge(feet(w, x_l=0.10, x_r=-0.08), flat_feet)),
        # arms folded high, leaning back, the right heel out in front with the toes up
        (merge(hips(x=0.03, y=-0.02, z=-0.10, yaw=-14.0, roll=2.0), spine_bend=-8.0, spine_twist=-6.0,
               spine_side=3.0, head_nod=-14.0, head_turn=10.0, head_tilt=-6.0, clav_up_l=8.0, clav_up_r=8.0,
               wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0),
               **hands((0.47, -0.20, 0.18), (0.43, 0.20, 0.06), (-0.2, 1.0, -0.6), (-0.2, -1.0, -0.6))),
         merge(feet(w, x_r=0.22, z_r=0.12), flat_feet, foot_pitch_r=-25.0)),
        # a point straight out at the crowd, the other hand on the hip, the hips popped to the side
        (merge(hips(x=0.0, y=0.07, z=-0.08, yaw=-10.0, roll=-8.0), spine_bend=2.0, spine_twist=-8.0,
               spine_side=10.0, head_nod=-4.0, head_turn=-6.0, head_tilt=-10.0, clav_up_l=12.0, clav_up_r=4.0,
               wrist_l=(30.0, 0.0, -40.0), wrist_r=(-8.0, 0.0, 0.0),
               **hands((0.06, 0.40, -0.24), (0.62, -0.20, 0.26), (-0.4, 1.0, 0.1), (-0.4, -0.4, -1.0))),
         merge(feet(w + 0.04), flat_feet)),
        # low crouch, knees wide, a fist up by the shoulder and the other forearm on the knee, eyes up
        (merge(hips(x=-0.03, y=0.0, z=-0.27, yaw=8.0, roll=0.0, pitch=10.0), spine_bend=18.0, spine_twist=-6.0,
               spine_side=0.0, head_nod=-32.0, head_turn=-8.0, head_tilt=4.0, clav_up_l=6.0, clav_up_r=12.0,
               wrist_l=(20.0, 0.0, 0.0), wrist_r=(20.0, 0.0, 60.0),
               **hands((0.40, 0.30, -0.26), (0.30, -0.44, 0.28), (-0.2, 1.0, -0.2), (-0.2, -0.6, -1.0))),
         merge(feet(w + 0.08), flat_feet, knee_l=knee(30.0), knee_r=knee(-30.0))),
    ]
    for i, (body, legs) in enumerate(freezes):
        u = 4.0 * i
        rock = 1.0 if i % 2 == 0 else -1.0
        # two loose bounces, rocking side to side, then a little dip before the hit
        d.key(u, ease="out", **merge(loose, hips(y=0.03 * rock, z=-0.08, roll=-3.0 * rock), spine_side=4.0 * rock,
                                     head_tilt=3.0 * rock))
        d.key(u + 1.0, ease="inout", **merge(loose, hips(y=-0.03 * rock, z=-0.08, roll=3.0 * rock),
                                             spine_side=-4.0 * rock, head_tilt=-3.0 * rock))
        d.key(u + 1.5, ease="inout", **merge(loose, hips(y=0.0, z=-0.12), spine_bend=12.0, clav_up_l=10.0,
                                             clav_up_r=10.0))
        d.key(u + 2.0, ease="in", **body)
        d.key(u + 3.4, ease="linear", **body)
        d.key(u, ease="inout", **merge(feet(w), flat_feet))
        d.key(u + 1.5, ease="inout", **merge(feet(w), flat_feet))
        d.key(u + 2.0, ease="in", **legs)
        d.key(u + 3.4, ease="linear", **legs)
    d.overlay(calm(groove(depth=0.05, per_beat=1, chest=3.0, nod=6.0), [(4.0 * i + 2.0, 4.0 * i + 3.4)
                                                                         for i in range(4)], ramp=0.2))
    d.follow("head_tilt", "spine_side", gain=0.3)
    return d


def arm_roll():
    """The wop-style arm roll: the forearms roll forward in circles in front of the body, one arm after the other,
    each shoulder bobbing up as its hand comes over the top, the head nodding and the weight rocking from foot to
    foot. In the second bar the arms fall into step and roll together while the body pumps with them. Loose and
    funky."""
    d = Dance(bpm=100, beats=8)
    steps = 8
    rx, rz, cx, cz = 0.16, 0.14, 0.50, 0.08
    for k in range(8 * steps + 1):
        t = k / float(steps)
        if t >= 8.0:
            break
        # the right arm runs half a turn behind in the first bar, catches up for the second and drops back again
        # over the last beat
        lag = math.pi * (1.0 - _ease(t - 3.0) + _ease(t - 7.0))
        a_l = 2.0 * math.pi * t
        a_r = a_l - lag
        pose = {}
        for side, a, sg in (("l", a_l, 1.0), ("r", a_r, -1.0)):
            x, z = cx - rx * math.cos(a), cz + rz * math.sin(a)
            pose.update(hands(**{"left" if side == "l" else "right": (x, sg * 0.30, z)}))
            pose["elbow_" + side] = (-0.6, sg * 1.0, -0.5)
            pose["clav_up_" + side] = 5.0 + 7.0 * math.sin(a)
            pose["clav_fwd_" + side] = 6.0 - 6.0 * math.cos(a)
            pose["wrist_" + side] = (10.0 - 25.0 * math.sin(a + 0.6), 0.0, -30.0)
        together = 1.0 - lag / math.pi
        pump = math.sin(a_l)
        sway_ = math.sin(math.pi * t)
        pose.update(hips(y=0.045 * sway_, z=-0.09, roll=-4.0 * sway_, pitch=4.0 - 3.0 * together * pump))
        pose["spine_side"] = 5.0 * sway_
        pose["spine_bend"] = 10.0 - 7.0 * together * pump
        pose["head_nod"] = 4.0 * together * pump
        pose["spine_twist"] = 6.0 * math.sin(a_l) * (1.0 - together)
        d.key(t, ease="smooth", **pose)
    d.key(0, **feet(0.17))
    d.overlay(groove(depth=0.04, per_beat=1, chest=2.5, nod=6.0, lag=0.15))
    d.follow("head_tilt", "spine_side", gain=0.5)
    d.follow("head_turn", "spine_twist", gain=0.5)
    return d


DANCES = {
    "toprock": toprock,
    "arm_wave": arm_wave,
    "lock_it_up": lock_it_up,
    "krump_stomp": krump_stomp,
    "neon_shuffle": neon_shuffle,
    "two_step": two_step,
    "heel_toe": heel_toe,
    "moon_glide": moon_glide,
    "dab_drop": dab_drop,
    "pop_circuit": pop_circuit,
    "tut_box": tut_box,
    "freeze_frame": freeze_frame,
    "arm_roll": arm_roll,
}
