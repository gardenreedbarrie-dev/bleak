/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): the database (section 3.10). The world tables hold the placed cafes and their pieces
 * (BleakholdCafeSite.cpp writes them); the characters tables hold the baristas, their day and week rows, the player
 * orders with their money, the weekly payouts and the bot hints.
 *
 * Money (D13): every move of a player order's money is one CharacterDatabase transaction together with the order row's
 * new state and the player's SaveGoldToDB, or a mail inside that transaction. A crash never refunds money the
 * database never lost: an order row exists exactly when its price left the customer's saved purse.
 */

#include "BleakholdCafe.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Item.h"
#include "Log.h"
#include "Mail.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "WorldSession.h"

#include <algorithm>

namespace Bleakhold
{
    namespace D = CafeData;
    namespace R = CafeRules;

    namespace
    {
        constexpr uint64_t BaristaSaveGapMs = 30000;
        constexpr uint64_t BoardCacheMs = 15000;
        constexpr uint32_t CrownSec = 7 * 86400;
        constexpr uint32_t GoldenApron = 909384;

        std::string Esc(std::string s)
        {
            CharacterDatabase.EscapeString(s);
            return s;
        }

        std::string CafeName(uint8_t cafeId) { return std::string(D::Cafes[cafeId == 2 ? 1 : 0].name); }
        uint32_t OwnerOf(uint8_t cafeId) { return D::Cafes[cafeId == 2 ? 1 : 0].owner; }

        std::string Thousands(uint32_t v)
        {
            std::string s = std::to_string(v);
            for (int i = static_cast<int>(s.size()) - 3; i > 0; i -= 3)
                s.insert(static_cast<std::size_t>(i), ",");
            return s;
        }
    }

    // =============================================================================================================
    // Tables and startup
    // =============================================================================================================
    void Cafe::EnsureTables()
    {
        for (std::string_view sql : R::WorldTablesSql)
            WorldDatabase.DirectExecute(sql);
        for (std::string_view sql : R::CharacterTablesSql)
            CharacterDatabase.DirectExecute(sql);
        for (R::AddedColumn const& c : R::CharacterAddedColumns)
            if (!CharacterDatabase.Query("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND "
                "TABLE_NAME = '{}' AND COLUMN_NAME = '{}'", c.table, c.column))
            {
                CharacterDatabase.DirectExecute(c.alter);
                LOG_INFO("module", "[Bleakhold] Cafe: added the column {} to {}", c.column, c.table);
            }
        // a name column narrower than a two-part name (a table from an earlier copy of the module SQL)
        auto widen = [](auto& db, R::WidenedColumn const& c) {
            if (!db.Query("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{}' "
                "AND COLUMN_NAME = '{}' AND CHARACTER_MAXIMUM_LENGTH < {}", c.table, c.column, c.chars))
                return;
            db.DirectExecute(c.modify);
            LOG_INFO("module", "[Bleakhold] Cafe: widened the column {} of {} to {} characters", c.column, c.table, c.chars);
        };
        for (R::WidenedColumn const& c : R::WorldWidenedColumns)
            widen(WorldDatabase, c);
        for (R::WidenedColumn const& c : R::CharacterWidenedColumns)
            widen(CharacterDatabase, c);
    }

    // Order ids continue the table's (BHW::Front::AddOutpost's MAX(id) + 1 pattern): no LAST_INSERT_ID round trip.
    void Cafe::SeedOrderIds()
    {
        _nextOrderId = 1;
        if (QueryResult r = CharacterDatabase.Query("SELECT MAX(`id`) FROM `bleakhold_cafe_order`"))
            if (!(*r)[0].IsNull())
                _nextOrderId = (*r)[0].Get<uint32>() + 1;
    }

    // Section 3.8.5: an order row is what was paid. W, T, H: all back; R with a barista paid: the house share back;
    // R made by the house: all back (the restart, not the customer, broke the pickup). One transaction per row.
    void Cafe::SettleLeftoverOrders()
    {
        QueryResult r = CharacterDatabase.Query("SELECT `id`, `cafe_id`, `customer_guid`, `price`, `tip`, `state`, "
            "`barista_guid`, `share_pct` FROM `bleakhold_cafe_order`");
        if (!r)
            return;
        uint32_t count = 0;
        uint64_t total = 0;
        do
        {
            Field* f = r->Fetch();
            uint32_t const id = f[0].Get<uint32>();
            uint8_t const cafeId = f[1].Get<uint8>();
            uint32_t const customer = f[2].Get<uint32>();
            uint32_t const price = f[3].Get<uint32>();
            uint32_t const tip = f[4].Get<uint32>();
            std::string const state = f[5].Get<std::string>();
            uint32_t const barista = f[6].Get<uint32>();
            uint32_t const sharePct = f[7].Get<uint8>();   // the share the wage was paid at, not today's config
            R::Money const m = R::SettleOrder(R::StartupEnd(state.empty() ? 'W' : state[0], barista != 0), price, tip,
                sharePct);
            CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
            if (m.refunded)
                MailMoney(customer, cafeId, m.refunded, CafeName(cafeId) + ": refund",
                    "The cafe had to close before your drink was ready. Here is your money back.", &t);
            t->Append("DELETE FROM `bleakhold_cafe_order` WHERE `id` = {}", id);
            CharacterDatabase.CommitTransaction(t);
            ++count;
            total += m.refunded;
        } while (r->NextRow());
        LOG_INFO("module", "[Bleakhold] Cafe money: {} orders left from the last run settled, {}c refunded by mail", count,
            total);
    }

    void Cafe::LoadSites()
    {
        for (CafeRt& c : _cafes)
        {
            c.placed = false;
            c.pieces.clear();
        }
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `map`, `zone`, `x`, `y`, `z`, `o`, `layout_ver`, `enabled`, "
            "`placed_by`, `placed_at` FROM `bleakhold_cafe`"))
            do
            {
                Field* f = r->Fetch();
                CafeRt* c = CafeOf(f[0].Get<uint8>());
                if (!c)
                    continue;
                c->placed = true;
                c->map = f[1].Get<uint16>();
                c->zone = f[2].Get<uint16>();
                c->anchor = { f[3].Get<float>(), f[4].Get<float>(), f[5].Get<float>(), f[6].Get<float>() };
                c->layoutVer = f[7].Get<uint16>();
                c->enabled = f[8].Get<uint8>() != 0;
                c->placedBy = f[9].Get<std::string>();
                c->placedAt = f[10].Get<uint32>();
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `cafe_id`, `slot`, `role`, `entry`, `link`, `f`, `l`, `u`, `turn`, "
            "`x`, `y`, `z`, `o`, `snap`, `enabled` FROM `bleakhold_cafe_piece` ORDER BY `cafe_id`, `slot`"))
            do
            {
                Field* f = r->Fetch();
                CafeRt* c = CafeOf(f[0].Get<uint8>());
                if (!c || !c->placed)
                    continue;
                Piece p;
                p.slot = f[1].Get<uint16>();
                p.role = f[2].Get<std::string>();
                p.entry = f[3].Get<uint32>();
                p.link = f[4].Get<uint16>();
                p.f = f[5].Get<float>();
                p.l = f[6].Get<float>();
                p.u = f[7].Get<float>();
                p.turn = f[8].Get<float>();
                p.x = f[9].Get<float>();
                p.y = f[10].Get<float>();
                p.z = f[11].Get<float>();
                p.o = f[12].Get<float>();
                p.snap = f[13].Get<uint8>() != 0;
                p.enabled = f[14].Get<uint8>() != 0;
                p.creature = p.role.rfind("staff_", 0) == 0;
                c->pieces[p.slot] = p;
            } while (r->NextRow());
        for (CafeRt& c : _cafes)
        {
            if (!c.placed)
                continue;
            if (c.pieces.empty())
            {
                LOG_ERROR("module", "[Bleakhold] Cafe: {} has a bleakhold_cafe row but no pieces; .cafe build {} force",
                    CafeName(c.id), D::Cafes[c.id - 1].cityKey);
                c.placed = false;
                continue;
            }
            SpawnSite(c);   // the furniture spawns whatever BleakholdUi.Cafe.Enable says; the staff only while it is on
            BuildSite(c);
        }
    }

    bool Cafe::SaveCafeRow(CafeRt const& c)
    {
        WorldDatabase.DirectExecute(Acore::StringFormat("REPLACE INTO `bleakhold_cafe` (`id`, `map`, `zone`, `x`, `y`, "
            "`z`, `o`, `layout_ver`, `enabled`, `placed_by`, `placed_at`) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, '{}', {})",
            c.id, c.map, c.zone, c.anchor.x, c.anchor.y, c.anchor.z, c.anchor.o, c.layoutVer, c.enabled ? 1 : 0,
            Esc(c.placedBy), c.placedAt));
        // DirectExecute does not say whether the row was written: read it back
        QueryResult r = WorldDatabase.Query("SELECT `enabled` FROM `bleakhold_cafe` WHERE `id` = {}", c.id);
        if (!r || ((*r)[0].Get<uint8>() != 0) != c.enabled)
        {
            LOG_ERROR("module", "[Bleakhold] Cafe: the bleakhold_cafe row of {} could not be written", CafeName(c.id));
            return false;
        }
        return true;
    }

    bool Cafe::SavePieceRows(CafeRt const& c, std::vector<uint16_t> const& slots)
    {
        if (slots.empty())
            return true;
        WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
        for (uint16_t slot : slots)
        {
            auto it = c.pieces.find(slot);
            if (it == c.pieces.end())
                continue;
            Piece const& p = it->second;
            std::string role = p.role;
            WorldDatabase.EscapeString(role);
            t->Append("REPLACE INTO `bleakhold_cafe_piece` (`cafe_id`, `slot`, `role`, `entry`, `link`, `f`, `l`, `u`, "
                "`turn`, `x`, `y`, `z`, `o`, `snap`, `enabled`) VALUES ({}, {}, '{}', {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, "
                "{}, {})", c.id, p.slot, role, p.entry, p.link, p.f, p.l, p.u, p.turn, p.x, p.y, p.z, p.o, p.snap ? 1 : 0,
                p.enabled ? 1 : 0);
        }
        WorldDatabase.DirectCommitTransaction(t);
        // read back: every row there, with its entry
        std::map<uint16_t, uint32_t> found;
        if (QueryResult r = WorldDatabase.Query("SELECT `slot`, `entry` FROM `bleakhold_cafe_piece` WHERE `cafe_id` = {}", c.id))
            do
            {
                Field* f = r->Fetch();
                found[f[0].Get<uint16>()] = f[1].Get<uint32>();
            } while (r->NextRow());
        for (uint16_t slot : slots)
        {
            auto it = c.pieces.find(slot);
            if (it == c.pieces.end())
                continue;
            auto row = found.find(slot);
            if (row == found.end() || row->second != it->second.entry)
            {
                LOG_ERROR("module", "[Bleakhold] Cafe: the piece row {} of {} could not be written", slot, CafeName(c.id));
                return false;
            }
        }
        return true;
    }

    bool Cafe::DeletePieceRow(uint8_t cafeId, uint16_t slot)
    {
        WorldDatabase.DirectExecute(Acore::StringFormat("DELETE FROM `bleakhold_cafe_piece` WHERE `cafe_id` = {} AND "
            "`slot` = {}", cafeId, slot));
        return !WorldDatabase.Query("SELECT 1 FROM `bleakhold_cafe_piece` WHERE `cafe_id` = {} AND `slot` = {}", cafeId, slot);
    }

    bool Cafe::DeleteSiteRows(uint8_t cafeId)
    {
        WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
        t->Append("DELETE FROM `bleakhold_cafe_piece` WHERE `cafe_id` = {}", cafeId);
        t->Append("DELETE FROM `bleakhold_cafe` WHERE `id` = {}", cafeId);
        WorldDatabase.DirectCommitTransaction(t);
        return !WorldDatabase.Query("SELECT 1 FROM `bleakhold_cafe` WHERE `id` = {}", cafeId);
    }

    // =============================================================================================================
    // Baristas (section 3.10.4: loaded the first time a player touches the cafe, saved when dirty)
    // =============================================================================================================
    Cafe::Barista* Cafe::LoadedBarista(uint32_t lowGuid)
    {
        auto it = _baristas.find(lowGuid);
        return it == _baristas.end() ? nullptr : &it->second;
    }

    Cafe::Barista& Cafe::BaristaOf(Player* player)
    {
        uint32_t const low = player->GetGUID().GetCounter();
        auto it = _baristas.find(low);
        if (it != _baristas.end())
        {
            it->second.expireMs = 0;
            return it->second;
        }
        Barista& b = _baristas[low];
        b.low = low;
        b.account = player->GetSession() ? player->GetSession()->GetAccountId() : 0;
        b.name = player->GetName();
        b.classId = player->getClass();
        LoadBaristaRow(b);
        return b;
    }

    void Cafe::LoadBaristaRow(Barista& b)
    {
        if (QueryResult r = CharacterDatabase.Query("SELECT `xp`, `drinks`, `perfects`, `memory_drinks`, `best_streak`, "
            "`fastest_ms`, `weekly_wins`, `flags`, `crown_until`, `staff_day`, `shift_accum_sec`, `off_shift_since` FROM "
            "`bleakhold_cafe_barista` WHERE `guid` = {}", b.low))
        {
            Field* f = r->Fetch();
            b.exists = true;
            b.xp = f[0].Get<uint32>();
            b.level = R::LevelOf(b.xp);
            b.drinks = f[1].Get<uint32>();
            b.perfects = f[2].Get<uint32>();
            b.memoryDrinks = f[3].Get<uint32>();
            b.bestStreak = f[4].Get<uint16>();
            b.fastestMs = f[5].Get<uint32>();
            b.weeklyWins = f[6].Get<uint16>();
            b.flags = f[7].Get<uint32>();
            b.crownUntil = f[8].Get<uint32>();
            b.staffDay = f[9].Get<uint32>();
            b.tired.accumSec = f[10].Get<uint32>();
            b.tired.offSince = f[11].Get<uint32>();
            b.tired = R::TiredLoaded(b.tired, _startSec);   // a shift the last run never ended: the break counts
        }
        b.day = DayRow();
        b.day.dayId = _dayId;
        if (QueryResult r = CharacterDatabase.Query("SELECT `cafe_id`, `xp_full`, `xp_half`, `tips`, `points`, `drinks`, "
            "`perfects`, `orders_placed`, `rush_served` FROM `bleakhold_cafe_day` WHERE `day_id` = {} AND `guid` = {}",
            _dayId, b.low))
        {
            Field* f = r->Fetch();
            b.day.cafeId = f[0].Get<uint8>();
            b.day.xpFull = f[1].Get<uint16>();
            b.day.xpHalf = f[2].Get<uint16>();
            b.day.tips = f[3].Get<uint32>();
            b.day.points = f[4].Get<uint16>();
            b.day.drinks = f[5].Get<uint16>();
            b.day.perfects = f[6].Get<uint16>();
            b.day.ordersPlaced = f[7].Get<uint8>();
            b.day.rushServed = f[8].Get<uint16>();
        }
        b.week = WeekRowRt();
        b.week.weekId = _weekId;
        if (QueryResult r = CharacterDatabase.Query("SELECT `cafe_id`, `points`, `drinks`, `perfects`, `days_mask`, "
            "`score_at` FROM `bleakhold_cafe_week` WHERE `week_id` = {} AND `guid` = {}", _weekId, b.low))
        {
            Field* f = r->Fetch();
            b.week.cafeId = f[0].Get<uint8>();
            b.week.points = f[1].Get<uint32>();
            b.week.drinks = f[2].Get<uint32>();
            b.week.perfects = f[3].Get<uint32>();
            b.week.daysMask = f[4].Get<uint8>();
            b.week.scoreAt = f[5].Get<uint32>();
        }
    }

    void Cafe::RollDay(Barista& b)
    {
        if (b.day.dayId == _dayId)
            return;
        if (b.day.dirty)
            SaveDayWeek(b);
        uint8_t const cafeId = b.day.cafeId;
        b.day = DayRow();
        b.day.dayId = _dayId;
        b.day.cafeId = cafeId;
        if (b.staffDay != _dayId)
            b.staffOffer = false;
    }

    void Cafe::SaveBarista(Barista& b, bool sync)
    {
        SaveDayWeek(b);
        if (!b.dirty)
            return;
        std::string const sql = Acore::StringFormat("REPLACE INTO `bleakhold_cafe_barista` (`guid`, `account`, `level`, "
            "`xp`, `drinks`, `perfects`, `memory_drinks`, `best_streak`, `fastest_ms`, `weekly_wins`, `flags`, "
            "`crown_until`, `staff_day`, `shift_accum_sec`, `off_shift_since`) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, "
            "{}, {}, {}, {}, {}, {})", b.low, b.account, b.level, b.xp, b.drinks, b.perfects, b.memoryDrinks,
            std::min<uint32_t>(b.bestStreak, 65535), b.fastestMs, std::min<uint32_t>(b.weeklyWins, 65535), b.flags,
            b.crownUntil, b.staffDay, b.tired.accumSec, b.tired.offSince);
        if (sync)
            CharacterDatabase.DirectExecute(sql);
        else
            CharacterDatabase.Execute(sql);
        b.dirty = false;
        b.exists = true;
        b.lastSaveMs = Mgr::NowMs();
    }

    void Cafe::SaveDayWeek(Barista& b)
    {
        if (b.day.dirty)
        {
            DayRow const& d = b.day;
            CharacterDatabase.Execute("INSERT INTO `bleakhold_cafe_day` (`day_id`, `guid`, `cafe_id`, `xp_full`, `xp_half`, "
                "`tips`, `points`, `drinks`, `perfects`, `orders_placed`, `rush_served`) VALUES ({}, {}, {}, {}, {}, {}, {}, "
                "{}, {}, {}, {}) ON DUPLICATE KEY UPDATE `cafe_id` = VALUES(`cafe_id`), `xp_full` = VALUES(`xp_full`), "
                "`xp_half` = VALUES(`xp_half`), `tips` = VALUES(`tips`), `points` = VALUES(`points`), `drinks` = "
                "VALUES(`drinks`), `perfects` = VALUES(`perfects`), `orders_placed` = VALUES(`orders_placed`), "
                "`rush_served` = VALUES(`rush_served`)", d.dayId, b.low, d.cafeId, std::min<uint32_t>(d.xpFull, 65535),
                std::min<uint32_t>(d.xpHalf, 65535), d.tips, std::min<uint32_t>(d.points, 65535),
                std::min<uint32_t>(d.drinks, 65535), std::min<uint32_t>(d.perfects, 65535),
                std::min<uint32_t>(d.ordersPlaced, 255), std::min<uint32_t>(d.rushServed, 65535));
            b.day.dirty = false;
        }
        if (b.week.dirty && b.week.cafeId)
        {
            WeekRowRt const& w = b.week;
            CharacterDatabase.Execute("INSERT INTO `bleakhold_cafe_week` (`week_id`, `guid`, `cafe_id`, `name`, `class`, "
                "`points`, `drinks`, `perfects`, `days_mask`, `score_at`) VALUES ({}, {}, {}, '{}', {}, {}, {}, {}, {}, {}) "
                "ON DUPLICATE KEY UPDATE `cafe_id` = VALUES(`cafe_id`), `name` = VALUES(`name`), `class` = VALUES(`class`), "
                "`points` = VALUES(`points`), `drinks` = VALUES(`drinks`), `perfects` = VALUES(`perfects`), `days_mask` = "
                "VALUES(`days_mask`), `score_at` = VALUES(`score_at`)", w.weekId, b.low, w.cafeId,
                Esc(R::NameForColumn(b.name)), b.classId, w.points, w.drinks, w.perfects, w.daysMask, w.scoreAt);
            b.week.dirty = false;
            _boards.erase({ w.weekId, w.cafeId });
        }
    }

    void Cafe::FlushDb(uint64_t nowMs, bool all)
    {
        for (auto& [low, b] : _baristas)
        {
            SaveDayWeek(b);
            if (b.dirty && (all || nowMs - b.lastSaveMs >= BaristaSaveGapMs))
                SaveBarista(b);
        }
    }

    // =============================================================================================================
    // Player orders and their money (sections 3.4.5 and 3.8)
    // =============================================================================================================
    void Cafe::MailMoney(uint32_t lowGuid, uint8_t cafeId, uint32_t copper, std::string const& subject,
        std::string const& body, CharacterDatabaseTransaction* trans)
    {
        if (!copper || !lowGuid || !trans)
            return;
        MailDraft(subject, body).AddMoney(copper).SendMailTo(*trans, MailReceiver(lowGuid),
            MailSender(MAIL_CREATURE, OwnerOf(cafeId)), MAIL_CHECK_MASK_NONE);
    }

    // CORDER: the money leaves the purse and the row is written in one transaction with the purse.
    bool Cafe::PayOrder(Player* player, Order const& o)
    {
        uint32_t const total = o.price + o.tip;
        if (!player->ModifyMoney(-static_cast<int32_t>(total), false))
            return false;
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        player->SaveGoldToDB(t);
        t->Append("INSERT INTO `bleakhold_cafe_order` (`id`, `cafe_id`, `customer_guid`, `customer_account`, `recipe_id`, "
            "`price`, `tip`, `state`, `barista_guid`, `created`, `ready_until`, `share_pct`) VALUES ({}, {}, {}, {}, {}, {}, "
            "{}, 'W', 0, {}, 0, {})", o.id, o.cafeId, o.customerLow, o.customerAccount, o.recipeId, o.price, o.tip, NowSec(),
            uint32_t(o.sharePct));
        CharacterDatabase.CommitTransaction(t);
        return true;
    }

    // A state change without money (W -> T -> H, house-made R): the row follows the order.
    void Cafe::SaveOrderState(Order const& o)
    {
        if (o.kind != 'P')
            return;
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        t->Append("UPDATE `bleakhold_cafe_order` SET `state` = '{}', `barista_guid` = {}, `ready_until` = {} WHERE `id` = {}",
            o.state == 'T' || o.state == 'H' || o.state == 'R' ? o.state : 'W', o.state == 'T' ? o.baristaLow : 0u,
            o.state == 'R' ? o.readyUntilEpoch : 0u, o.id);
        CharacterDatabase.CommitTransaction(t);
    }

    // Served by a barista: the wage and the order's R state in one transaction (a mail when the purse is full or the
    // barista is gone).
    void Cafe::PayWage(Order& o, Player* barista, uint32_t wage)
    {
        o.readyUntilEpoch = NowSec() + _cfg.pickupSec;
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        bool mailed = false;
        if (wage && barista && barista->ModifyMoney(static_cast<int32_t>(wage), false))
            barista->SaveGoldToDB(t);
        else if (wage)
        {
            MailMoney(o.baristaLow, o.cafeId, wage, CafeName(o.cafeId) + ": your wages",
                "For the drink you made. The customer's tip is in it too.", &t);
            mailed = true;
        }
        t->Append("UPDATE `bleakhold_cafe_order` SET `state` = 'R', `barista_guid` = {}, `ready_until` = {} WHERE `id` = {}",
            o.baristaLow, o.readyUntilEpoch, o.id);
        CharacterDatabase.CommitTransaction(t);
        LOG_INFO("module", "[Bleakhold] Cafe money: order {}: wage {}c to {}{}", o.id, wage, o.baristaName,
            mailed ? " (by mail)" : "");
    }

    // A refund (all of it, or the house share of an expired pickup) and the row's DELETE in one transaction.
    void Cafe::RefundOrder(Order const& o, uint32_t amount, std::string_view why)
    {
        if (o.kind != 'P')
            return;
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        bool mailed = false;
        if (amount)
        {
            Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid));
            if (cu && cu->ModifyMoney(static_cast<int32_t>(amount), false))
                cu->SaveGoldToDB(t);
            else
            {
                MailMoney(o.customerLow, o.cafeId, amount, CafeName(o.cafeId) + ": refund",
                    "Your order could not be finished. Here is your money back.", &t);
                mailed = true;
            }
        }
        t->Append("DELETE FROM `bleakhold_cafe_order` WHERE `id` = {}", o.id);
        CharacterDatabase.CommitTransaction(t);
        LOG_INFO("module", "[Bleakhold] Cafe money: order {} ({}): {}c refunded to {}{}", o.id, why, amount, o.customer,
            mailed ? " by mail" : "");
    }

    void Cafe::DeleteOrderRow(uint32_t orderId)
    {
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        t->Append("DELETE FROM `bleakhold_cafe_order` WHERE `id` = {}", orderId);
        CharacterDatabase.CommitTransaction(t);
    }

    // =============================================================================================================
    // The weekly board (section 3.9.7)
    // =============================================================================================================
    std::vector<R::WeekRow> Cafe::WeekRows(uint32_t weekId, uint8_t cafeId)
    {
        std::vector<R::WeekRow> rows;
        if (QueryResult r = CharacterDatabase.Query("SELECT `guid`, `name`, `class`, `points`, `drinks`, `perfects`, "
            "`days_mask`, `score_at` FROM `bleakhold_cafe_week` WHERE `week_id` = {} AND `cafe_id` = {} AND `drinks` >= {}",
            weekId, cafeId, _cfg.weeklyMinDrinks))
            do
            {
                Field* f = r->Fetch();
                R::WeekRow w;
                w.guid = f[0].Get<uint32>();
                w.cafeId = cafeId;
                w.name = f[1].Get<std::string>();
                w.classId = f[2].Get<uint8>();
                w.points = f[3].Get<uint32>();
                w.drinks = f[4].Get<uint32>();
                w.perfects = f[5].Get<uint32>();
                w.daysMask = f[6].Get<uint8>();
                w.scoreAt = f[7].Get<uint32>();
                rows.push_back(std::move(w));
            } while (r->NextRow());
        return R::WeeklyRank(std::move(rows), _cfg.weeklyMinDrinks, _cfg.weeklyMinDays);
    }

    // The ranked board of a week and cafe, cached for 15 s (LBQ C, CAFP, the gossip's top 3).
    std::vector<R::WeekRow> const& Cafe::BoardRows(uint32_t weekId, uint8_t cafeId)
    {
        uint64_t const now = Mgr::NowMs();
        if (!R::BoardCached(weekId, _weekId))
        {
            // another week (LBQ C names any): read for this answer only, so the cache never grows with them
            _boardOther = (cafeId == 1 || cafeId == 2) ? WeekRows(weekId, cafeId) : std::vector<R::WeekRow>();
            return _boardOther;
        }
        BoardCache& cache = _boards[{ weekId, cafeId }];
        if (!cache.atMs || now - cache.atMs >= BoardCacheMs)
        {
            cache.ranked = (cafeId == 1 || cafeId == 2) ? WeekRows(weekId, cafeId) : std::vector<R::WeekRow>();
            cache.atMs = now;
        }
        return cache.ranked;
    }

    void Cafe::LoadLastWinners()
    {
        _lastWinners.clear();
        if (!_weekId)
            return;
        for (uint8_t cafeId : { uint8_t(1), uint8_t(2) })
        {
            std::vector<R::WeekRow> const ranked = WeekRows(_weekId - 1, cafeId);
            if (ranked.empty())
                continue;
            _lastWinners.push_back({ _weekId - 1, cafeId, ranked[0].name, ranked[0].points });
        }
    }

    // The payout of an ended week: once per (week, cafe) (bleakhold_cafe_payout), every mail of a cafe and the payout row
    // in one transaction. `dry` only reports.
    void Cafe::WeeklyPayout(uint32_t weekId, bool dry, Reply const* say)
    {
        uint32_t totals[2] = { 0, 0 };
        std::string topLines[2];
        for (uint8_t cafeId : { uint8_t(1), uint8_t(2) })
        {
            std::string const cafe = CafeName(cafeId);
            if (QueryResult r = CharacterDatabase.Query("SELECT CAST(COALESCE(SUM(`drinks`), 0) AS UNSIGNED) FROM "
                "`bleakhold_cafe_week` WHERE `week_id` = {} AND `cafe_id` = {}", weekId, cafeId))
                totals[cafeId - 1] = static_cast<uint32_t>(std::min<uint64_t>((*r)[0].Get<uint64>(), 0xFFFFFFFFull));
            if (!dry && CharacterDatabase.Query("SELECT 1 FROM `bleakhold_cafe_payout` WHERE `week_id` = {} AND `cafe_id` = {}",
                weekId, cafeId))
            {
                if (say)
                    (*say)(cafe + ": week " + std::to_string(weekId) + " was paid already.");
                continue;
            }
            std::vector<R::WeekRow> const ranked = WeekRows(weekId, cafeId);
            if (dry)
            {
                if (say)
                {
                    (*say)(cafe + ", week " + std::to_string(weekId) + ": " + std::to_string(ranked.size()) + " eligible");
                    for (std::size_t i = 0; i < ranked.size() && i < 10; ++i)
                        (*say)("  #" + std::to_string(i + 1) + " " + ranked[i].name + ": " + std::to_string(ranked[i].points) +
                            " points, " + std::to_string(ranked[i].drinks) + " drinks, " +
                            std::to_string(R::PerfectPermille(ranked[i].perfects, ranked[i].drinks)) + " permille Perfect, " +
                            std::to_string(R::Payout(static_cast<uint32_t>(i + 1), _cfg.weeklyRewardCopper)) + "c");
                }
                continue;
            }
            CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
            uint32_t const now = NowSec();
            for (std::size_t i = 0; i < ranked.size(); ++i)
            {
                uint32_t const rank = static_cast<uint32_t>(i + 1);
                uint32_t const copper = R::Payout(rank, _cfg.weeklyRewardCopper);
                R::WeekRow const& w = ranked[i];
                if (copper)
                    MailMoney(w.guid, cafeId, copper, cafe + ": Best Barista of the week",
                        "You finished #" + std::to_string(rank) + " on this week's board. Well brewed!", &t);
                if (rank != 1)
                    continue;
                // #1: the crown for a week, a win, and the Golden Apron the first time
                uint32_t flags = 0;
                if (QueryResult f = CharacterDatabase.Query("SELECT `flags` FROM `bleakhold_cafe_barista` WHERE `guid` = {}", w.guid))
                    flags = (*f)[0].Get<uint32>();
                if (Barista* b = LoadedBarista(w.guid))
                    flags = b->flags;
                uint32_t const gain = (flags & CafeRewardGolden) ? 0u : static_cast<uint32_t>(CafeRewardGolden);
                if (gain)
                {
                    MailDraft draft(cafe + ": the Golden Apron", "The first Best Barista of the week at " + cafe +
                        " wears gold. Congratulations!");
                    if (Item* item = Item::CreateItem(GoldenApron, 1))
                    {
                        item->SaveToDB(t);
                        draft.AddItem(item);
                    }
                    draft.SendMailTo(t, MailReceiver(w.guid), MailSender(MAIL_CREATURE, OwnerOf(cafeId)), MAIL_CHECK_MASK_NONE);
                }
                t->Append("UPDATE `bleakhold_cafe_barista` SET `weekly_wins` = `weekly_wins` + 1, `crown_until` = {}, "
                    "`flags` = `flags` | {} WHERE `guid` = {}", now + CrownSec, gain, w.guid);
                if (Barista* b = LoadedBarista(w.guid))
                {
                    ++b->weeklyWins;
                    b->crownUntil = now + CrownSec;
                    b->flags |= gain;
                    if (Player* p = ObjectAccessor::FindPlayerByLowGUID(w.guid))
                    {
                        GrantLevelRewards(p, *b, false);   // the Legend title at the third win
                        Ui::Toast(p, ToastKind::Info, "Best Barista of the week", cafe + " \xC2\xB7 " + Thousands(w.points) +
                            " points", "cafe");
                    }
                }
            }
            t->Append("INSERT INTO `bleakhold_cafe_payout` (`week_id`, `cafe_id`, `paid_at`) VALUES ({}, {}, {})", weekId,
                cafeId, now);
            CharacterDatabase.CommitTransaction(t);
            LOG_INFO("module", "[Bleakhold] Cafe money: week {} at {} paid to {} baristas", weekId, cafe,
                std::min<std::size_t>(ranked.size(), _cfg.weeklyRewardCopper.size()));
            if (ranked.empty())
                continue;
            std::string line = "Best Barista of the week at " + cafe + ": " + ranked[0].name + " (" +
                Thousands(ranked[0].points) + " points)";
            if (ranked.size() >= 3)
                line += ", then " + ranked[1].name + " and " + ranked[2].name;
            else if (ranked.size() == 2)
                line += ", then " + ranked[1].name;
            topLines[cafeId - 1] = line + ".";
        }
        if (dry)
            return;
        std::string const served = " The Lion's Roast served " + Thousands(totals[0]) + " drinks, The Grinding Tusk " +
            Thousands(totals[1]) + ".";
        for (std::string const& l : topLines)
            if (!l.empty())
                AnnounceCafe(l + served);
        if (say)
            (*say)("Week " + std::to_string(weekId) + " paid.");
    }

    // =============================================================================================================
    // Bot hints (section 3.15): a row for a GM to read, never a punishment
    // =============================================================================================================
    void Cafe::FlagShift(Shift const& s, Barista const& b)
    {
        if (!R::BotFlag(b.day.drinks, b.day.perfects, s.releaseOffsets, _cfg.botMinDrinks, _cfg.botPerfectPermille,
            _cfg.botSdMs))
            return;
        uint32_t const permille = R::PerfectPermille(b.day.perfects, b.day.drinks);
        uint32_t const sd = R::StdDevMs(s.releaseOffsets);
        CharacterDatabase.Execute("INSERT INTO `bleakhold_cafe_flag` (`guid`, `at`, `drinks`, `perfect_permille`, "
            "`release_sd_ms`) VALUES ({}, {}, {}, {}, {})", b.low, NowSec(), b.day.drinks, permille, std::min<uint32_t>(sd, 65535));
        LOG_WARN("module", "[Bleakhold] Cafe: {} looks scripted ({} drinks today, {} permille Perfect, releases within {} ms); "
            "see .cafe flags", s.name, b.day.drinks, permille, sd);
    }
}
