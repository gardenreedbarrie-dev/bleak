"""Classic, ballroom, folk and retro dances: the steps of the dance halls, choreographed for Bleakhold."""

import math

from dflib.choreo import Dance

from moves import arms_fk, feet, groove, hands, hips, merge, sway, STANCE, ANKLE_Z

# The foot from the ankle to the ball (the toe joint): its length and how far it points down at rest.
_FOOT = math.hypot(0.21, 0.085)
_FOOT_DOWN = math.degrees(math.atan2(0.085, 0.21))
_BALL = 0.21


def _yaw(deg, down=0.0):
    """Unit direction on the ground turned `deg` to the left (knee directions), tipped `down` downwards."""
    r = math.radians(deg)
    return (math.cos(r), math.sin(r), -down)


def _ball_z(pitch):
    """Ankle height with the ball of the foot on the ground and the heel raised `pitch` degrees."""
    return 0.02 + _FOOT * math.sin(math.radians(_FOOT_DOWN + pitch))


def _peel(pitch):
    """How far forward the ankle moves when the heel peels up `pitch` degrees with the ball staying put."""
    return _BALL - _FOOT * math.cos(math.radians(_FOOT_DOWN + pitch))


def _swivel(x, y, yaw):
    """Ankle position of a foot turned `yaw` degrees about its ball, the ball staying where it is at yaw 0."""
    r = math.radians(yaw)
    return (x + _BALL - _BALL * math.cos(r), y - _BALL * math.sin(r), ANKLE_Z)


def _m(side):
    """+1 for the left side, -1 for the right."""
    return 1.0 if side == "l" else -1.0


def _other(side):
    return "r" if side == "l" else "l"


def _hip_hand(side):
    """The hand resting on the hip, the elbow out to the side."""
    m = _m(side)
    return {"ik_" + side: 1.0, "hand_" + side: (-0.05, 0.34 * m, -0.31), "elbow_" + side: (-0.4, m, 0.1),
            "wrist_" + side: (30.0, 0.0, 70.0)}


def charleston():
    """The Charleston: step forward, kick forward, step back, tap back, the planted foot swivelling heels in and
    out and the knees knocking, the arms swinging in opposition with flat hands; the second bar kicks forward and
    back with the arms flung wider."""
    d = Dance(bpm=150, beats=8)
    w = 0.10
    for bar in range(2):
        b0 = bar * 4.0
        big = bar == 1
        # 1: the left foot steps in front, toes out, the heels swivelling in
        d.key(b0, ease="inout", lift=0.06, **{
            "foot_l": _swivel(0.07, w, 22.0), "foot_yaw_l": 30.0, "knee_l": _yaw(30.0), "foot_pitch_l": 0.0,
            "toe_l": 0.0})
        d.key(b0, ease="inout", **{"foot_r": _swivel(-0.08, -w, 20.0), "foot_yaw_r": 12.0, "knee_r": _yaw(-6.0),
                                   "foot_pitch_r": 0.0, "toe_r": 0.0})
        # 2: the right foot kicks forward, the left swivels toes in, the knees knock
        kick = (0.84, -w + 0.01, 0.68) if big else (0.80, -w + 0.01, 0.56)
        d.key(b0 + 1.0, ease="out", **{"foot_r": kick, "foot_yaw_r": -10.0, "knee_r": (0.3, 0.0, 1.0),
                                         "foot_pitch_r": 25.0, "toe_r": -10.0})
        d.key(b0 + 1.0, ease="inout", **{"foot_l": _swivel(0.07, w, -22.0), "foot_yaw_l": -14.0,
                                         "knee_l": _yaw(-30.0), "foot_pitch_l": 0.0, "toe_l": 0.0})
        # 3: the right foot steps back, toes out
        d.key(b0 + 2.0, ease="in", **{"foot_r": _swivel(-0.08, -w, -22.0), "foot_yaw_r": -30.0,
                                       "knee_r": _yaw(-30.0), "foot_pitch_r": 0.0, "toe_r": 0.0})
        # the planted foot stays flat until it leaves for the tap or kick behind
        d.key(b0 + 2.0, ease="inout", **{"foot_l": _swivel(0.07, w, 20.0), "foot_yaw_l": 12.0, "knee_l": _yaw(6.0),
                                         "foot_pitch_l": 0.0, "toe_l": 0.0})
        # 4: the left foot taps back (or kicks up behind in the second bar), the right swivels toes in
        if big:
            d.key(b0 + 3.0, ease="out", lift=0.04, **{"foot_l": (-0.30, w, 0.36), "foot_yaw_l": 10.0,
                                                      "knee_l": (0.6, 0.1, -1.0), "foot_pitch_l": 45.0,
                                                      "toe_l": -10.0})
        else:
            d.key(b0 + 3.0, ease="out", lift=0.06, **{"foot_l": (-0.30, w, _ball_z(32.0)), "foot_yaw_l": 10.0,
                                                      "knee_l": _yaw(5.0), "foot_pitch_l": 32.0, "toe_l": 32.0})
        d.key(b0 + 3.0, ease="inout", **{"foot_r": _swivel(-0.08, -w, 22.0), "foot_yaw_r": 14.0,
                                         "knee_r": _yaw(30.0)})
        # the body rocks over the feet: back on the forward kick, forward on the back kick
        for k in range(4):
            b = b0 + k
            fwd = k % 2 == 0           # the right arm swings forward on the steps, the left on the kicks
            s = 1.0 if fwd else -1.0
            hx = (0.05, -0.02, -0.05, -0.02)[k]
            lean = (10.0, -2.0, 10.0, 17.0 if big else 14.0)[k]
            reach = (75.0, -30.0, 20.0, 0.0) if not big else (88.0, -8.0, 12.0, 0.0)
            behind = (-62.0, -48.0, 25.0, 0.0) if not big else (-70.0, -36.0, 15.0, 0.0)
            arm_l, arm_r = (behind, reach) if fwd else (reach, behind)
            d.key(b, ease="inout", **merge(
                arms_fk(arm_l, arm_r), hips(x=hx, z=-0.08 if k % 2 else -0.06, yaw=-8.0 * s, pitch=6.0),
                spine_bend=lean, spine_twist=14.0 * s, head_turn=-6.0 * s, head_nod=-0.6 * lean,
                wrist_l=(-30.0, 0.0, 0.0), wrist_r=(-30.0, 0.0, 0.0)))
            # half way the arms pass the hips low and close
            d.key(b + 0.5, ease="in", **arms_fk((10.0, -80.0, 18.0, 0.0), (10.0, -80.0, 18.0, 0.0)))
    d.overlay(groove(depth=0.03, per_beat=1, chest=2.0, nod=3.0))
    d.follow("head_turn", "spine_twist", gain=0.4, hz=2.6)
    d.follow("head_nod", "spine_bend", gain=0.5, hz=2.4)
    return d


def salsa_step():
    """The salsa basic: the left foot breaks forward on 1, the weight rocks back on 2, the feet close on 3 and pause
    on 4, then the right foot breaks back on 5-6-7 with a pause on 8, the hips rolling Cuban style over every
    step. The first basic keeps the arms in a dance frame; in the second one hand then the other flourishes up over
    the head with a twirl of the wrist."""
    d = Dance(bpm=150, beats=16)
    w = 0.12
    flat = {"foot_pitch_l": 0.0, "toe_l": 0.0, "foot_pitch_r": 0.0, "toe_r": 0.0}

    def ball(side, pitch):
        return {"foot_pitch_" + side: pitch, "toe_" + side: pitch}

    # (beat in the basic, left foot x, right foot x, heel up: side and pitch, hips x, weight side)
    steps = [
        (0, 0.22, -0.02, ("r", 18.0), 0.08, 1.0),     # 1: break forward on the left
        (1, 0.22, -0.02, ("l", 12.0), -0.01, -1.0),   # 2: rock back onto the right
        (2, 0.0, -0.02, ("r", 14.0), 0.0, 1.0),       # 3: close onto the left
        (3, 0.0, -0.02, ("r", 22.0), 0.0, 1.0),       # 4: pause, the hip settles
        (4, 0.0, -0.22, ("l", 14.0), -0.08, -1.0),    # 5: break back on the right
        (5, 0.0, -0.22, ("r", 16.0), 0.01, 1.0),      # 6: rock forward onto the left
        (6, 0.0, 0.0, ("l", 14.0), 0.0, -1.0),        # 7: close onto the right
        (7, 0.0, 0.0, ("l", 22.0), 0.0, -1.0),        # 8: pause
    ]
    for basic in range(2):
        for k, xl, xr, (heel, pitch), hx, s in steps:
            b = basic * 8.0 + k
            fl = (xl + (_peel(pitch) if heel == "l" else 0.0), w, _ball_z(pitch) if heel == "l" else ANKLE_Z)
            fr = (xr + (_peel(pitch) if heel == "r" else 0.0), -w, _ball_z(pitch) if heel == "r" else ANKLE_Z)
            settle = k in (3, 7)
            d.key(b, ease="out", lift=0.03 if k in (0, 2, 4, 6) else 0.0, foot_l=fl, foot_r=fr)
            d.key(b, ease="out", **merge(flat, ball(heel, pitch)))
            d.key(b, ease="out", **merge(
                hips(x=hx, y=(0.065 if settle else 0.05) * s, z=-0.05 if settle else -0.07,
                     roll=-(11.0 if settle else 8.0) * s, yaw=(13.0 if settle else 10.0) * s),
                spine_side=(8.0 if settle else 5.0) * s, spine_twist=-12.0 * s, spine_bend=4.0 + 60.0 * hx))
    # the dance frame: the left hand up at the side as if holding a partner's hand, the right in front
    frame_l = hands(left=(0.24, 0.50, 0.30), elbow_l=(-0.2, 1.0, -0.8))
    frame_r = hands(right=(0.34, -0.32, 0.10), elbow_r=(-0.3, -1.0, 0.2))
    d.key(0, **merge(frame_l, frame_r, wrist_l=(-10.0, 0.0, 20.0), wrist_r=(-35.0, 0.0, -30.0), head_turn=0.0,
                     head_nod=0.0))
    d.key(7.5, **merge(frame_l, frame_r, wrist_l=(-10.0, 0.0, 20.0), wrist_r=(-35.0, 0.0, -30.0), head_turn=0.0))
    # the right hand flourishes: out to the side, up over the head with a twirl, and back down into the frame
    d.key(8.5, ease="inout", **merge(hands(right=(0.22, -0.48, 0.10), elbow_r=(-0.4, -1.0, -0.6)),
                                      wrist_r=(-20.0, 0.0, -60.0), head_turn=-15.0))
    d.key(9.5, ease="out", **merge(hands(right=(0.10, -0.52, 0.66), elbow_r=(0.0, -1.0, 0.2)),
                                   wrist_r=(30.0, 0.0, 120.0), head_turn=-10.0, head_nod=-8.0))
    d.key(10.5, ease="inout", **merge(hands(right=(0.20, -0.42, 0.30), elbow_r=(-0.2, -1.0, -0.4)),
                                      wrist_r=(-10.0, 0.0, -30.0), head_turn=-6.0, head_nod=0.0))
    d.key(11.5, ease="inout", **merge(frame_r, wrist_r=(-35.0, 0.0, -30.0), head_turn=0.0))
    # and the left hand answers on 5-6-7
    d.key(11.5, **merge(frame_l, wrist_l=(-10.0, 0.0, 20.0)))
    d.key(12.5, ease="inout", **merge(hands(left=(0.22, 0.48, 0.10), elbow_l=(-0.4, 1.0, -0.6)),
                                      wrist_l=(-20.0, 0.0, -60.0), head_turn=15.0))
    d.key(13.5, ease="out", **merge(hands(left=(0.10, 0.52, 0.66), elbow_l=(0.0, 1.0, 0.2)),
                                    wrist_l=(30.0, 0.0, 120.0), head_turn=10.0, head_nod=-8.0))
    d.key(14.5, ease="inout", **merge(hands(left=(0.20, 0.42, 0.30), elbow_l=(-0.2, 1.0, -0.4)),
                                      wrist_l=(-10.0, 0.0, -30.0), head_turn=6.0, head_nod=0.0))

    def frame_and_shoulders(beat):
        # the frame pushes forward on the forward break and draws back on the back break; the shoulders shimmy
        # through the pauses on 4 and 8
        dx = 0.05 * math.cos(2.0 * math.pi * beat / 8.0)
        p = (beat - 3.0) % 4.0
        env = max(0.0, 1.0 - min(p, 4.0 - p) / 0.7)
        sh = 7.0 * env * math.sin(2.0 * math.pi * beat * 2.0)
        # the body turns towards each flourish and leans away from it, the raised arm making one long line
        f = [0.5 + 0.5 * math.cos(math.pi * min(1.0, abs(beat - c) / 1.4)) for c in (9.5, 13.5)]
        return {"hand_l": (dx, 0.0, 0.0), "hand_r": (dx, 0.0, 0.0), "clav_fwd_l": sh, "clav_fwd_r": -sh,
                "spine_twist": 14.0 * (f[1] - f[0]), "spine_side": 8.0 * (f[0] - f[1]),
                "head_nod": -6.0 * (f[0] + f[1])}

    d.overlay(frame_and_shoulders)
    d.overlay(groove(depth=0.015, per_beat=1, chest=1.0, nod=1.5))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.2)
    d.follow("head_turn", "spine_twist", gain=0.3, hz=2.4)
    return d


def hustle_roll():
    """Disco: the forearms roll round each other in front of the chest for four counts, then the right hand points
    up to the sky with the left on the hip, then the left points up the other side, the hips swaying over side
    step touches the whole time."""
    d = Dance(bpm=120, beats=8)
    # step touches: out on the left, touch the right beside it; out on the right, touch the left
    for k in range(8):
        b = float(k)
        s = 1.0 if k % 4 in (0, 1) else -1.0      # the weight side
        step = k % 2 == 0
        out, tap = ("l", "r") if s > 0 else ("r", "l")
        m_out = _m(out)
        d.key(b, ease="out", lift=0.04 if step else 0.0, **{
            "foot_" + out: (0.0, 0.14 * m_out, ANKLE_Z), "foot_pitch_" + out: 0.0, "toe_" + out: 0.0})
        d.key(b, ease="out", lift=0.0 if step else 0.04, **{
            "foot_" + tap: ((0.0, 0.14 * -m_out, ANKLE_Z) if step else (0.02, 0.03 * m_out, _ball_z(22.0))),
            "foot_pitch_" + tap: 0.0 if step else 22.0, "toe_" + tap: 0.0 if step else 22.0})
        d.key(b, ease="inout", **merge(hips(y=(0.05 if step else 0.07) * s, z=-0.08 if step else -0.05,
                                            roll=-(5.0 if step else 8.0) * s, yaw=4.0 * s),
                                       spine_side=(4.0 if step else 6.0) * s))
    # the roll: the fists circle round each other, half a turn apart, one turn a beat
    rest = {"wrist_l": (0.0, 0.0, 20.0), "wrist_r": (0.0, 0.0, 20.0), "head_turn": 0.0, "head_nod": 0.0,
            "spine_twist": 0.0}
    for i in range(29):
        b = i / 8.0
        a = 2.0 * math.pi * i / 8.0
        c, s_ = math.cos(a), math.sin(a)
        d.key(b, **hands((0.48 + 0.09 * c, 0.08, 0.02 + 0.09 * s_), (0.48 - 0.09 * c, -0.08, 0.02 - 0.09 * s_),
                         (-0.2, 1.0, -0.6), (-0.2, -1.0, -0.6)))
    d.key(0, **rest)
    d.key(3.5, **rest)
    # point up to the right, the left fist on the hip; hold; then the other side
    for b, side in ((4.0, "r"), (6.0, "l")):
        m = _m(side)
        hip = _other(side)
        pose = merge({"ik_" + side: 0.0, "arm_" + side: (18.0, 52.0, 2.0, 0.0), "wrist_" + side: (0.0, 0.0, 0.0)},
                     _hip_hand(hip), head_turn=24.0 * m, head_nod=-14.0, spine_twist=10.0 * m)
        d.key(b, ease="inout", **pose)
        d.key(b + 1.25, ease="hold", **pose)
    d.overlay(groove(depth=0.025, per_beat=1, chest=2.0, nod=2.5))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.2)
    return d


def cossack_kicks():
    """Cossack squat kicks: down in a deep squat with the arms folded high across the chest, one leg shoots out
    straight in front, comes back under and the other kicks out, bouncing on every switch; for the last two kicks
    the arms fling open wide."""
    d = Dance(bpm=132, beats=8)
    w = 0.14
    for k in range(8):
        b = float(k)
        kick = "r" if k % 2 == 0 else "l"
        plant = _other(kick)
        mk = _m(kick)
        # the kick: the leg straight out in front, the heel low, the toes up
        d.key(b, ease="in", **{
            "foot_" + kick: (0.66, 0.12 * mk, 0.25), "knee_" + kick: (0.2, 0.15 * mk, 1.0),
            "foot_pitch_" + kick: -25.0, "toe_" + kick: 0.0,
            "foot_" + plant: (0.02, w * -mk, ANKLE_Z), "knee_" + plant: _yaw(-30.0 * mk),
            "foot_pitch_" + plant: 0.0, "toe_" + plant: 0.0})
        d.key(b, ease="in", **merge(hips(x=-0.06, y=-0.03 * mk, z=-0.22, pitch=-6.0, roll=4.0 * mk),
                                    spine_bend=-4.0, spine_side=-3.0 * mk, head_nod=-4.0))
        # the switch: both feet under the body, the knees wide, the bottom of the bounce
        d.key(b + 0.5, ease="out", **{
            "foot_" + kick: (0.02, w * mk, ANKLE_Z), "knee_" + kick: _yaw(30.0 * mk),
            "foot_pitch_" + kick: 0.0, "toe_" + kick: 0.0})
        d.key(b + 0.5, ease="out", **merge(hips(x=0.0, y=0.0, z=-0.275, pitch=4.0, roll=0.0),
                                          spine_bend=6.0, spine_side=0.0, head_nod=2.0))
    # the arms folded high across the chest, the left forearm over the right
    folded = merge(hands((0.30, -0.20, 0.10), (0.27, 0.18, -0.03), (0.2, 1.0, 0.1), (0.2, -1.0, -0.1)),
                   wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0))
    wide = merge(arms_fk((15.0, 35.0, 15.0, 0.0), (15.0, 35.0, 15.0, 0.0)),
                 wrist_l=(-20.0, 0.0, 30.0), wrist_r=(-20.0, 0.0, 30.0))
    d.key(0, **folded)
    d.key(5.25, **folded)
    d.key(6.0, ease="out", **wide)
    d.key(7.25, ease="hold", **wide)
    d.overlay(groove(depth=0.02, per_beat=2, chest=1.5, nod=2.0))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.6)
    return d


def tavern_jig():
    """A tavern jig: hands on the hips and the chest up, hopping on one foot while the other points its toe in
    front, cuts up by the knee and flicks behind, then the same on the other foot; then two jumps clicking the
    heels together out to the side, right and left."""
    d = Dance(bpm=140, beats=8)
    w = 0.11

    def foot(side, where, hop=False):
        m = _m(side)
        z_hop = 0.08 if hop else 0.0
        shapes = {
            "down": ((0.0, w * m, ANKLE_Z + z_hop), 0.0, 0.0, _yaw(10.0 * m)),
            "point": ((0.25, (w - 0.01) * m, _ball_z(45.0) + 0.05), 45.0, 0.0, _yaw(5.0 * m)),
            "cut": ((0.10, 0.05 * m, 0.44), 45.0, 0.0, _yaw(35.0 * m, -0.1)),
            "flick": ((-0.18, w * m, 0.42), 50.0, 0.0, (1.0, 0.1 * m, -0.8)),
        }
        pos, pitch, toe, knee = shapes[where]
        return {"foot_" + side: pos, "foot_pitch_" + side: pitch, "toe_" + side: toe, "knee_" + side: knee,
                "foot_yaw_" + side: 8.0 * m, "foot_roll_" + side: 0.0}

    # the hop-point bars: (beat, hopping foot, the free foot's shape)
    for half in range(2):
        hop, free = ("l", "r") if half == 0 else ("r", "l")
        b0 = half * 2.0
        mf = _m(free)
        for i, shape in enumerate(("point", "cut", "point", "flick")):
            b = b0 + i * 0.5
            up = i % 2 == 1                      # in the air on the "and"
            d.key(b, ease="out" if up else "in", **merge(
                foot(hop, "down", hop=up), foot(free, shape),
                hips(y=-0.03 * mf, z=0.0 if up else -0.08, roll=3.0 * mf, yaw=-5.0 * mf),
                spine_side=-2.0 * mf, spine_twist=8.0 * mf, head_turn=10.0 * mf if shape == "point" else 0.0))
    # the heel clicks: crouch on both feet, jump with both feet out to one side and the heels together, land
    for side, b in (("r", 4.0), ("l", 6.0)):
        m = _m(side)
        d.key(b, ease="in", **merge(foot("l", "down"), foot("r", "down"), hips(z=-0.12, y=0.0, roll=0.0, yaw=0.0),
                                    spine_side=0.0, spine_twist=0.0, head_turn=0.0, spine_bend=6.0))
        o, i_ = side, _other(side)
        d.key(b + 0.5, ease="out", **merge(
            {"foot_" + o: (0.02, 0.36 * m, 0.40), "foot_pitch_" + o: 10.0, "toe_" + o: 0.0,
             "knee_" + o: _yaw(20.0 * m), "foot_yaw_" + o: 30.0 * m, "foot_roll_" + o: -15.0 * m,
             "foot_" + i_: (0.02, 0.23 * m, 0.40), "foot_pitch_" + i_: 10.0, "toe_" + i_: 0.0,
             "knee_" + i_: _yaw(-10.0 * m), "foot_yaw_" + i_: -30.0 * m, "foot_roll_" + i_: 15.0 * m},
            hips(y=-0.06 * m, z=0.12, roll=-4.0 * m), spine_side=-6.0 * m, spine_bend=-4.0, head_turn=20.0 * m))
        d.key(b + 1.0, ease="in", **merge(foot("l", "down"), foot("r", "down"),
                                          hips(z=-0.12, y=0.0, roll=0.0), spine_side=0.0, spine_bend=6.0,
                                          head_turn=0.0))
        d.key(b + 1.5, ease="out", **merge(hips(z=-0.04), spine_bend=-2.0))
    d.key(0, **merge(_hip_hand("l"), _hip_hand("r"), spine_bend=-3.0, head_nod=-6.0))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.6)
    d.follow("head_nod", "spine_bend", gain=0.4, hz=2.6)
    return d


def lindy_kick():
    """Solo lindy hop: rock step back and forward, a bouncy triple step, a kick ball change, then a triple step
    with the arms flung out wide like the end of a swingout, the knees pulsing down on every beat."""
    d = Dance(bpm=150, beats=8)
    w = 0.11

    def ft(side, x, z=ANKLE_Z, pitch=0.0, toe=None, knee=0.0):
        m = _m(side)
        return {"foot_" + side: (x, w * m, z), "foot_pitch_" + side: pitch,
                "toe_" + side: pitch if toe is None else toe, "knee_" + side: _yaw((10.0 + knee) * m)}

    # (beat, ease, lift, left foot, right foot, hips x, weight side)
    steps = [
        (0.0, "out", 0.05, ft("l", -0.20), ft("r", 0.03 + _peel(12.0), _ball_z(12.0), 12.0), -0.05, 1.0),  # 1 rock
        (1.0, "out", 0.0, ft("l", -0.20 + _peel(20.0), _ball_z(20.0), 20.0), ft("r", 0.03), 0.02, -1.0),   # 2
        (2.0, "out", 0.05, ft("l", 0.02), ft("r", 0.03), 0.01, 1.0),                            # 3 triple
        (2.5, "out", 0.04, ft("l", 0.02), ft("r", 0.0), 0.0, -1.0),                             # &
        (3.0, "out", 0.04, ft("l", 0.0), ft("r", 0.0), 0.0, 1.0),                               # 4
        (4.0, "out", 0.06, ft("l", 0.0), ft("r", 0.42, 0.30, 30.0, 0.0, -5.0), -0.03, 1.0),     # 5 kick
        (4.5, "in", 0.0, ft("l", 0.0), ft("r", -0.06, _ball_z(25.0), 25.0), -0.01, -1.0),       # & ball
        (5.0, "out", 0.04, ft("l", 0.02), ft("r", -0.04, _ball_z(10.0), 10.0), 0.01, 1.0),      # 6 change
        (6.0, "out", 0.05, ft("l", 0.02), ft("r", 0.02), 0.0, -1.0),                            # 7 triple
        (6.5, "out", 0.04, ft("l", 0.0), ft("r", 0.02), 0.0, 1.0),                              # &
        (7.0, "out", 0.04, ft("l", 0.0), ft("r", 0.03), 0.0, -1.0),                             # 8
    ]
    for b, ease, lift, fl, fr, hx, s in steps:
        d.key(b, ease=ease, lift=lift if s > 0 else 0.0, **{k: v for k, v in fl.items() if k == "foot_l"})
        d.key(b, ease=ease, lift=lift if s < 0 else 0.0, **{k: v for k, v in fr.items() if k == "foot_r"})
        d.key(b, ease=ease, **{k: v for k, v in merge(fl, fr).items() if k not in ("foot_l", "foot_r")})
        d.key(b, ease="inout", **merge(hips(x=hx, y=0.035 * s, z=-0.08, roll=-4.0 * s, yaw=6.0 * s),
                                       spine_side=3.0 * s))
    # arms: swing back on the rock, forward on the replace, pumping on the triples, open on the kick, flung out
    sw = [
        (0.0, (-45.0, -55.0, 40.0, 0.0), (-45.0, -55.0, 40.0, 0.0), 14.0, 0.0),
        (1.0, (60.0, -40.0, 60.0, 0.0), (60.0, -40.0, 60.0, 0.0), -2.0, 0.0),
        (2.0, (35.0, -65.0, 75.0, 0.0), (5.0, -70.0, 60.0, 0.0), 6.0, -10.0),
        (3.0, (5.0, -70.0, 60.0, 0.0), (35.0, -65.0, 75.0, 0.0), 6.0, 10.0),
        (4.0, (58.0, -32.0, 30.0, 0.0), (-50.0, -40.0, 25.0, 0.0), -6.0, -12.0),
        (5.0, (35.0, -65.0, 75.0, 0.0), (5.0, -70.0, 60.0, 0.0), 8.0, -8.0),
        (6.0, (35.0, 48.0, 8.0, 0.0), (-35.0, -22.0, 12.0, 0.0), -6.0, 26.0),
        (7.25, (30.0, 52.0, 8.0, 0.0), (-30.0, -20.0, 12.0, 0.0), -4.0, 22.0),
    ]
    for b, al, ar, lean, twist in sw:
        open_ = b >= 6.0 or b == 4.0
        d.key(b, ease="out" if b != 7.25 else "linear", **merge(
            arms_fk(al, ar), spine_bend=lean, spine_twist=twist, head_turn=-0.5 * twist,
            wrist_l=(-30.0, 0.0, 40.0) if open_ else (10.0, 0.0, 0.0),
            wrist_r=(-30.0, 0.0, 40.0) if open_ else (10.0, 0.0, 0.0)))
    d.overlay(groove(depth=0.035, per_beat=1, chest=2.5, nod=3.5))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.4)
    d.follow("head_turn", "spine_twist", gain=0.4, hz=2.4)
    return d


def tango_strut():
    """Solo tango, slow-slow-quick-quick-slow: a long stalking step forward, a rock back onto the other foot with
    the head snapping sharply to the side, two quick steps closing back, then the free leg flicks up behind the
    standing knee like a gancho; the arms hold a proud frame the whole time."""
    d = Dance(bpm=116, beats=8)
    w = 0.09

    def ft(side, x, z=ANKLE_Z, pitch=0.0, toe=None, knee=8.0, yaw=8.0):
        m = _m(side)
        return {"foot_" + side: (x, w * m, z), "foot_pitch_" + side: pitch,
                "toe_" + side: pitch if toe is None else toe, "knee_" + side: _yaw(knee * m),
                "foot_yaw_" + side: yaw * m}

    def body(hx, hz, lean, twist, roll=0.0, hy=0.0):
        return merge(hips(x=hx, y=hy, z=hz, yaw=-0.5 * twist, roll=roll), spine_bend=lean, spine_twist=twist)

    # slow: the left foot reaches forward and the weight glides onto it, the right heel peeling up behind
    d.key(0.0, ease="inout", lift=0.03, **ft("l", 0.32, pitch=-10.0, toe=0.0))
    d.key(0.0, ease="inout", **merge(ft("r", 0.0), body(0.04, -0.11, 4.0, -8.0)))
    d.key(1.0, ease="inout", **merge(ft("l", 0.32), ft("r", _peel(25.0), _ball_z(25.0), 25.0),
                                     body(0.14, -0.12, 9.0, -14.0, hy=0.02)))
    # slow: rock back onto the right, the left leg long in front with the toe pointed; the head snaps
    d.key(2.0, ease="inout", **merge(ft("r", 0.0), ft("l", 0.36, _ball_z(30.0) + 0.04, 30.0, 0.0),
                                     body(-0.04, -0.14, -9.0, 14.0, roll=3.0, hy=-0.02)))
    d.key(3.25, ease="linear", **merge(ft("l", 0.36, _ball_z(30.0) + 0.04, 30.0, 0.0),
                                       body(-0.05, -0.14, -10.0, 15.0, roll=3.0, hy=-0.02)))
    # quick, quick: the left closes back under the body, the right takes a small step back
    d.key(4.0, ease="out", lift=0.03, **merge(ft("l", 0.0), body(0.0, -0.08, 2.0, 0.0, hy=0.02)))
    d.key(4.0, ease="out", **ft("r", 0.0))
    d.key(5.0, ease="out", lift=0.03, **merge(ft("r", 0.0), body(-0.03, -0.10, 4.0, -4.0, hy=-0.02)))
    d.key(5.0, ease="out", **ft("l", 0.0))
    # slow: the left leg flicks up behind the right knee and down again
    d.key(5.5, ease="inout", **merge(ft("l", 0.04, ANKLE_Z + 0.02, 10.0), body(-0.03, -0.11, 4.0, -4.0, hy=-0.03)))
    d.key(6.0, ease="in", **merge(
        {"foot_l": (-0.12, 0.02, 0.56), "foot_pitch_l": 50.0, "toe_l": 0.0, "knee_l": (1.0, 0.25, -0.5),
         "foot_yaw_l": 0.0}, body(-0.05, -0.08, 12.0, 10.0, roll=-3.0, hy=-0.035)))
    d.key(6.4, ease="linear", **merge(
        {"foot_l": (-0.10, 0.03, 0.54), "foot_pitch_l": 50.0, "toe_l": 0.0, "knee_l": (1.0, 0.25, -0.5),
         "foot_yaw_l": 0.0}, body(-0.05, -0.08, 12.0, 10.0, roll=-3.0, hy=-0.035)))
    d.key(7.25, ease="inout", **merge(ft("l", -0.02, _ball_z(15.0), 15.0), body(-0.02, -0.11, 2.0, -2.0)))
    d.key(7.25, ease="inout", **ft("r", 0.0))
    # the frame: the left arm out holding the partner's hand, the right arm round the partner's back
    frame = merge(hands((0.22, 0.60, 0.22), (0.36, -0.28, 0.10), (-0.2, 1.0, -0.7), (-0.3, -1.0, 0.3)),
                  wrist_l=(-15.0, 0.0, 10.0), wrist_r=(-30.0, 0.0, -30.0))
    tight = merge(hands((0.26, 0.56, 0.26), (0.34, -0.26, 0.12), (-0.2, 1.0, -0.6), (-0.3, -1.0, 0.4)),
                  wrist_l=(-25.0, 0.0, 10.0), wrist_r=(-35.0, 0.0, -30.0))
    d.key(0, **frame)
    d.key(2.0, ease="snap", **tight)
    d.key(3.25, ease="linear", **tight)
    d.key(4.25, **frame)
    # the head: proud and forward, then the sharp snap to the left on the rock back, held, and back
    d.key(0, head_turn=0.0, head_nod=-4.0, head_tilt=0.0)
    d.key(1.6, head_turn=0.0, head_nod=-4.0, head_tilt=0.0)
    d.key(2.0, ease="snap", head_turn=62.0, head_nod=0.0, head_tilt=-6.0)
    d.key(3.25, ease="linear", head_turn=64.0, head_nod=0.0, head_tilt=-6.0)
    d.key(4.25, ease="inout", head_turn=0.0, head_nod=-4.0, head_tilt=0.0)
    d.key(6.0, ease="snap", head_turn=-20.0, head_nod=6.0, head_tilt=0.0)
    d.key(7.0, ease="inout", head_turn=0.0, head_nod=-4.0, head_tilt=0.0)
    d.overlay(groove(depth=0.01, per_beat=1, chest=0.8, nod=0.0))
    return d


def mashed_potato():
    """The mashed potato: up on the balls of the feet, the heels twist in and out while one foot then the other
    kicks out to the side, the bent arms pumping and the whole body bobbing happily; the second bar brings the
    arms up high."""
    d = Dance(bpm=132, beats=8)
    w = 0.11
    up = 12.0                                  # the heels a little off the floor all the time
    for k in range(8):
        b = float(k)
        kick = "r" if k % 2 == 0 else "l"
        sup = _other(kick)
        mk, ms = _m(kick), _m(sup)
        high = k >= 4
        # the kick: the free foot flicks out to the side, the standing heel twists out (toes in)
        d.key(b, ease="out", **{
            "foot_" + kick: (0.03, 0.38 * mk, 0.22), "foot_pitch_" + kick: 30.0, "toe_" + kick: 0.0,
            "foot_yaw_" + kick: 25.0 * mk, "knee_" + kick: _yaw(45.0 * mk, -0.1),
            "foot_" + sup: _swivel(-_peel(up), w * ms, -16.0 * ms)[:2] + (_ball_z(up),),
            "foot_pitch_" + sup: up, "toe_" + sup: up, "foot_yaw_" + sup: -16.0 * ms, "knee_" + sup: _yaw(-20.0 * ms)})
        # and: both feet back under the body, the heels twisting in (toes out)
        d.key(b + 0.5, ease="in", **{
            "foot_" + kick: _swivel(-_peel(up), w * mk, 22.0 * mk)[:2] + (_ball_z(up),),
            "foot_pitch_" + kick: up, "toe_" + kick: up, "foot_yaw_" + kick: 22.0 * mk, "knee_" + kick: _yaw(25.0 * mk),
            "foot_" + sup: _swivel(-_peel(up), w * ms, 22.0 * ms)[:2] + (_ball_z(up),),
            "foot_pitch_" + sup: up, "toe_" + sup: up, "foot_yaw_" + sup: 22.0 * ms, "knee_" + sup: _yaw(25.0 * ms)})
        d.key(b, ease="in", **merge(hips(y=0.03 * ms, z=-0.11, roll=-4.0 * ms, pitch=6.0), spine_side=4.0 * ms,
                                    spine_bend=8.0, spine_twist=-8.0 * mk))
        d.key(b + 0.5, ease="out", **merge(hips(y=0.0, z=-0.05, roll=0.0, pitch=4.0), spine_side=0.0,
                                          spine_bend=4.0, spine_twist=0.0))
        # the bent arms pump in opposition to the kick
        fwd = (45.0, -30.0, 100.0, 0.0) if high else (40.0, -52.0, 90.0, 0.0)
        back = (-30.0, -40.0, 95.0, 0.0) if high else (-35.0, -58.0, 85.0, 0.0)
        arm_k, arm_s = back, fwd
        d.key(b, ease="out", **merge(arms_fk(**{("left" if kick == "l" else "right"): arm_k,
                                                ("left" if sup == "l" else "right"): arm_s}),
                                     wrist_l=(-10.0, 0.0, 20.0), wrist_r=(-10.0, 0.0, 20.0)))
    d.overlay(groove(depth=0.015, per_beat=2, chest=1.5, nod=3.0))
    d.follow("head_tilt", "spine_side", gain=0.6, hz=2.6)
    d.follow("head_turn", "spine_twist", gain=0.4, hz=2.6)
    return d


def hand_jive():
    """The fifties hand jive, sixteen counts with every move twice: pat the thighs, clap, the flat hands cross over
    each other (right on top, then left), the fists stack and hammer (right on top, then left), then thumbs hitch
    back over the right shoulder and the left; the knees bounce on every count."""
    d = Dance(bpm=150, beats=16)
    out_l, out_r = (-0.3, 1.0, -0.3), (-0.3, -1.0, -0.3)
    down_l, down_r = (-0.1, 0.5, -1.0), (-0.1, -0.5, -1.0)

    def arms(hl, hr, el, er, wl, wr, **extra):
        return merge(hands(hl, hr, el, er), wrist_l=wl, wrist_r=wr, **extra)

    flat = (-25.0, 0.0, -45.0)
    upright = (0.0, -30.0, 0.0)
    thumb = (-30.0, 0.0, 75.0)                 # palm in, the thumb pointing back over the shoulder
    moves = [
        # (hit pose, rebound pose) for each count
        (arms((0.24, 0.15, -0.42), (0.24, -0.15, -0.42), (-0.6, 1.0, -0.3), (-0.6, -1.0, -0.3),
              (10.0, 0.0, 0.0), (10.0, 0.0, 0.0), spine_bend=12.0, head_nod=8.0, head_turn=0.0),
         arms((0.27, 0.16, -0.28), (0.27, -0.16, -0.28), (-0.6, 1.0, -0.3), (-0.6, -1.0, -0.3),
              (-10.0, 0.0, 0.0), (-10.0, 0.0, 0.0), spine_bend=8.0, head_nod=3.0)),
        (arms((0.38, 0.065, 0.04), (0.38, -0.065, 0.04), down_l, down_r, upright, upright,
              spine_bend=2.0, head_nod=-2.0),
         arms((0.36, 0.17, 0.08), (0.36, -0.17, 0.08), down_l, down_r, upright, upright, spine_bend=0.0)),
        (arms((0.46, -0.07, -0.10), (0.46, 0.07, 0.01), out_l, out_r, flat, flat, spine_bend=4.0, head_nod=4.0),
         arms((0.44, 0.24, -0.02), (0.44, -0.24, -0.02), out_l, out_r, flat, flat, spine_bend=3.0)),
        (arms((0.46, -0.07, 0.01), (0.46, 0.07, -0.10), out_l, out_r, flat, flat, spine_bend=4.0, head_nod=4.0),
         arms((0.44, 0.24, -0.02), (0.44, -0.24, -0.02), out_l, out_r, flat, flat, spine_bend=3.0)),
        (arms((0.42, 0.01, -0.06), (0.42, -0.01, 0.05), down_l, down_r, upright, upright, head_nod=4.0),
         arms((0.42, 0.02, -0.06), (0.36, -0.03, 0.22), down_l, down_r, upright, upright, head_nod=-2.0)),
        (arms((0.42, 0.01, 0.05), (0.42, -0.01, -0.06), down_l, down_r, upright, upright, head_nod=4.0),
         arms((0.36, 0.03, 0.22), (0.42, -0.02, -0.06), down_l, down_r, upright, upright, head_nod=-2.0)),
        (arms((0.30, 0.20, -0.14), (0.06, -0.54, 0.36), (-0.3, 1.0, -0.6), (0.2, -1.0, -0.6),
              (0.0, 0.0, 0.0), thumb, head_turn=-24.0, head_nod=-4.0, spine_twist=-12.0),
         arms((0.30, 0.20, -0.14), (0.22, -0.46, 0.16), (-0.3, 1.0, -0.6), (0.2, -1.0, -0.6),
              (0.0, 0.0, 0.0), thumb, head_turn=-12.0, head_nod=0.0, spine_twist=-6.0)),
        (arms((0.06, 0.54, 0.36), (0.30, -0.20, -0.14), (0.2, 1.0, -0.6), (-0.3, -1.0, -0.6),
              thumb, (0.0, 0.0, 0.0), head_turn=24.0, head_nod=-4.0, spine_twist=12.0),
         arms((0.22, 0.46, 0.16), (0.30, -0.20, -0.14), (0.2, 1.0, -0.6), (-0.3, -1.0, -0.6),
              thumb, (0.0, 0.0, 0.0), head_turn=12.0, head_nod=0.0, spine_twist=6.0)),
    ]
    for k, (hit, rebound) in enumerate(moves):
        for j in range(2):
            b = k * 2.0 + j
            reset = {k: 0.0 for k in ("head_turn", "spine_twist") if k not in hit}
            d.key(b, ease="in" if j else "inout", **merge(hit, reset))
            if j == 0:                       # after the second count the hands flow on into the next move
                d.key(b + 0.5, ease="out", **rebound)
    # into and out of the hitchhike the hand swings forward and wide, keeping clear of the shoulder
    d.key(11.5, ease="inout", **merge(hands(right=(0.30, -0.36, 0.0), elbow_r=(-0.2, -1.0, -0.6))))
    d.key(13.5, ease="inout", **merge(hands((0.30, 0.36, 0.0), (0.30, -0.36, 0.0), (-0.2, 1.0, -0.6),
                                          (-0.2, -1.0, -0.6)), wrist_r=(0.0, 0.0, 0.0)))
    d.key(15.5, ease="inout", **merge(hands(left=(0.30, 0.36, 0.0), elbow_l=(-0.2, 1.0, -0.6)),
                                    wrist_l=(0.0, 0.0, 0.0)))
    d.key(0, **merge(feet(STANCE + 0.02), hips(z=-0.07)))
    d.overlay(groove(depth=0.035, per_beat=1, chest=1.5, nod=2.0))
    d.overlay(sway(amount=0.025, period=4.0, roll=3.0))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.2)
    return d


def swim_stroke():
    """The sixties swim: the arms do the front crawl, reaching forward and pulling down in turn with the shoulders
    rolling, then the backstroke over the top, then one hand holds the nose and the other waves overhead as the
    body sinks down wiggling and comes back up; the hips sway all the way."""
    d = Dance(bpm=124, beats=12)

    def strokes(t0, t1, back):
        """Both arms circle round the shoulders half a turn apart, one turn every two beats."""
        for i in range(int(round((t1 - t0) * 8)) + 1):
            t = t0 + i / 8.0
            roll = 0.0
            for side, phase in (("r", math.pi), ("l", 0.0)):
                th = math.pi / 2.0 + math.pi * (t - t0) + phase
                c, sn = math.cos(th), math.sin(th)
                x = 0.04 + 0.56 * (c if back else -c)
                z = 0.20 + 0.56 * sn
                m = _m(side)
                d.key(t, **{"ik_" + side: 1.0, "hand_" + side: (x, (0.35 + 0.05 * sn) * m, z),
                            "elbow_" + side: (-0.2, m, 0.0), "wrist_" + side: (-10.0, 0.0, 60.0 if back else -20.0)})
                if side == "r":
                    roll = c if back else -c                           # the reaching shoulder leads
            d.key(t, spine_twist=14.0 * roll, hips_yaw=-5.0 * roll, spine_bend=10.0 if not back else -4.0,
                  head_nod=4.0 if not back else -8.0)

    strokes(0.0, 3.75, False)
    strokes(4.25, 8.5, True)
    # hold the nose, the other hand up overhead waving, and sink down wiggling; then come back up
    nose = hands(right=(0.30, -0.05, 0.42), elbow_r=(0.2, -1.0, -0.5))
    for i in range(9):
        b = 9.0 + i * 0.3125
        s = 1.0 if i % 2 == 0 else -1.0
        depth = min(1.0, (b - 8.75) / 1.5) if b <= 10.25 else max(0.0, 1.0 - (b - 10.25) / 1.25)
        d.key(b, ease="inout", **merge(
            nose, arms_fk(left=(15.0 + 10.0 * s, 80.0, 10.0, 0.0)),
            hips(y=0.04 * s, z=-0.06 - 0.21 * depth, roll=-6.0 * s, yaw=0.0), wrist_r=(-30.0, 0.0, 40.0),
            wrist_l=(0.0, 25.0 * s, 0.0), spine_side=5.0 * s, spine_twist=0.0, spine_bend=6.0 * depth,
            head_nod=-6.0, head_tilt=0.0))
    d.key(11.5, ease="inout", **merge(hips(y=0.0, z=-0.06, roll=0.0), spine_side=0.0))
    d.key(0, **feet(STANCE + 0.03))
    d.overlay(groove(depth=0.02, per_beat=1, chest=1.0, nod=1.5))
    d.overlay(sway(amount=0.03, period=2.0, roll=4.0))
    d.follow("head_turn", "spine_twist", gain=0.6, hz=2.0)
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.4)
    return d


def _belt():
    """Both thumbs hooked in the belt, the elbows out."""
    return merge(hands((0.12, 0.20, -0.34), (0.12, -0.20, -0.34), (-0.3, 1.0, 0.2), (-0.3, -1.0, 0.2)),
                 wrist_l=(40.0, 0.0, 30.0), wrist_r=(40.0, 0.0, 30.0))


def _clap(apart=0.0):
    """The hands clapping in front of the chest, palms together (or `apart` further from each other)."""
    y = 0.065 + apart
    return merge(hands((0.38, y, 0.04), (0.38, -y, 0.04), (-0.1, 0.5, -1.0), (-0.1, -0.5, -1.0)),
                 wrist_l=(0.0, -30.0, 0.0), wrist_r=(0.0, -30.0, 0.0))


def line_dance():
    """A country line dance with the thumbs hooked in the belt: a grapevine to the right (step, behind, step,
    touch and clap) and back to the left, then heel digs right and left, and heel, toe, heel, hitch with a clap.
    The vines travel right and come back, so the dance stays in place."""
    d = Dance(bpm=128, beats=16)
    w = 0.11

    def ft(side, x, y, z=ANKLE_Z, pitch=0.0, toe=None):
        m = _m(side)
        return {"foot_" + side: (x, y, z), "foot_pitch_" + side: pitch, "toe_" + side: pitch if toe is None else toe,
                "knee_" + side: _yaw(8.0 * m)}

    heel_z = ANKLE_Z + 0.015
    # (count, left foot, right foot, hips y, weight side)
    steps = [
        (0.0, ft("l", 0.0, w), ft("r", 0.0, -0.29), -0.19, -1.0),                     # 1 step right
        (1.0, ft("l", -0.11, -0.26), ft("r", 0.0, -0.29), -0.25, 1.0),               # 2 left behind
        (2.0, ft("l", -0.11, -0.26), ft("r", 0.0, -0.47), -0.37, -1.0),              # 3 step right
        (3.0, ft("l", 0.02, -0.25, _ball_z(25.0), 25.0), ft("r", 0.0, -0.47), -0.39, -1.0),   # 4 touch, clap
        (4.0, ft("l", 0.0, -0.07), ft("r", 0.0, -0.47), -0.16, 1.0),                 # 5 step left
        (5.0, ft("l", 0.0, -0.07), ft("r", -0.11, -0.11), -0.10, -1.0),              # 6 right behind
        (6.0, ft("l", 0.0, w), ft("r", -0.11, -0.11), 0.02, 1.0),                    # 7 step left
        (7.0, ft("l", 0.0, w), ft("r", 0.02, -w, _ball_z(25.0), 25.0), 0.04, 1.0),   # 8 touch, clap
        (8.0, ft("l", 0.0, w), ft("r", 0.26, -w, heel_z, -30.0, 0.0), 0.04, 1.0),    # 9 right heel
        (9.0, ft("l", 0.0, w), ft("r", 0.0, -w), -0.01, -1.0),                       # 10 together
        (10.0, ft("l", 0.26, w, heel_z, -30.0, 0.0), ft("r", 0.0, -w), -0.04, -1.0), # 11 left heel
        (11.0, ft("l", 0.0, w), ft("r", 0.0, -w), 0.01, 1.0),                        # 12 together
        (12.0, ft("l", 0.0, w), ft("r", 0.26, -w, heel_z, -30.0, 0.0), 0.04, 1.0),   # 13 heel
        (13.0, ft("l", 0.0, w), ft("r", -0.22, -w, _ball_z(35.0) + 0.03, 35.0, 0.0), 0.04, 1.0),  # 14 toe
        (14.0, ft("l", 0.0, w), ft("r", 0.26, -w, heel_z, -30.0, 0.0), 0.04, 1.0),   # 15 heel
        (15.0, ft("l", 0.0, w), ft("r", 0.12, -w, 0.42, 20.0, 0.0), 0.05, 1.0),      # 16 hitch, clap
    ]
    for b, fl, fr, hy, s in steps:
        behind = b in (1.0, 5.0)
        heel = fl["foot_pitch_l"] < 0.0 or fr["foot_pitch_r"] < 0.0
        d.key(b, ease="out", lift=0.05, foot_l=fl["foot_l"])
        d.key(b, ease="out", lift=0.05, foot_r=fr["foot_r"])
        d.key(b, ease="out", **{k: v for k, v in merge(fl, fr).items() if k not in ("foot_l", "foot_r")})
        # a cowboy swagger: the hips push out over the standing foot, the shoulders swing against them
        d.key(b, ease="inout", **merge(hips(y=hy, z=-0.10 if behind else -0.07, roll=-7.0 * s, yaw=-6.0 * s),
                                       spine_side=5.0 * s, spine_twist=10.0 * s,
                                       spine_bend=-6.0 if heel else 3.0))
    d.key(15.0, knee_r=(1.0, -0.1, 0.2))
    d.key(14.0, knee_r=_yaw(-8.0))
    # thumbs in the belt, out to a clap on the touches and the hitch
    for b in (3.0, 7.0, 15.0):
        d.key(b - 0.5, ease="inout", **_belt())
        d.key(b - 0.12, ease="in", **_clap(0.06))
        d.key(b, ease="out", **_clap())
        d.key(b + 0.6, ease="inout", **_belt())
    d.key(0.0, **_belt())
    # the head looks the way the vine travels
    d.key(0.0, head_turn=-15.0)
    d.key(3.0, head_turn=-15.0)
    d.key(4.0, head_turn=15.0)
    d.key(7.0, head_turn=12.0)
    d.key(8.0, head_turn=0.0, head_nod=6.0)
    d.key(15.0, head_turn=0.0, head_nod=-4.0)
    d.overlay(groove(depth=0.03, per_beat=1, chest=2.0, nod=2.5))
    d.follow("head_tilt", "spine_side", gain=0.5, hz=2.2)
    return d


def can_can():
    """The can-can: knee up, high kick, knee up, high kick on the right, then the same on the left, bouncing on
    the standing leg and leaning back into every kick; the hand on the kicking side flips an imaginary skirt at
    the side while the other rests on the hip."""
    d = Dance(bpm=150, beats=8)
    w = 0.11
    for half in range(2):
        kick = "r" if half == 0 else "l"
        sup = _other(kick)
        mk, ms = _m(kick), _m(sup)
        b0 = half * 4.0
        for i in range(4):
            b = b0 + i
            high = i % 2 == 1
            if high:
                foot = {"foot_" + kick: (0.78, 0.09 * mk, 1.17), "knee_" + kick: (0.0, 0.1 * mk, 1.0),
                        "foot_pitch_" + kick: 40.0, "toe_" + kick: -10.0}
                body = merge(hips(x=-0.05, y=0.04 * ms, z=-0.06, pitch=-8.0, roll=3.0 * mk), spine_bend=-10.0,
                             spine_side=-4.0 * mk, head_nod=-6.0, head_tilt=-8.0 * mk)
            else:
                foot = {"foot_" + kick: (0.30, 0.10 * mk, 0.52), "knee_" + kick: (1.0, 0.1 * mk, 0.4),
                        "foot_pitch_" + kick: 30.0, "toe_" + kick: 0.0}
                body = merge(hips(x=0.0, y=0.04 * ms, z=-0.08, pitch=4.0, roll=2.0 * mk), spine_bend=6.0,
                             spine_side=-2.0 * mk, head_nod=2.0, head_tilt=8.0 * mk)
            d.key(b, ease="out", **merge(foot, body, {
                "foot_" + sup: (0.0, w * ms, ANKLE_Z), "foot_pitch_" + sup: 0.0, "toe_" + sup: 0.0,
                "knee_" + sup: _yaw(8.0 * ms)}))
            # the skirt hand flips up on the kicks and down on the knees; the other hand stays on the hip
            skirt = (0.22, 0.54 * mk, -0.02) if high else (0.16, 0.46 * mk, -0.30)
            d.key(b, ease="out", **merge(_hip_hand(sup), {
                "ik_" + kick: 1.0, "hand_" + kick: skirt, "elbow_" + kick: (-0.4, mk, -0.6),
                "wrist_" + kick: (-40.0 if high else 30.0, 0.0, 30.0)}))
        # the kicking leg comes down and the weight changes over to it
        d.key(b0 + 3.5, ease="inout", **{
            "foot_" + kick: (0.02, w * mk, ANKLE_Z), "knee_" + kick: _yaw(8.0 * mk), "foot_pitch_" + kick: 0.0,
            "toe_" + kick: 0.0})
        d.key(b0 + 3.5, ease="inout", **merge(hips(x=0.0, y=0.0, z=-0.10, pitch=0.0, roll=0.0), spine_bend=4.0,
                                              spine_side=0.0))
    d.overlay(groove(depth=0.025, per_beat=2, chest=1.5, nod=2.0))
    d.follow("head_tilt", "spine_side", gain=0.4, hz=2.6)
    return d


def light_bulb():
    """The Bollywood light bulb: one hand screws a bulb in above the head, the wrist twisting back and forth,
    while the other pats the dog at hip height, the shoulders shimmying and the whole body bouncing from foot to
    foot; after four counts the hands swap."""
    d = Dance(bpm=128, beats=8)
    w = 0.12
    for half in range(2):
        up = "r" if half == 0 else "l"
        pat = _other(up)
        mu, mp = _m(up), _m(pat)
        b0 = half * 4.0
        for i in range(8):
            b = b0 + i * 0.5
            if (half == 0 and i == 0) or b > b0 + 3.26:   # the swap keys below own these beats
                continue
            on = i % 2 == 0                       # the beat: the pat lands, the bulb turns one way
            k = i // 2
            d.key(b, ease="inout", **{
                "ik_" + up: 1.0, "hand_" + up: (0.18 + 0.02 * (k % 2), 0.46 * mu, 0.72 - (0.0 if on else 0.03)),
                "elbow_" + up: (0.0, mu, -0.3), "wrist_" + up: (-20.0, 0.0, 70.0 if on else -40.0),
                "ik_" + pat: 1.0, "hand_" + pat: (0.34, 0.40 * mp, -0.40 if on else -0.26),
                "elbow_" + pat: (-0.4, mp, 0.0), "wrist_" + pat: (25.0 if on else -30.0, 0.0, -30.0),
                "head_turn": 10.0 * mu, "head_nod": -10.0})
        # the swap: both hands open out wide, then the raised hand comes down to pat and the other goes up
        d.key(b0 + 3.55, ease="inout", **merge(
            hands((0.16, 0.56, 0.16), (0.16, -0.56, 0.16), (-0.3, 1.0, -0.4), (-0.3, -1.0, -0.4)),
            wrist_l=(-20.0, 0.0, 20.0), wrist_r=(-20.0, 0.0, 20.0), head_turn=0.0, head_nod=-4.0))
        d.key(b0 + 4.0 if half == 0 else 0.0, ease="inout", **{
            "ik_" + pat: 1.0, "hand_" + pat: (0.18, 0.46 * mp, 0.72), "elbow_" + pat: (0.0, mp, -0.3),
            "wrist_" + pat: (-20.0, 0.0, 70.0),
            "ik_" + up: 1.0, "hand_" + up: (0.34, 0.40 * mu, -0.40), "elbow_" + up: (-0.4, mu, 0.0),
            "wrist_" + up: (25.0, 0.0, -30.0), "head_turn": 10.0 * mp, "head_nod": -10.0})
    # bouncing from foot to foot, the free heel popping up
    for k in range(8):
        s = 1.0 if k % 2 == 0 else -1.0
        free = "r" if s > 0 else "l"
        weight = _other(free)
        d.key(float(k), ease="out", **merge(
            hips(y=0.035 * s, z=-0.09, roll=-5.0 * s), spine_side=4.0 * s, head_tilt=6.0 * s, **{
                "foot_" + free: (_peel(18.0), w * _m(free), _ball_z(18.0)), "foot_pitch_" + free: 18.0,
                "toe_" + free: 18.0, "foot_" + weight: (0.0, w * _m(weight), ANKLE_Z),
                "foot_pitch_" + weight: 0.0, "toe_" + weight: 0.0}))
        d.key(k + 0.5, ease="in", **hips(y=0.0, z=-0.04, roll=0.0))
    d.key(0, knee_l=_yaw(10.0), knee_r=_yaw(-10.0))

    def shimmy(beat):
        s = math.sin(2.0 * math.pi * beat * 2.0)
        return {"spine_twist": 6.0 * s, "clav_fwd_l": 6.0 * s, "clav_fwd_r": -6.0 * s,
                "clav_up_l": 3.0 * max(0.0, s), "clav_up_r": 3.0 * max(0.0, -s)}

    d.overlay(shimmy)
    d.overlay(groove(depth=0.03, per_beat=2, chest=2.0, nod=2.5))
    return d


DANCES = {
    "charleston": charleston,
    "salsa_step": salsa_step,
    "hustle_roll": hustle_roll,
    "cossack_kicks": cossack_kicks,
    "tavern_jig": tavern_jig,
    "lindy_kick": lindy_kick,
    "tango_strut": tango_strut,
    "mashed_potato": mashed_potato,
    "hand_jive": hand_jive,
    "swim_stroke": swim_stroke,
    "line_dance": line_dance,
    "can_can": can_can,
    "light_bulb": light_bulb,
}
