"""Made-up character skeletons laid out like 3.3.5a character models (no game data): the tests run the rig on these.

skeleton(**options) -> (bones, key_bones) in the form dflib.retarget.build_rig takes. The layout follows what the
client's key bones say about a character model: Root (key bone 26) above a pelvis bone that holds the legs,
SpineLow (key bone 4) starting the upper body, clavicles (2, 3), upper arms (0, 1), finger key bones (8 to 17) under
the hands, the head (6); helper bones at the elbows, knees and wrists and twin bones at the ankles, as the real
models have them. Options change proportions and shape so the tests cover the variety of races.
"""

NONE = 0xFFFF


class Builder:
    def __init__(self):
        self.bones = []
        self.keys = [NONE] * 27

    def add(self, parent, pivot, key=None, animated=True):
        self.bones.append(dict(parent=parent, pivot=tuple(float(x) for x in pivot), animated=animated))
        i = len(self.bones) - 1
        if key is not None:
            self.keys[key] = i
        return i


def skeleton(scale=1.0, hunch=0.0, digitigrade=False, legs=True, fingers=5, neck_bones=2, spine_bones=3,
             arm_drop=0.3, helpers=True, drop_key=None, forward=0.0):
    """scale: overall size (a gnome is about 0.35); hunch: forward lean of the upper spine (model units per unit of
    height); digitigrade: an extra leg segment (tauren, draenei); legs False: a tail instead (naga); fingers: finger key
    bones per hand; arm_drop: how far the bind-pose arms hang (0 straight out, 1 straight down); drop_key: leave
    that key bone out (for the failure tests); forward: everything shifted along x."""
    b = Builder()
    s = scale

    def p(x, y, z):
        return (forward + x * s, y * s, z * s)

    still = b.add(-1, p(0, 0, 0), animated=False)
    root = b.add(still, p(0.05, 0.0, 1.125), key=26)
    pelvis = b.add(root, p(0.05, 0.0, 1.11))
    spine_low = b.add(root, p(0.057, 0.0, 1.158), key=4)
    b.add(pelvis, p(0.18, 0.0, 1.10))                          # tabard front
    b.add(pelvis, p(-0.12, 0.0, 1.14))                         # tabard back / cape
    for k in range(4):                                         # bones the client never animates
        b.add(spine_low, p(0.057, 0.0, 1.158), animated=False)
    if legs:
        for sign in (-1.0, 1.0):
            thigh = b.add(pelvis, p(0.03, 0.12 * sign, 1.04))
            if helpers:
                b.add(thigh, p(0.0, 0.165 * sign, 0.60))       # knee helper
            knee = b.add(thigh, p(0.0, 0.165 * sign, 0.60))
            b.add(knee, p(0.0, 0.165 * sign, 0.60))            # knee attachment helper
            if digitigrade:
                hock = b.add(knee, p(-0.07, 0.2 * sign, 0.48))
                b.add(knee, p(-0.07, 0.2 * sign, 0.48))
                ankle_parent = hock
                ankle_pos = p(-0.04, 0.22 * sign, 0.30)
                toe_pos = p(0.24, 0.22 * sign, 0.11)
            else:
                ankle_parent = knee
                ankle_pos = p(-0.09, 0.215 * sign, 0.112)
                toe_pos = p(0.125, 0.215 * sign, 0.025)
            twin = b.add(ankle_parent, ankle_pos)              # the ankle twin the real models have
            ankle = b.add(twin, ankle_pos)
            b.add(ankle, toe_pos)
    else:
        tail = pelvis
        for k in range(6):
            tail = b.add(tail, p(-0.05, 0.0, 0.9 - 0.3 * k))
    # spine up to the chest, leaning forward by `hunch`
    prev = spine_low
    heights = [1.158 + (1.43 - 1.158) * (k + 1) / spine_bones for k in range(spine_bones)]
    for z in heights:
        prev = b.add(prev, p(0.05 + hunch * (z - 1.158), 0.0, z))
    chest = prev
    top = 1.43
    lean = hunch * (top - 1.158)
    for sign, ckey, ukey, side in ((1.0, 2, 0, "L"), (-1.0, 3, 1, "R")):
        clav = b.add(chest, p(0.03 + lean, 0.043 * sign, 1.675), key=ckey)
        shoulder = (-0.048 + lean, 0.259 * sign, 1.633)
        upper = b.add(clav, p(*shoulder), key=ukey)
        # elbow and wrist: arm_drop 0 points the arm straight out, 1 straight down
        reach = 0.37
        elbow = (shoulder[0] - 0.05, shoulder[1] + sign * reach * (1 - arm_drop), shoulder[2] - reach * arm_drop)
        wrist = (elbow[0] + 0.04, elbow[1] + sign * 0.3 * (1 - arm_drop), elbow[2] - 0.3 * arm_drop)
        if helpers:
            b.add(upper, p(*elbow))                            # elbow helper
            b.add(upper, p(*[(a + c) / 2 for a, c in zip(shoulder, elbow)]))   # bicep twist
        forearm = b.add(upper, p(*elbow))
        if helpers:
            b.add(forearm, p(*[(a + c) / 2 for a, c in zip(elbow, wrist)]))     # forearm twist
            b.add(forearm, p(*wrist))                          # wrist helper
        hand = b.add(forearm, p(*wrist))
        first = 13 if side == "L" else 8
        tip = (wrist[0] + 0.03, wrist[1] + sign * 0.09 * (1 - arm_drop), wrist[2] - 0.09 * arm_drop)
        for f in range(fingers):
            b.add(hand, p(tip[0] - 0.02 * f, tip[1], tip[2] - 0.01 * f), key=first + f)
        b.add(hand, p(0, 0, 0))                                # weapon attachment helper at the origin
    prev = chest
    for k in range(neck_bones):
        prev = b.add(prev, p(-0.02 + lean, 0.0, 1.727 + 0.06 * k))
    head = b.add(prev, p(lean, 0.0, 1.848), key=6)
    b.add(head, p(0.06 + lean, 0.0, 1.86), key=7)              # jaw
    for k in range(5):                                         # face and hair
        b.add(head, p(0.14 + lean, 0.03 * (k - 2), 1.88 + 0.01 * k))
    b.add(-1, p(-0.08, 0.0, 2.24), key=22)                     # name plate bone, outside the skeleton
    if drop_key is not None:
        b.keys[drop_key] = NONE
    return b.bones, b.keys


def to_text(bones, keys, frames):
    """The input of dance_core_test --rig."""
    lines = ["bones %d" % len(bones)]
    lines += ["%d %r %r %r %d" % (bn["parent"], bn["pivot"][0], bn["pivot"][1], bn["pivot"][2], 1 if bn["animated"] else 0)
              for bn in bones]
    lines += ["keys %d" % len(keys), " ".join(str(k) for k in keys)]
    lines += ["frames %d" % len(frames)]
    for hips, rots in frames:
        lines.append(" ".join(repr(float(x)) for x in list(hips) + [c for q in rots for c in q]))
    return "\n".join(lines) + "\n"
