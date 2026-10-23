"""Party dances: the well-known social dances everybody recognises, choreographed for Bleakhold."""

import math

from dflib.choreo import Dance

from moves import arms_fk, feet, groove, hands, hips, merge, sway, STANCE, ANKLE_Z


def string_swing():
    """Straight arms swing from side to side, one in front of the body and one behind, while the hips swing the
    other way: the arm-swing party dance."""
    d = Dance(bpm=118, beats=4)
    front, back = (132.0, -55.0, 6.0, 0.0), (-48.0, -52.0, 6.0, 0.0)
    for k in range(8):
        b = k * 0.5
        right = k % 2 == 0           # arms swing to the right side on the even counts
        arm_l, arm_r = (front, back) if right else (back, front)
        side = 1.0 if right else -1.0  # the hips go the other way
        d.key(b, ease="out", **merge(
            arms_fk(arm_l, arm_r),
            hips(y=0.1 * side, z=-0.06, roll=-9.0 * side, yaw=7.0 * side),
            spine_side=12.0 * side, spine_twist=-10.0 * side, head_tilt=-6.0 * side,
            wrist_l=(-12.0, 0.0, 0.0), wrist_r=(-12.0, 0.0, 0.0)))
        # half way the arms brush past the hips, low and close
        pass_l = (40.0 if right else 45.0, -84.0, 4.0, 0.0)
        pass_r = (45.0 if right else 40.0, -84.0, 4.0, 0.0)
        d.key(b + 0.25, ease="in", **arms_fk(pass_l, pass_r))
    d.key(0, **feet(STANCE + 0.03))
    d.overlay(groove(depth=0.025, per_beat=2, chest=1.5, nod=2.0))
    d.follow("head_tilt", "spine_side", gain=0.45, hz=2.6)
    return d


def running_man():
    """The running man: a knee comes up while the other foot slides back, then they swap, with the forearms pushing
    down on every step."""
    d = Dance(bpm=108, beats=4)
    up_z, back_x = 0.36, -0.24
    for k in range(4):
        b = float(k)
        left = k % 2 == 0
        lift = "l" if left else "r"
        plant = "r" if left else "l"
        sl = 1.0 if lift == "l" else -1.0
        # count: the knee is up, the other foot planted under the body
        d.key(b, ease="out", lift=0.0, **{
            "foot_" + lift: (0.13, sl * STANCE, up_z), "foot_" + plant: (0.0, -sl * STANCE, ANKLE_Z),
            "foot_pitch_" + lift: 28.0, "foot_pitch_" + plant: 0.0, "toe_" + plant: 0.0})
        # and: the knee steps down in front while the planted foot slides back
        d.key(b + 0.5, ease="in", **{
            "foot_" + lift: (0.02, sl * STANCE, ANKLE_Z), "foot_" + plant: (back_x, -sl * STANCE, ANKLE_Z + 0.02),
            "foot_pitch_" + lift: 0.0, "foot_pitch_" + plant: 18.0, "toe_" + plant: 25.0})
        d.key(b, ease="out", **merge(hips(z=-0.02, x=0.02, pitch=4.0), spine_bend=6.0,
                                     **hands((0.32, 0.22, 0.02), (0.32, -0.22, 0.02), (-1.0, 0.5, -0.3), (-1.0, -0.5, -0.3))))
        d.key(b + 0.5, ease="in", **merge(hips(z=-0.10, x=0.0, pitch=8.0), spine_bend=12.0,
                                          **hands((0.30, 0.20, -0.18), (0.30, -0.20, -0.18))))
        d.key(b, wrist_l=(20.0, 0.0, 0.0), wrist_r=(20.0, 0.0, 0.0))
        d.key(b + 0.5, wrist_l=(-25.0, 0.0, 0.0), wrist_r=(-25.0, 0.0, 0.0))
    d.overlay(sway(amount=0.025, period=2.0, roll=3.0))
    d.follow("head_nod", "spine_bend", gain=0.7, hz=2.4)
    return d


def disco_point():
    """Saturday-night disco: the right hand points up to the sky, then down across the body, with the hips rolling
    side to side; the left hand rests on the hip."""
    d = Dance(bpm=112, beats=8)
    up = (25.0, 62.0, 4.0, 0.0)
    down = (110.0, -55.0, 8.0, 0.0)
    for bar in range(2):
        base = bar * 4.0
        for k in range(4):
            b = base + k
            pointing_up = k % 2 == 0
            side = 1.0 if pointing_up else -1.0
            pose = merge(
                arms_fk(right=up if pointing_up else down),
                hips(y=0.06 * side, z=-0.05, roll=-6.0 * side, yaw=-12.0 if pointing_up else 10.0),
                spine_side=-8.0 * side, spine_twist=-14.0 if pointing_up else 12.0,
                head_turn=-20.0 if pointing_up else 15.0, head_nod=-12.0 if pointing_up else 10.0,
                wrist_r=(0.0, 0.0, 0.0))
            # hit the pose on the beat, hold it, then travel to the next one over the second half of the beat
            d.key(b, ease="inout", **pose)
            d.key(b + 0.45, ease="hold", **pose)
    d.key(0, **merge(hands(left=(0.06, 0.24, -0.36), elbow_l=(0.0, 1.0, 0.0)), wrist_l=(30.0, 0.0, 70.0)))
    d.key(0, **feet(STANCE + 0.03))
    d.key(0, foot_pitch_l=0.0)
    d.overlay(groove(depth=0.02, per_beat=1, chest=2.0, nod=0.0))
    d.follow("head_tilt", "spine_side", gain=0.5)
    return d


def twist():
    """The twist: up on the balls of the feet, hips and feet swivel one way while the shoulders and arms swing the
    other, going low and coming back up."""
    d = Dance(bpm=152, beats=8)
    for k in range(8):
        b = float(k)
        side = 1.0 if k % 2 == 0 else -1.0
        low = 0.5 - 0.5 * math.cos(math.pi * k / 4.0)   # down over the bar, then up
        z = -0.06 - 0.16 * low
        d.key(b, ease="inout", **merge(
            hips(z=z, yaw=32.0 * side, pitch=6.0 + 10.0 * low),
            spine_twist=-48.0 * side, spine_bend=8.0 + 16.0 * low, head_turn=18.0 * side,
            foot_yaw_l=28.0 * side + 6.0, foot_yaw_r=28.0 * side - 6.0,
            **hands((0.26 + 0.1 * side, 0.30, -0.12), (0.26 - 0.1 * side, -0.30, -0.12),
                    (-0.6, 1.0, -0.4), (-0.6, -1.0, -0.4))))
    d.key(0, **feet(STANCE + 0.04, z_l=ANKLE_Z + 0.035, z_r=ANKLE_Z + 0.035))
    d.key(0, foot_pitch_l=22.0, foot_pitch_r=22.0, toe_l=22.0, toe_r=22.0)
    d.follow("head_turn", "spine_twist", gain=0.35, hz=2.8)
    return d


def raise_the_roof():
    """Palms up, pushing the roof up on every beat, the head nodding along."""
    d = Dance(bpm=100, beats=4)
    for k in range(8):
        b = k * 0.5
        up = k % 2 == 0
        z = 0.42 if up else 0.18
        d.key(b, ease="pop" if up else "inout", **merge(
            hands((0.10, 0.30, z), (0.10, -0.30, z), (-0.4, 1.0, -0.6), (-0.4, -1.0, -0.6)),
            wrist_l=(-75.0, 0.0, 0.0), wrist_r=(-75.0, 0.0, 0.0), head_nod=-8.0 if up else 4.0))
    d.key(0, **merge(feet(STANCE + 0.03), hips(z=-0.05)))
    d.overlay(groove(depth=0.035, per_beat=1, chest=3.0, nod=4.0))
    d.overlay(sway(amount=0.03, period=2.0, roll=4.0))
    return d


def robot():
    """The robot: stiff arms hit angular shapes on the beat and hold, the head clicks round, the knees lock and
    unlock."""
    d = Dance(bpm=104, beats=8)
    shapes = [
        ((70.0, 0.0, 90.0, 0.0), (70.0, 0.0, 90.0, 0.0), 0.0, 0.0),
        ((90.0, 0.0, 0.0, 0.0), (20.0, -10.0, 95.0, 90.0), 25.0, -10.0),
        ((20.0, -10.0, 95.0, 90.0), (90.0, 0.0, 0.0, 0.0), -25.0, 10.0),
        ((0.0, 0.0, 90.0, 90.0), (0.0, 0.0, 90.0, 90.0), 0.0, 0.0),
        ((0.0, 0.0, 90.0, -90.0), (0.0, 0.0, 90.0, -90.0), 0.0, 0.0),
        ((60.0, 30.0, 70.0, 0.0), (-30.0, -60.0, 10.0, 0.0), 35.0, 15.0),
        ((-30.0, -60.0, 10.0, 0.0), (60.0, 30.0, 70.0, 0.0), -35.0, -15.0),
        ((70.0, 0.0, 90.0, 0.0), (70.0, 0.0, 90.0, 0.0), 0.0, 0.0),
    ]
    for k, (left, right, turn, twist_) in enumerate(shapes):
        b = float(k)
        d.key(b, ease="snap", **merge(
            arms_fk(left, right), hips(z=-0.03 if k % 2 == 0 else -0.09),
            head_turn=turn, spine_twist=twist_ * 0.6, wrist_l=(0.0, 0.0, 0.0), wrist_r=(0.0, 0.0, 0.0)))
    d.key(0, **feet(STANCE + 0.02))
    return d


DANCES = {
    "string_swing": string_swing,
    "running_man": running_man,
    "disco_point": disco_point,
    "twist": twist,
    "raise_the_roof": raise_the_roof,
    "robot": robot,
}
