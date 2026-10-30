"""Emitter presets (CAFE.SPEC.md section 5.2.7): each returns a build.ParticleDef with the section's values, so a
prop writes `d.particles = [E.steam(tip), E.exhaust_smoke(top)]`. Keyword arguments override any field of
m2write.Particle (speed, life, emission_rate, colors, alphas, scales, ...). At most two emitters per model.

  steam          the wand steam (the Particle defaults): rises 0.35 yd/s, 14 puffs a second, lit
  vent_wisp      a thin wisp from a safety valve (EspressoSW's boiler vent)
  kettle_steam   section 5.2.7 variant: rate 8, life 2.2, born small at the spout tip in a narrow cone
  cup_steam      a tiny lazy wisp over a hot cup (CupSW's optional steam)
  exhaust_smoke  section 5.2.7 variant (Orgrimmar): grey (90, 90, 90), rate 5, life 2.5, gravity -0.08
  frost_mist     section 5.2.7 variant (cold boxes): sinks over the front lip; place it on the lip
  embers         section 5.2.7 variant (Orgrimmar stove): flags 0x20001 (unlit), additive, orange sparks

Every preset keeps the contract: head quads (flags & 0x20000), never tail quads, emitter type 1, one key per
track, three part-track keys, twinkle 10 / 1 / 1; m2check verifies the plume against the bounds.
"""

from . import build as B


def steam(pos, texture="Steam", **kw):
    return B.ParticleDef(pos, texture, **kw)


def vent_wisp(pos, texture="Steam", **kw):
    p = dict(speed=0.18, variation=0.3, latitude=0.2, gravity=-0.1, life=1.4, emission_rate=4.0,
             scales=((0.03, 0.03), (0.1, 0.1), (0.18, 0.18)), alphas=(0, 12000, 0))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


def kettle_steam(pos, texture="Steam", **kw):
    """Section 5.2.7's kettle variant (rate 8, about life 2), tuned so the plume visibly leaves the spout: born
    small (0.02) and slow in a narrow cone (0.12 rad), already faintly visible at birth, growing to 0.16 as it
    rises (the default 0.05 start and 0.25 spread put the first puff well above and beside the tip). Place it on
    the spout tip."""
    p = dict(emission_rate=8.0, life=2.2, speed=0.22, latitude=0.12, gravity=-0.12,
             scales=((0.02, 0.02), (0.08, 0.08), (0.16, 0.16)), alphas=(9000, 16000, 0))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


def cup_steam(pos, texture="Steam", **kw):
    p = dict(speed=0.12, variation=0.3, latitude=0.15, gravity=-0.06, life=1.5, emission_rate=3.0,
             scales=((0.02, 0.02), (0.05, 0.05), (0.09, 0.09)), alphas=(0, 9000, 0))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


def exhaust_smoke(pos, texture="Steam", **kw):
    p = dict(colors=((90.0, 90.0, 90.0),) * 3, emission_rate=5.0, life=2.5, gravity=-0.08,
             scales=((0.06, 0.06), (0.2, 0.2), (0.34, 0.34)))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


def frost_mist(pos, texture="Steam", **kw):
    """A plane emitter fires along its +Z, so only a near-zero speed and a positive gravity make the mist fall
    over the edge (CPlaneParticleEmitter::CreateParticle, ParticleSystem2.cpp:2893-2924)."""
    p = dict(speed=0.03, variation=0.5, latitude=1.3, gravity=0.15, life=2.0, emission_rate=6.0,
             alphas=(0, 9000, 0), colors=((225.0, 240.0, 255.0),) * 3,
             scales=((0.08, 0.08), (0.18, 0.18), (0.26, 0.26)))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


def embers(pos, texture="Steam", **kw):
    """Unlit (flag 0x1, `[VERIFY V33]`) additive orange sparks that rise and fade."""
    p = dict(flags=0x20001, blend=4, colors=((255.0, 140.0, 40.0),) * 3, emission_rate=10.0, life=1.0,
             speed=0.4, variation=0.5, latitude=0.4, gravity=-0.2,
             scales=((0.02, 0.02), (0.015, 0.015), (0.0, 0.0)), alphas=(32767, 24000, 0))
    p.update(kw)
    return B.ParticleDef(pos, texture, **p)


PRESETS = {"steam": steam, "vent_wisp": vent_wisp, "kettle_steam": kettle_steam, "cup_steam": cup_steam,
           "exhaust_smoke": exhaust_smoke, "frost_mist": frost_mist, "embers": embers}
