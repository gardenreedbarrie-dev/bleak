"""Fun dances: comedic, mime and character dances, choreographed for Bleakhold."""

import math

from dflib.choreo import Dance, bounce

from moves import arms_fk, feet, groove, hands, hips, merge, sway, toe_lift, STANCE, WIDE, ANKLE_Z


def _mix(a, b, w):
    """Blends two poses (dicts of controls) by w (0 gives a, 1 gives b)."""
    out = {}
    for name, va in a.items():
        vb = b.get(name, va)
        if isinstance(va, tuple):
            out[name] = tuple(x + (y - x) * w for x, y in zip(va, vb))
        else:
            out[name] = va + (vb - va) * w
    return out


def _window(beat, start, end, ramp=0.5):
    """0..1: rises to 1 over `ramp` beats around `start`, falls back to 0 around `end`."""
    def edge(x):
        x = min(1.0, max(0.0, x))
        return x * x * (3.0 - 2.0 * x)
    return edge((beat - start) / ramp + 0.5) * (1.0 - edge((beat - end) / ramp + 0.5))


def air_guitar():
    """Shredding an invisible guitar in a wide power stance: the left hand slides up and down the neck while the
    right hand strums hard at the hip and the head bangs along; at the end of the phrase the right arm winds round
    in a big windmill, crashes down on the strings and the guitarist leans back with the neck raised."""
    d = Dance(bpm=132, beats=8)
    strum_up, strum_down = (0.30, -0.15, -0.08), (0.27, -0.19, -0.24)
    strum_elbow = (-0.6, -0.8, 0.0)
    # the fret hand slides along the neck: low on the neck (far out) to high (close to the body) and back
    neck_far, neck_near = (0.42, 0.60, 0.04), (0.40, 0.40, -0.04)
    fret_elbow = (-0.2, 0.5, -1.0)
    slide = [neck_far, neck_near, neck_near, neck_far, neck_far]
    for k in range(5):
        b = float(k)
        d.key(b, ease="in", **merge(hands(right=strum_down, elbow_r=strum_elbow), wrist_r=(35.0, 0.0, 0.0)))
        d.key(b + 0.5, ease="out", **merge(hands(right=strum_up, elbow_r=strum_elbow), wrist_r=(-20.0, 0.0, 0.0)))
        d.key(b, ease="inout", **hands(left=slide[k], elbow_l=fret_elbow))
        # the head bangs down on the beat, the upper body pumping with it
        d.key(b, ease="in", head_nod=26.0, spine_bend=8.0)
        d.key(b + 0.5, ease="out", head_nod=-8.0, spine_bend=0.0)
    # the windmill: the right arm drops back, swings up overhead and crashes down across the strings on beat 6
    d.key(5.0, ease="inout", **merge(arms_fk(right=(-35.0, -55.0, 10.0, 0.0)), wrist_r=(0.0, 0.0, 0.0),
                                     head_nod=6.0, spine_bend=4.0))
    d.key(5.5, **merge(arms_fk(right=(-5.0, 78.0, 6.0, 0.0)), head_nod=-14.0, spine_bend=-6.0))
    d.key(5.75, **merge(arms_fk(right=(45.0, 40.0, 8.0, 0.0)), head_nod=0.0, spine_bend=2.0))
    d.key(6.0, ease="linear", **merge(arms_fk(right=(70.0, -42.0, 12.0, 0.0)), head_nod=24.0, spine_bend=14.0))
    # lean back with the neck raised and the right arm flung out to the side, then back to the strings
    rock = (10.0, 28.0, 10.0, 0.0)
    d.key(6.5, ease="out", **merge(arms_fk(right=rock), wrist_r=(-30.0, 0.0, 0.0), head_nod=-20.0, spine_bend=-14.0))
    d.key(7.0, ease="out", **merge(arms_fk(right=rock), head_nod=-26.0, spine_bend=-18.0))
    d.key(5.0, **hands(left=neck_near))
    d.key(6.0, **hands(left=neck_near))
    d.key(6.75, ease="out", **hands(left=(0.36, 0.60, 0.10), elbow_l=(-0.2, 0.8, -0.8)))
    d.key(7.25, **hands(left=(0.36, 0.60, 0.10)))
    d.key(0, wrist_l=(20.0, 0.0, 60.0))
    # power stance: wide, the left foot forward, knees bent; the hips sink on the lean back
    d.key(0, **merge(feet(WIDE, x_l=0.08, x_r=-0.06), hips(z=-0.14, yaw=-10.0), spine_twist=6.0))
    d.key(5.5, **hips(z=-0.11, yaw=-10.0))
    d.key(6.0, **hips(z=-0.17, yaw=-12.0, pitch=6.0))
    d.key(6.75, **hips(x=-0.04, z=-0.20, yaw=-8.0, pitch=-6.0))
    d.key(7.25, **hips(x=-0.04, z=-0.19, yaw=-8.0, pitch=-6.0))
    d.overlay(groove(depth=0.03, per_beat=1, chest=0.0, nod=0.0))
    d.overlay(sway(amount=0.02, period=4.0, roll=2.5))
    d.follow("head_tilt", "spine_side", gain=0.5)
    d.follow("head_nod", "spine_bend", gain=0.4, hz=2.6)
    return d


def headbanger():
    """Metal headbanging in a wide stance: the whole upper body pumps down on every beat with the head whipping
    after it and the knees bending, a devil-horn fist punching up at the stage, first the right, then the left;
    at the end of the phrase both fists go up in a V and the head swings round in a full circle."""
    d = Dance(bpm=140, beats=8)
    hit, pull = (-0.04, 0.56, 0.66), (0.10, 0.52, 0.30)
    horn_elbow = (-0.2, 1.0, -0.6)
    rest, rest_elbow = (0.16, 0.30, -0.34), (-0.6, 1.0, -0.4)

    def arm(side, at):
        s = 1.0 if side == "l" else -1.0
        return {"hand_" + side: (at[0], s * at[1], at[2]), "elbow_" + side: (at[3], s * at[4], at[5]),
                "ik_" + side: 1.0}

    for k in range(6):
        b = float(k)
        # bang: the torso drops and the head whips down on the beat, then everything snaps back up
        d.key(b, ease="in", spine_bend=32.0, head_nod=24.0, head_tilt=0.0, spine_side=0.0)
        d.key(b + 0.5, ease="out", spine_bend=2.0, head_nod=-22.0)
        d.key(b, ease="in", **hips(z=-0.15, pitch=10.0, y=0.0))
        d.key(b + 0.5, ease="out", **hips(z=-0.09, pitch=0.0, y=0.0))
        side = "r" if k < 4 else "l"
        d.key(b, ease="in", **arm(side, hit + horn_elbow))
        d.key(b + 0.5, ease="out", **arm(side, pull + horn_elbow))
    # the right fist comes down to the hip as the left goes up, then both go up in a V for the circle
    # (the arms travel up and down out at the side, so they never fold in past the shoulder)
    side = (0.10, 0.64, 0.04, -0.4, 0.3, -1.0)
    d.key(0, **arm("l", rest + rest_elbow))
    d.key(3.0, **arm("l", rest + rest_elbow))
    d.key(3.5, **merge(arm("l", side), arm("r", side)))
    d.key(4.25, ease="out", **arm("r", rest + rest_elbow))
    d.key(5.0, **arm("r", rest + rest_elbow))
    vee = (0.12, 0.62, 0.58, 0.0, 1.0, -0.5)
    d.key(5.5, **arm("r", side))
    d.key(6.0, **merge(arm("l", vee), arm("r", vee)))
    d.key(7.0, **merge(arm("l", vee), arm("r", vee)))
    d.key(7.5, ease="inout", **merge(arm("r", pull + horn_elbow), arm("l", side)))
    # the circle: forward on beat 6, round to the left, back, round to the right and forward again on the one
    for k in range(8):
        b = 6.0 + k * 0.25
        a = 2.0 * math.pi * k / 8.0
        d.key(b, spine_bend=22.0 + 12.0 * math.cos(a), spine_side=18.0 * math.sin(a),
              head_nod=4.0 + 22.0 * math.cos(a - 0.6), head_tilt=20.0 * math.sin(a - 0.6),
              **hips(z=-0.12, pitch=6.0 * math.cos(a), y=-0.04 * math.sin(a)))
    d.key(0, wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0))
    d.key(0, **feet(WIDE + 0.04))
    d.overlay(groove(depth=0.04, per_beat=1, chest=0.0, nod=0.0))
    d.follow("head_nod", "spine_bend", gain=0.6, hz=2.4)
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def noodle_arms():
    """Boneless: the arms flop up over the head and down again in turn like wet noodles, the elbows and wrists
    trailing behind the shoulders, the body wobbling the other way; in the second bar the arms flap loosely out at
    the sides while the knees knock in and out and the head lolls about."""
    d = Dance(bpm=112, beats=8)
    pi = math.pi

    def flop(b):
        # the arms whip up and flop down in turn, a wave running out from the shoulder to the hand
        pose = {}
        for side, ph in (("l", 0.0), ("r", 1.0)):
            c = math.cos(pi * (b - ph))
            lag = math.cos(pi * (b - ph - 0.3))
            pose["arm_" + side] = (12.0 + 15.0 * math.sin(pi * (b - ph)), 2.0 + 60.0 * c,
                                   55.0 - 45.0 * lag, 20.0 * math.sin(pi * (b - ph - 0.6)))
        s = math.cos(pi * (b - 0.25))
        pose.update(spine_side=12.0 * s, spine_twist=6.0 * math.sin(pi * b), spine_bend=4.0,
                    hips=(0.0, -0.035 * math.cos(pi * (b - 0.1)), -0.08), hips_roll=5.0 * s,
                    knee_l=(1.0, 0.15, 0.0), knee_r=(1.0, -0.15, 0.0))
        return pose

    def flap(b):
        # the arms flap loosely out at the sides, flopping down as the knees knock in on the beat
        pose = {}
        for side, ph in (("l", 0.0), ("r", 0.12)):
            c = math.cos(2.0 * pi * (b - ph))
            pose["arm_" + side] = (20.0 + 10.0 * math.sin(pi * (b - ph)), -15.0 - 40.0 * c,
                                   45.0 + 35.0 * math.cos(2.0 * pi * (b - ph - 0.3)),
                                   25.0 * math.sin(2.0 * pi * (b - ph - 0.5)))
        k = math.cos(2.0 * pi * b)
        s = math.cos(pi * (b - 0.2))
        pose.update(spine_side=10.0 * s, spine_twist=-8.0 * math.sin(pi * b), spine_bend=10.0,
                    hips=(0.0, -0.045 * s, -0.15 - 0.03 * k), hips_roll=6.0 * s,
                    knee_l=(1.0, 0.15 - 0.45 * k, 0.0), knee_r=(1.0, -0.15 + 0.45 * k, 0.0))
        return pose

    for i in range(32):
        b = i * 0.25
        w = _window(b, 4.0, 8.0, ramp=1.0) + _window(b, -4.0, 0.0, ramp=1.0)
        pose = _mix(flop(b), flap(b), w)
        d.key(b, **merge(pose, ik_l=0.0, ik_r=0.0))
    # the head lolls round, loosely
    for i in range(16):
        b = i * 0.5
        a = 2.0 * pi * b / 4.0
        d.key(b, head_tilt=16.0 * math.sin(a), head_nod=6.0 + 10.0 * math.cos(a), head_turn=8.0 * math.sin(a))
    d.key(0, **feet(STANCE + 0.04))
    d.overlay(groove(depth=0.04, per_beat=1, chest=2.0, nod=0.0, sharp=1.5))
    d.follow("head_tilt", "spine_side", gain=1.0, hz=1.8, damping=0.25)
    d.follow("head_nod", "spine_bend", gain=0.8, hz=1.8, damping=0.25)
    for side in "lr":
        d.follow("wrist_" + side, "arm_" + side, gain=0.9, hz=2.0, damping=0.3, component=1)
        d.follow("wrist_" + side, "arm_" + side, gain=0.6, hz=2.0, damping=0.3, component=0)
    return d


def flex_show():
    """Bodybuilder posing on the beat: a front double biceps, a side chest turned to the right, a hunched
    most-muscular crunch and a lat spread with the fists on the waist; each pose hits on the beat and is held with
    a little trembling shake, then a proud strut in place (arms out, stepping left, right) carries to the next."""
    d = Dance(bpm=100, beats=8)
    ready = hands((0.14, 0.36, -0.34), (0.14, -0.36, -0.34), (-1.0, 0.5, -0.2), (-1.0, -0.5, -0.2))
    poses = [
        # front double biceps: upper arms out level, fists up by the ears, chest up
        merge(hands((0.02, 0.50, 0.48), (0.02, -0.50, 0.48), (0.0, 1.0, -0.8), (0.0, -1.0, -0.8)),
              hips(z=-0.07, yaw=0.0, pitch=0.0), spine_bend=-6.0, spine_twist=0.0, spine_side=0.0, head_nod=-6.0,
              head_turn=0.0, clav_up_l=10.0, clav_up_r=10.0, clav_fwd_l=0.0, clav_fwd_r=0.0,
              wrist_l=(30.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 0.0)),
        # side chest: turned to the right, the left forearm across the belly, the right hand gripping its wrist
        merge(hands((0.30, 0.02, -0.10), (0.30, -0.08, -0.14), (-0.6, 1.0, -0.6), (-0.4, -1.0, -0.3)),
              hips(z=-0.10, yaw=-35.0, pitch=0.0), spine_bend=-4.0, spine_twist=-12.0, spine_side=-4.0, head_nod=-4.0,
              head_turn=42.0, clav_up_l=6.0, clav_up_r=4.0, clav_fwd_l=10.0, clav_fwd_r=10.0,
              wrist_l=(20.0, 0.0, 0.0), wrist_r=(30.0, 0.0, 0.0)),
        # most muscular: hunched forward, fists together low in front, shoulders shrugged and rolled in
        merge(hands((0.32, 0.07, -0.10), (0.32, -0.07, -0.10), (0.3, 1.0, 0.2), (0.3, -1.0, 0.2)),
              hips(z=-0.14, yaw=0.0, pitch=6.0), spine_bend=20.0, spine_twist=0.0, spine_side=0.0, head_nod=-8.0,
              head_turn=0.0, clav_up_l=18.0, clav_up_r=18.0, clav_fwd_l=18.0, clav_fwd_r=18.0,
              wrist_l=(40.0, 0.0, 0.0), wrist_r=(40.0, 0.0, 0.0)),
        # lat spread: fists on the waist, elbows flared out wide, chest proud
        merge(hands((0.0, 0.24, -0.24), (0.0, -0.24, -0.24), (0.5, 1.0, 0.1), (0.5, -1.0, 0.1)),
              hips(z=-0.07, yaw=0.0, pitch=0.0), spine_bend=-8.0, spine_twist=0.0, spine_side=0.0, head_nod=-8.0,
              head_turn=0.0, clav_up_l=4.0, clav_up_r=4.0, clav_fwd_l=-8.0, clav_fwd_r=-8.0,
              wrist_l=(0.0, -30.0, 0.0), wrist_r=(0.0, -30.0, 0.0)),
    ]
    stances = [
        dict(feet(WIDE), foot_yaw_l=8.0, foot_yaw_r=-8.0, knee_l=(1.0, 0.3, 0.0), knee_r=(1.0, -0.3, 0.0)),
        dict(feet(WIDE, x_l=0.06, x_r=-0.04), foot_yaw_l=-20.0, foot_yaw_r=-40.0,
             knee_l=(0.8, -0.6, 0.0), knee_r=(0.8, -0.6, 0.0)),
        dict(feet(WIDE + 0.03), foot_yaw_l=12.0, foot_yaw_r=-12.0, knee_l=(1.0, 0.4, 0.0), knee_r=(1.0, -0.4, 0.0)),
        dict(feet(WIDE), foot_yaw_l=8.0, foot_yaw_r=-8.0, knee_l=(1.0, 0.3, 0.0), knee_r=(1.0, -0.3, 0.0)),
    ]
    strut = merge(ready, hips(z=-0.05, yaw=0.0, pitch=0.0), spine_bend=-3.0, spine_twist=0.0, spine_side=0.0,
                  head_nod=0.0, head_turn=0.0, clav_up_l=0.0, clav_up_r=0.0, clav_fwd_l=0.0, clav_fwd_r=0.0,
                  wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0))
    release = hands((0.10, 0.66, 0.06), (0.10, -0.66, 0.06), (-0.5, 0.5, -1.0), (-0.5, -0.5, -1.0))
    for k, pose in enumerate(poses):
        b = 2.0 * k
        d.key(b, ease="in", **pose)
        d.key(b + 0.85, ease="hold", **pose)
        d.key(b + 1.4, ease="inout", **strut)
        if k == 0:
            # the double biceps rises and falls out at the sides, so the arms never fold in past the shoulders
            d.key(b + 1.1, ease="inout", **release)
        if k == 3:
            d.key(b + 1.7, **release)
        # the strut: the feet move to the next pose's stance, the left foot stepping, then the right
        here, there = stances[k], stances[(k + 1) % 4]
        d.key(b, **here)
        d.key(b + 1.0, **{n: here[n] for n in ("foot_l", "foot_r")})
        d.key(b + 1.45, ease="inout", lift=0.07, foot_l=there["foot_l"])
        d.key(b + 1.45, ease="inout", foot_r=here["foot_r"])
        d.key(b + 1.9, ease="inout", lift=0.07, foot_r=there["foot_r"])
    # the trembling shake while a pose is held
    def shake(beat):
        k = math.floor(beat / 2.0)
        u = beat - 2.0 * k
        w = _window(u, 0.5, 0.85, ramp=0.5)
        v = math.sin(2.0 * math.pi * 4.0 * beat)
        return {"spine_side": 1.2 * w * v, "clav_up_l": 3.0 * w * v, "clav_up_r": -3.0 * w * v,
                "head_tilt": -1.0 * w * v}
    d.overlay(shake)
    d.overlay(lambda b: {"hips": (0.0, 0.0, -0.025 * bounce(b * 2.0) * _window(b % 2.0, 1.6, 2.0, ramp=0.4))})
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def tribal_stomp():
    """A war dance: heavy stomps from knees lifted high, left, right, left, right, each fist pounding the chest
    with its own foot; two big stomps with both fists pounding together; then both arms thrown up to the sky
    and the dancer leans back in a roar before the stomping starts again."""
    d = Dance(bpm=96, beats=8)
    width = WIDE
    knee_up = 0.48

    def foot(side, z=ANKLE_Z, x=0.0):
        s = 1.0 if side == "l" else -1.0
        return {"foot_" + side: (x, s * width, z)}

    def lifted(side):
        s = 1.0 if side == "l" else -1.0
        return merge(foot(side, knee_up, 0.12), {"foot_pitch_" + side: 25.0,
                                                 "knee_" + side: (1.0, 0.45 * s, 0.0)})

    def planted(side):
        s = 1.0 if side == "l" else -1.0
        return merge(foot(side), {"foot_pitch_" + side: 0.0, "knee_" + side: (1.0, 0.35 * s, 0.0)})

    stomps = ["l", "r", "l", "r", "l", "r"]
    for k, side in enumerate(stomps):
        b = float(k)
        other = "r" if side == "l" else "l"
        s = 1.0 if side == "l" else -1.0
        # the knee comes up on the "and" before, the foot slams down on the beat, the body dropping with it
        d.key(b - 0.5 if b > 0 else 7.5, ease="out", **lifted(side))
        d.key(b, ease="in", **planted(side))
        d.key(b + 1.0, ease="linear", **planted(side))     # stays put while the other foot stomps
        d.key(b, ease="in", **merge(hips(y=0.0, z=-0.21, pitch=5.0, roll=0.0), spine_bend=6.0, head_nod=-6.0))
        d.key(b + 0.5, ease="out", **merge(hips(y=-0.05 * s, z=-0.08, pitch=2.0, roll=5.0 * s), spine_bend=-2.0,
                                          head_nod=-10.0))
        if k < 4:
            # the fist on the stomping side pounds the chest, the other one is pulled back out wide
            hit = {"hand_" + side: (0.25, 0.05 * s, 0.06), "hand_" + other: (0.18, -0.50 * s, 0.14)}
        else:
            hit = {"hand_l": (0.25, 0.09, 0.06), "hand_r": (0.25, -0.09, 0.06)}
        d.key(b, ease="in", **hit)
        d.key(b + 0.5, ease="out", hand_l=(0.20, 0.50, 0.18), hand_r=(0.20, -0.50, 0.18))
    d.key(0, ease="linear", **merge(planted("r"), elbow_l=(-0.2, 1.0, -0.6), elbow_r=(-0.2, -1.0, -0.6),
                                    ik_l=1.0, ik_r=1.0, wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0)))
    # beat 6: both feet planted wide, the arms thrown up to the sky, a roar leaning back
    d.key(7.0, ease="linear", **planted("l"))
    sky = hands((0.12, 0.52, 0.70), (0.12, -0.52, 0.70), (0.0, 1.0, -0.4), (0.0, -1.0, -0.4))
    d.key(6.0, ease="out", **merge(sky, hips(y=0.0, z=-0.12, pitch=-4.0, roll=0.0), spine_bend=-14.0,
                                   head_nod=-24.0))
    d.key(7.0, **merge(sky, hips(y=0.0, z=-0.15, pitch=-8.0, roll=0.0), spine_bend=-24.0, head_nod=-32.0))
    d.key(6.0, wrist_l=(-10.0, 0.0, 0.0), wrist_r=(-10.0, 0.0, 0.0))
    d.key(7.0, wrist_l=(-10.0, 0.0, 0.0), wrist_r=(-10.0, 0.0, 0.0))
    # coming out of the roar the fists swing down out at the sides, the left knee rising for the next stomp
    d.key(7.5, ease="inout", **merge(hands((0.30, 0.50, 0.24), (0.30, -0.50, 0.24)),
                                     hips(y=-0.05, z=-0.08, pitch=2.0, roll=5.0), spine_bend=0.0, head_nod=-6.0,
                                     wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0)))
    d.follow("head_nod", "spine_bend", gain=0.5, hz=2.4)
    d.follow("head_tilt", "hips_roll", gain=0.5)
    return d


def bunny_hop():
    """The bunny hop with the hands held up like paws by the chest: a hop forward on both feet, a kick out to the
    side, a hop back, a kick with the other foot, two little hops on the spot, then a kick each side; the feet
    really leave the ground on every hop and the knees soak up each landing."""
    d = Dance(bpm=120, beats=8)
    width = STANCE
    stand_z = -0.07

    def both_feet(x, z=None, pitch=0.0):
        # on the ground the heels come up with the pitch, the balls of the feet stay down
        z = ANKLE_Z + toe_lift(pitch) if z is None else z
        return merge(feet(width, x_l=x, x_r=x, z_l=z, z_r=z), foot_pitch_l=pitch, foot_pitch_r=pitch)

    def hop(land, x_from, x_to, height, rise, toes):
        # crouch, push off, fly with the toes pointed, land on the beat and sink into the knees
        mid = 0.5 * (x_from + x_to)
        d.key(land - 0.5, ease="inout", **merge(both_feet(x_from), hips(x=x_from, y=0.0, z=-0.15, roll=0.0),
                                                 spine_bend=10.0, spine_side=0.0))
        d.key(land - 0.36, ease="in", **merge(both_feet(x_from, pitch=10.0), hips(x=x_from + 0.02, z=-0.03)))
        d.key(land - 0.18, ease="out", **merge(both_feet(mid, ANKLE_Z + height, toes),
                                               hips(x=mid + 0.02, z=rise), spine_bend=0.0))
        d.key(land, ease="in", **merge(both_feet(x_to, pitch=0.0), hips(x=x_to, z=-0.06)))
        d.key(land + 0.18, ease="out", **merge(hips(x=x_to, z=-0.17), spine_bend=8.0))
        d.key(land + 0.5, ease="inout", **merge(both_feet(x_to), hips(x=x_to, z=stand_z), spine_bend=2.0))

    def kick(beat, side, x):
        # one foot flicks out to the side, the weight on the other, the body leaning away
        s = 1.0 if side == "l" else -1.0
        other = "r" if side == "l" else "l"
        d.key(beat, ease="out", **merge(
            {"foot_" + side: (x + 0.04, s * 0.40, ANKLE_Z + 0.12), "foot_" + other: (x, -s * width, ANKLE_Z),
             "foot_pitch_" + side: 15.0, "foot_roll_" + side: 20.0 * s},
            hips(x=x, y=-0.05 * s, z=-0.09, roll=-5.0 * s), spine_side=-9.0 * s, spine_bend=2.0))
        d.key(beat + 0.45, ease="inout", **merge(both_feet(x), {"foot_roll_" + side: 0.0},
                                                 hips(x=x, y=0.0, z=stand_z, roll=0.0), spine_side=0.0))

    fwd = 0.16
    hop(2.0, fwd, 0.0, 0.16, 0.13, 30.0)          # hop back
    hop(4.0, 0.0, 0.0, 0.09, 0.06, 18.0)          # two little hops on the spot
    hop(5.0, 0.0, 0.0, 0.09, 0.06, 18.0)
    kick(1.0, "r", fwd)
    kick(3.0, "l", 0.0)
    kick(6.0, "r", 0.0)
    kick(6.95, "l", 0.0)
    # the hop forward lands on the one (its take-off keys sit at the end of the loop)
    d.key(7.5, ease="inout", **merge(both_feet(0.0), hips(x=0.0, y=0.0, z=-0.15, roll=0.0), spine_bend=10.0,
                                     spine_side=0.0))
    d.key(7.64, ease="in", **merge(both_feet(0.0, pitch=10.0), hips(x=0.02, z=-0.03)))
    d.key(7.82, ease="out", **merge(both_feet(0.5 * fwd, ANKLE_Z + 0.16, 30.0), hips(x=0.5 * fwd + 0.02, z=0.13),
                                    spine_bend=0.0))
    d.key(0.0, ease="in", **merge(both_feet(fwd, pitch=0.0), hips(x=fwd, z=-0.06),
                                  foot_roll_l=0.0, foot_roll_r=0.0))
    d.key(0.18, ease="out", **merge(hips(x=fwd, z=-0.17), spine_bend=8.0))
    d.key(0.5, ease="inout", **merge(both_feet(fwd), hips(x=fwd, z=stand_z), spine_bend=2.0))
    # paws up by the chest, flicking on every landing
    d.key(0, **hands((0.26, 0.20, 0.11), (0.26, -0.20, 0.11), (-0.3, 0.6, -1.0), (-0.3, -0.6, -1.0)))
    for b in (0.0, 2.0, 4.0, 5.0):
        d.key(b, ease="in", wrist_l=(75.0, 0.0, -90.0), wrist_r=(75.0, 0.0, -90.0))
        d.key(b + 0.3, ease="out", wrist_l=(45.0, 0.0, -90.0), wrist_r=(45.0, 0.0, -90.0))
    d.key(0, head_nod=0.0)
    d.overlay(lambda b: {"head_tilt": 6.0 * math.sin(math.pi * b / 2.0)})
    d.follow("head_nod", "spine_bend", gain=0.8, hz=2.6)
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def drum_solo():
    """Air drums, perched as if on a stool: the right hand rides the cymbal while the left cracks the snare and
    the right foot thumps the bass pedal; then a fill rolls round the toms, a crash on beat 6 and a crazy last
    fill with the sticks crossing over, the head nodding hard all the way."""
    d = Dance(bpm=120, beats=8)
    # the kit, in the chest's frame (+y the left)
    snare_l, snare_r = (0.40, 0.16, -0.12), (0.40, 0.02, -0.12)
    tom1_l, tom1_r, tom2 = (0.44, 0.20, 0.02), (0.44, 0.06, 0.02), (0.44, -0.12, 0.02)
    floor, crash, ride = (0.32, -0.38, -0.14), (0.26, 0.46, 0.26), (0.34, -0.38, 0.14)
    crossed_r, crossed_l = (0.40, 0.22, 0.20), (0.34, -0.28, -0.22)     # the sticks crossed over
    cocked = (0.36, 0.26, 0.04)      # the left stick held up, waiting for the backbeat
    hits_r = [(0.0, ride), (0.5, ride), (1.0, ride), (1.5, ride), (2.0, ride), (2.5, ride), (3.0, ride), (3.5, ride),
              (4.0, snare_r), (4.5, tom1_r), (5.0, tom2), (5.5, floor), (6.0, ride), (6.5, ride),
              (7.0, crossed_r), (7.25, crossed_r)]
    hits_l = [(0.0, None), (1.0, snare_l), (2.0, None), (3.0, snare_l),
              (4.25, snare_l), (4.75, tom1_l), (5.25, tom2), (6.0, crash), (6.5, snare_l),
              (7.0, crossed_l), (7.25, crossed_l)]

    def strokes(side, hits):
        n = len(hits)
        for i, (b, pos) in enumerate(hits):
            if pos is None:
                d.key(b, ease="out", **{"hand_" + side: cocked, "wrist_" + side: (-20.0, 0.0, -90.0)})
                continue
            nb, npos = hits[(i + 1) % n]
            npos = npos or cocked
            if nb <= b:
                nb += 8.0
            # down into the drum on the beat with the wrist snapping, then the stick lifts over the next drum
            snap = 6.0 + 12.0 * min(1.0, (nb - b) / 0.5)
            d.key(b, ease="in", **{"hand_" + side: pos, "wrist_" + side: (snap, 0.0, -90.0)})
            lift = min(0.16, 0.06 + 0.10 * (nb - b))
            d.key((b + 0.6 * (nb - b)) % 8.0, ease="inout", **{
                "hand_" + side: (npos[0] - 0.02, npos[1], npos[2] + lift), "wrist_" + side: (-snap, 0.0, -90.0)})

    strokes("r", hits_r)
    strokes("l", hits_l)
    d.key(0, **merge(hands(elbow_l=(-0.5, 1.0, -0.7), elbow_r=(-0.5, -1.0, -0.7)), ik_l=1.0, ik_r=1.0))
    # the body leans into the side being played; the head nods hard on every beat
    lean = [(0.0, 0.0), (4.0, 4.0), (5.0, -6.0), (5.5, -16.0), (6.0, 0.0), (6.5, 0.0), (7.0, 8.0), (7.25, 8.0)]
    for b, tw in lean:
        d.key(b, spine_twist=tw)
    for k in range(8):
        d.key(float(k), ease="in", head_nod=14.0, spine_bend=5.0)
        d.key(k + 0.5, ease="out", head_nod=-8.0, spine_bend=0.0)
    d.key(6.0, ease="in", head_nod=18.0, spine_bend=8.0, spine_side=8.0)
    d.key(6.5, ease="out", head_nod=-12.0, spine_bend=-2.0, spine_side=0.0)
    d.key(0, spine_side=0.0)
    # bass pedal under the right foot (on one, three and the "and" of three), the left foot on the hi-hat pedal
    # on the backbeat: the toes come up just before the hit and press down on it, the heel staying put
    d.key(0, **hips(z=-0.17, x=-0.03))
    for side, x, y, taps, up, toes in (("r", 0.12, -WIDE, (0.0, 2.0, 2.5, 4.0, 6.0), 0.04, -14.0),
                                       ("l", 0.06, WIDE, (1.0, 3.0, 5.0, 7.0), 0.03, -10.0)):
        for b in taps:
            d.key((b - 0.45) % 8.0, ease="linear", **{"foot_" + side: (x, y, ANKLE_Z), "foot_pitch_" + side: 0.0})
            d.key((b - 0.2) % 8.0, ease="out", **{"foot_" + side: (x, y, ANKLE_Z + up),
                                                  "foot_pitch_" + side: toes})
            d.key(b, ease="in", **{"foot_" + side: (x, y, ANKLE_Z), "foot_pitch_" + side: 0.0})
    d.overlay(groove(depth=0.02, per_beat=1, chest=0.0, nod=0.0))
    d.follow("head_turn", "spine_twist", gain=0.4)
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def dj_scratch():
    """Behind the decks: the left hand presses an imaginary headphone to the ear, elbow up, while the right hand
    scratches a record back and forth at waist height, the head nodding and the knees bouncing; then both hands go
    up and pump the crowd before the DJ drops back onto the decks."""
    d = Dance(bpm=124, beats=8)
    phone = hands(left=(0.0, 0.28, 0.32), elbow_l=(0.0, 1.0, 0.3))
    rec_fwd, rec_back = (0.42, -0.16, -0.13), (0.32, -0.25, -0.14)
    deck = merge(hands(right=rec_fwd, elbow_r=(-0.4, -1.0, 0.1)), wrist_r=(10.0, 0.0, -90.0))
    d.key(0, **merge(phone, deck, wrist_l=(-10.0, 0.0, 0.0), head_tilt=8.0, head_turn=-10.0, spine_side=4.0,
                     spine_twist=-8.0, **hips(z=-0.07, roll=0.0)))
    d.key(3.0, **merge(phone, wrist_l=(-10.0, 0.0, 0.0), head_tilt=8.0, head_turn=-10.0, spine_side=4.0,
                       spine_twist=-8.0, **hips(z=-0.07, roll=0.0)))
    # the scratch: forward and back in eighths, with a quick double ("wikka") on the "and" of two
    scratch = [0.0, 0.5, 1.0, 1.5, 2.0, 2.25, 2.5, 2.75, 3.0]
    for i, b in enumerate(scratch):
        pos = rec_back if i % 2 else rec_fwd
        d.key(b, ease="inout", hand_r=pos, wrist_r=(-5.0 if i % 2 else 15.0, 0.0, -90.0))
    # both hands up, pumping the crowd on every beat
    for k in range(4, 7):
        b = float(k)
        d.key(b, ease="in", **merge(hands((0.24, 0.42, 0.68), (0.24, -0.42, 0.68), (0.0, 1.0, -0.3),
                                          (0.0, -1.0, -0.3)),
                                    wrist_l=(10.0, 0.0, 0.0), wrist_r=(10.0, 0.0, 0.0), head_tilt=0.0,
                                    head_turn=0.0, spine_side=0.0, spine_twist=0.0, spine_bend=-6.0, head_nod=-10.0,
                                    **hips(z=-0.13)))
        d.key(b + 0.5, ease="out", **merge(hands((0.22, 0.54, 0.32), (0.22, -0.54, 0.32)), spine_bend=0.0,
                                           head_nod=0.0, **hips(z=-0.05)))
    # in from the deck, out to the crowd, back to the deck
    d.key(3.5, ease="inout", **merge(hands((0.20, 0.42, 0.30), (0.24, -0.40, 0.10), (0.0, 1.0, -0.6),
                                           (-0.2, -1.0, -0.6)), wrist_r=(10.0, 0.0, 0.0), head_tilt=4.0))
    d.key(7.25, ease="inout", **merge(hands((0.16, 0.42, 0.38), (0.26, -0.36, 0.02), (0.0, 1.0, -0.2),
                                            (-0.3, -1.0, -0.4)), wrist_r=(20.0, 0.0, -45.0), head_tilt=6.0,
                                      spine_twist=-4.0, spine_side=2.0))
    for k in range(4):
        d.key(float(k), ease="in", head_nod=12.0, spine_bend=4.0)
        d.key(k + 0.5, ease="out", head_nod=-2.0, spine_bend=1.0)
    d.key(0, **feet(STANCE + 0.04))
    d.overlay(groove(depth=0.04, per_beat=1, chest=0.0, nod=0.0))
    d.overlay(sway(amount=0.025, period=2.0, roll=3.0))
    d.follow("head_tilt", "spine_side", gain=0.4)
    return d


def conductor():
    """Conducting the orchestra: the right hand beats a four-four pattern (down, in, out, up) while the left hand
    rises palm up through a crescendo and the whole body rises with it; the second bar beats bigger, both arms go
    up for the last chord and cut it off together on the last beat with a sharp bow into it."""
    d = Dance(bpm=96, beats=8)
    centre = (0.40, -0.18, 0.24)

    def big(p, s):
        return tuple(c + (x - c) * f for x, c, f in zip(p, centre, (s, s, 0.5 + 0.5 * s)))

    pattern = [(0.44, -0.20, 0.13), (0.42, 0.04, 0.17), (0.42, -0.48, 0.19), (0.38, -0.44, 0.38)]
    rebound = [(0.0, 0.05, 0.09), (0.0, -0.06, 0.04), (0.0, 0.02, 0.09), (0.0, 0.0, 0.04)]
    for k in range(6):
        s = 1.0 if k < 4 else 1.35
        p = big(pattern[k % 4], s)
        r = tuple(a + b * s for a, b in zip(p, rebound[k % 4]))
        # the baton clicks into each beat point and bounces off it towards the next
        d.key(float(k), ease="in", hand_r=p, wrist_r=(25.0, 0.0, -90.0))
        d.key(k + 0.4, ease="out", hand_r=r, wrist_r=(-15.0, 0.0, -90.0))
        d.key(float(k), head_turn=(0.0, 12.0, -12.0, 0.0)[k % 4], spine_twist=(0.0, 8.0, -10.0, 0.0)[k % 4])
    d.key(0, **merge(hands(elbow_r=(-0.4, -1.0, -0.6), elbow_l=(-0.4, 1.0, -0.6)), ik_l=1.0, ik_r=1.0))
    # bar one: the left hand rises palm up through the crescendo and the body grows taller with it
    d.key(0, ease="inout", hand_l=(0.32, 0.32, 0.0), wrist_l=(-20.0, 0.0, 90.0))
    d.key(3.6, ease="inout", hand_l=(0.30, 0.46, 0.46), wrist_l=(-30.0, 0.0, 90.0))
    d.key(0, ease="in", **merge(hips(z=-0.10, pitch=3.0), spine_bend=6.0, head_nod=6.0))
    d.key(3.6, ease="inout", **merge(hips(z=-0.03, pitch=0.0), spine_bend=-8.0, head_nod=-12.0))
    # bar two: both hands beat big, then go up high for the last chord
    d.key(4.0, ease="in", **merge(hands(left=big((0.44, 0.20, 0.13), 1.35)), hips(z=-0.12, pitch=4.0),
                                  wrist_l=(25.0, 0.0, 0.0), spine_bend=8.0, head_nod=8.0))
    d.key(4.4, ease="out", **merge(hands(left=(0.44, 0.26, 0.22)), wrist_l=(-15.0, 0.0, 0.0)))
    d.key(5.0, ease="in", **merge(hands(left=(0.42, 0.48, 0.16)), wrist_l=(25.0, 0.0, 0.0), spine_bend=4.0,
                                  head_nod=0.0))
    up = merge(hands((0.30, 0.40, 0.52), (0.30, -0.40, 0.52)), hips(z=-0.02, pitch=-2.0),
               wrist_l=(-15.0, 0.0, 0.0), wrist_r=(-15.0, 0.0, -90.0), spine_bend=-10.0, head_nod=-16.0,
               head_turn=0.0, spine_twist=0.0)
    d.key(6.0, ease="inout", **up)
    d.key(6.55, ease="out", **merge(up, hands((0.28, 0.36, 0.60), (0.28, -0.36, 0.60))))
    # the cut-off: both hands snap down and out on the last beat, the body bowing into it, and hold
    cut = merge(hands((0.42, 0.46, 0.18), (0.42, -0.46, 0.18)), hips(z=-0.12, pitch=4.0),
                wrist_l=(20.0, 0.0, 0.0), wrist_r=(20.0, 0.0, -90.0), spine_bend=9.0, head_nod=12.0)
    d.key(7.0, ease="in", **cut)
    d.key(7.4, ease="hold", **cut)
    # the upbeat: the baton lifts for the next downbeat, the left hand sinks back
    d.key(7.75, ease="inout", **merge(hands((0.32, 0.32, 0.0), (0.40, -0.30, 0.38)), hips(z=-0.08, pitch=2.0),
                                      wrist_l=(-20.0, 0.0, 60.0), wrist_r=(-15.0, 0.0, -90.0), spine_bend=4.0,
                                      head_nod=-4.0))
    d.key(0, **feet(STANCE + 0.02, x_l=0.04, x_r=-0.02))
    d.overlay(groove(depth=0.015, per_beat=1, chest=1.5, nod=2.0))
    d.follow("head_turn", "spine_twist", gain=0.4)
    d.follow("head_nod", "spine_bend", gain=0.5, hz=2.0)
    return d


def jumping_jacks():
    """The workout: two jumping jacks (jump the feet apart with the arms sweeping up to a clap overhead, jump them
    back together with the arms down at the sides), then two deep squats with the arms out in front, and a jump
    straight back into the next jack; the feet leave the ground on every jump."""
    d = Dance(bpm=120, beats=8)
    wide, narrow = 0.30, 0.10
    clap, vee = (118.0, 64.0, 5.0, 0.0), (2.0, 40.0, 6.0, 0.0)
    down, front = (5.0, -80.0, 8.0, 0.0), (82.0, 2.0, 4.0, 0.0)

    def jump(land, w_from, w_to):
        # push off, fly with the feet moving to the new width, land on the beat and bend the knees
        mid = 0.5 * (w_from + w_to)
        d.key((land - 0.42) % 8.0, ease="inout", **merge(feet(w_from), hips(x=0.0, z=-0.12, pitch=0.0),
                                                         foot_pitch_l=0.0, foot_pitch_r=0.0))
        toes = ANKLE_Z + toe_lift(15.0)
        d.key((land - 0.32) % 8.0, ease="in", **merge(feet(w_from, z_l=toes, z_r=toes), hips(x=0.0, z=-0.02, pitch=0.0),
                                                      foot_pitch_l=15.0, foot_pitch_r=15.0))
        d.key((land - 0.16) % 8.0, ease="out", **merge(feet(mid, z_l=ANKLE_Z + 0.11, z_r=ANKLE_Z + 0.11),
                                                       hips(x=0.0, z=0.05, pitch=0.0),
                                                       foot_pitch_l=25.0, foot_pitch_r=25.0))
        d.key(land % 8.0, ease="in", **merge(feet(w_to), hips(x=0.0, z=-0.06, pitch=0.0),
                                             foot_pitch_l=0.0, foot_pitch_r=0.0))
        d.key((land + 0.2) % 8.0, ease="out", **hips(x=0.0, z=-0.15, pitch=0.0))

    jump(1.0, wide, narrow)
    jump(2.0, narrow, wide)
    jump(3.0, wide, narrow)
    jump(8.0, narrow, wide)
    d.key(0.5, ease="inout", **hips(x=0.0, z=-0.08, pitch=0.0))
    d.key(2.5, ease="inout", **hips(x=0.0, z=-0.08, pitch=0.0))
    # the arms sweep up through the sides and clap together overhead as the feet land apart, then sweep back
    # down the same way (the clap is a little in front, so the hands clear a big head)
    for b in (0.0, 2.0):
        d.key((b - 0.4) % 8.0, ease="inout", **arms_fk(vee, vee))
        d.key(b, ease="in", **merge(arms_fk(clap, clap), spine_bend=-4.0, head_nod=-8.0))
        d.key(b + 0.45, ease="out", **arms_fk(vee, vee))
        d.key(b + 1.0, ease="in", **merge(arms_fk(down, down), spine_bend=2.0, head_nod=2.0))
    # two squats, sitting back with the arms out in front, then standing tall
    for b in (4.0, 6.0):
        d.key(b, ease="inout", **merge(hips(x=-0.10, z=-0.30, pitch=12.0), arms_fk(front, front),
                                       spine_bend=20.0, head_nod=-14.0))
        d.key(b + 1.0, ease="inout", **merge(hips(x=0.0, z=-0.04, pitch=0.0), arms_fk(down, down), spine_bend=0.0,
                                             head_nod=0.0))
    d.key(0, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0), knee_l=(1.0, 0.15, 0.0), knee_r=(1.0, -0.15, 0.0))
    d.key(4.0, knee_l=(1.0, 0.35, 0.0), knee_r=(1.0, -0.35, 0.0))
    d.key(6.0, knee_l=(1.0, 0.35, 0.0), knee_r=(1.0, -0.35, 0.0))
    d.follow("head_nod", "spine_bend", gain=0.4)
    return d


def boxer_bounce():
    """Shadow boxing, bouncing on the balls of the feet with the guard up: jab, jab, cross, a left hook, then
    bob and weave under a punch, down to the left and up, down to the right and up, and a quick one-two to finish
    the phrase; the hands snap back to the guard after every punch."""
    d = Dance(bpm=128, beats=8)
    guard_l, guard_r = (0.44, 0.16, 0.14), (0.38, -0.11, 0.14)
    elbow_l, elbow_r = (-0.3, 0.4, -1.0), (-0.3, -0.4, -1.0)
    body = merge(hips(z=-0.10, y=0.0, yaw=-18.0, pitch=4.0), spine_twist=0.0, spine_side=0.0, spine_bend=6.0,
                 head_turn=14.0, head_nod=8.0, head_tilt=0.0)
    turn = {"jab": merge(body, spine_twist=-8.0, head_turn=20.0),
            "cross": merge(body, hips(z=-0.12, yaw=-6.0, pitch=4.0), spine_twist=24.0, head_turn=-4.0),
            "hook": merge(body, hips(z=-0.12, yaw=-26.0, pitch=4.0), spine_twist=-24.0, head_turn=30.0)}
    targets = {"jab": ("l", (0.62, 0.06, 0.24), (-0.2, 0.3, -1.0)),
               "cross": ("r", (0.62, -0.02, 0.24), (-0.2, -0.3, -1.0)),
               "hook": ("l", (0.44, -0.02, 0.25), (-0.2, 1.0, 0.25))}

    def arm(side, pos, elbow, twist=-60.0):
        return {"hand_" + side: pos, "elbow_" + side: elbow, "wrist_" + side: (0.0, 0.0, twist)}

    def guard(side):
        return arm(side, guard_l if side == "l" else guard_r, elbow_l if side == "l" else elbow_r)

    def punch(b, kind, start=None, back=0.4):
        side, pos, elbow = targets[kind]
        d.key((b - 0.25) % 8.0, ease="inout", **(start or guard(side)))
        d.key(b, ease="out", **arm(side, pos, elbow, -90.0))
        d.key(b + back, ease="inout", **guard(side))
        d.key(b, ease="out", **turn[kind])

    d.key(0, **merge(guard("l"), guard("r"), ik_l=1.0, ik_r=1.0))
    punch(0.0, "jab")
    punch(1.0, "jab")
    punch(2.0, "cross", back=0.35)
    punch(3.0, "hook", start=arm("l", (0.30, 0.30, 0.20), (-0.4, 1.0, -0.2)))
    for b in (0.4, 1.4, 2.4, 3.45):
        d.key(b, ease="inout", **body)
    d.key(2.7, ease="inout", **merge(body, spine_twist=8.0, head_turn=8.0))
    # bob and weave: down to the left, up, down to the right, up, the guard tight
    d.key(4.0, ease="inout", **body)
    d.key(4.5, ease="inout", **merge(body, hips(z=-0.27, y=0.07, yaw=-18.0, pitch=10.0), spine_bend=22.0,
                                     spine_side=14.0, head_tilt=4.0))
    d.key(5.0, ease="inout", **merge(body, hips(z=-0.10, y=-0.02, yaw=-18.0, pitch=4.0), spine_side=-4.0))
    d.key(5.5, ease="inout", **merge(body, hips(z=-0.27, y=-0.07, yaw=-18.0, pitch=10.0), spine_bend=22.0,
                                     spine_side=-14.0, head_tilt=-4.0))
    d.key(5.8, ease="inout", **body)
    # the one-two
    punch(6.0, "jab", back=0.35)
    punch(6.5, "cross")
    d.key(6.9, ease="inout", **body)
    # on the balls of the feet, left foot forward
    balls = ANKLE_Z + toe_lift(14.0)
    d.key(0, **merge(feet(STANCE, x_l=0.12, x_r=-0.10, z_l=balls, z_r=balls),
                     foot_pitch_l=14.0, foot_pitch_r=14.0, toe_l=14.0, toe_r=14.0, foot_yaw_l=-10.0,
                     foot_yaw_r=-30.0, knee_l=(1.0, 0.0, 0.0), knee_r=(0.8, -0.5, 0.0)))
    d.overlay(groove(depth=0.035, per_beat=1, chest=0.0, nod=2.0, sharp=1.5))
    d.overlay(sway(amount=0.02, period=2.0, roll=2.0))
    d.follow("head_tilt", "spine_side", gain=0.3)
    return d


def ghoul_shuffle():
    """A spooky zombie dance: arms stretched out in front with the hands hanging limp, a lurching shuffle (one
    foot steps out, the other drags after it) to the left and back, to the right and back, the head lolling;
    then the shoulders twitch and the ghoul lunges forward with clawed hands before shambling back."""
    d = Dance(bpm=100, beats=8)
    w = 0.12
    reach = hands((0.56, 0.21, 0.27), (0.56, -0.21, 0.27), (-0.2, 0.3, -1.0), (-0.2, -0.3, -1.0))
    limp = dict(wrist_l=(50.0, 0.0, -90.0), wrist_r=(50.0, 0.0, -90.0))
    d.key(0, **merge(reach, limp))
    d.key(5.1, **merge(reach, limp))
    # the shuffle: the lead foot steps out on the "and", the other drags in on the beat
    steps = [(0.0, w, -w), (0.5, 0.30, -w), (1.0, 0.30, 0.06), (1.5, 0.30, -w), (2.0, w, -w),
             (2.5, w, -0.30), (3.0, -0.06, -0.30), (3.5, w, -0.30), (4.0, w, -w)]
    for i, (b, yl, yr) in enumerate(steps):
        if i == 0:
            d.key(b, ease="inout", foot_l=(0.0, yl, ANKLE_Z), foot_r=(0.0, yr, ANKLE_Z))
            continue
        pyl = steps[i - 1][1]
        moving, still = ("l", "r") if yl != pyl else ("r", "l")
        # the moving foot scuffs along (a low lift); the other stays planted
        d.key(b, ease="inout", lift=0.04, **{"foot_" + moving: (0.0, yl if moving == "l" else yr, ANKLE_Z)})
        d.key(b, ease="inout", **{"foot_" + still: (0.0, yl if still == "l" else yr, ANKLE_Z)})
        centre = 0.5 * (yl + yr)
        drag = (i % 2 == 0)
        lean = 1.0 if centre > 0.01 else (-1.0 if centre < -0.01 else 0.0)
        d.key(b, ease="inout", **merge(hips(y=centre, z=-0.14 if drag else -0.08, roll=-6.0 * lean,
                                            x=0.0, pitch=6.0), spine_side=10.0 * lean, spine_bend=12.0))
    d.key(0, **merge(hips(y=0.0, z=-0.14, roll=0.0, x=0.0, pitch=6.0), spine_side=0.0, spine_bend=12.0))
    # the shoulders twitch, the head jerks
    twitches = [(4.25, 14.0, 0.0, 10.0), (4.5, 0.0, 0.0, 0.0), (4.75, 0.0, 16.0, -12.0), (5.0, 0.0, 0.0, 0.0),
                (5.25, 12.0, 12.0, 6.0), (5.5, 0.0, 0.0, 0.0)]
    d.key(4.0, clav_up_l=0.0, clav_up_r=0.0, head_tilt=0.0)
    for b, cl, cr, tilt in twitches:
        d.key(b, ease="pop", clav_up_l=cl, clav_up_r=cr, head_tilt=tilt)
    d.key(0, clav_up_l=0.0, clav_up_r=0.0, head_tilt=0.0)
    # the lunge: wind back, then the right foot lunges forward and the clawed hands reach
    claws = dict(wrist_l=(-35.0, 0.0, -90.0), wrist_r=(-35.0, 0.0, -90.0))
    d.key(5.6, ease="inout", **merge(hands((0.22, 0.48, 0.22), (0.22, -0.48, 0.22), (-0.4, 1.0, -0.5),
                                           (-0.4, -1.0, -0.5)), claws,
                                     hips(y=0.0, z=-0.10, x=-0.04, pitch=-4.0, roll=0.0), spine_bend=-6.0,
                                     spine_side=0.0, head_nod=-10.0))
    lunge = merge(hands((0.58, 0.24, 0.40), (0.58, -0.24, 0.40), (-0.2, 0.6, -1.0), (-0.2, -0.6, -1.0)), claws,
                  hips(y=-0.02, z=-0.20, x=0.12, pitch=10.0, roll=0.0), spine_bend=20.0, spine_side=0.0,
                  head_nod=-14.0)
    d.key(6.0, ease="out", **lunge)
    d.key(6.75, ease="inout", **merge(lunge, hands((0.62, 0.26, 0.44), (0.62, -0.26, 0.44))))
    d.key(7.4, ease="inout", **merge(reach, limp, hips(y=0.0, z=-0.12, x=0.02, pitch=6.0, roll=0.0),
                                     spine_bend=12.0, head_nod=0.0))
    d.key(5.6, ease="inout", foot_r=(0.0, -w, ANKLE_Z))
    d.key(6.0, ease="out", lift=0.06, foot_r=(0.30, -w - 0.02, ANKLE_Z))
    d.key(7.2, ease="inout", foot_r=(0.30, -w - 0.02, ANKLE_Z))
    d.key(7.7, ease="inout", lift=0.05, foot_r=(0.0, -w, ANKLE_Z))
    d.key(0, head_nod=0.0)
    d.key(4.0, head_nod=0.0)
    # the head lolls loosely about
    d.overlay(lambda b: {"head_turn": 10.0 * math.sin(math.pi * b / 2.0 + 0.5),
                         "head_tilt": 9.0 * math.sin(math.pi * b / 2.0 - 0.7)})
    d.follow("head_tilt", "spine_side", gain=-0.9, hz=1.6, damping=0.25)
    d.follow("head_nod", "spine_bend", gain=0.6, hz=1.8, damping=0.3)
    return d


DANCES = {
    "air_guitar": air_guitar,
    "headbanger": headbanger,
    "noodle_arms": noodle_arms,
    "flex_show": flex_show,
    "tribal_stomp": tribal_stomp,
    "bunny_hop": bunny_hop,
    "drum_solo": drum_solo,
    "dj_scratch": dj_scratch,
    "conductor": conductor,
    "jumping_jacks": jumping_jacks,
    "boxer_bounce": boxer_bounce,
    "ghoul_shuffle": ghoul_shuffle,
}
