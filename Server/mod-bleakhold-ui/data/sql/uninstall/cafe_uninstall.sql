-- mod-bleakhold-ui: removes the cafe (docs/BleakholdProtocol.md section 21) for good. NOT applied by the database
-- updater (it lives outside db-world and db-characters): run it by hand, with the worldserver stopped.
--
-- Before you run it:
--   1. Set BleakholdUi.Cafe.Enable = 0 and type .bleakhold reload (or .cafe reload): every shift ends and every order
--      that was paid and not served is refunded by mail. Orders still in bleakhold_cafe_order are lost with the table.
--   2. Stop the worldserver, back up both databases, then run part 1 in the world database and part 2 in the
--      characters database (the USE lines below name the default databases; change them to yours).
--   3. Take the cafe's client archives out (bash /root/cafeforge/restore.sh on the server; bleakserv's
--      deploy/README.md, the cafe's "Going back").
--
-- What stays: each database's `updates` table keeps its rows for data/sql/db-world/03_ and 04_, the cafe's DBC revs
-- (rev_<numbers>.sql) and data/sql/db-characters/01_.
-- ac-db-import never runs an applied file again while its content is unchanged, so the cafe stays removed across
-- updates; only a changed file runs again (a later module's changed 04_ brings the templates back, and the cafe stays
-- off without its spell rows: the startup log says what is missing). While the module is deployed, every worldserver
-- start creates the cafe's tables again, empty (CREATE TABLE IF NOT EXISTS, whatever BleakholdUi.Cafe.Enable says);
-- with the cafe off nothing uses them.
--
-- To reinstall later: remove those `updates` rows, then run the update (bleakserv's deploy/update-bleakhold-ui.sh)
-- as for a first install, so ac-db-import applies them all again. The cafe's revs are the files in
-- data/sql/updates/*db_world/ (and /root/bleakhold-generated-sql/pending_db_world) whose first line holds
-- "(mod-bleakhold-ui, The Lion's Roast":
--   world:      DELETE FROM `updates` WHERE `name` IN ('03_bleakhold_cafe_tables.sql',
--                   '04_bleakhold_cafe_templates.sql', 'rev_<numbers>.sql');   -- every cafe rev by its file name
--   characters: DELETE FROM `updates` WHERE `name` = '01_bleakhold_cafe_characters.sql';
--
-- Spawns: the module spawns the cafe at runtime and never writes it to `gameobject` or `creature`; part 1 still
-- removes any row a .gobject command left behind. `creature`.`id` is the core's column since the 2026_06_16_00 update
-- (id1 became id). The mysql client stops at the first error, so every line here must match the current schema.

-- =====================================================================================================================
-- Part 1: the world database
-- =====================================================================================================================
-- USE `acore_world`;

DROP TABLE IF EXISTS `bleakhold_cafe_piece`;
DROP TABLE IF EXISTS `bleakhold_cafe`;

DELETE ga FROM `gameobject_addon` ga JOIN `gameobject` g ON g.`guid` = ga.`guid` WHERE g.`id` BETWEEN 909300 AND 909379;
DELETE FROM `gameobject` WHERE `id` BETWEEN 909300 AND 909379;
DELETE ca FROM `creature_addon` ca JOIN `creature` c ON c.`guid` = ca.`guid` WHERE c.`id` BETWEEN 909300 AND 909379;
DELETE FROM `creature` WHERE `id` BETWEEN 909300 AND 909379;

DELETE FROM `gameobject_template_addon` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `gameobject_template_locale` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `creature_template_addon` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `creature_template_model` WHERE `CreatureID` BETWEEN 909300 AND 909379;
DELETE FROM `creature_template_locale` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `creature_template` WHERE `entry` BETWEEN 909300 AND 909379;
DELETE FROM `item_template_locale` WHERE `ID` BETWEEN 909380 AND 909389;
DELETE FROM `item_template` WHERE `entry` BETWEEN 909380 AND 909389;
DELETE FROM `npc_text_locale` WHERE `ID` BETWEEN 909300 AND 909319;
DELETE FROM `npc_text` WHERE `ID` BETWEEN 909300 AND 909319;
DELETE FROM `spell_custom_attr` WHERE `spell_id` BETWEEN 100900 AND 100959;
DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 100900 AND 100959;
DELETE FROM `gameobjectdisplayinfo_dbc` WHERE `ID` BETWEEN 19300 AND 19339;
DELETE FROM `chartitles_dbc` WHERE `ID` IN (190, 191);

-- =====================================================================================================================
-- Part 2: the characters database
-- =====================================================================================================================
-- USE `acore_characters`;

DROP TABLE IF EXISTS `bleakhold_cafe_flag`;
DROP TABLE IF EXISTS `bleakhold_cafe_order`;
DROP TABLE IF EXISTS `bleakhold_cafe_payout`;
DROP TABLE IF EXISTS `bleakhold_cafe_week`;
DROP TABLE IF EXISTS `bleakhold_cafe_day`;
DROP TABLE IF EXISTS `bleakhold_cafe_barista`;

-- the cafe's auras (drinks, the shift, Tired) and its items (aprons and the rest of 909380-909389), wherever they are
DELETE FROM `character_aura` WHERE `spell` BETWEEN 100900 AND 100959;
DELETE mi FROM `mail_items` mi JOIN `item_instance` ii ON ii.`guid` = mi.`item_guid`
    WHERE ii.`itemEntry` BETWEEN 909380 AND 909389;
DELETE ci FROM `character_inventory` ci JOIN `item_instance` ii ON ii.`guid` = ci.`item`
    WHERE ii.`itemEntry` BETWEEN 909380 AND 909389;
DELETE FROM `item_instance` WHERE `itemEntry` BETWEEN 909380 AND 909389;
