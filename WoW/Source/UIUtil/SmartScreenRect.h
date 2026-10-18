#ifndef WOW_SOURCE_UIUTIL_SMARTSCREENRECT_H
#define WOW_SOURCE_UIUTIL_SMARTSCREENRECT_H

#include <cstdint>

enum SCREENRECTGRIDS : uint32_t {
    SRECTGRID_NAMEPLATES = 0,
    SRECTGRID_WORLDTEXT = 1,
    SRECTGRID_UNKNOWN_2 = 2,

    // NUM_SRECTGRIDS = 2, // Historical count; not current storage capacity.
};

class C3Vector;
class CRect;
class CSimpleFrame;

void SmartScreenRectClearAllGrids();
void SmartScreenRectShutdown();
void SmartScreenRectClearGrid(SCREENRECTGRIDS grid);
void SmartScreenRectPlace(SCREENRECTGRIDS grid, CRect& rect);
void SmartScreenRectPositionFrame(SCREENRECTGRIDS grid, CSimpleFrame* frame, CSimpleFrame* parent, const C3Vector& position, int32_t center);

#endif
