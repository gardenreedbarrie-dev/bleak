"""Choreography: a dance is keyed poses on beats, eased between, plus grooves and follow-through.

    d = Dance(bpm=120, beats=8)
    d.key(0, hips=(0, 0, -0.03), hand_l=(0.3, 0.2, 0.1))       # controls of dflib.rig, from this beat on
    d.key(1, ease="snap", hand_l=(0.4, 0.3, 0.5))               # arrive at this key the "snap" way
    d.overlay(lambda b: {"hips": (0, 0, -0.02 * bounce(b))})    # added to the keyed values
    d.follow("head_nod", "spine_bend", gain=0.6)                # the head lags the torso
    frames = d.sample(fps=30)                                   # [(hips, rotations)] for one loop

Every control is its own channel: a key only sets the controls it names, and a channel without keys keeps the
rig's default. Channels loop: after the last key the value travels back to the first one. A key's `ease` says
how the motion arrives at that key:

  smooth  Catmull-Rom through the neighbouring keys (the default; flowing motion)
  inout   eases out of the previous key and into this one (smoothstep)
  in      accelerates into the key (a hit on the beat)
  out     decelerates into the key (a reach)
  snap    holds, then moves into the key in the last third of the way (popping, hits on the beat)
  pop     moves into the key in the first third of the way, then holds
  back    eases into the key with a small overshoot
  linear  constant speed
  hold    keeps the previous value until this key's beat, then jumps

`lift` on a key arcs a position channel (feet, hands) upwards by that height half way to the key.
"""

import math

from . import quat as Q
from . import rig
from . import skeleton as S


def _ease_back(x, s=0.9):
    x -= 1.0
    return 1.0 + (s + 1.0) * x * x * x + s * x * x


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


# A hit still takes a third of the way between keys: at 30 frames a second that is 4 to 6 frames, fast but never a
# jump.
HIT = 0.34

EASES = {
    "linear": lambda u: u,
    "inout": _smooth,
    "in": lambda u: u * u,
    "out": lambda u: 1.0 - (1.0 - u) * (1.0 - u),
    "snap": lambda u: _smooth((u - (1.0 - HIT)) / HIT),
    "pop": lambda u: _smooth(u / HIT),
    "back": lambda u: _ease_back(u),
    "hold": lambda u: 0.0,
}
ALL_EASES = set(EASES) | {"smooth"}


def bounce(beat, sharp=2.0):
    """0..1 groove pulse: 1 on every beat (the drop), 0 half way between, eased like a knee bounce."""
    phase = beat - math.floor(beat)
    v = 0.5 + 0.5 * math.cos(2.0 * math.pi * phase)
    return v ** sharp


def sway(beat, period=2.0, offset=0.0):
    """-1..1 smooth side to side over `period` beats."""
    return math.sin(2.0 * math.pi * (beat / period + offset))


class Key:
    __slots__ = ("beat", "value", "ease", "lift")

    def __init__(self, beat, value, ease, lift):
        self.beat = beat
        self.value = value
        self.ease = ease
        self.lift = lift


def _vadd(a, b):
    if isinstance(a, tuple):
        return tuple(x + y for x, y in zip(a, b))
    return a + b


def _vsub(a, b):
    if isinstance(a, tuple):
        return tuple(x - y for x, y in zip(a, b))
    return a - b


def _vscale(a, s):
    if isinstance(a, tuple):
        return tuple(x * s for x in a)
    return a * s


def _hermite(p0, p1, m0, m1, u, dt):
    u2 = u * u
    u3 = u2 * u
    h00 = 2 * u3 - 3 * u2 + 1
    h10 = u3 - 2 * u2 + u
    h01 = -2 * u3 + 3 * u2
    h11 = u3 - u2
    return _vadd(_vadd(_vscale(p0, h00), _vscale(m0, h10 * dt)), _vadd(_vscale(p1, h01), _vscale(m1, h11 * dt)))


class Channel:
    def __init__(self, name, beats):
        self.name = name
        self.beats = beats
        self.keys = []

    def add(self, key):
        self.keys = [k for k in self.keys if abs(k.beat - key.beat) > 1e-9]
        self.keys.append(key)
        self.keys.sort(key=lambda k: k.beat)

    def _at(self, i):
        """Key i with its beat unwrapped (i may run past either end of the loop)."""
        n = len(self.keys)
        wraps, j = divmod(i, n)
        k = self.keys[j]
        return k.beat + wraps * self.beats, k.value, k

    def _tangent(self, i):
        t0, p0, _ = self._at(i - 1)
        t2, p2, _ = self._at(i + 1)
        if t2 - t0 <= 1e-9:
            return _vscale(p0, 0.0)
        return _vscale(_vsub(p2, p0), 1.0 / (t2 - t0))

    def value(self, beat):
        n = len(self.keys)
        if n == 1:
            return self.keys[0].value
        beat = beat % self.beats
        i = 0
        while i < n and self.keys[i].beat <= beat:
            i += 1
        i -= 1  # key at or before beat; -1 means wrapping from the last key
        t0, p0, _ = self._at(i)
        t1, p1, k1 = self._at(i + 1)
        span = t1 - t0
        u = 0.0 if span <= 1e-9 else (beat - t0) / span
        if k1.ease == "smooth":
            v = _hermite(p0, p1, self._tangent(i), self._tangent(i + 1), u, span)
            e = u
        else:
            e = EASES[k1.ease](u)
            v = _vadd(p0, _vscale(_vsub(p1, p0), e))
        if k1.lift and isinstance(v, tuple):
            v = (v[0], v[1], v[2] + k1.lift * math.sin(math.pi * min(1.0, max(0.0, e))))
        return v


class Dance:
    def __init__(self, bpm, beats):
        if bpm <= 0 or beats <= 0:
            raise ValueError("bpm and beats must be positive")
        self.bpm = float(bpm)
        self.beats = float(beats)
        self.channels = {}
        self.overlays = []
        self.follows = []
        self._defaults = rig.defaults()

    @property
    def seconds(self):
        return self.beats * 60.0 / self.bpm

    def key(self, beat, ease="smooth", lift=0.0, **controls):
        if ease not in ALL_EASES:
            raise ValueError("unknown ease %r" % ease)
        if not 0.0 <= beat < self.beats:
            raise ValueError("beat %s outside the dance (0..%s)" % (beat, self.beats))
        for name, value in controls.items():
            if name not in self._defaults:
                raise ValueError("unknown control %r" % name)
            default = self._defaults[name]
            if isinstance(default, tuple):
                value = tuple(float(x) for x in value)
                if len(value) != len(default):
                    raise ValueError("control %r takes %d numbers" % (name, len(default)))
            else:
                value = float(value)
            ch = self.channels.get(name)
            if ch is None:
                ch = self.channels[name] = Channel(name, self.beats)
            ch.add(Key(float(beat), value, ease, float(lift) if name.startswith(("foot_", "hand_")) else 0.0))
        return self

    def pose(self, beat, pose, ease="smooth", lift=0.0, mirror=False, **extra):
        """Keys a whole pose (a dict of controls), optionally mirrored left to right, plus extra controls."""
        controls = dict(pose)
        if mirror:
            controls = dict(rig.mirror_control(k, v) for k, v in controls.items())
        controls.update(extra)
        return self.key(beat, ease=ease, lift=lift, **controls)

    def overlay(self, fn):
        """fn(beat) -> dict of control offsets added on top of the keys."""
        self.overlays.append(fn)
        return self

    def follow(self, target, source, gain=0.5, hz=2.2, damping=0.45, component=None):
        """Adds gain * (spring(source) - source) to target: target lags behind and overshoots source's motion."""
        self.follows.append((target, source, gain, hz, damping, component))
        return self

    def controls_at(self, beat):
        c = {name: ch.value(beat) for name, ch in self.channels.items()}
        for fn in self.overlays:
            for name, off in fn(beat).items():
                base = c.get(name, self._defaults[name])
                c[name] = _vadd(base, tuple(float(x) for x in off) if isinstance(base, tuple) else float(off))
        return c

    def _scalar(self, controls, name, component):
        v = controls.get(name, self._defaults[name])
        if isinstance(v, tuple):
            return v[component or 0]
        return v

    def sample(self, fps=30):
        """[(hips, rotations)] for one loop at fps (the frame after the last is frame 0 again)."""
        count = max(2, int(round(self.seconds * fps)))
        beats = [self.beats * f / count for f in range(count)]
        frames = [self.controls_at(b) for b in beats]
        dt = self.seconds / count
        for target, source, gain, hz, damping, component in self.follows:
            src = [self._scalar(c, source, component) for c in frames]
            omega = 2.0 * math.pi * hz
            y, v = src[0], 0.0
            out = [0.0] * count
            for _ in range(4):  # run the loop until the spring settles into its periodic motion
                for f in range(count):
                    sub = 4
                    for _ in range(sub):
                        h = dt / sub
                        acc = omega * omega * (src[f] - y) - 2.0 * damping * omega * v
                        v += acc * h
                        y += v * h
                    out[f] = y
            for f, c in enumerate(frames):
                lag = gain * (out[f] - src[f])
                base = c.get(target, self._defaults[target])
                if isinstance(base, tuple):
                    i = component or 0
                    c[target] = tuple(x + lag if k == i else x for k, x in enumerate(base))
                else:
                    c[target] = base + lag
        return [rig.solve(c) for c in frames]


def check_loop(frames, limit_deg=25.0):
    """Largest rotation step (degrees) between consecutive frames, the wrap included."""
    worst = 0.0
    n = len(frames)
    for f in range(n):
        a = frames[f][1]
        b = frames[(f + 1) % n][1]
        for j in range(S.COUNT):
            worst = max(worst, Q.qangle(a[j], b[j]))
    return worst
