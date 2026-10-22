-- mod-bleakhold: characters database tables (records the module keeps itself). Safe to run again.

-- LB / LBME: finished runs reported by your systems (Bleakhold::Ui::RecordLeaderboardRun).
-- One row per group, board, season and dungeon: a group's better run replaces its older row.
CREATE TABLE IF NOT EXISTS `bleakhold_leaderboard` (
  `id` INT UNSIGNED NOT NULL,
  `board` CHAR(1) NOT NULL COMMENT 'K keys, R rift, E raid echoes',
  `season_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `dungeon_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `value` BIGINT NULL DEFAULT NULL COMMENT 'K: key level, R: floor',
  `time_sec` BIGINT NULL DEFAULT NULL COMMENT 'K: time left (negative = over time), R: run time, E: kill time',
  `date` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Unix time',
  `label` VARCHAR(48) NOT NULL DEFAULT '' COMMENT 'E: boss name',
  `team_key` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'sorted character guids',
  `members` VARCHAR(400) NOT NULL DEFAULT '' COMMENT 'Name~classId:Name~classId',
  `member_guids` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `idx_board` (`board`, `season_id`, `dungeon_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: leaderboard runs';

-- FIRSTS: server firsts (Bleakhold::Ui::RecordServerFirst), once per first_id.
CREATE TABLE IF NOT EXISTS `bleakhold_server_first` (
  `first_id` VARCHAR(64) NOT NULL,
  `kind_key` VARCHAR(16) NOT NULL DEFAULT '',
  `text` VARCHAR(120) NOT NULL DEFAULT '',
  `who` VARCHAR(80) NOT NULL DEFAULT '',
  `date` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Unix time',
  PRIMARY KEY (`first_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: server firsts';

-- SEASON: war effort points per character and part (Bleakhold::Ui::WarEffortAdd, token hand-ins).
CREATE TABLE IF NOT EXISTS `bleakhold_war_effort` (
  `season_id` INT UNSIGNED NOT NULL,
  `guid` INT UNSIGNED NOT NULL COMMENT 'characters.guid',
  `part_id` INT UNSIGNED NOT NULL,
  `points` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`season_id`, `guid`, `part_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: war effort contributions';
