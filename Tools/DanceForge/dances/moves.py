"""Building blocks the dances share: stances, hand shapes in the chest's frame and grooves."""

import math

from dflib.choreo import bounce

# Feet (ankle positions, ground at z = 0; the rig's rest stance has them at y = +-0.115).
ANKLE_Z = 0.105
STANCE = 0.13          # a relaxed dance stance, a little wider than the rest pose
WIDE = 0.2


def feet(width=STANCE, x_l=0.0, x_r=0.0, z_l=ANKLE_Z, z_r=ANKLE_Z):
    return {"foot_l": (x_l, width, z_l), "foot_r": (x_r, -width, z_r)}


def hips(x=0.0, y=0.0, z=-0.05, **angles):
    out = {"hips": (x, y, z)}
    for k, v in angles.items():
        out["hips_" + k] = v
    return out


def arms_fk(left=None, right=None):
    """Arms by angles (swing, raise, bend, twist); None leaves an arm on its hand position."""
    out = {}
    if left is not None:
        out["ik_l"] = 0.0
        out["arm_l"] = left
    if right is not None:
        out["ik_r"] = 0.0
        out["arm_r"] = right
    return out


def hands(left=None, right=None, elbow_l=None, elbow_r=None):
    """Hands by position in the chest's frame; elbows say where the elbow points."""
    out = {}
    if left is not None:
        out["ik_l"] = 1.0
        out["hand_l"] = left
    if right is not None:
        out["ik_r"] = 1.0
        out["hand_r"] = right
    if elbow_l is not None:
        out["elbow_l"] = elbow_l
    if elbow_r is not None:
        out["elbow_r"] = elbow_r
    return out


def merge(*parts, **extra):
    out = {}
    for p in parts:
        out.update(p)
    out.update(extra)
    return out


def groove(depth=0.03, per_beat=1, sharp=2.0, chest=2.5, nod=3.0, lag=0.12):
    """The bounce every dance rides on: the hips drop on the beat (the knees follow through the leg IK), the chest
    pops a little and the head nods a moment later."""
    def fn(beat):
        b = bounce(beat * per_beat, sharp)
        late = bounce(beat * per_beat - lag, sharp)
        return {"hips": (0.0, 0.0, -depth * b), "spine_bend": chest * b, "head_nod": nod * late}
    return fn


def sway(amount=0.03, period=2.0, roll=3.0, offset=0.0):
    """Weight shifting from foot to foot over `period` beats."""
    def fn(beat):
        s = math.sin(2.0 * math.pi * (beat / period + offset))
        return {"hips": (0.0, amount * s, 0.0), "hips_roll": -roll * s, "spine_side": roll * 0.8 * s}
    return fn
