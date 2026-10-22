"""Runs vs_3_0 bytecode (the subset the stand-in and the patched grass shader use) on vertices in float32, and
compares the patched shader with an independent reference of the wind (WarcraftXL's model): the patched o0 must
be the stock projection of the stock view position plus the reference offset turned into view space.

    python3 -I emulate.py <tests dir> <test_grasswind binary>"""
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

f32 = np.float32


def tokens(path):
    return np.fromfile(path, dtype=np.uint32)


def regtype(p):
    return ((p >> 28) & 7) | ((p >> 8) & 0x18)


def run(code, inputs, consts):
    """inputs: dict reg -> (N,4) float32; consts: (256,4). Returns dict of outputs o# -> (N,4)."""
    n = next(iter(inputs.values())).shape[0]
    regs = {0: np.zeros((32, n, 4), f32), 1: {k: v.astype(f32) for k, v in inputs.items()}, 6: np.zeros((12, n, 4), f32)}
    defs = {}
    i = 1
    while i < len(code):
        t = int(code[i])
        op = t & 0xFFFF
        if op == 0xFFFE:
            i += 1 + ((t >> 16) & 0x7FFF)
            continue
        if op == 0xFFFF:
            break
        ln = (t >> 24) & 0xF
        p = [int(x) for x in code[i + 1:i + 1 + ln]]
        i += 1 + ln
        if op == 31:   # dcl
            continue
        if op == 81:
            defs[p[0] & 0x7FF] = np.frombuffer(np.array(p[1:5], np.uint32).tobytes(), f32)
            continue

        def src(tok):
            ty, num = regtype(tok), tok & 0x7FF
            if ty == 0:
                v = regs[0][num]
            elif ty == 1:
                v = regs[1][num]
            elif ty == 2:
                v = np.broadcast_to(defs.get(num, consts[num]).astype(f32), (n, 4))
            else:
                raise ValueError(f"src type {ty}")
            sw = (tok >> 16) & 0xFF
            v = v[:, [(sw >> (2 * k)) & 3 for k in range(4)]]
            mod = (tok >> 24) & 0xF
            if mod == 1:
                v = -v
            elif mod != 0:
                raise ValueError(f"modifier {mod}")
            return v.astype(f32)

        d = p[0]
        s = [src(x) for x in p[1:]]
        if op == 1:
            r = s[0]
        elif op == 2:
            r = s[0] + s[1]
        elif op == 4:
            r = s[0] * s[1] + s[2]
        elif op == 5:
            r = s[0] * s[1]
        elif op == 6:
            r = np.repeat((f32(1) / s[0][:, :1]), 4, 1)
        elif op == 7:
            r = np.repeat((f32(1) / np.sqrt(np.abs(s[0][:, :1]))), 4, 1)
        elif op == 8:
            r = np.repeat((s[0][:, :3] * s[1][:, :3]).sum(1, keepdims=True), 4, 1)
        elif op == 9:
            r = np.repeat((s[0] * s[1]).sum(1, keepdims=True), 4, 1)
        elif op == 12:
            r = (s[0] < s[1]).astype(f32)
        elif op == 19:
            r = s[0] - np.floor(s[0])
        elif op == 35:
            r = np.abs(s[0])
        elif op == 36:
            l = np.sqrt((s[0][:, :3] ** 2).sum(1, keepdims=True))
            r = s[0] / l
        elif op == 37:
            a = s[0][:, :1]
            r = np.concatenate([np.cos(a), np.sin(a), np.zeros((n, 2), f32)], 1)
        else:
            raise ValueError(f"opcode {op}")
        r = r.astype(f32)
        if (d >> 20) & 1:
            r = np.clip(r, 0, 1)
        mask = [(d >> (16 + k)) & 1 for k in range(4)]
        ty, num = regtype(d), d & 0x7FF
        dst = regs[0][num] if ty == 0 else regs[6][num]
        for k in range(4):
            if mask[k]:
                dst[:, k] = r[:, k]
    return {k: regs[6][k].copy() for k in range(4)}


def view_matrix(yaw, pitch):
    """Row-vector view rotation (rows = images of the world x, y, z axes), like a camera turned by yaw/pitch,
    with WoW's axis swap (view z forward)."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    fwd = np.array([cy * cp, sy * cp, sp])
    right = np.array([sy, -cy, 0.0])
    up = np.cross(fwd, right)
    # view x = right, y = up, z = forward: p_view = p_world @ M with M columns right, up, fwd
    return np.stack([right, up, fwd], 1)


def main():
    rng = np.random.default_rng(7)
    cam = np.array([100.5, -2000.25, 50.0])
    player = np.array([103.0, -1996.0, 48.0])
    M = view_matrix(0.7, -0.25)
    chunk = np.array([95.0, -2005.0, 46.0])
    n = 4000
    local = np.concatenate([rng.uniform(0, 14, (n, 2)), rng.uniform(0, 3.5, (n, 1))], 1)
    uv = rng.uniform(0, 1, (n, 2))
    world = chunk + local
    worldView = np.zeros((4, 4))
    worldView[:3, :3] = M
    worldView[3, :3] = (chunk - cam) @ M
    worldView[3, 3] = 1
    proj = np.array([[1.2, 0, 0, 0], [0, 1.6, 0, 0], [0, 0, 1.0002, 1], [0, 0, -0.2, 0]])
    consts = np.zeros((256, 4), f32)
    consts[0:4] = worldView
    consts[4:8] = proj
    consts[8] = (-0.01, 1.2, 0, 0)
    consts[9] = (-0.1, 7, 0, 0)
    consts[10] = (0.3, 0.5, 0.8, 1)
    consts[11] = (0.4, 0.4, 0.4, 1)
    consts[12] = (0.6, 0.6, 0.5, 1)
    inputs = {0: np.concatenate([local, np.ones((n, 1))], 1), 1: np.tile([0, 0, 1, 0], (n, 1)),
              2: rng.uniform(0, 1, (n, 4)), 3: np.concatenate([uv, np.zeros((n, 2))], 1)}
    stock = run(tokens(os.path.join(sys.argv[1], "standin_vs.cso")), inputs, consts)
    patched_code = tokens(os.path.join(sys.argv[1], "standin_vs_patched.cso"))
    tool = sys.argv[2]
    work = tempfile.mkdtemp()
    consts_bin = os.path.join(work, "consts.bin")
    ok = True
    for seconds, strength in ((0.0, 0.0), (12.34, 1.0), (98765.4321, 2.0)):
        subprocess.run([tool, "--constants", str(seconds), str(strength), consts_bin], check=True)
        c = np.fromfile(consts_bin, f32).reshape(9, 4)
        cc = consts.copy()
        cc[240:249] = c
        out = run(patched_code, inputs, cc)
        # Reference (WarcraftXL's model): wind + parting in the world plane
        twopi = 2 * math.pi
        a1, a2 = math.radians(45), math.radians(80)
        d1, d2 = np.array([math.cos(a1), math.sin(a1)]), np.array([math.cos(a2), math.sin(a2)])
        k1, k2 = twopi / 18.0, twopi / 6.5
        ph1 = -math.fmod(k1 * 3.0 * seconds, twopi)
        ph2 = -math.fmod(k2 * 3.0 * 1.37 * seconds, twopi)
        amp1, amp2 = 0.06 * strength, 0.02 * strength
        p = world
        cone = np.clip((p[:, 2] - player[2] - 0.3) / 0.5, 0, 1)
        dxy = p[:, :2] - player[:2]
        dist = np.sqrt((dxy ** 2).sum(1) + 1e-3)
        t = np.clip(dist / 2.0, 0, 1)
        force = (0.0 - 0.5) * t + 0.5
        rep = dxy / dist[:, None] * (force * (dist < 2.0) * cone)[:, None]
        viewz = (p - cam) @ M[:, 2]
        weight = np.clip((1 - uv[:, 1] - 0.3) / 0.7, 0, 1) ** 2 / (1 + np.abs(viewz) * 0.015)
        jit = np.mod(p[:, 0] * 0.737 + p[:, 1] * 1.311, 1.0)
        weight = weight * ((1 - 0.3) + 0.6 * jit)
        s1 = np.sin(k1 * (p[:, :2] @ d1) + jit * 1.7 + ph1)
        s2 = np.sin(k2 * (p[:, :2] @ d2) + jit * 1.7 + ph2)
        off = rep + weight[:, None] * (np.outer(s1 + 0.35, amp1 * d1) + np.outer(s2, amp2 * d2))
        if strength == 0.0:
            off = np.zeros_like(rep)
        viewpos = np.concatenate([(p - cam) @ M, np.ones((n, 1))], 1)
        viewpos[:, :3] += off[:, :1] * M[0] + off[:, 1:2] * M[1]
        ref_o0 = viewpos @ proj
        err = np.abs(out[0] - ref_o0).max()
        moved = np.abs(out[0] - stock[0]).max()
        same_rest = all(np.array_equal(out[k], stock[k]) for k in (2,))
        print(f"t={seconds} strength={strength}: max |o0 - reference| {err:.2e}, max move vs stock {moved:.3f}, uv out unchanged {same_rest}")
        ok &= err < 2e-3 and same_rest
    # strength 0 (the test tool then turns the parting off too): bit-identical to the stock shader
    subprocess.run([tool, "--constants", "5", "0", consts_bin], check=True)
    c = np.fromfile(consts_bin, f32).reshape(9, 4)
    cc = consts.copy()
    cc[240:249] = c
    out = run(patched_code, inputs, cc)
    identical = all(np.array_equal(out[k], stock[k]) for k in range(4))
    print("strength 0 and no parting: identical to the stock shader:", identical)
    ok &= identical
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
