"""MapForge data side: the DBC rows of a new map, the patch archives that carry them, and the server SQL.

The DBC reader and writer is RaceForge's (`Tools/RaceForge/rflib/dbc.py`): rows are kept as raw column values, the
string block of each file is kept byte for byte and new strings are appended, so every row that was in a file is
written back unchanged. The layouts come from the client's own record classes (`WoW/Source/DB/Rec`), the archives
are written and read with `Tools/MpqPack`, and textures with `Tools/BlpConvert`.

The sibling tools are added to the end of sys.path, so a module of MapForge (its `tests` package, say) always wins
over one of the same name in those folders.
"""

from __future__ import annotations

import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIBLINGS = tuple(os.path.join(TOOLS_DIR, name) for name in ("RaceForge", "MpqPack", "BlpConvert"))

for _path in SIBLINGS:
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.append(_path)
