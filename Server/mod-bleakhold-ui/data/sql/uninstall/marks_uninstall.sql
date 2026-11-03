-- mod-bleakhold-ui: removes the glowing marks (docs/BleakholdProtocol.md section 22) for good. NOT applied by the
-- database updater (it lives outside db-world and db-characters): run it by hand, with the worldserver stopped.
--
-- Before you run it:
--   1. Set BleakholdUi.Marks.Enable = 0 and type .bleakhold reload: every client clears its marks at the next HELLO.
--   2. Stop the worldserver, back up both databases, then run part 1 in the world database and part 2 in the
--      characters database (the USE lines below name the default databases; change them to yours).
--   3. Take the marks' client archive out (bash deploy/marks/build-marks.sh --rollback on the server; bleakserv's
--      deploy/README.md, "Glowing marks").
--
-- What stays: each database's `updates` table keeps its rows for data/sql/db-world/05_ and
-- data/sql/db-characters/02_ and for the catalogue revs (rev_<numbers>.sql whose first line holds "Bleakhold glowing
-- marks"). While the module is deployed, every worldserver start creates both tables again, empty (CREATE TABLE IF NOT
-- EXISTS, whatever BleakholdUi.Marks.Enable says); with an empty catalogue no race-sex is offered and the feature bit
-- stays off. The choices players paid for are gone with part 2.
--
-- To reinstall later: remove those `updates` rows, then run the update (bleakserv's deploy/update-bleakhold-ui.sh)
-- and deploy/marks/build-marks.sh again:
--   world:      DELETE FROM `updates` WHERE `name` IN ('05_bleakhold_marks_catalogue.sql', 'rev_<numbers>.sql');
--   characters: DELETE FROM `updates` WHERE `name` = '02_bleakhold_marks_characters.sql';

-- =====================================================================================================================
-- Part 1: the world database
-- =====================================================================================================================
-- USE `acore_world`;

DROP TABLE IF EXISTS `bleakhold_mark_catalogue`;

-- =====================================================================================================================
-- Part 2: the characters database
-- =====================================================================================================================
-- USE `acore_characters`;

DROP TABLE IF EXISTS `bleakhold_marks`;
