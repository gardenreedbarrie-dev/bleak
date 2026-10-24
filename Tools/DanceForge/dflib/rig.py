"""Turns a pose given as named controls into the canonical skeleton's world rotations.

Controls (all optional, `defaults()` lists them; angles in degrees, positions in hip heights):

- hips (x, y, z): offset of the hips from the rest position; hips_yaw, hips_pitch, hips_roll (turn left, tip
  forward, lean left).
- spine_bend, spine_side, spine_twist: the whole spine (forward, lean left, turn left), spread over Spine,
  Spine2 and Chest.
- head_nod, head_tilt, head_turn: head and neck together (nod down, tilt left, turn left).
- clav_up_l / clav_fwd_l (and _r): shoulder shrug and roll forward.
- hand_l / hand_r (x, y, z): wrist position in the chest's frame (origin at the Chest joint, turning with it);
  elbow_l / elbow_r: where the elbow points, also in the chest's frame. Two-bone IK places the arm.
- arm_l / arm_r (swing, raise, bend, twist): the arm by angles instead, in the chest's frame: swing forward from
  straight out to the side (90 points forward, -90 back), raise up (90 straight up, -90 down), elbow bend, twist
  of the elbow round the arm. ik_l / ik_r blend the two: 1 (the default) the hand position, 0 the angles.
- wrist_l / wrist_r (bend, side, twist): hand towards the palm, towards the thumb side, palm turning forward.
- foot_l / foot_r (x, y, z): ankle position in the dance's space (ground at z = 0); knee_l / knee_r: where the
  knee points (world). Two-bone IK places the leg.
- foot_yaw_l, foot_pitch_l, foot_roll_l (and _r): the foot's world turn left, toes down, lean left; toe_l,
  toe_r: toes bent up.
"""

import math

from . import quat as Q
from . import skeleton as S

J = S.INDEX

REST_HIPS = (0.0, 0.0, -0.025)          # knees a little soft, so the default stance never locks them
REST_HAND_L = (0.05, 0.29, -0.40)
REST_ELBOW_L = (-0.45, 0.25, -1.0)
REST_FOOT_L = (0.0, 0.115, 0.105)
TOE_OUT = 8.0


def _mirror_vec(v):
    return (v[0], -v[1], v[2])


def defaults():
    d = {
        "hips": REST_HIPS, "hips_yaw": 0.0, "hips_pitch": 0.0, "hips_roll": 0.0,
        "spine_bend": 0.0, "spine_side": 0.0, "spine_twist": 0.0,
        "head_nod": 0.0, "head_tilt": 0.0, "head_turn": 0.0,
    }
    for side, m in (("l", lambda v: v), ("r", _mirror_vec)):
        d["clav_up_" + side] = 0.0
        d["clav_fwd_" + side] = 0.0
        d["hand_" + side] = m(REST_HAND_L)
        d["elbow_" + side] = m(REST_ELBOW_L)
        d["wrist_" + side] = (0.0, 0.0, 0.0)
        d["arm_" + side] = (0.0, -75.0, 15.0, 0.0)
        d["ik_" + side] = 1.0
        d["foot_" + side] = m(REST_FOOT_L)
        yaw = TOE_OUT if side == "l" else -TOE_OUT
        d["knee_" + side] = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0)
        d["foot_yaw_" + side] = yaw
        d["foot_pitch_" + side] = 0.0
        d["foot_roll_" + side] = 0.0
        d["toe_" + side] = 0.0
    return d


VECTOR_CONTROLS = frozenset(k for k, v in defaults().items() if isinstance(v, tuple))

# How a control changes when a pose is mirrored left to right.
_NEGATE = {"hips_yaw", "hips_roll", "spine_side", "spine_twist", "head_tilt", "head_turn"}


def mirror_control(name, value):
    """(mirrored name, mirrored value) of one control."""
    if name.endswith("_l") or name.endswith("_r"):
        other = name[:-1] + ("r" if name.endswith("_l") else "l")
        base = name[:-2]
        if base in ("hand", "elbow", "foot", "knee"):
            return other, _mirror_vec(value)
        if base in ("wrist", "arm"):
            return other, value
        if base in ("foot_yaw", "foot_roll"):
            return other, -value
        return other, value
    if name == "hips":
        return name, _mirror_vec(value)
    if name in _NEGATE:
        return name, -value
    return name, value


def _axis_from_to(a, b):
    return Q.normalize(Q.cross(a, b))


def soft_reach(dist, reach):
    """Pulls targets the limb cannot reach in smoothly, so a straightening limb never snaps."""
    soft = reach * 0.985
    if dist <= soft:
        return dist
    span = reach - soft
    return soft + span * (1.0 - math.exp(-(dist - soft) / span))


def two_bone(root, target, l1, l2, pole):
    """Middle joint and end position of a two-bone limb from root towards target, bending towards pole."""
    d = Q.sub(target, root)
    dist = Q.length(d)
    u = Q.normalize(d, Q.normalize(pole))
    dist = min(max(soft_reach(dist, l1 + l2), abs(l1 - l2) + 1e-4), (l1 + l2) * 0.99995)
    cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
    cos_a = max(-1.0, min(1.0, cos_a))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    v = Q.sub(pole, Q.scale(u, Q.dot(pole, u)))
    if Q.length(v) < 1e-6:
        v = Q.cross(u, (0.0, 0.0, 1.0))
        if Q.length(v) < 1e-6:
            v = Q.cross(u, (1.0, 0.0, 0.0))
    v = Q.normalize(v)
    mid = Q.add(root, Q.add(Q.scale(u, l1 * cos_a), Q.scale(v, l1 * sin_a)))
    end = Q.add(root, Q.scale(u, dist))
    return mid, end, v


def _fk_arm(chest_rot, side, swing, raise_, bend, twist, rest_dir):
    """Upper arm and forearm world rotations of an arm posed by angles (see the module doc)."""
    sw, rs = math.radians(swing), math.radians(raise_)
    out = 1.0 if side == "L" else -1.0
    local_dir = (math.cos(rs) * math.sin(sw), out * math.cos(rs) * math.cos(sw), math.sin(rs))
    ref = (-1.0, 0.0, -0.6)
    pole = Q.sub(ref, Q.scale(local_dir, Q.dot(ref, local_dir)))
    if Q.length(pole) < 1e-4:
        pole = Q.sub((0.0, 0.0, -1.0), Q.scale(local_dir, local_dir[2]))
    pole = Q.normalize(pole)
    if twist:
        pole = Q.qrot(Q.qaxis(local_dir, twist * out), pole)
    b = math.radians(bend)
    fore = Q.normalize(Q.sub(Q.scale(local_dir, math.cos(b)), Q.scale(pole, math.sin(b))))
    a = Q.qrot(chest_rot, local_dir)
    v = Q.qrot(chest_rot, pole)
    f = Q.qrot(chest_rot, fore)
    upper = Q.qfrom_frames(rest_dir, S.ELBOW_REST, a, v)
    lower = Q.qmul(Q.qbetween(a, f), upper)
    return upper, lower


def _limb_rotations(root, target, l1, l2, pole, rest_dir, rest_pole):
    mid, end, v = two_bone(root, target, l1, l2, pole)
    a = Q.normalize(Q.sub(mid, root))
    f = Q.normalize(Q.sub(end, mid))
    vp = Q.sub(v, Q.scale(a, Q.dot(v, a)))
    vp = Q.normalize(vp, Q.normalize(Q.sub(Q.scale(a, Q.dot(f, a)), f)))
    upper = Q.qfrom_frames(rest_dir, rest_pole, a, vp)
    lower = Q.qmul(Q.qbetween(a, f), upper)
    return upper, lower


def solve(controls):
    """(hips position, world rotations of the 22 joints) for a dict of controls (missing ones take defaults)."""
    c = defaults()
    c.update(controls)
    rot = [Q.IDENTITY] * S.COUNT
    hips = Q.add(S.REST[J["Hips"]], c["hips"])
    rot[J["Hips"]] = Q.qeuler(c["hips_yaw"], c["hips_pitch"], c["hips_roll"])
    for name, share in (("Spine", 0.34), ("Spine2", 0.33), ("Chest", 0.33)):
        local = Q.qeuler(c["spine_twist"] * share, c["spine_bend"] * share, c["spine_side"] * share)
        rot[J[name]] = Q.qmul(rot[S.PARENT[J[name]]], local)
    for name, share in (("Neck", 0.4), ("Head", 0.6)):
        local = Q.qeuler(c["head_turn"] * share, c["head_nod"] * share, c["head_tilt"] * share)
        rot[J[name]] = Q.qmul(rot[S.PARENT[J[name]]], local)
    pos = S.positions(hips, rot)
    chest = J["Chest"]
    for side, sfx in (("L", "l"), ("R", "r")):
        clav = J["Clav" + side]
        bone = S.DIRECTION[clav]
        local = Q.qmul(Q.qaxis(_axis_from_to(bone, (1.0, 0.0, 0.0)), c["clav_fwd_" + sfx]),
                       Q.qaxis(_axis_from_to(bone, (0.0, 0.0, 1.0)), c["clav_up_" + sfx]))
        rot[clav] = Q.qmul(rot[chest], local)
        upper = J["UpperArm" + side]
        shoulder = Q.add(pos[clav], Q.qrot(rot[clav], Q.sub(S.REST[upper], S.REST[clav])))
        target = Q.add(pos[chest], Q.qrot(rot[chest], c["hand_" + sfx]))
        pole = Q.qrot(rot[chest], c["elbow_" + sfx])
        ik = min(1.0, max(0.0, c["ik_" + sfx]))
        if ik > 0.0:
            iu, il = _limb_rotations(shoulder, target, S.UPPER_ARM, S.FOREARM, pole, bone, S.ELBOW_REST)
        if ik < 1.0:
            fu, fl = _fk_arm(rot[chest], side, *c["arm_" + sfx], rest_dir=bone)
        if ik >= 1.0:
            rot[upper], rot[J["Forearm" + side]] = iu, il
        elif ik <= 0.0:
            rot[upper], rot[J["Forearm" + side]] = fu, fl
        else:
            rot[upper] = Q.qslerp(fu, iu, ik)
            rot[J["Forearm" + side]] = Q.qslerp(fl, il, ik)
        bend, side_dev, twist = c["wrist_" + sfx]
        local = Q.qmul(Q.qaxis(_axis_from_to((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)), twist),
                       Q.qmul(Q.qaxis(_axis_from_to(bone, (1.0, 0.0, 0.0)), side_dev),
                              Q.qaxis(_axis_from_to(bone, (0.0, 0.0, -1.0)), bend)))
        rot[J["Hand" + side]] = Q.qmul(rot[J["Forearm" + side]], local)
        thigh = J["Thigh" + side]
        hip_joint = Q.add(hips, Q.qrot(rot[J["Hips"]], Q.sub(S.REST[thigh], S.REST[J["Hips"]])))
        rot[thigh], rot[J["Calf" + side]] = _limb_rotations(hip_joint, c["foot_" + sfx], S.THIGH, S.CALF,
                                                            Q.normalize(c["knee_" + sfx]), S.DIRECTION[thigh],
                                                            S.KNEE_REST)
        foot = Q.qeuler(c["foot_yaw_" + sfx], c["foot_pitch_" + sfx], c["foot_roll_" + sfx])
        rot[J["Foot" + side]] = foot
        rot[J["Toe" + side]] = Q.qmul(foot, Q.qaxis((0.0, 1.0, 0.0), -c["toe_" + sfx]))
    return hips, [Q.qnormalize(q) for q in rot]
