-- mod-bleakhold-ui: the cafe's world tables (docs/BleakholdProtocol.md section 21).
-- Applied by the worldserver's database updater (Updates.EnableDatabases) or by hand; safe to run again. The module
-- also runs these statements at startup (CafeRules::WorldTablesSql in src/BleakholdCafeRules.h holds the same text).
--
-- One bleakhold_cafe row per cafe and one bleakhold_cafe_piece row per piece, written by ".cafe build" and the other
-- .cafe placement commands (never by hand while the worldserver runs: the module keeps its own copy). The pieces are
-- spawned at runtime from these rows and never written to `gameobject` or `creature`. The templates come from
-- 04_bleakhold_cafe_templates.sql (Tools/CafeForge).

CREATE TABLE IF NOT EXISTS `bleakhold_cafe` (
  `id`         TINYINT UNSIGNED  NOT NULL COMMENT '1 The Lion''s Roast (Stormwind), 2 The Grinding Tusk (Orgrimmar)',
  `map`        SMALLINT UNSIGNED NOT NULL,
  `zone`       SMALLINT UNSIGNED NOT NULL,
  `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL, `o` FLOAT NOT NULL COMMENT 'anchor: where a customer orders, facing the counter',
  `layout_ver` SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  `enabled`    TINYINT UNSIGNED  NOT NULL DEFAULT 0,
  `placed_by`  VARCHAR(30)       NOT NULL DEFAULT '' COMMENT 'the GM''s name (two names fit: up to 30 characters)',
  `placed_at`  INT UNSIGNED      NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bleakhold_cafe_piece` (
  `cafe_id` TINYINT UNSIGNED  NOT NULL,
  `slot`    SMALLINT UNSIGNED NOT NULL COMMENT 'layout slot; 200+ for pieces added with .cafe add',
  `role`    VARCHAR(24)       NOT NULL COMMENT 'station_E, counter, backbar, chair_1, table_1, queue_3, door, path_1, staff_owner, decor, ...',
  `entry`   INT UNSIGNED      NOT NULL DEFAULT 0 COMMENT 'gameobject or creature entry (new-art entry; the stand-in is entry+30); 0 for markers',
  `link`    SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'chair or parasol: its table slot; on-counter piece: its counter or back bar slot',
  `f` FLOAT NOT NULL, `l` FLOAT NOT NULL, `u` FLOAT NOT NULL, `turn` FLOAT NOT NULL COMMENT 'relative to the anchor: forward, left, up (yards), turn (radians)',
  `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL, `o` FLOAT NOT NULL COMMENT 'world position, kept in step with f/l/u/turn',
  `snap`    TINYINT UNSIGNED  NOT NULL DEFAULT 1,
  `enabled` TINYINT UNSIGNED  NOT NULL DEFAULT 1,
  PRIMARY KEY (`cafe_id`, `slot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
