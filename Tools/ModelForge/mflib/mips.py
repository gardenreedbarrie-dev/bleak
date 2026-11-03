"""Gutters, edge dilation, coverage-preserving mips and BLP output (CAFE.SPEC.md section 5.5, "Mips").

ModelForge builds the mip chain itself and writes it with blpconvert.write_blp(path, levels, fmt); blpconvert and
its default box filter stay unchanged. Empty atlas texels take the colour of the nearest island (a multi-source
breadth-first dilation, so the gutter between two islands splits between them and no island's colour reaches
another island's texels down to mip 2). For cutout (blend 1) textures every level keeps the alpha coverage of
mip 0: alpha is scaled so the fraction of texels >= 224 matches mip 0 (the client cuts blend-1 materials at
0.878 x element alpha, CM2SceneRender.cpp:296-305; a box-filtered 0/255 fringe would erode to 128 and vanish
within a few yards). Only the cutout texels take part: build.py passes a mask of the texels that belong to
cutout-material islands (and their gutters), so glass or opaque parts sharing the atlas keep their box-filtered
alpha at every distance and the opaque texels do not dilute the cutout target. Encodings: dxt1 for opaque
textures, dxt5 for alpha; powers of two, never 6:1.
"""

import collections

import blpconvert as B  # noqa: E402  Tools/BlpConvert (read-only)

ALPHA_REF = 224


def dilate_islands(img, owner, fill_alpha=None):
    """img: blpconvert.Image; owner: per-texel island id (-1 = empty). Fills every empty texel with the colour
    of the nearest covered texel (4-neighbour BFS from all islands at once). Returns the owner map after
    filling. Alpha of filled texels: copied, or fill_alpha when given."""
    w, h = img.width, img.height
    own = list(owner)
    src = [-1] * (w * h)
    q = collections.deque()
    for i, o in enumerate(own):
        if o >= 0:
            src[i] = i
            q.append(i)
    d = img.data
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for j in ((i - 1) if x > 0 else -1, (i + 1) if x < w - 1 else -1, (i - w) if y > 0 else -1,
                  (i + w) if y < h - 1 else -1):
            if j >= 0 and own[j] < 0:
                own[j] = own[i]
                src[j] = src[i]
                s = 4 * src[i]
                o = 4 * j
                d[o] = d[s]
                d[o + 1] = d[s + 1]
                d[o + 2] = d[s + 2]
                d[o + 3] = d[s + 3] if fill_alpha is None else fill_alpha
                q.append(j)
    return own


def coverage(img, ref=ALPHA_REF):
    a = img.data[3::4]
    return sum(1 for v in a if v >= ref) / float(len(a) or 1)


def _half_mask(frac, w, h):
    """One 2x2 box step of a per-texel fraction map (the same footprint as blpconvert's box filter)."""
    nw, nh = max(1, w // 2), max(1, h // 2)
    out = [0.0] * (nw * nh)
    for y in range(nh):
        r0 = min(2 * y, h - 1) * w
        r1 = min(2 * y + 1, h - 1) * w
        for x in range(nw):
            x0 = min(2 * x, w - 1)
            x1 = min(2 * x + 1, w - 1)
            out[y * nw + x] = (frac[r0 + x0] + frac[r0 + x1] + frac[r1 + x0] + frac[r1 + x1]) * 0.25
    return out, nw, nh


def mask_levels(mask, levels):
    """Per-level texel selections for a level-0 mask (truthy = cutout texel): a texel of level n is selected
    when at least half of the level-0 texels it covers are."""
    w, h = levels[0].width, levels[0].height
    frac = [1.0 if v else 0.0 for v in mask]
    if len(frac) != w * h:
        raise ValueError("cutout mask has %d entries for a %dx%d level" % (len(frac), w, h))
    out = []
    for li, lv in enumerate(levels):
        if li:
            frac, w, h = _half_mask(frac, w, h)
        if (w, h) != (lv.width, lv.height):
            raise ValueError("level %d is %dx%d, the mask %dx%d" % (li, lv.width, lv.height, w, h))
        out.append([i for i, f in enumerate(frac) if f >= 0.5])
    return out


def preserve_coverage(levels, ref=ALPHA_REF, mask=None):
    """Scales each level's alpha so its fraction of texels >= ref comes as close as it can to level 0's: the
    scale k = ref / v for the alpha value v whose 'texels at or above v' fraction is nearest the target.
    mask (level-0 per-texel truthy values) limits the target, the histogram and the scaling to the cutout
    texels; None means the whole texture is cutout."""
    if mask is None:
        sel = [range(lv.width * lv.height) for lv in levels]
    else:
        sel = mask_levels(mask, levels)
    a0 = levels[0].data
    n0 = len(sel[0])
    if n0 == 0:
        return levels
    target = sum(1 for i in sel[0] if a0[4 * i + 3] >= ref) / float(n0)
    if target <= 0.0:
        return levels
    for lv, idx in zip(levels[1:], sel[1:]):
        n = len(idx)
        if n == 0:
            continue
        d = lv.data
        hist = [0] * 256
        for i in idx:
            hist[d[4 * i + 3]] += 1
        best_v, best_err = ref, None
        above = 0
        for v in range(255, 0, -1):
            above += hist[v]
            k = ref / float(v)
            if k > 8.0 or k < 0.25:
                continue
            err = abs(above / float(n) - target)
            if best_err is None or err < best_err - 1e-12:
                best_v, best_err = v, err
        k = ref / float(best_v)
        for i in idx:
            v = int(d[4 * i + 3] * k + 0.5)
            d[4 * i + 3] = 255 if v > 255 else v
    return levels


def build_chain(img, cutout=False, alpha=False):
    """cutout: False, True (the whole texture is cutout) or a level-0 per-texel mask of the cutout texels."""
    levels = B.build_mips(img, True)
    is_cut = cutout is True or (cutout is not False and cutout is not None and any(cutout))
    if alpha or is_cut:
        B.fill_transparent(levels)
    if is_cut:
        preserve_coverage(levels, mask=None if cutout is True else cutout)
    return levels


def check_size(w, h):
    if not (B.is_pow2(w) and B.is_pow2(h)):
        raise ValueError("%dx%d is not a power of two" % (w, h))
    if w == 6 * h:
        raise ValueError("%dx%d: six times as wide as tall loads as a cube map" % (w, h))
    if max(w, h) > 4 * min(w, h):
        raise ValueError("%dx%d: aspect beyond 1:4" % (w, h))


def write(path, img, fmt=None, cutout=False, pool=None):
    """Builds the chain and writes the BLP; returns the levels written. cutout as for build_chain."""
    check_size(img.width, img.height)
    alpha = fmt == "dxt5" or (fmt is None and img.has_alpha())
    fmt = fmt or ("dxt5" if alpha else "dxt1")
    levels = build_chain(img, cutout, alpha)
    B.write_blp(path, levels, fmt, True, pool)
    return levels
