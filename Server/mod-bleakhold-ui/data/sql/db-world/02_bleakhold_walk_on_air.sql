-- mod-bleakhold-ui: Walk on Air, the High Elf glide (GLIDE, docs/BleakholdProtocol.md section 16): spell 100801 in the
-- spellbook and spell 100800, the glide's aura.
-- The server reads these rows like Spell.dbc rows (DBCStores.cpp: spell_dbc). The client needs the same rows in its
-- Spell.dbc (a patch MPQ: Tools/RaceForge's races.json, raceforge.py update) for the spellbook entry, the buff's name,
-- icon and tooltip, and the glide's look; without them the glide still works through /glide, with no buff shown and
-- nothing in the spellbook. BleakholdUi.Glide.Spell falls back to Slow Fall (130) while 100800 is missing, and
-- BleakholdUi.Glide.CastSpell is off while 100801 is.
-- Ids 100800-100809 are kept for the camping spells; AzerothCore's own spell_dbc rows use 100001-100102,
-- mod-transmog-plus 90170-90189 and the RaceForge racials (Tools/RaceForge/races.json) 90500 on.
--
-- 100800 Walk on Air (the aura): a feather fall aura (SPELL_AURA_FEATHER_FALL) on the caster, 10 s (SpellDuration 1),
--   instant, self, no cost, no cooldown (the module keeps it), not dispellable, cancellable; the icon of Cyclone Fall
--   (59892): 1931 Spell_Nature_EyeOfTheStorm. No aura interrupt flags: the module ends the aura when the glide lands.
--   $d in the tooltip is the 10 s. Its spell visual is the glide's look: 63, Slow Fall's (130), a light at the hands
--   and a soft flash at the head when the glide starts, nothing that stays on the character (races.json lists the
--   other stock visuals that fit; change it there and here together).
-- 100801 Walk on Air (the racial in the spellbook): the module teaches it to the races of BleakholdUi.Glide.Races and
--   its spell script (spell_bleakhold_walk_on_air) starts the glide when it is cast, in the air only. Instant, off the
--   global cooldown, a 90 s cooldown (RecoveryTime: the action bar shows it), self, a dummy effect on the caster, no
--   visual of its own; the icon of Slow Fall: 505 Spell_Magic_FeatherFall.
DELETE FROM `spell_dbc` WHERE `ID` IN (100800, 100801);
INSERT INTO `spell_dbc` (`ID`, `Attributes`, `CastingTimeIndex`, `ProcChance`, `DurationIndex`, `RangeIndex`, `EquippedItemClass`, `Effect_1`, `EffectDieSides_1`, `ImplicitTargetA_1`, `EffectAura_1`, `SpellVisualID_1`, `SpellIconID`, `Name_Lang_enUS`, `Name_Lang_Mask`, `NameSubtext_Lang_enUS`, `NameSubtext_Lang_Mask`, `Description_Lang_enUS`, `Description_Lang_Mask`, `AuraDescription_Lang_enUS`, `AuraDescription_Lang_Mask`, `EffectChainAmplitude_1`, `EffectChainAmplitude_2`, `EffectChainAmplitude_3`, `SchoolMask`, `EffectBonusMultiplier_1`) VALUES
(100800, 262160, 1, 101, 1, 1, -1, 6, 1, 1, 105, 63, 1931, 'Walk on Air', 16712190, 'Racial', 16712190, 'Glide through the air for $d, steering your descent. Does not gain altitude.', 16712190, 'Gliding on the air. Turn to steer; you do not gain altitude.', 16712190, 1.0, 1.0, 1.0, 1, 1.0);
INSERT INTO `spell_dbc` (`ID`, `Attributes`, `CastingTimeIndex`, `RecoveryTime`, `ProcChance`, `RangeIndex`, `EquippedItemClass`, `Effect_1`, `EffectDieSides_1`, `ImplicitTargetA_1`, `SpellIconID`, `Name_Lang_enUS`, `Name_Lang_Mask`, `NameSubtext_Lang_enUS`, `NameSubtext_Lang_Mask`, `Description_Lang_enUS`, `Description_Lang_Mask`, `AuraDescription_Lang_Mask`, `EffectChainAmplitude_1`, `EffectChainAmplitude_2`, `EffectChainAmplitude_3`, `SchoolMask`) VALUES
(100801, 262160, 1, 90000, 101, 1, -1, 3, 1, 1, 505, 'Walk on Air', 16712190, 'Racial', 16712190, 'Glide through the air for $100800d, steering your descent by turning. Use it while falling or jumping. Does not gain altitude.', 16712190, 16712188, 1.0, 1.0, 1.0, 1);

-- The spellbook racial's script (src/BleakholdScripts.cpp): the glide's checks on the cast, the glide on the hit.
DELETE FROM `spell_script_names` WHERE `spell_id` = 100801 AND `ScriptName` = 'spell_bleakhold_walk_on_air';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (100801, 'spell_bleakhold_walk_on_air');
