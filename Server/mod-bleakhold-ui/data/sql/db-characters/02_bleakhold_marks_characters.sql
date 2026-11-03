-- mod-bleakhold-ui: the glowing marks' characters table (docs/BleakholdProtocol.md section 22). Safe to run again; the
-- module also runs this statement at startup (MarksRules::CharacterTablesSql in src/BleakholdMarksRules.h holds the same
-- text).
--
-- bleakhold_marks: each character's chosen mark (design and colour) and eye colour, written by MARKSET in the same
-- transaction as the money it cost. A stored choice the catalogue no longer offers is kept and reads as none. A deleted
-- character's row goes with it.

CREATE TABLE IF NOT EXISTS `bleakhold_marks` (
  `guid` INT UNSIGNED NOT NULL,
  `design` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 none, 1-4',
  `colour` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 none, 1-3',
  `eye` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 the race''s own, 1-5',
  `changes` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'accepted MARKSET changes (FirstFree: the first is free)',
  `changed_at` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'unix time of the last change (CooldownHours)',
  `paid_total` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'copper paid for changes, all told',
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
