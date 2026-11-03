"""Reference implementation of Bleakhold.exe's dance retargeting (Engine/Source/Model2/BleakDance.cpp).

`build_rig(bones, key_bones)` maps the canonical skeleton onto a character model's bones; `pose_bones(rig, ...)`
turns one clip frame into the model-space rotation of every mapped bone and the hips offset; `local_overrides`
gives the local transform the client puts in place of the bone's animation. The tests compare the C++ code with
this one, and the preview tool (preview.py) renders through it.

A bone is a dict: parent (-1 for none), pivot (x, y, z), key_bone (-1 for none), animated (bool: the client
animates it, M2 bone flags 0x280, and none of the spherical/cylindrical flags 0x7 or billboard flags 0x78).
key_bones maps key bone ids to bone indices (the M2's key-bone lookup).
"""

import math

from . import quat as Q
from . import skeleton as S

KB_ARM_L, KB_ARM_R, KB_SHOULDER_L, KB_SHOULDER_R, KB_SPINE_LOW, KB_HEAD = 0, 1, 2, 3, 4, 6
KB_FINGERS_R = (8, 9, 10, 11, 12)
KB_FINGERS_L = (13, 14, 15, 16, 17)
KB_ROOT = 26

# Rule kinds of a mapped bone.
MAP, SPINE, NECK, RIGID, PELVIS, ROOT, STILL = "map", "spine", "neck", "rigid", "pelvis", "root", "still"

SAME_PIVOT = 1e-3
SIDE_FRACTION = 0.04       # a leg bone is at least this far (in hip heights) off the centre line
FOOT_FRACTION = 0.25       # the lowest leg bone is at most this high


class Rig:
    def __init__(self):
        self.ok = False
        self.reason = ""
        self.rules = {}            # bone -> (kind, joint or fraction, alignment quaternion) ; RIGID: (kind, owner bone)
        self.root = -1
        self.scale = 1.0           # model units per canonical hip height
        self.legs = {}             # "L"/"R" -> (thigh, calf, foot) bones
        self.has_legs = False


def _ancestors(bones, i):
    out = []
    guard = 0
    while i >= 0 and guard <= len(bones):
        out.append(i)
        i = bones[i]["parent"]
        guard += 1
    return out


def _lca(bones, ids):
    first = _ancestors(bones, ids[0])
    common = set(first)
    for x in ids[1:]:
        common &= set(_ancestors(bones, x))
    for a in first:
        if a in common:
            return a
    return -1


def _path(bones, top, bottom):
    """Bones from top down to bottom, both included; None when bottom does not descend from top."""
    out = []
    i = bottom
    guard = 0
    while i >= 0 and i != top and guard <= len(bones):
        out.append(i)
        i = bones[i]["parent"]
        guard += 1
    if i != top:
        return None
    out.append(top)
    out.reverse()
    return out


def _piv(bones, i):
    return bones[i]["pivot"]


def _align(bones, bone, toward, joint):
    """Rotation taking the bone's bind direction (bone pivot towards `toward`) onto the joint's rest direction."""
    d = Q.sub(toward, _piv(bones, bone))
    if Q.length(d) < 1e-6:
        return Q.IDENTITY
    return Q.qfrom_frames(d, S.ROLL[joint], S.DIRECTION[joint], S.ROLL[joint])


def build_rig(bones, key_bones):
    rig = Rig()

    def kb(k):
        if 0 <= k < len(key_bones):
            b = key_bones[k]
            if 0 <= b < len(bones):
                return b
        return -1

    def fail(reason):
        rig.reason = reason
        rig.rules = {}
        return rig

    root, spine_low, head = kb(KB_ROOT), kb(KB_SPINE_LOW), kb(KB_HEAD)
    clav = {"L": kb(KB_SHOULDER_L), "R": kb(KB_SHOULDER_R)}
    upper = {"L": kb(KB_ARM_L), "R": kb(KB_ARM_R)}
    if min(root, spine_low, head, clav["L"], clav["R"], upper["L"], upper["R"]) < 0:
        return fail("missing key bones")
    if root not in _ancestors(bones, spine_low) or root == spine_low:
        return fail("SpineLow is not below Root")
    chest = _lca(bones, [clav["L"], clav["R"]])
    spine = _path(bones, spine_low, chest) if chest >= 0 else None
    if spine is None:
        return fail("no spine from SpineLow to the shoulders")
    neck_path = _path(bones, chest, head)
    if neck_path is None or len(neck_path) < 2:
        return fail("the head is not below the chest")
    neck = neck_path[1:-1]
    hip_height = _piv(bones, root)[2]
    if hip_height <= 1e-3:
        return fail("Root is at or below the ground")

    arms = {}
    for side, fingers in (("L", KB_FINGERS_L), ("R", KB_FINGERS_R)):
        f = [x for x in (kb(k) for k in fingers) if x >= 0]
        if len(f) < 2:
            return fail("not enough finger key bones (%s)" % side)
        hand = _lca(bones, f)
        if hand < 0 or _path(bones, clav[side], upper[side]) is None:
            return fail("arm chain broken (%s)" % side)
        chain = _path(bones, upper[side], hand)
        if chain is None or len(chain) < 3:
            return fail("no forearm (%s)" % side)
        forearm, best = -1, -1.0
        for x in chain[1:-1]:
            dist = Q.length(Q.sub(_piv(bones, x), _piv(bones, upper[side])))
            if Q.length(Q.sub(_piv(bones, x), _piv(bones, hand))) > SAME_PIVOT and dist > best:
                forearm, best = x, dist
        if forearm < 0:
            return fail("no forearm (%s)" % side)
        arms[side] = (clav[side], upper[side], forearm, hand, chain)

    # Legs: below Root but outside the upper body, the lowest animated bone on each side.
    children = [[] for _ in bones]
    for i, b in enumerate(bones):
        if 0 <= b["parent"] < len(bones):
            children[b["parent"]].append(i)
    upper_body = set()
    stack = [spine_low]
    while stack:
        x = stack.pop()
        if x not in upper_body:
            upper_body.add(x)
            stack.extend(children[x])
    lower = []
    stack = [root]
    seen = set()
    while stack:
        x = stack.pop()
        if x in upper_body or x in seen:
            continue
        seen.add(x)
        lower.append(x)
        stack.extend(children[x])
    lower.sort()
    legs = {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        cands = [x for x in lower if bones[x]["animated"] and sign * _piv(bones, x)[1] > SIDE_FRACTION * hip_height]
        if not cands:
            break
        low = min(cands, key=lambda x: (round(_piv(bones, x)[2], 4), -_piv(bones, x)[0], x))
        if _piv(bones, low)[2] > FOOT_FRACTION * hip_height:
            break
        chain = _path(bones, root, low)
        groups = []
        for x in chain[1:]:
            if groups and Q.length(Q.sub(_piv(bones, x), _piv(bones, groups[-1][-1]))) < SAME_PIVOT:
                groups[-1].append(x)
            else:
                groups.append([x])
        hip = next((k for k, g in enumerate(groups) if sign * _piv(bones, g[-1])[1] > SIDE_FRACTION * hip_height), -1)
        if hip < 0 or len(groups) - hip < 4:
            break
        legs[side] = (groups[:hip], groups[hip:])
    rig.has_legs = len(legs) == 2

    rules = rig.rules
    rules[root] = (ROOT, S.INDEX["Hips"], Q.IDENTITY)
    total = 0.0
    marks = [0.0]
    for a, b in zip(spine[:-1], spine[1:]):
        total += Q.length(Q.sub(_piv(bones, b), _piv(bones, a)))
        marks.append(total)
    neck_base = neck[0] if neck else head
    for k, bone in enumerate(spine):
        nxt = spine[k + 1] if k + 1 < len(spine) else neck_base
        frac = marks[k] / total if total > 1e-6 else (1.0 if k else 0.0)
        rules[bone] = (SPINE, frac, _align(bones, bone, _piv(bones, nxt), S.INDEX["Spine"]))
    for k, bone in enumerate(neck):
        nxt = neck[k + 1] if k + 1 < len(neck) else head
        rules[bone] = (NECK, (k + 1.0) / (len(neck) + 1.0), _align(bones, bone, _piv(bones, nxt), S.INDEX["Neck"]))
    rules[head] = (MAP, S.INDEX["Head"], Q.IDENTITY)
    for side in "LR":
        c, u, f, h, chain = arms[side]
        rules[c] = (MAP, S.INDEX["Clav" + side], _align(bones, c, _piv(bones, u), S.INDEX["Clav" + side]))
        rules[u] = (MAP, S.INDEX["UpperArm" + side], _align(bones, u, _piv(bones, f), S.INDEX["UpperArm" + side]))
        rules[f] = (MAP, S.INDEX["Forearm" + side], _align(bones, f, _piv(bones, h), S.INDEX["Forearm" + side]))
        rules[h] = (MAP, S.INDEX["Hand" + side], rules[f][2])
        for x in chain[1:-1]:
            if x not in rules:
                owner = u if _path(bones, u, x) is not None and _path(bones, x, f) is not None else f
                rules[x] = (RIGID, owner, None)
    if rig.has_legs:
        for side in "LR":
            pelvis, groups = legs[side]
            for g in pelvis:
                for x in g:
                    rules[x] = (PELVIS, S.INDEX["Hips"], Q.IDENTITY)
            hip, knee, ankle, toe = groups[0], groups[1], groups[-2], groups[-1]
            j = S.INDEX
            rules[hip[-1]] = (MAP, j["Thigh" + side], _align(bones, hip[-1], _piv(bones, knee[-1]), j["Thigh" + side]))
            rules[knee[-1]] = (MAP, j["Calf" + side], _align(bones, knee[-1], _piv(bones, ankle[-1]), j["Calf" + side]))
            rules[ankle[-1]] = (MAP, j["Foot" + side], _align(bones, ankle[-1], _piv(bones, toe[-1]), j["Foot" + side]))
            rules[toe[-1]] = (MAP, j["Toe" + side], rules[ankle[-1]][2])
            for g in (hip, knee, ankle, toe):
                for x in g[:-1]:
                    rules[x] = (STILL, 0, Q.IDENTITY)
            for g in groups[2:-2]:
                for x in g:
                    rules[x] = (RIGID, knee[-1], None)
            rig.legs[side] = (hip[-1], knee[-1], ankle[-1])
        thighs = [_piv(bones, rig.legs[s][0])[2] for s in "LR"]
        rig.scale = sum(thighs) / 2.0
    else:
        rig.scale = hip_height
    for bone, rule in rules.items():
        if not bones[bone]["animated"]:
            return fail("bone %d is mapped but not animated" % bone)
        if rule[0] == RIGID and (rule[1] not in rules or rules[rule[1]][0] == RIGID):
            return fail("rigid bone without an owner")
    rig.root = root
    rig.bones = bones
    rig.ok = True
    return rig


def _spine_rot(rots, frac):
    a, b, c = rots[S.INDEX["Spine"]], rots[S.INDEX["Spine2"]], rots[S.INDEX["Chest"]]
    if frac <= 0.5:
        return Q.qslerp(a, b, frac * 2.0)
    return Q.qslerp(b, c, (frac - 0.5) * 2.0)


def pose_bones(rig, hips, rots):
    """Model-space rotation of every mapped bone (dict) and the hips offset in model units."""
    out = {}
    for bone, rule in rig.rules.items():
        kind = rule[0]
        if kind in (MAP, ROOT, PELVIS):
            out[bone] = Q.qmul(rots[rule[1]], rule[2])
        elif kind == SPINE:
            out[bone] = Q.qmul(_spine_rot(rots, rule[1]), rule[2])
        elif kind == NECK:
            out[bone] = Q.qmul(Q.qslerp(rots[S.INDEX["Neck"]], rots[S.INDEX["Head"]], rule[1] * 0.5), rule[2])
    for bone, rule in rig.rules.items():
        if rule[0] == RIGID:
            out[bone] = out[rule[1]]
    offset = Q.scale(Q.sub(hips, S.REST[S.INDEX["Hips"]]), rig.scale)
    return out, offset


def local_overrides(rig, targets, offset, stock_local):
    """Local (rotation, translation) of every bone in index order, given the model-space targets of the mapped
    bones and stock_local(i) -> (rotation, translation) for the others. Mirrors the client's bone loop."""
    bones = rig.bones
    world = [Q.IDENTITY] * len(bones)
    out = []
    for i, b in enumerate(bones):
        p = b["parent"]
        prot = world[p] if 0 <= p < i else Q.IDENTITY
        rule = rig.rules.get(i)
        if rule is None:
            r, t = stock_local(i)
            world[i] = Q.qmul(prot, r)
            out.append((r, t))
            continue
        if rule[0] == STILL:
            world[i] = prot
            out.append((Q.IDENTITY, (0.0, 0.0, 0.0)))
            continue
        g = targets[i]
        world[i] = g
        local = Q.qmul(Q.qconj(prot), g)
        t = (0.0, 0.0, 0.0)
        if i == rig.root:
            t = Q.qrot(Q.qconj(prot), offset)
        out.append((Q.qnormalize(local), t))
    return out
