-- mod-bleakhold-ui: starting rows for the world tables (INSERT IGNORE: rows you changed are kept).
-- Never change this file after a release: the database updater runs a changed file again, and rows you deleted
-- come back. New starting rows go into a new file (02_bleakhold_world_seed.sql, ...).
-- Names and texts are the Bleakhold UI's own built-in texts, so nothing changes on screen until you edit them.
-- Not filled on purpose (they are your game rules): bleakhold_week_schedule, bleakhold_war_effort_part, the
-- min_points of the ranks and the points_required of the rewards. Examples are at the end of this file.

INSERT IGNORE INTO `bleakhold_affix` (`id`, `name`, `description`) VALUES
(1, 'Fortified', 'Non-boss enemies have more health and hit harder.'),
(2, 'Tyrannical', 'Bosses have more health and hit harder.'),
(3, 'Bolstering', 'When a non-boss enemy dies, its allies nearby grow stronger.'),
(4, 'Volcanic', 'Plumes of flame erupt under players fighting at range.'),
(5, 'Raging', 'Non-boss enemies enrage when their health is low.'),
(6, 'Sanguine', 'Slain non-boss enemies leave a pool that heals their allies.'),
(7, 'Bursting', 'Slain non-boss enemies burst and hurt the whole group.'),
(8, 'Necrotic', 'Enemy melee hits stack a wound that reduces healing taken.');

INSERT IGNORE INTO `bleakhold_era` (`id`, `name`, `description`, `legacy_tier`) VALUES
(1, 'Molten Core', 'Tier 1 tokens and Molten Core loot drop in every key and Rift floor.', 1),
(2, 'Blackwing Lair', 'Tier 2 tokens and Blackwing Lair loot drop in every key and Rift floor.', 2),
(3, 'Ahn''Qiraj', 'Tier 2.5 tokens and Ahn''Qiraj loot drop in every key and Rift floor.', 3),
(4, 'Naxxramas', 'Tier 3 tokens and Naxxramas loot drop in every key and Rift floor.', 4),
(5, 'Karazhan', 'Tier 4 tokens, Karazhan, Gruul and Magtheridon loot drop in every key and Rift floor.', 5),
(6, 'Serpentshrine', 'Tier 5 tokens, Serpentshrine and Tempest Keep loot drop in every key and Rift floor.', 6),
(7, 'The Black Temple', 'Tier 6 tokens, Hyjal, Black Temple and Sunwell loot drop in every key and Rift floor.', 7);

INSERT IGNORE INTO `bleakhold_task_template` (`id`, `title`, `description`) VALUES
(1, 'Heroic hero', 'Clear any heroic dungeon.'),
(2, 'Key sweeper', 'Defeat 20 enemies inside a Mythic key.'),
(3, 'Into the Rift', 'Clear 5 Eclipse Rift floors.'),
(4, 'Timed and tested', 'Finish 3 keys of +5 or higher in time.'),
(5, 'Echo hunter', 'Defeat 2 Raid Echoes in keys or the Rift.'),
(6, 'Echoes of the era', 'Clear a dungeon or key this week.'),
(7, 'Journey onward', 'Finish 3 dungeons from the board.'),
(8, 'Bounty hunter', 'Finish today''s bounty dungeon.');

INSERT IGNORE INTO `bleakhold_weekly_bonus` (`id`, `title`, `description`) VALUES
(1, 'First Raid Lord Echo', 'Your first Raid Echo kill this week drops an era token for sure.');

INSERT IGNORE INTO `bleakhold_chapter` (`id`, `name`, `description`) VALUES
(1, 'Chapter I - Old Kingdoms', 'The first dungeons of the journey.'),
(2, 'Chapter II - Deep Places', 'Caverns, crypts and sunken halls.'),
(3, 'Chapter III - The Blackrock Depths', 'Fire and iron under the mountain.'),
(4, 'Chapter IV - Outland', 'Through the Dark Portal.'),
(5, 'Chapter V - Northrend', 'The last road north.');

INSERT IGNORE INTO `bleakhold_dungeon` (`map_id`, `name`, `chapter`, `level_min`, `level_max`, `bosses`, `time_limit_sec`) VALUES
(389, 'Ragefire Chasm', 1, 13, 18, '', NULL),
(36, 'The Deadmines', 1, 15, 21, '', NULL),
(43, 'Wailing Caverns', 1, 16, 22, '', NULL),
(33, 'Shadowfang Keep', 1, 18, 24, '', NULL),
(48, 'Blackfathom Deeps', 2, 21, 27, '', NULL),
(90, 'Gnomeregan', 2, 25, 31, '', NULL),
(47, 'Razorfen Kraul', 2, 27, 33, '', NULL),
(189, 'Scarlet Monastery', 2, 30, 40, '', NULL),
(209, 'Zul''Farrak', 3, 42, 48, '', NULL),
(349, 'Maraudon', 3, 44, 50, '', NULL),
(230, 'Blackrock Depths', 3, 50, 56, '', NULL),
(229, 'Blackrock Spire', 3, 55, 60, '', NULL),
(329, 'Stratholme', 3, 56, 61, '', NULL),
(289, 'Scholomance', 3, 56, 61, '', NULL),
(429, 'Dire Maul', 3, 56, 61, '', NULL),
(543, 'Hellfire Ramparts', 4, 58, 63, '', NULL),
(547, 'The Slave Pens', 4, 61, 66, '', NULL),
(558, 'Auchenai Crypts', 4, 64, 69, '', NULL),
(555, 'Shadow Labyrinth', 4, 67, 70, '', NULL),
(574, 'Utgarde Keep', 5, 69, 73, '', NULL),
(576, 'The Nexus', 5, 70, 74, '', NULL),
(604, 'Gundrak', 5, 74, 78, '', NULL),
(602, 'Halls of Lightning', 5, 77, 80, 'General Bjarngrim; Volkhan; Ionar; Loken', 1800),
(599, 'Halls of Stone', 5, 76, 80, 'Krystallus; Maiden of Grief; Tribunal of Ages; Sjonnir the Ironshaper', 1800),
(575, 'Utgarde Pinnacle', 5, 78, 80, 'Svala Sorrowgrave; Gortok Palehoof; Skadi the Ruthless; King Ymiron', 1800);

INSERT IGNORE INTO `bleakhold_legacy_tier` (`id`, `label`, `raids`, `era_id`, `source_dungeons`, `level_min`, `level_max`, `echo_boss`, `piece_total`) VALUES
(1, 'Tier 1', 'Molten Core, Zul''Gurub', 1, '229, 329, 289, 429, 543', 58, 61, 'Ragnaros', 8),
(2, 'Tier 2', 'Blackwing Lair, AQ20', 2, '229, 329, 289', 60, 63, 'Nefarian', 8),
(3, 'Tier 2.5', 'Temple of Ahn''Qiraj', 3, '349, 230', 60, 64, 'C''Thun', 5),
(4, 'Tier 3', 'Naxxramas 40', 4, '329, 289', 60, 65, 'Kel''Thuzad', 9),
(5, 'Tier 4', 'Karazhan, Gruul, Magtheridon', 5, '543, 547, 558', 66, 70, 'Prince Malchezaar', 5),
(6, 'Tier 5', 'Serpentshrine, Tempest Keep', 6, '555, 558', 68, 70, 'Kael''thas Sunstrider', 5),
(7, 'Tier 6', 'Hyjal, Black Temple, Sunwell', 7, '602, 599, 575', 70, 80, 'Illidan Stormrage', 8);

-- one example set (Tier 1, Warrior); add a row per tier and class
INSERT IGNORE INTO `bleakhold_legacy_set` (`set_id`, `tier`, `class_id`, `name`, `item_ids`, `source_dungeons`, `level_min`, `level_max`, `echo_boss`, `note`) VALUES
(201, 1, 1, 'Battlegear of Might', '16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862', '229, 329, 289, 429, 543', 58, 61, 'Ragnaros', '');

INSERT IGNORE INTO `bleakhold_season` (`id`, `name`, `description`, `state`, `war_effort_title`, `war_effort_text`) VALUES
(1, 'Season 1 - Bleak Dawn', 'Naxxramas, the Bleakhold raid, Mythic+ Season 1, Eclipse Rift', 1, 'Breach the Greymane Wall', 'Fill the bar together and the next season opens.'),
(2, 'Season 2 - The Fallen Kingdom', 'Gilneas, Karazhan Crypts, Ulduar', 2, '', ''),
(3, 'Season 3 - Twilight Gate', 'Grim Batol, Azshara Crater, Trial of the Crusader', 2, '', ''),
(4, 'Season 4 - Dream''s End', 'The Emerald Nightmare, Icecrown Citadel', 2, '', '');

INSERT IGNORE INTO `bleakhold_war_effort_rank` (`id`, `name`, `min_points`) VALUES
(1, 'Recruit of the Wall', NULL),
(2, 'Sergeant of the Wall', NULL),
(3, 'Captain of the Wall', NULL),
(4, 'Commander of the Wall', NULL);

INSERT IGNORE INTO `bleakhold_season_reward` (`id`, `season_id`, `name`, `requirement_text`, `points_required`) VALUES
(1, 1, 'Title', '"of the Bleak Dawn" at 500 points', 0),
(2, 1, 'Cosmetic set', 'Time 20 keys of +10 or higher', 0),
(3, 1, 'Season mount', 'Rift floor 30 solo', 0),
(4, 1, 'Banner', 'Top 100 War Effort', 0);

INSERT IGNORE INTO `bleakhold_mythic_level` (`level`, `description`) VALUES
(0, 'Where every keystone begins: beat a dungeon''s end boss on Mythic 0 to get your first key.'),
(2, 'Keystones start here. Enemies grow stronger with every level.'),
(4, 'A second affix joins the first.'),
(7, 'A third affix joins in.'),
(10, 'Bosses and enemies gain extra abilities.'),
(15, 'The highest keystone level.');

-- Examples (remove the leading "-- " to use them):
-- INSERT IGNORE INTO `bleakhold_week_schedule` (`starts_at`, `era_id`, `affix_ids`, `weekly_bonus_id`) VALUES
-- ('2026-10-21 04:00:00', 7, '1, 3, 4', 1),
-- ('2026-10-28 04:00:00', 3, '2, 5, 6', 1);
-- INSERT IGNORE INTO `bleakhold_war_effort_part` (`season_id`, `part_id`, `name`, `goal_points`) VALUES
-- (1, 1, 'Materials', 500000), (1, 2, 'Bosses and Echoes', 250000), (1, 3, 'Keys in time', 100000);
-- UPDATE `bleakhold_war_effort_rank` SET `min_points` = 0 WHERE `id` = 1;
-- UPDATE `bleakhold_war_effort_rank` SET `min_points` = 1000 WHERE `id` = 2;
-- UPDATE `bleakhold_season_reward` SET `points_required` = 500 WHERE `id` = 1;
