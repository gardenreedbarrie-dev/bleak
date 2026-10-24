"""The canonical dance skeleton: 22 joints in a T-pose, in units of the hip-joint height, WoW axes.

A dance clip stores, for every frame, the hips position and each joint's world rotation relative to this rest
pose. Bleakhold.exe maps the joints onto each character model's bones (Engine/Source/Model2/BleakDance.cpp holds
the same table; tests/test_agreement.py checks that both agree). Proportions are a human male's, scaled so the
hip joints are at height 1.
"""

from . import quat as Q

JOINTS = (
    "Hips", "Spine", "Spine2", "Chest", "Neck", "Head",
    "ClavL", "UpperArmL", "ForearmL", "HandL",
    "ClavR", "UpperArmR", "ForearmR", "HandR",
    "ThighL", "CalfL", "FootL", "ToeL",
    "ThighR", "CalfR", "FootR", "ToeR",
)
INDEX = {name: i for i, name in enumerate(JOINTS)}
COUNT = len(JOINTS)

PARENT = (-1, 0, 1, 2, 3, 4,
          3, 6, 7, 8,
          3, 10, 11, 12,
          0, 14, 15, 16,
          0, 18, 19, 20)

REST = (
    (0.0, 0.0, 1.0), (0.0, 0.0, 1.11), (0.0, 0.0, 1.23), (0.0, 0.0, 1.37), (0.0, 0.0, 1.66), (0.0, 0.0, 1.78),
    (0.0, 0.04, 1.61), (0.0, 0.25, 1.57), (0.0, 0.605, 1.57), (0.0, 0.895, 1.57),
    (0.0, -0.04, 1.61), (0.0, -0.25, 1.57), (0.0, -0.605, 1.57), (0.0, -0.895, 1.57),
    (0.0, 0.115, 1.0), (0.0, 0.115, 0.58), (0.0, 0.115, 0.105), (0.21, 0.115, 0.02),
    (0.0, -0.115, 1.0), (0.0, -0.115, 0.58), (0.0, -0.115, 0.105), (0.21, -0.115, 0.02),
)

# Rest direction of each joint's bone and the second axis that fixes its roll (both world). The client aligns a
# model's bind pose to these: the bone from a joint to its main child onto `direction`, `roll` as the up axis.
_UP, _FWD, _LEFT, _RIGHT, _DOWN = (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)
FOOT_DIRECTION = Q.normalize((0.21, 0.0, -0.085))
DIRECTION = (
    _UP, _UP, _UP, _UP, _UP, _UP,
    _LEFT, _LEFT, _LEFT, _LEFT,
    _RIGHT, _RIGHT, _RIGHT, _RIGHT,
    _DOWN, _DOWN, FOOT_DIRECTION, _FWD,
    _DOWN, _DOWN, FOOT_DIRECTION, _FWD,
)
ROLL = (
    _FWD, _FWD, _FWD, _FWD, _FWD, _FWD,
    _FWD, _FWD, _FWD, _FWD,
    _FWD, _FWD, _FWD, _FWD,
    _FWD, _FWD, _UP, _UP,
    _FWD, _FWD, _UP, _UP,
)

# Where the elbows and knees point in the rest pose (the bend direction): elbows back, knees forward.
ELBOW_REST = (-1.0, 0.0, 0.0)
KNEE_REST = (1.0, 0.0, 0.0)


def bone_length(a, b):
    return Q.length(Q.sub(REST[INDEX[b]], REST[INDEX[a]]))


UPPER_ARM = bone_length("UpperArmL", "ForearmL")
FOREARM = bone_length("ForearmL", "HandL")
THIGH = bone_length("ThighL", "CalfL")
CALF = bone_length("CalfL", "FootL")


def positions(hips, rotations):
    """World position of every joint for a hips position and world rotations (forward kinematics)."""
    out = [None] * COUNT
    for i in range(COUNT):
        p = PARENT[i]
        if p < 0:
            out[i] = hips
        else:
            out[i] = Q.add(out[p], Q.qrot(rotations[p], Q.sub(REST[i], REST[p])))
    return out


def mirror_name(name):
    if name.endswith("L") and name[:-1] + "R" in INDEX:
        return name[:-1] + "R"
    if name.endswith("R") and name[:-1] + "L" in INDEX:
        return name[:-1] + "L"
    return name
