"""Vectors and quaternions as plain tuples (standard library only).

Quaternions are (x, y, z, w) and act as active rotations: qrot(q, v) turns v by q, and qmul(a, b) is "b, then a".
That is also how the client reads them (C44Matrix::FromQuaternion with row vectors), so a world rotation written
here means the same in Bleakhold.exe. Axes are WoW's: +x forward, +y left, +z up.
"""

import math

IDENTITY = (0.0, 0.0, 0.0, 1.0)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def normalize(a, fallback=(1.0, 0.0, 0.0)):
    n = length(a)
    if n < 1e-12:
        return fallback
    return (a[0] / n, a[1] / n, a[2] / n)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qnormalize(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if n < 1e-12:
        return IDENTITY
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def qrot(q, v):
    # v + 2w (u x v) + 2 u x (u x v), u = vector part
    u = (q[0], q[1], q[2])
    t = scale(cross(u, v), 2.0)
    return add(add(v, scale(t, q[3])), cross(u, t))


def qaxis(axis, degrees):
    axis = normalize(axis)
    h = math.radians(degrees) * 0.5
    s = math.sin(h)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(h))


def qdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


def qslerp(a, b, t):
    d = qdot(a, b)
    if d < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        d = -d
    if d > 0.9995:
        return qnormalize(tuple(a[i] + (b[i] - a[i]) * t for i in range(4)))
    th = math.acos(min(1.0, d))
    s = math.sin(th)
    wa = math.sin((1.0 - t) * th) / s
    wb = math.sin(t * th) / s
    return tuple(a[i] * wa + b[i] * wb for i in range(4))


def qangle(a, b):
    """Angle in degrees between two rotations."""
    d = min(1.0, abs(qdot(qnormalize(a), qnormalize(b))))
    return math.degrees(2.0 * math.acos(d))


def qfrom_basis(x, y, z):
    """The rotation whose columns (images of the x, y and z axes) are x, y, z (an orthonormal right-handed basis)."""
    m00, m10, m20 = x
    m01, m11, m21 = y
    m02, m12, m22 = z
    t = m00 + m11 + m22
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    return qnormalize(q)


def frame(primary, secondary):
    """Orthonormal basis: x along primary, y as close to secondary as possible. None when they are parallel."""
    x = normalize(primary)
    y = sub(secondary, scale(x, dot(secondary, x)))
    if length(y) < 1e-6:
        return None
    y = normalize(y)
    return x, y, cross(x, y)


def qfrom_frames(from_primary, from_secondary, to_primary, to_secondary):
    """The rotation taking frame(from_primary, from_secondary) onto frame(to_primary, to_secondary)."""
    fa = frame(from_primary, from_secondary)
    fb = frame(to_primary, to_secondary)
    if fa is None or fb is None:
        return qbetween(from_primary, to_primary)
    qa = qfrom_basis(*fa)
    qb = qfrom_basis(*fb)
    return qnormalize(qmul(qb, qconj(qa)))


def qbetween(a, b):
    """The shortest rotation taking direction a onto direction b."""
    a = normalize(a)
    b = normalize(b)
    d = dot(a, b)
    if d > 0.999999:
        return IDENTITY
    if d < -0.999999:
        axis = cross(a, (1.0, 0.0, 0.0))
        if length(axis) < 1e-6:
            axis = cross(a, (0.0, 1.0, 0.0))
        return qaxis(axis, 180.0)
    c = cross(a, b)
    return qnormalize((c[0], c[1], c[2], 1.0 + d))


def qeuler(yaw=0.0, pitch=0.0, roll=0.0):
    """Turn left by yaw (about +z), then tip forward by pitch (about +y), then lean left by roll, in degrees."""
    q = IDENTITY
    if yaw:
        q = qaxis((0.0, 0.0, 1.0), yaw)
    if pitch:
        q = qmul(q, qaxis((0.0, 1.0, 0.0), pitch))
    if roll:
        q = qmul(q, qaxis((1.0, 0.0, 0.0), -roll))
    return q
