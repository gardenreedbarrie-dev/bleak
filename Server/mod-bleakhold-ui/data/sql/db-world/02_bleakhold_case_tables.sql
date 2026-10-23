-- mod-bleakhold-ui: cases (docs/BleakholdProtocol.md section 15).
-- Applied by the worldserver's database updater (Updates.EnableDatabases) or by hand; safe to run again.
-- Edit the rows with any SQL tool, then type .bleakhold reload in game (or restart).
--
-- A case is any item listed here: the Bleakhold addon opens the case window when a player right-clicks it
-- in the bags, and Unlock asks the server to open one. The item needs no spell or loot of its own (give it
-- none, so a stock client cannot use it); class 15 (Miscellaneous) and a chest or box icon look right.

CREATE TABLE IF NOT EXISTS `bleakhold_case` (
  `item_id` INT UNSIGNED NOT NULL COMMENT 'the case item (item_template.entry)',
  `title` VARCHAR(60) NOT NULL DEFAULT '' COMMENT 'the window title; empty: the item name',
  `description` VARCHAR(120) NOT NULL DEFAULT '' COMMENT 'the line under the title',
  `key_item_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'an item needed (and used up) to open it; 0: none',
  `key_count` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `announce_tier` TINYINT UNSIGNED NOT NULL DEFAULT 5 COMMENT 'tell the realm about rewards of this tier or higher; 0: never',
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: cases';

CREATE TABLE IF NOT EXISTS `bleakhold_case_reward` (
  `case_item_id` INT UNSIGNED NOT NULL COMMENT 'bleakhold_case.item_id',
  `item_id` INT UNSIGNED NOT NULL COMMENT 'the reward (item_template.entry)',
  `sort` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'display order in the window',
  `count` SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  `weight` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'the chance is weight / the sum of the case''s weights; 0: off',
  `tier` TINYINT NOT NULL DEFAULT -1 COMMENT 'the card colour, 0 poor .. 6 artifact; -1: the item quality',
  PRIMARY KEY (`case_item_id`, `item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bleakhold: what each case can give';

-- Example (not applied): case item 990001 with three rewards, 45 % / 45 % / 10 %, the last one announced.
-- INSERT INTO `bleakhold_case` (`item_id`, `title`, `description`, `key_item_id`, `key_count`, `announce_tier`) VALUES
--   (990001, 'Arms Case', 'Unlock it to receive one of the items below.', 0, 1, 5);
-- INSERT INTO `bleakhold_case_reward` (`case_item_id`, `item_id`, `sort`, `count`, `weight`, `tier`) VALUES
--   (990001, 12584, 1, 1, 45, -1),
--   (990001, 13262, 2, 1, 45, -1),
--   (990001, 19019, 3, 1, 10, 5);
