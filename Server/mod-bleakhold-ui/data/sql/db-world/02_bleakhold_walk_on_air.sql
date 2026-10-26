-- mod-bleakhold-ui: Walk on Air (spell 100800), the High Elf glide (GLIDE, docs/BleakholdProtocol.md section 16).
-- The server reads this row like a Spell.dbc row (DBCStores.cpp: spell_dbc). The client needs the same row in its
-- Spell.dbc (a patch MPQ) for the buff's name, icon, tooltip and wings; without it the glide still works, with no
-- buff shown. BleakholdUi.Glide.Spell falls back to Slow Fall (130) while this row is missing.
-- Ids 100800-100809 are kept for the camping spells (100800 Walk on Air); AzerothCore's own spell_dbc rows use
-- 100001-100102, mod-transmog-plus 90170-90189 and the RaceForge racials (Tools/RaceForge/races.json) 90500 on.
--   a feather fall aura (SPELL_AURA_FEATHER_FALL) on the caster, 10 s (SpellDuration 1), instant, self, no cost,
--   no cooldown (the module keeps it), not dispellable, cancellable; the spell visual of Magic Wings (24742):
--   visual 7370, wings at the head (no sound and no forced animation: the player keeps their own run, jump and
--   fall), and the icon of Cyclone Fall (59892): 1931 Spell_Nature_EyeOfTheStorm.
--   No aura interrupt flags: the module ends the aura when the glide lands. $d in the tooltip is the 10 s.
DELETE FROM `spell_dbc` WHERE `ID` = 100800;
INSERT INTO `spell_dbc` (`ID`, `Attributes`, `CastingTimeIndex`, `ProcChance`, `DurationIndex`, `RangeIndex`, `EquippedItemClass`, `Effect_1`, `EffectDieSides_1`, `ImplicitTargetA_1`, `EffectAura_1`, `SpellVisualID_1`, `SpellIconID`, `Name_Lang_enUS`, `Name_Lang_Mask`, `NameSubtext_Lang_enUS`, `NameSubtext_Lang_Mask`, `Description_Lang_enUS`, `Description_Lang_Mask`, `AuraDescription_Lang_enUS`, `AuraDescription_Lang_Mask`, `EffectChainAmplitude_1`, `EffectChainAmplitude_2`, `EffectChainAmplitude_3`, `SchoolMask`, `EffectBonusMultiplier_1`) VALUES
(100800, 262160, 1, 101, 1, 1, -1, 6, 1, 1, 105, 7370, 1931, 'Walk on Air', 16712190, 'Racial', 16712190, 'Glide through the air for $d, steering your descent. Does not gain altitude.', 16712190, 'Gliding on the air. Turn to steer; you do not gain altitude.', 16712190, 1.0, 1.0, 1.0, 1, 1.0);
