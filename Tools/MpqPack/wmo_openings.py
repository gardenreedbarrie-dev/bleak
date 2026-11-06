#!/usr/bin/env python3
"""Find the openings (holes) in a WMO's walls, from the client's own archives: can it be walked into from outside?

    python3 -I wmo_openings.py <client Data folder> "World\\wmo\\Dungeon\\KL_OnyxiasLair\\KL_OnyxiasLair_B.wmo"
    python3 -I wmo_openings.py <Data> <root.wmo> --min 4 --top 12

A dungeon interior such as Molten Core is a closed shell: every wall edge is shared by two triangles, so the mesh
has no boundary, and the only way in is a teleport. A cave with a real mouth (a place the terrain can meet it) has a
boundary loop there: a ring of edges used by one triangle only.

This reads every group file (<root>_NNN.wmo: MOVT vertices, MOVI triangles), welds the vertices of ALL groups by
position (WMO meshes split vertices along texture seams, and each group ends at the portal planes between groups,
so only a welded whole shows the real holes), then lists the boundary loops, biggest first, with their size and
centre. Centres are given in model space and in the ORIGINAL map's world coordinates (a WDT global WMO at rotation 0:
world = (-x, -y, z)), so they can be compared with the map's entrance and boss coordinates.

Small loops are normal (decor, seams that do not weld exactly); --min (yards, default 3) hides them. Nothing is
written. Reads through wmo_info.py's CRC-tolerant block reader (keep the files together).
"""
from __future__ import annotations

import argparse
import math
import os
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wmo_info  # noqa: E402  (installs the CRC-tolerant reader on mpqpack)

mpqpack = wmo_info.mpqpack


class Archives:
    """Every MPQ under a Data folder, opened once; the last archive holding a file wins (patches over base)."""

    def __init__(self, data_dir: str):
        paths = []
        for root, _d, files in os.walk(data_dir):
            for f in files:
                if f.lower().endswith(".mpq"):
                    paths.append(os.path.join(root, f))
        paths.sort(key=lambda p: ("patch" in os.path.basename(p).lower(), os.path.basename(p).lower()))
        self.archives = []
        for p in paths:
            try:
                self.archives.append(mpqpack.MpqArchive(p))
            except Exception:
                continue

    def read(self, name: str) -> bytes | None:
        found = None
        for a in self.archives:
            try:
                if a.has_file(name):
                    found = a.read(name)
            except Exception:
                continue
        return found


def group_mesh(raw: bytes):
    """(vertices, triangles) of a group file: MOGP's sub-chunks MOVT (float3) and MOVI (uint16 x 3)."""
    verts, tris = [], []
    for tag, p in wmo_info.chunks(raw):
        if tag != "MOGP":
            continue
        off = 68  # the MOGP header; its sub-chunks follow
        while off + 8 <= len(p):
            sub = p[off:off + 4][::-1].decode("ascii", "replace")
            size = struct.unpack_from("<I", p, off + 4)[0]
            body = p[off + 8:off + 8 + size]
            if sub == "MOVT":
                verts = [struct.unpack_from("<3f", body, i * 12) for i in range(len(body) // 12)]
            elif sub == "MOVI":
                idx = struct.unpack_from(f"<{len(body) // 2}H", body)
                tris = [idx[i:i + 3] for i in range(0, len(idx) - 2, 3)]
            off += 8 + size
    return verts, tris


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data_dir")
    ap.add_argument("wmo", help="client path of the ROOT wmo")
    ap.add_argument("--min", type=float, default=3.0, help="hide loops smaller than this across (yards)")
    ap.add_argument("--top", type=int, default=10, help="list at most this many loops")
    ap.add_argument("--weld", type=float, default=0.05, help="vertices closer than this (yards) are one")
    args = ap.parse_args()

    arch = Archives(args.data_dir)
    root = arch.read(args.wmo)
    if root is None:
        print(f"not found: {args.wmo}")
        return 2
    n_groups = 0
    group_flags = []
    for tag, p in wmo_info.chunks(root):
        if tag == "MOHD":
            n_groups = struct.unpack_from("<I", p, 4)[0]
        elif tag == "MOGI":
            group_flags = [struct.unpack_from("<I", p, i * 32)[0] for i in range(len(p) // 32)]
    stem = args.wmo[:-4]

    q = 1.0 / args.weld
    vid: dict[tuple, int] = {}
    pos: list[tuple] = []
    vgroup: list[set] = []
    edges: dict[tuple, int] = defaultdict(int)
    total_tris = 0
    for g in range(n_groups):
        raw = arch.read(f"{stem}_{g:03d}.wmo")
        if raw is None:
            print(f"  group {g}: file missing")
            continue
        verts, tris = group_mesh(raw)
        ids = []
        for v in verts:
            key = (round(v[0] * q), round(v[1] * q), round(v[2] * q))
            if key not in vid:
                vid[key] = len(pos)
                pos.append(v)
                vgroup.append(set())
            ids.append(vid[key])
            vgroup[vid[key]].add(g)
        for a, b, c in tris:
            if max(a, b, c) >= len(ids):
                continue
            ta, tb, tc = ids[a], ids[b], ids[c]
            if ta == tb or tb == tc or ta == tc:
                continue
            total_tris += 1
            for u, w in ((ta, tb), (tb, tc), (tc, ta)):
                edges[(u, w) if u < w else (w, u)] += 1
        kind = "indoor " if g < len(group_flags) and group_flags[g] & 0x2000 else "outdoor"
        print(f"  group {g:2}: {kind} {len(verts):6} vertices {len(tris):6} triangles")

    boundary = [e for e, n in edges.items() if n == 1]
    adj: dict[int, list[int]] = defaultdict(list)
    for u, w in boundary:
        adj[u].append(w)
        adj[w].append(u)
    seen: set[int] = set()
    loops = []
    for start in adj:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        xs = [pos[v][0] for v in comp]
        ys = [pos[v][1] for v in comp]
        zs = [pos[v][2] for v in comp]
        span = math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
        groups = sorted(set().union(*(vgroup[v] for v in comp)))
        loops.append((span, len(comp), (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)),
                      (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)), groups))
    loops.sort(reverse=True)

    print(f"\n  {len(pos)} welded vertices, {total_tris} triangles, {len(boundary)} boundary edges, "
          f"{len(loops)} boundary loop(s)")
    big = [lp for lp in loops if lp[0] >= args.min]
    if not big:
        print(f"  no opening {args.min:g} yards or more across: a CLOSED shell (only a teleport gets in)")
        return 0
    print(f"  openings {args.min:g}+ yards across (biggest first; centre in model space -> original map world):")
    for span, n, (cx, cy, cz), (sx, sy, sz), groups in big[:args.top]:
        kinds = ",".join(("o" if g < len(group_flags) and not group_flags[g] & 0x2000 else "i") + str(g)
                         for g in groups)
        print(f"    {span:6.1f} yd across ({sx:5.1f} x {sy:5.1f} x {sz:5.1f}), {n:4} vertices, "
              f"centre model ({cx:7.1f}, {cy:7.1f}, {cz:6.1f}) -> world ({-cx:7.1f}, {-cy:7.1f}, {cz:6.1f}), "
              f"groups {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
