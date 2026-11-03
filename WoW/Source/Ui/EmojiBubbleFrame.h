#ifndef WOW_SOURCE_UI_EMOJIBUBBLEFRAME_H
#define WOW_SOURCE_UI_EMOJIBUBBLEFRAME_H

#include <cstdint>
#include "Engine/Source/Base/CDataAllocator.h"
#include "Engine/Source/Frame/CSimpleFrame.h"
#include "Engine/Source/Storm/H/stpl.h"
#include "Engine/Source/Tempest/C3Vector.h"
#include "WoW/Source/Object/WGUID.h"

class CGUnit_C;
class CGWorldFrame;
class CSimpleTexture;
struct CVar;

// BLEAKHOLD(emoji): an emoji that pops up over a unit's head for a few seconds (SMSG_PLAY_SPELL_VISUAL kits
// BLEAKHOLD_EMOJI_KIT_BASE + N, WoW/Common/BleakholdEmoji.h). Drawn like the chat bubbles: a pooled frame under the
// world frame, placed over the head each frame from the world frame's layer update and render. A bubble keeps only
// the unit's GUID and looks the unit up again every frame; one unit has at most one bubble.
class CGEmojiBubbleFrame : public TSLinkedNode<CGEmojiBubbleFrame>, public CSimpleFrame {
    public:
    static CDataAllocator s_emojiBubbleHeap;

    // ~CSimpleFrame deletes its children with a plain delete, which must give the memory back to the heap.
    static void operator delete(void* ptr);
    static void ClearAll();
    static bool EmojiBubblesCallback(CVar* var, const char* oldValue, const char* value, void* arg);
    static void InitializeGame();
    static void OnWorldLayerUpdate();
    static void OnWorldRender(CGWorldFrame* worldFrame);
    static void Remove(CGEmojiBubbleFrame* bubble);
    // From the packet handler: shows emoji `emoji` over `unit`, or does nothing (feature off, too far, no art,
    // `unit` on the ignore list).
    static void ShowEmoji(const WOWGUID& unit, uint32_t emoji);
    static void ShutdownGame();

    CSimpleTexture* m_texture;
    WOWGUID m_unit;
    C3Vector m_worldPosition;
    uint32_t m_emoji;
    uint32_t m_showTime;
    uint32_t m_age;
    float m_screenX;      // last anchor; -1 = not anchored yet
    float m_screenY;
    float m_screenDepth;
    float m_drawnSize;    // last SetWidth/SetHeight; -1 = none
    uint8_t m_positionValid;
    uint8_t m_inRange;

    ~CGEmojiBubbleFrame() override;

    CGEmojiBubbleFrame(CSimpleFrame* parent);
    // False when the art cannot be loaded (the texture is then cleared).
    bool Initialize(const WOWGUID& unit, uint32_t emoji);
    void Render(CGWorldFrame* worldFrame);
    // False when the bubble is over or its unit can no longer carry it.
    bool Update(CGUnit_C* player, CGUnit_C* unit, uint32_t now);
};

#endif
