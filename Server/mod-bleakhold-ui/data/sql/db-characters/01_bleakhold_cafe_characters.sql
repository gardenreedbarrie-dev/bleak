-- mod-bleakhold-ui: the cafe's characters tables (docs/BleakholdProtocol.md section 21). Safe to run again; the module
-- also runs these statements at startup (CafeRules::CharacterTablesSql in src/BleakholdCafeRules.h holds the same text).
--
-- bleakhold_cafe_barista: progress per character; _day and _week: the daily caps and the weekly board;
-- _payout: one row per paid week and cafe (the payout never runs twice); _order: player orders that were paid and
-- not finished (written in the same transaction as every money move, refunded by mail at the next start);
-- _flag: bot hints for .cafe flags (never a punishment). A deleted character's rows go with it.

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_barista` (
  `guid` INT UNSIGNED NOT NULL, `account` INT UNSIGNED NOT NULL DEFAULT 0,
  `level` TINYINT UNSIGNED NOT NULL DEFAULT 1, `xp` INT UNSIGNED NOT NULL DEFAULT 0,
  `drinks` INT UNSIGNED NOT NULL DEFAULT 0, `perfects` INT UNSIGNED NOT NULL DEFAULT 0,
  `memory_drinks` INT UNSIGNED NOT NULL DEFAULT 0, `best_streak` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `fastest_ms` INT UNSIGNED NOT NULL DEFAULT 0, `weekly_wins` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `flags` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1 apprentice apron, 2 master apron, 4 golden apron, 8 title barista, 16 title legend, 32 tutorial done, 64/128 shot/steam lines heard',
  `crown_until` INT UNSIGNED NOT NULL DEFAULT 0, `staff_day` INT UNSIGNED NOT NULL DEFAULT 0,
  `shift_accum_sec` INT UNSIGNED NOT NULL DEFAULT 0, `off_shift_since` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_day` (
  `day_id` INT UNSIGNED NOT NULL, `guid` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `xp_full` SMALLINT UNSIGNED NOT NULL DEFAULT 0, `xp_half` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `tips` INT UNSIGNED NOT NULL DEFAULT 0, `points` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `drinks` SMALLINT UNSIGNED NOT NULL DEFAULT 0, `perfects` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `orders_placed` TINYINT UNSIGNED NOT NULL DEFAULT 0, `rush_served` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`day_id`, `guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_week` (
  `week_id` INT UNSIGNED NOT NULL, `guid` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL,
  `name` VARCHAR(30) NOT NULL DEFAULT '' COMMENT 'two names fit (mod-two-names: up to 30 characters)', `class` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `points` INT UNSIGNED NOT NULL DEFAULT 0, `drinks` INT UNSIGNED NOT NULL DEFAULT 0,
  `perfects` INT UNSIGNED NOT NULL DEFAULT 0, `days_mask` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `score_at` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'when points last rose (tie-break)',
  PRIMARY KEY (`week_id`, `guid`), KEY `idx_board` (`week_id`, `cafe_id`, `points`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_payout` (
  `week_id` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL, `paid_at` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`week_id`, `cafe_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_order` (
  `id` INT UNSIGNED NOT NULL COMMENT 'module counter, seeded with MAX(id)+1 at startup', `cafe_id` TINYINT UNSIGNED NOT NULL,
  `customer_guid` INT UNSIGNED NOT NULL, `customer_account` INT UNSIGNED NOT NULL,
  `recipe_id` SMALLINT UNSIGNED NOT NULL, `price` INT UNSIGNED NOT NULL, `tip` INT UNSIGNED NOT NULL,
  `state` CHAR(1) NOT NULL DEFAULT 'W' COMMENT 'W T H R; written in the same transaction as every money move', `barista_guid` INT UNSIGNED NOT NULL DEFAULT 0,
  `created` INT UNSIGNED NOT NULL, `ready_until` INT UNSIGNED NOT NULL DEFAULT 0,
  `share_pct` TINYINT UNSIGNED NOT NULL DEFAULT 60 COMMENT 'Order.BaristaSharePct when it was paid: every split of this order uses it',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_flag` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT, `guid` INT UNSIGNED NOT NULL, `at` INT UNSIGNED NOT NULL,
  `drinks` INT UNSIGNED NOT NULL, `perfect_permille` SMALLINT UNSIGNED NOT NULL, `release_sd_ms` SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (`id`), KEY `idx_guid` (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
