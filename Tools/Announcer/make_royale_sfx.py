#!/usr/bin/env python3
# Bleakhold Royale's own sound effects (the Royale UX spec, sections 1.6 and 1.8), synthesised from scratch.
#
#   python3 -I Tools/Announcer/make_royale_sfx.py [--out DIR] [--check]
#
# Writes Interface/AddOns/Bleakhold/Sounds/Royale/<name>.wav and <name>_quiet.wav: 22.05 kHz, mono, 16-bit PCM like
# the announcer's lines. Every sound's loud part is brought to about -18 dBFS RMS with no peak over -1 dBFS (a soft
# limiter takes at most 3 dB off the sharpest hits), and each _quiet copy is 9 dB lower (3.3.5a's PlaySoundFile has no
# volume argument). 3.3.5a cannot stop or fade a playing sound (WoW/Source/Ui/SoundInterface2_Scripts.cpp), so every
# file is exactly as long as its moment:
#
#   tick         0.22 s  a soft forged tick: a short filtered metal click over a low 70 Hz thump (countdown 15..4)
#   tick3/2/1    < 0.5 s hammer on anvil with a short ring-out, rising in pitch (3 lowest) (the last three seconds)
#   kill         0.4 s   a metallic clang and a thump (the player eliminates someone)
#   wind         7.5 s   a filtered pink-noise air rush with a slow swell; it starts 0.5 s after the DROP! gong and
#                        its 0.4 s fade lands on the canopy, so it lasts the freefall (Drop.FreefallMs, 8 s) less 0.5 s
#   canopy       0.5 s   a fabric snap: a noise burst with a fast decay and a 90 Hz thump
#   land         0.3 s   a soft thud
#
# Needs numpy. Deterministic (fixed seeds); --check renders in memory and exits 1 when a committed file differs.
import argparse
import io
import math
import os
import sys
import wave

try:
    import numpy as np
except ImportError:
    raise SystemExit("make_royale_sfx.py needs numpy: pip install numpy")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "Interface", "AddOns", "Bleakhold", "Sounds", "Royale")
RATE = 22050
FREEFALL_S = 8.0  # Bleakhold.Royale.Drop.FreefallMs (the owner's 8 s); the wind lasts it less its 0.5 s delay
PEAK_DB, RMS_DB, QUIET_DB = -1.0, -18.0, -9.0


def t_axis(seconds):
    return np.arange(int(round(seconds * RATE)), dtype=np.float64) / RATE


def env_exp(t, tau):
    return np.exp(-t / tau)


def fade(x, fade_in=0.002, fade_out=0.01):
    n_in, n_out = int(fade_in * RATE), int(fade_out * RATE)
    if n_in:
        x[:n_in] *= np.linspace(0.0, 1.0, n_in) ** 2
    if n_out:
        x[-n_out:] *= np.linspace(1.0, 0.0, n_out) ** 2
    return x


def spectral_filter(x, lo=None, hi=None, order=2):
    """Zero-phase band filter in the frequency domain: Butterworth-like magnitude, `order` per side."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1.0 / RATE)
    g = np.ones_like(f)
    if lo:
        g *= 1.0 / np.sqrt(1.0 + (lo / np.maximum(f, 1e-6)) ** (2 * order))
    if hi:
        g *= 1.0 / np.sqrt(1.0 + (f / hi) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x) * g, n)


def pink(n, rng):
    """Pink noise (1/f power) from white noise shaped in the frequency domain."""
    w = rng.standard_normal(n)
    f = np.fft.rfftfreq(n, 1.0 / RATE)
    s = np.fft.rfft(w) / np.sqrt(np.maximum(f, 20.0))
    p = np.fft.irfft(s, n)
    return p / (np.abs(p).max() or 1.0)


def thump(t, f0, f1, tau):
    """A low sine whose pitch falls from f0 to f1, decaying with time constant tau."""
    freq = f1 + (f0 - f1) * np.exp(-t / (tau * 0.5))
    phase = 2 * math.pi * np.cumsum(freq) / RATE
    return np.sin(phase) * env_exp(t, tau)


def metal(t, f0, ratios, taus, amps, rng, detune=0.004):
    """Inharmonic struck-metal partials (each with its own decay) plus a slight beating from a detuned twin."""
    out = np.zeros_like(t)
    for r, tau, a in zip(ratios, taus, amps):
        f = f0 * r
        ph = rng.uniform(0, 2 * math.pi)
        twin = 0.35 * np.sin(2 * math.pi * f * (1 + detune) * t)
        out += a * env_exp(t, tau) * (np.sin(2 * math.pi * f * t + ph) + twin)
    return out


def burst(t, rng, tau, lo, hi):
    n = rng.standard_normal(len(t))
    return spectral_filter(n, lo, hi) * env_exp(t, tau)


ANVIL = (1.0, 2.76, 5.40, 8.93, 13.34)


def tick():
    rng = np.random.default_rng(101)
    t = t_axis(0.22)
    click = burst(t, rng, 0.004, 1800, 7000) * 0.9
    ring = metal(t, 2150.0, (1.0, 1.58, 2.42), (0.018, 0.012, 0.008), (0.5, 0.3, 0.2), rng)
    low = thump(t, 95.0, 70.0, 0.055) * 0.9
    return fade(click + ring + low, 0.0005, 0.03)


def hammer(f0, seed, length=0.48):
    rng = np.random.default_rng(seed)
    t = t_axis(length)
    strike = burst(t, rng, 0.006, 900, 9000) * 1.2
    ring = metal(t, f0, ANVIL, (0.30, 0.19, 0.11, 0.06, 0.035), (1.0, 0.55, 0.35, 0.22, 0.12), rng)
    low = thump(t, 110.0, 60.0, 0.07) * 1.1
    return fade(strike + ring * 0.8 + low, 0.0005, 0.06)


def kill():
    rng = np.random.default_rng(131)
    t = t_axis(0.40)
    clang = metal(t, 380.0, (1.0, 2.32, 4.25, 6.63, 9.38), (0.22, 0.15, 0.09, 0.05, 0.03), (1.0, 0.7, 0.45, 0.3, 0.15),
                  rng, detune=0.011)
    hit = burst(t, rng, 0.008, 600, 8000) * 1.1
    low = thump(t, 120.0, 55.0, 0.09) * 1.3
    return fade(clang + hit + low, 0.0005, 0.05)


def wind():
    """The freefall: pink noise through a resonant band that opens as the speed builds, with gusts."""
    rng = np.random.default_rng(151)
    length = FREEFALL_S - 0.5
    t = t_axis(length)
    n = len(t)
    base = pink(n, rng)
    # gust envelope: slow random swells
    g = rng.standard_normal(int(length * 6) + 4)
    gx = np.linspace(0, len(g) - 1, n)
    gust = np.interp(gx, np.arange(len(g)), g)
    gust = np.convolve(gust, np.ones(2205) / 2205, mode="same")
    gust = 0.8 + 0.25 * gust / (np.abs(gust).max() or 1.0)
    # the speed builds over about 3 s (terminal velocity after 3.1 s), then holds
    speed = 1.0 - np.exp(-t / 1.1)
    out = np.zeros(n)
    # a few bands whose centres rise with the speed: the rush brightens as the fall reaches full speed
    hop = 2048
    win = np.hanning(hop * 2)
    for start in range(0, n, hop):
        seg = base[start:start + hop * 2]
        if len(seg) < 16:
            break
        w = win[:len(seg)]
        s = speed[min(n - 1, start + hop)]
        centre = 300 + 900 * s
        f = np.fft.rfftfreq(len(seg), 1.0 / RATE)
        band = np.exp(-0.5 * (np.log(np.maximum(f, 20) / centre) / 0.9) ** 2)
        band += 0.35 * np.exp(-0.5 * (np.log(np.maximum(f, 20) / (centre * 3.2)) / 0.6) ** 2)
        y = np.fft.irfft(np.fft.rfft(seg * w) * band, len(seg))
        out[start:start + len(seg)] += y
    rumble = spectral_filter(rng.standard_normal(n), 30, 120) * 0.6
    out = (out / (np.abs(out).max() or 1.0)) * (0.25 + 0.75 * speed) * gust + rumble * speed * 0.3
    out = fade(out, 0.3, 0.4)
    return out


def canopy():
    rng = np.random.default_rng(171)
    t = t_axis(0.5)
    snap = burst(t, rng, 0.03, 250, 6000) * 1.2
    flap = np.zeros_like(t)
    for delay, amp in ((0.06, 0.5), (0.13, 0.3)):
        k = int(delay * RATE)
        tt = t[:len(t) - k]
        flap[k:] += burst(tt, rng, 0.02, 300, 4000) * amp
    low = thump(t, 120.0, 90.0, 0.08) * 1.0
    return fade(snap + flap + low, 0.0005, 0.08)


def land():
    rng = np.random.default_rng(191)
    t = t_axis(0.3)
    low = thump(t, 85.0, 55.0, 0.09) * 1.2
    dirt = burst(t, rng, 0.03, 120, 2500) * 0.45
    return fade(low + dirt, 0.001, 0.06)


SOUNDS = [("tick", tick), ("tick3", lambda: hammer(520.0, 111)), ("tick2", lambda: hammer(620.0, 113)),
          ("tick1", lambda: hammer(740.0, 117)), ("kill", kill), ("wind", wind), ("canopy", canopy), ("land", land)]


def db(v):
    return 20.0 * math.log10(max(v, 1e-12))


def master(x):
    """The loud part (where the envelope is within 20 dB of its top) towards -18 dBFS RMS, with no peak over -1
    dBFS: a soft limiter (tanh above -7 dBFS) rounds off at most 3 dB of the sharpest hits, so a click keeps its
    attack and ends up a little under -18 dBFS RMS rather than squashed."""
    x = x - x.mean()
    env = np.convolve(np.abs(x), np.ones(441) / 441, mode="same")
    active = env > env.max() * 0.1
    peak_lin = 10 ** (PEAK_DB / 20.0)
    knee = 10 ** ((PEAK_DB - 6.0) / 20.0)
    rms = math.sqrt(float(np.mean(x[active] ** 2))) or 1e-9
    gain = min(10 ** (RMS_DB / 20.0) / rms, 10 ** ((PEAK_DB + 3.0) / 20.0) / (np.abs(x).max() or 1.0))
    y = x * gain
    room = peak_lin - knee
    return np.where(np.abs(y) > knee, np.sign(y) * (knee + room * np.tanh((np.abs(y) - knee) / room)), y)


def wav_bytes(x):
    pcm = np.clip(np.rint(x * 32767.0), -32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def render():
    files = {}
    report = []
    for name, fn in SOUNDS:
        x = master(fn())
        quiet = x * 10 ** (QUIET_DB / 20.0)
        files[name + ".wav"] = wav_bytes(x)
        files[name + "_quiet.wav"] = wav_bytes(quiet)
        env = np.convolve(np.abs(x), np.ones(441) / 441, mode="same")
        active = env > env.max() * 0.1
        report.append("%-7s %.3f s  peak %5.1f dBFS  rms %5.1f dBFS" % (name, len(x) / RATE, db(np.abs(x).max()),
                                                                    db(math.sqrt(float(np.mean(x[active] ** 2))))))
    return files, report


def main():
    ap = argparse.ArgumentParser(description="Synthesise the Bleakhold Royale sound effects.")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="exit 1 when a committed file differs")
    a = ap.parse_args()
    files, report = render()
    if a.check:
        bad = [n for n, data in sorted(files.items())
               if not os.path.isfile(os.path.join(a.out, n)) or open(os.path.join(a.out, n), "rb").read() != data]
        if bad:
            print("make_royale_sfx: out of date: %s (run python3 -I Tools/Announcer/make_royale_sfx.py)"
                  % ", ".join(bad), file=sys.stderr)
            return 1
        print("make_royale_sfx: %d files match" % len(files))
        return 0
    os.makedirs(a.out, exist_ok=True)
    for n, data in sorted(files.items()):
        with open(os.path.join(a.out, n), "wb") as f:
            f.write(data)
    for line in report:
        print(line)
    print("wrote %d files to %s" % (len(files), os.path.relpath(a.out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
