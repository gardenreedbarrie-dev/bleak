// BLEAKHOLD(emoji): emoji bubbles over units' heads. The server sends SMSG_PLAY_SPELL_VISUAL with kit
// BLEAKHOLD_EMOJI_KIT_BASE + N to everyone near the unit (docs/BleakholdProtocol.md, section 13); Spell_C.cpp hands
// those kits to ShowEmoji instead of the SpellVisualKit table.
//
// A bubble is a pooled frame under the world frame, like CGChatBubbleFrame: OnWorldLayerUpdate (from
// CGWorldFrame::OnLayerUpdate) ages it and finds the head point, OnWorldRender (from CGWorldFrame::OnWorldRender,
// after the chat bubbles) projects it and anchors it above the unit's name, nameplate or chat bubble. Units are looked
// up by GUID every frame, so a unit that goes away cannot leave a dangling pointer. The frames die with the world
// frame (logout, /reload), which unlinks them from the lists below.

#include "WoW/Source/Ui/EmojiBubbleFrame.h"
#include <cmath>
#include <cstring>
#include <new>
#include <typeinfo>
#include "Engine/Source/Base/Coordinate.h"
#include "Engine/Source/ConsoleBase/ConsoleVar.h"
#include "Engine/Source/ConsoleBase/Types.h"
#include "Engine/Source/Frame/CLayoutFrame.h"
#include "Engine/Source/Frame/CSimpleTexture.h"
#include "Engine/Source/Frame/CSimpleTop.h"
#include "Engine/Source/Frame/Types.h"
#include "Engine/Source/Gx/Types.h"
#include "Engine/Source/Model2/M2Model.h"
#include "Engine/Source/Os/TimeManager.h"
#include "Engine/Source/Storm/H/storm.h"
#include "WoW/Common/BleakholdEmoji.h"
#include "WoW/Source/Game/GameClient/PlayerName.h"
#include "WoW/Source/Object/ObjectClient/Object_C.h"
#include "WoW/Source/Object/ObjectClient/Unit_C.h"
#include "WoW/Source/Object/ObjectClient/VehiclePassenger_C.h"
#include "WoW/Source/ObjectMgrClient/ObjectMgrClient.h"
#include "WoW/Source/Ui/ChatBubbleFrame.h"
#include "WoW/Source/Ui/GameUI.h"
#include "WoW/Source/Ui/NamePlateFrame.h"
#include "WoW/Source/Ui/WorldFrame.h"
#include "WoW/Source/WowSvcs/WowSvcsClient/FriendList.h"

// Defined first so it is destroyed last: the lists unlink their nodes, which live in its blocks, when they go.
CDataAllocator CGEmojiBubbleFrame::s_emojiBubbleHeap(sizeof(CGEmojiBubbleFrame), 10);

// Pooled bubbles, and the ones showing (oldest first, newest last and drawn on top).
static TSList<CGEmojiBubbleFrame> s_freeEmojiBubbles, s_emojiBubbles;

static CVar* s_emojiBubblesCVar;
static CVar* s_emojiBubbleScaleCVar;

// The showing list changed order: OnWorldLayerUpdate gives the bubbles new frame levels.
static bool s_levelsDirty;

// One bit per emoji whose art failed to load, so a missing file is not opened again for every packet.
static uint32_t s_missing[BLEAKHOLD_EMOJI_MAX / 32];

static const uint32_t MAX_ALIVE = 32;
// Sizes and gaps in reference pixels (pixels of a 768-pixel-tall screen).
static const float SIZE_PX = 48.0f;
static const float GAP_PX = 6.0f;           // between the head point and the bubble
static const float STACK_GAP_PX = 4.0f;     // between a chat bubble or nameplate and the bubble
static const float RISE_PX = 12.0f;         // how far it rises while it fades
static const float RANGE_SQ = 2500.0f;      // 50 yd squared, the chat bubbles' range
// Yards above the name point (times PlayerNameComputeScale), which clears three name lines.
static const float NAME_CLEARANCE = 0.7f;
// Above the nameplates (10 and 20) and the chat bubbles (2 and up), all at the world frame's strata.
static const int32_t FIRST_LEVEL = 64;

// One reference pixel in DDC. The world frame is not under UIParent, so the UI scale never applies.
static float ReferencePixel() {
    return NDCToDDCWidth(1.0f / (CoordinateGetAspectCompensation() * 1024.0f));
}

// emojiBubbleScale, clamped to 0.5..2 (a NaN or junk value reads as 0.5).
static float BubbleScale() {
    if (!s_emojiBubbleScaleCVar) {
        return 1.0f;
    }

    float scale = s_emojiBubbleScaleCVar->m_floatValue;

    if (!(scale >= 0.5f)) {
        return 0.5f;
    }

    if (scale > 2.0f) {
        return 2.0f;
    }

    return scale;
}

static C3Vector UnitPosition(CGUnit_C* unit) {
    return unit->IsInVehicle() ? unit->m_vehiclePassenger->ComputeInterpolatedUnitPosition() : unit->GetPosition();
}

static float DistanceSq(const C3Vector& a, const C3Vector& b) {
    C3Vector delta = a - b;
    return delta.x * delta.x + delta.y * delta.y + delta.z * delta.z;
}

static void ClearMissing() {
    memset(s_missing, 0, sizeof(s_missing));
}

void CGEmojiBubbleFrame::operator delete(void* ptr) {
    if (ptr) {
        CGEmojiBubbleFrame::s_emojiBubbleHeap.PutData(ptr, nullptr, 0);
    }
}

void CGEmojiBubbleFrame::InitializeGame() {
    // Flags 0: saved in Config.wtf and never deleted, so the pointers stay good. setCommand false: Lua's
    // GetCVar/SetCVar only find CVars registered that way, and the addon reads emojiBubbles to tell this client apart.
    s_emojiBubblesCVar = CVar::Register("emojiBubbles", "Show emoji bubbles over characters", 0, "1", CGEmojiBubbleFrame::EmojiBubblesCallback, CATEGORY_GAME, false, nullptr, false);
    s_emojiBubbleScaleCVar = CVar::Register("emojiBubbleScale", "Size of emoji bubbles (0.5 to 2)", 0, "1.0", nullptr, CATEGORY_GAME, false, nullptr, false);
    ClearMissing();
}

bool CGEmojiBubbleFrame::EmojiBubblesCallback(CVar* var, const char* oldValue, const char* value, void* arg) {
    if (value && SStrToInt(value) == 0) {
        CGEmojiBubbleFrame::ClearAll();
    }

    return true;
}

void CGEmojiBubbleFrame::ShutdownGame() {
    // The frames were deleted with the world frame, which unlinked them. Never Clear() the lists: their nodes come
    // from s_emojiBubbleHeap, not from SMemAlloc.
    ClearMissing();
    s_levelsDirty = false;
}

void CGEmojiBubbleFrame::ClearAll() {
    CGEmojiBubbleFrame* bubble;

    while ((bubble = s_emojiBubbles.Head()) != nullptr) {
        CGEmojiBubbleFrame::Remove(bubble);
    }

    ClearMissing();
}

void CGEmojiBubbleFrame::Remove(CGEmojiBubbleFrame* bubble) {
    bubble->Hide();
    bubble->m_unit = WOWGUID();
    s_freeEmojiBubbles.LinkToTail(bubble);
    s_levelsDirty = true;
}

void CGEmojiBubbleFrame::ShowEmoji(const WOWGUID& guid, uint32_t emoji) {
    if (!CGGameUI::s_inWorld || !CGWorldFrame::s_currentWorldFrame) {
        return;
    }

    if (!s_emojiBubblesCVar || !s_emojiBubblesCVar->m_intValue) {
        return;
    }

    if (emoji >= BLEAKHOLD_EMOJI_MAX || (s_missing[emoji / 32] & (1u << (emoji % 32)))) {
        return;
    }

    // Like chat from them (ChatFrame.cpp), nothing from a player on the ignore list. Creatures are never on it.
    if (FriendList::s_friendList && FriendList::s_friendList->IsIgnored(guid, true)) {
        return;
    }

    CGUnit_C* unit = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(guid, TYPEMASK_UNIT, __FILE__, __LINE__));

    if (!unit || !unit->m_worldObject || (unit->m_modelFlags & 0x10000)) {
        return;
    }

    CGUnit_C* player = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(ClntObjMgrGetActivePlayer(), TYPEMASK_PLAYER, __FILE__, __LINE__));

    if (!player || DistanceSq(player->GetPosition(), UnitPosition(unit)) >= RANGE_SQ) {
        return;
    }

    // The new bubble replaces the unit's own; otherwise the oldest goes once MAX_ALIVE show. Neither goes before a
    // free frame has loaded the art, so art missing from an older client package never takes a bubble away.
    CGEmojiBubbleFrame* old = nullptr;
    uint32_t count = 0;

    for (CGEmojiBubbleFrame* node = s_emojiBubbles.Head(); node; node = s_emojiBubbles.Next(node)) {
        if (node->m_unit == guid) {
            old = node;
            break;
        }

        count++;
    }

    // At most one frame more than MAX_ALIVE is ever made: the pool holds the one an evicted bubble gives back.
    CGEmojiBubbleFrame* bubble = s_freeEmojiBubbles.Head();

    if (!bubble) {
        void* data = CGEmojiBubbleFrame::s_emojiBubbleHeap.GetData(0, typeid(CGEmojiBubbleFrame).raw_name(), SLOG_OBJECT);
        bubble = data ? new (data) CGEmojiBubbleFrame(CGWorldFrame::s_currentWorldFrame) : nullptr;

        if (!bubble) {
            return;
        }
    }

    if (!bubble->Initialize(guid, emoji)) {
        // A failed texture allocation is not a missing file.
        if (bubble->m_texture) {
            s_missing[emoji / 32] |= 1u << (emoji % 32);
        }

        CGEmojiBubbleFrame::Remove(bubble);
        return;
    }

    s_emojiBubbles.LinkToTail(bubble);
    s_levelsDirty = true;

    if (old) {
        CGEmojiBubbleFrame::Remove(old);
    } else if (count >= MAX_ALIVE) {
        CGEmojiBubbleFrame::Remove(s_emojiBubbles.Head());
    }
}

void CGEmojiBubbleFrame::OnWorldLayerUpdate() {
    if (!s_emojiBubbles.Head()) {
        return;
    }

    CGUnit_C* player = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(ClntObjMgrGetActivePlayer(), TYPEMASK_PLAYER, __FILE__, __LINE__));
    uint32_t now = OsGetAsyncTimeMs();
    CGEmojiBubbleFrame* next;

    for (CGEmojiBubbleFrame* bubble = s_emojiBubbles.Head(); bubble; bubble = next) {
        next = s_emojiBubbles.Next(bubble);
        CGUnit_C* unit = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(bubble->m_unit, TYPEMASK_UNIT, __FILE__, __LINE__));

        if (!unit || !bubble->Update(player, unit, now)) {
            CGEmojiBubbleFrame::Remove(bubble);
        }
    }

    if (!s_levelsDirty) {
        return;
    }

    int32_t level = FIRST_LEVEL;

    for (CGEmojiBubbleFrame* bubble = s_emojiBubbles.Head(); bubble; bubble = s_emojiBubbles.Next(bubble)) {
        bubble->SetFrameLevel(level++, 1);
    }

    s_levelsDirty = false;
}

void CGEmojiBubbleFrame::OnWorldRender(CGWorldFrame* worldFrame) {
    if (!s_emojiBubbles.Head()) {
        return;
    }

    for (CGEmojiBubbleFrame* bubble = s_emojiBubbles.Head(); bubble; bubble = s_emojiBubbles.Next(bubble)) {
        bubble->Render(worldFrame);
    }

    CLayoutFrame::ResizePending();
}

CGEmojiBubbleFrame::CGEmojiBubbleFrame(CSimpleFrame* parent) : CSimpleFrame(parent) {
    this->m_texture = nullptr;
    this->m_unit = WOWGUID();
    this->m_worldPosition = C3Vector(0.0f, 0.0f, 0.0f);
    this->m_emoji = 0;
    this->m_showTime = 0;
    this->m_age = 0;
    this->m_screenX = -1.0f;
    this->m_screenY = -1.0f;
    this->m_screenDepth = -1.0f;
    this->m_drawnSize = -1.0f;
    this->m_positionValid = 0;
    this->m_inRange = 0;
    this->SetFrameFlag(0x40000, 1);

    // The frame owns its regions (~CSimpleFrame deletes them). No mouse events are enabled, so it never takes a click.
    void* data = CSimpleTexture::s_allocator.GetData(0, typeid(CSimpleTexture).raw_name(), SLOG_OBJECT);
    this->m_texture = data ? new (data) CSimpleTexture(this, 2, 1) : nullptr;

    if (this->m_texture) {
        this->m_texture->SetBlendMode(GxBlend_Alpha);
        this->m_texture->SetAllPoints(this, 1);
    }

    this->SetFrameAlpha(0);
}

bool CGEmojiBubbleFrame::Initialize(const WOWGUID& unit, uint32_t emoji) {
    if (!this->m_texture) {
        return false;
    }

    // Mipmapped: the 256 px art is drawn at about 48 px and moves with the head, so mip 0 alone would shimmer.
    char path[64];
    SStrPrintf(path, sizeof(path), BLEAKHOLD_EMOJI_TEXTURE, emoji);

    if (!this->m_texture->SetTexture(path, 0, 0, GxTex_LinearMipNearest, ImageMode_Normal)) {
        // A failed SetTexture keeps the old texture, which would show the emoji this frame had before.
        this->m_texture->SetTexture(nullptr, 0, 0, GxTex_LinearMipNearest, ImageMode_Normal);
        return false;
    }

    this->m_unit = unit;
    this->m_emoji = emoji;
    this->m_showTime = OsGetAsyncTimeMs();
    this->m_age = 0;
    this->m_positionValid = 0;
    this->m_inRange = 0;
    this->m_screenX = -1.0f;
    this->m_screenY = -1.0f;
    this->m_screenDepth = -1.0f;
    this->m_drawnSize = -1.0f;
    this->SetFrameAlpha(0);
    this->Show();
    return true;
}

bool CGEmojiBubbleFrame::Update(CGUnit_C* player, CGUnit_C* unit, uint32_t now) {
    this->m_age = now - this->m_showTime;

    // 0x10000: a disabled object (out of range, fading out), which stays findable until it is cleaned up.
    if (this->m_age >= BLEAKHOLD_EMOJI_LIFETIME_MS || !player || (unit->m_modelFlags & 0x10000)) {
        return false;
    }

    CMapEntity* entity = unit->m_worldObject;
    CM2Model* model = unit->m_worldModel;

    if (!entity || !model) {
        return false;
    }

    this->m_positionValid = 0;

    if (!model->IsLoaded(0, 0) || !(model->m_fFlags & 0x8000)) {
        return true;
    }

    C3Vector position = UnitPosition(unit);
    this->m_inRange = World::QueryObjectVisible(entity) && DistanceSq(player->GetPosition(), position) < RANGE_SQ;

    // The name point (attachment 18, or 29 when mounted), as the chat bubbles use it.
    C3Vector attachment = unit->IsMounted() ? unit->GetAttachmentPosition(29, nullptr) : unit->GetAttachmentPosition(18, nullptr);
    float height = attachment.z - unit->GetModelPosition().z;
    this->m_worldPosition = C3Vector(position.x, position.y, position.z + height + NAME_CLEARANCE * PlayerNameComputeScale(unit));
    this->m_positionValid = 1;
    return true;
}

void CGEmojiBubbleFrame::Render(CGWorldFrame* worldFrame) {
    uint8_t alpha = 0;
    CGUnit_C* unit = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(this->m_unit, TYPEMASK_UNIT, __FILE__, __LINE__));
    float scale = 1.0f;
    float fade = 0.0f;
    float rise = 0.0f;
    C3Vector screen(0.0f, 0.0f, 0.0f);
    uint32_t edges = 0;

    // GetScreenCoordinates is false behind the camera (without writing `screen`) and when the point is not fully
    // inside the world frame; the bubble is then transparent rather than stuck at its last place.
    if (unit && this->m_texture && this->m_positionValid && this->m_inRange && CGGameUI::m_visible
        && BleakholdEmojiPose(this->m_age, &scale, &fade, &rise)
        && worldFrame->GetScreenCoordinates(this->m_worldPosition, &screen, &edges)) {
        float px = ReferencePixel();
        float bubbleScale = BubbleScale();
        float size = SIZE_PX * px * bubbleScale;
        float bottom = screen.y + GAP_PX * px;

        // Sit above the unit's chat bubble or nameplate (their rects are current: both are placed before this).
        CGChatBubbleFrame* chatBubble = unit->m_chatBubble;

        if (chatBubble && chatBubble->m_positionValid && chatBubble->m_isVisible && chatBubble->GetEffectiveAlpha()) {
            float top = chatBubble->m_rect.maxY - worldFrame->m_rect.minY + STACK_GAP_PX * px;

            if (top > bottom) {
                bottom = top;
            }
        }

        CGNamePlateFrame* namePlate = unit->m_namePlateFrame;

        if (namePlate && namePlate->m_isVisible) {
            float top = namePlate->m_rect.maxY - worldFrame->m_rect.minY + STACK_GAP_PX * px;

            if (top > bottom) {
                bottom = top;
            }
        }

        float x = CSimpleTop::RoundToPixelWidth(screen.x);
        float y = CSimpleTop::RoundToPixelHeight(bottom + size * 0.5f + rise * RISE_PX * px * bubbleScale);
        float z = screen.z - worldFrame->m_layoutDepth;
        bool moveX = fabs(x - this->m_screenX) >= px;
        bool moveY = fabs(y - this->m_screenY) >= px;

        if (moveX || moveY) {
            if (moveX) {
                this->m_screenX = x;
            }

            if (moveY) {
                this->m_screenY = y;
            }

            this->SetPoint(FRAMEPOINT_CENTER, worldFrame, FRAMEPOINT_BOTTOMLEFT, this->m_screenX, this->m_screenY, 1);
        }

        // Sized rather than SetFrameScale'd, which would scale the anchor offsets too.
        float drawn = size * (scale > 0.02f ? scale : 0.02f);

        if (fabs(drawn - this->m_drawnSize) >= 0.5f * px) {
            this->m_drawnSize = drawn;
            this->SetWidth(drawn);
            this->SetHeight(drawn);
        }

        if (fabs(z - this->m_screenDepth) >= px) {
            this->m_screenDepth = z;
            this->SetFrameDepth(z, false);
        }

        alpha = static_cast<uint8_t>(fade * 255.0f + 0.5f);
    }

    if (this->m_alpha != alpha) {
        this->SetFrameAlpha(alpha);
    }
}

CGEmojiBubbleFrame::~CGEmojiBubbleFrame() {
}
