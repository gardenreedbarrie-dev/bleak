-- mod-bleakhold-ui: the glowing marks' catalogue (docs/BleakholdProtocol.md section 22). Applied by the worldserver's
-- database updater (Updates.EnableDatabases) or by hand; safe to run again. The module also runs this statement at
-- startup (MarksRules::WorldTablesSql in src/BleakholdMarksRules.h holds the same text), and so does the catalogue rev
-- of bleakserv's deploy/marks/build-marks.sh: the three texts are the same.
--
-- The module ships the table empty: build-marks.sh writes one row per mark look (M: 4 designs x 3 colours per
-- race-sex) and per eye sprite (E) from MarkForge's manifest, as a rev of its own, after the files reached the players
-- (patch-W.MPQ). The server reads it at startup and on .bleakhold reload, drops a row that breaks a rule (the log
-- says which), and offers a race-sex only with all 12 looks.

CREATE TABLE IF NOT EXISTS `bleakhold_mark_catalogue` (
  `race` TINYINT UNSIGNED NOT NULL, `sex` TINYINT UNSIGNED NOT NULL,
  `kind` CHAR(1) NOT NULL COMMENT 'M a mark look, E an eye sprite',
  `design` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'M: 1-4; E: 0',
  `colour` TINYINT UNSIGNED NOT NULL COMMENT 'M: 1-3; E: the eye, 1-5',
  `race_file` VARCHAR(16) NOT NULL,
  `design_key` VARCHAR(32) NOT NULL DEFAULT '', `design_name` VARCHAR(48) NOT NULL DEFAULT '',
  `colour_key` VARCHAR(32) NOT NULL, `colour_name` VARCHAR(48) NOT NULL,
  `hex` CHAR(6) NOT NULL, `glow` TINYINT UNSIGNED NOT NULL DEFAULT 0, `dk_only` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `texture` VARCHAR(120) NOT NULL, `sha1` CHAR(40) NOT NULL DEFAULT '',
  `build` VARCHAR(40) NOT NULL DEFAULT '' COMMENT 'the build-marks.sh build id (the manifest sha1)',
  PRIMARY KEY (`race`, `sex`, `kind`, `design`, `colour`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
