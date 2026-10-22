-- mod-bleakhold: world database tables.
-- Applied by the worldserver's database updater (Updates.EnableDatabases) or by hand; safe to run again.
-- Edit the rows with any SQL tool, then type .bleakhold reload in game (or restart).
-- Lists: numbers may be separated by commas or spaces ("1, 3, 4"); names by semicolons ("Volkhan; Ionar").

-- DEF A: Mythic+ affixes
CREATE TABLE IF NOT EXISTS `bleakhold_affix` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(40) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: affixes (DEF A)';

-- DEF E: eras (the raid era whose loot drops this week)
CREATE TABLE IF NOT EXISTS `bleakhold_era` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(48) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  `legacy_tier` INT UNSIGNED NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: eras (DEF E)';

-- DEF T: task templates (names and texts only: which tasks a player gets is your task system)
CREATE TABLE IF NOT EXISTS `bleakhold_task_template` (
  `id` INT UNSIGNED NOT NULL,
  `title` VARCHAR(48) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: task templates (DEF T)';

-- DEF B: weekly bonuses
CREATE TABLE IF NOT EXISTS `bleakhold_weekly_bonus` (
  `id` INT UNSIGNED NOT NULL,
  `title` VARCHAR(48) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: weekly bonuses (DEF B)';

-- DEF C: Dungeon Journey chapters
CREATE TABLE IF NOT EXISTS `bleakhold_chapter` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(60) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: journey chapters (DEF C)';

-- DEF D: dungeons by map id. bosses: names in kill order separated by ';' (boss i = bit i-1 of the key tracker)
CREATE TABLE IF NOT EXISTS `bleakhold_dungeon` (
  `map_id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(48) NOT NULL DEFAULT '',
  `chapter` INT UNSIGNED NULL DEFAULT NULL,
  `level_min` TINYINT UNSIGNED NULL DEFAULT NULL,
  `level_max` TINYINT UNSIGNED NULL DEFAULT NULL,
  `bosses` VARCHAR(500) NOT NULL DEFAULT '',
  `time_limit_sec` INT UNSIGNED NULL DEFAULT NULL COMMENT 'keystone timer',
  PRIMARY KEY (`map_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: dungeons (DEF D)';

-- DEF L: legacy (raid tier) definitions. source_dungeons: map ids
CREATE TABLE IF NOT EXISTS `bleakhold_legacy_tier` (
  `id` INT UNSIGNED NOT NULL,
  `label` VARCHAR(24) NOT NULL DEFAULT '',
  `raids` VARCHAR(80) NOT NULL DEFAULT '',
  `era_id` INT UNSIGNED NULL DEFAULT NULL,
  `source_dungeons` VARCHAR(100) NOT NULL DEFAULT '',
  `level_min` TINYINT UNSIGNED NULL DEFAULT NULL,
  `level_max` TINYINT UNSIGNED NULL DEFAULT NULL,
  `echo_boss` VARCHAR(48) NOT NULL DEFAULT '',
  `piece_total` TINYINT UNSIGNED NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: legacy tiers (DEF L)';

-- SET / LIDX: one legacy set per tier and class. item_ids in piece order; source_dungeons: map ids
CREATE TABLE IF NOT EXISTS `bleakhold_legacy_set` (
  `set_id` INT UNSIGNED NOT NULL,
  `tier` TINYINT UNSIGNED NOT NULL,
  `class_id` TINYINT UNSIGNED NOT NULL COMMENT 'ChrClasses id',
  `name` VARCHAR(60) NOT NULL DEFAULT '',
  `item_ids` VARCHAR(200) NOT NULL DEFAULT '',
  `source_dungeons` VARCHAR(100) NOT NULL DEFAULT '',
  `level_min` TINYINT UNSIGNED NULL DEFAULT NULL,
  `level_max` TINYINT UNSIGNED NULL DEFAULT NULL,
  `echo_boss` VARCHAR(48) NOT NULL DEFAULT '',
  `note` VARCHAR(120) NOT NULL DEFAULT '',
  PRIMARY KEY (`set_id`),
  KEY `idx_tier_class` (`tier`, `class_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: legacy sets (SET, LIDX)';

-- DEF S + SEASON: seasons. state: 0 past, 1 current, 2 upcoming (the module uses the row with state 1)
CREATE TABLE IF NOT EXISTS `bleakhold_season` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(60) NOT NULL DEFAULT '',
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  `state` TINYINT UNSIGNED NOT NULL DEFAULT 2,
  `war_effort_title` VARCHAR(60) NOT NULL DEFAULT '',
  `war_effort_text` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: seasons (DEF S, SEASON)';

-- SEASON: the parts of the war effort bar. A part is full at goal_points (0 = no bar for that part).
-- Points come only from your systems (Bleakhold::Ui::WarEffortAdd) or from token hand-ins (mod_bleakhold.conf).
CREATE TABLE IF NOT EXISTS `bleakhold_war_effort_part` (
  `season_id` INT UNSIGNED NOT NULL,
  `part_id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(40) NOT NULL DEFAULT '',
  `goal_points` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`season_id`, `part_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: war effort parts (SEASON P records)';

-- DEF K: war effort ranks. min_points: a player holds the highest rank whose min_points they reached;
-- NULL = the module does not assign this rank by points.
CREATE TABLE IF NOT EXISTS `bleakhold_war_effort_rank` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(48) NOT NULL DEFAULT '',
  `min_points` BIGINT UNSIGNED NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: war effort ranks (DEF K)';

-- DEF W + SEASON R records: season rewards. points_required > 0: earned at that many war effort points;
-- 0: your system reports it (Bleakhold::Ui::SetSeasonRewardSource), otherwise it is shown without a state.
CREATE TABLE IF NOT EXISTS `bleakhold_season_reward` (
  `id` INT UNSIGNED NOT NULL,
  `season_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `name` VARCHAR(40) NOT NULL DEFAULT '',
  `requirement_text` VARCHAR(120) NOT NULL DEFAULT '',
  `points_required` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: season rewards (DEF W)';

-- DEF M: the Mythic level ladder on the Keys tab (level 0 = Mythic 0)
CREATE TABLE IF NOT EXISTS `bleakhold_mythic_level` (
  `level` TINYINT UNSIGNED NOT NULL,
  `description` VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: mythic levels (DEF M)';

-- DEF X: extra classes your server adds (the ten stock classes need no row)
CREATE TABLE IF NOT EXISTS `bleakhold_extra_class` (
  `id` TINYINT UNSIGNED NOT NULL,
  `name` VARCHAR(24) NOT NULL DEFAULT '',
  `token` VARCHAR(24) NOT NULL DEFAULT '',
  `color_hex` CHAR(6) NOT NULL DEFAULT 'B8B2A6',
  `short_label` VARCHAR(4) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: extra classes (DEF X)';

-- DEF R: Eclipse Rift bosses (names only; the Rift itself is your system)
CREATE TABLE IF NOT EXISTS `bleakhold_rift_boss` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(48) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: rift bosses (DEF R)';

-- ERA: the week schedule. The row with the latest starts_at that has passed is this week; the next row
-- is "next week's era". affix_ids: the affixes of the week. Times are server (realm) time.
CREATE TABLE IF NOT EXISTS `bleakhold_week_schedule` (
  `starts_at` DATETIME NOT NULL,
  `era_id` INT UNSIGNED NOT NULL,
  `affix_ids` VARCHAR(50) NOT NULL DEFAULT '',
  `weekly_bonus_id` INT UNSIGNED NULL DEFAULT NULL,
  PRIMARY KEY (`starts_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: era and affixes per week (ERA)';
