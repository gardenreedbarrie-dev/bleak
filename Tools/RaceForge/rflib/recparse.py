"""Read DBC layouts from the client's own record classes (WoW/Source/DB/Rec/<Name>Rec.h and .cpp).

Each Rec header declares s_numColumns, s_rowSize and s_generatedID, and each Read() reads the columns in file
order with SFileReadFile. WowClientDB_Common::Load aborts when a file's column count or row size differs from
s_numColumns / s_rowSize, so these classes are the authority for every table RaceForge writes.

The Read() functions use six statement forms:

    SFileReadFile(file, &this->m_x, sizeof(this->m_x), ...)          one column of m_x's type
    SFileReadFile(file, &this->m_x[3], sizeof(this->m_x[3]), ...)    one array element
    SFileReadFile(file, this->m_x, sizeof(this->m_x), ...)           a whole array, one column per element
    SFileReadFile(file, &xOffset, sizeof(xOffset), ...)              a string offset
    SFileReadFile(file, &xOffset[3], sizeof(xOffset[3]), ...)        one string of an array, or of a localized string
    SFileReadFile(file, &xFlags, sizeof(xFlags), ...)                the flags column ending a localized string

A localized string is 16 offsets (one per locale, Read keeps the one for s_locale) followed by its flags column.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

TYPE_SIZES = {"int32_t": 4, "float": 4, "int8_t": 1, "const char*": 4}
LOCALE_COUNT = 16


@dataclass(frozen=True)
class Column:
    """One physical DBC column."""

    name: str  # "raceID", "itemID[3]", "name[0]" .. "name[15]", "name_flags"
    kind: str  # "int", "float", "byte", "str", "locstr", "locflags"
    size: int  # bytes in the row

    @property
    def is_string(self) -> bool:
        return self.kind in ("str", "locstr")


@dataclass
class TableSchema:
    name: str  # "ChrRaces"
    filename: str  # "DBFilesClient\\ChrRaces.dbc"
    num_columns: int  # s_numColumns
    row_size: int  # s_rowSize
    generated_id: bool  # s_generatedID: rows carry no id column, the row index is the id
    columns: list[Column] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        self._index = {c.name: i for i, c in enumerate(self.columns)}

    def index(self, name: str) -> int:
        try:
            return self._index[name]
        except KeyError:
            raise KeyError(f"{self.name} has no column {name!r}") from None

    def has(self, name: str) -> bool:
        return name in self._index

    def field_columns(self, field_name: str) -> list[int]:
        """Indices of every column of a field: the field itself, or all its array elements in order."""
        if field_name in self._index:
            return [self._index[field_name]]

        out = []
        i = 0

        while f"{field_name}[{i}]" in self._index:
            out.append(self._index[f"{field_name}[{i}]"])
            i += 1

        if not out:
            raise KeyError(f"{self.name} has no field {field_name!r}")

        return out

    def localized_fields(self) -> list[str]:
        return [c.name[:-len("_flags")] for c in self.columns if c.kind == "locflags"]

    def computed_row_size(self) -> int:
        return sum(c.size for c in self.columns)

    def struct_format(self) -> str:
        return "<" + "".join("B" if c.size == 1 else "I" for c in self.columns)


class RecParseError(Exception):
    pass


_HEADER_CONST = re.compile(r"static const (?:int32_t|bool) (s_numColumns|s_rowSize|s_generatedID) = (\w+);")
_MEMBER = re.compile(r"/\*\s*[0-9A-Fa-f]+\s*\*/\s*(const char\*|int32_t|float|int8_t)\s+m_(\w+)\s*(?:\[(\d+)\])?\s*;")
_FILENAME = re.compile(r'GetFilename\(\)\s*\{\s*return\s+"([^"]+)"')
_READ_CALL = re.compile(r"SFileReadFile\(file,\s*(&?)([\w>\-.]+(?:\[\d+\])?),\s*sizeof\(([^)]*)\)")
_LOCAL_DECL = re.compile(r"^\s*uint32_t (\w+?)(Offset|Flags)(?:\[(\d+)\])?;", re.MULTILINE)


def parse_rec(header_text: str, source_text: str, name: str) -> TableSchema:
    """Build the schema of one table from its Rec header and source."""
    consts = dict(_HEADER_CONST.findall(header_text))

    for key in ("s_numColumns", "s_rowSize", "s_generatedID"):
        if key not in consts:
            raise RecParseError(f"{name}Rec.h: {key} not found")

    members = {}

    for type_name, member, count in _MEMBER.findall(header_text):
        members[member] = (type_name, int(count) if count else 1)

    match = _FILENAME.search(source_text)

    if not match:
        raise RecParseError(f"{name}Rec.cpp: GetFilename not found")

    filename = match.group(1).replace("\\\\", "\\")

    read_start = source_text.find("::Read(SFileImpl* file")

    if read_start < 0:
        raise RecParseError(f"{name}Rec.cpp: Read() not found")

    body = source_text[read_start:]
    body = body[:body.find("if (!")] if "if (!" in body else body

    locals_ = {}

    for base, suffix, count in _LOCAL_DECL.findall(body):
        locals_[base + suffix] = int(count) if count else 1

    columns: list[Column] = []
    calls = _READ_CALL.findall(body)

    if not calls:
        raise RecParseError(f"{name}Rec.cpp: no SFileReadFile calls in Read()")

    for i, (address_of, target, size_expr) in enumerate(calls):
        # Members of the record.
        member_match = re.fullmatch(r"this->m_(\w+)(?:\[(\d+)\])?", target)

        if member_match:
            member, element = member_match.group(1), member_match.group(2)

            if member not in members:
                raise RecParseError(f"{name}: m_{member} is read but not declared in the header")

            type_name, count = members[member]

            if type_name == "const char*":
                raise RecParseError(f"{name}: string member m_{member} read directly")

            kind = {"int32_t": "int", "float": "float", "int8_t": "byte"}[type_name]
            size = TYPE_SIZES[type_name]

            if address_of and element is None:
                if count != 1:
                    raise RecParseError(f"{name}: &this->m_{member} of an array")
                columns.append(Column(member, kind, size))
            elif address_of:
                columns.append(Column(f"{member}[{element}]", kind, size))
            else:
                # Whole array in one read: sizeof(this->m_x) covers every element.
                if size_expr.strip() != f"this->m_{member}":
                    raise RecParseError(f"{name}: unexpected sizeof({size_expr}) for m_{member}")
                columns.extend(Column(f"{member}[{e}]", kind, size) for e in range(count))
            continue

        # Locals: string offsets and localized-string flags.
        local_match = re.fullmatch(r"(\w+?)(Offset|Flags)(?:\[(\d+)\])?", target)

        if not local_match or not address_of:
            raise RecParseError(f"{name}: unrecognised read target {target!r}")

        base, suffix, element = local_match.groups()

        if base + suffix not in locals_:
            raise RecParseError(f"{name}: local {base}{suffix} is read but not declared")

        if suffix == "Flags":
            columns.append(Column(f"{base}_flags", "locflags", 4))
            continue

        count = locals_[base + "Offset"]

        if element is None:
            columns.append(Column(base, "str", 4))
        else:
            # An offset array followed by a flags read is a localized string.
            localized = count == LOCALE_COUNT and f"{base}Flags" in locals_
            columns.append(Column(f"{base}[{element}]", "locstr" if localized else "str", 4))

    schema = TableSchema(name, filename, int(consts["s_numColumns"]), int(consts["s_rowSize"]), consts["s_generatedID"] == "true", columns)
    check_schema(schema)
    return schema


def check_schema(schema: TableSchema):
    """The parsed columns must add up to the header constants, and localized strings must be complete."""
    if len(schema.columns) != schema.num_columns:
        raise RecParseError(f"{schema.name}: {len(schema.columns)} columns parsed, s_numColumns is {schema.num_columns}")

    if schema.computed_row_size() != schema.row_size:
        raise RecParseError(f"{schema.name}: parsed row size {schema.computed_row_size()}, s_rowSize is {schema.row_size}")

    names = [c.name for c in schema.columns]

    if len(set(names)) != len(names):
        raise RecParseError(f"{schema.name}: duplicate column names")

    for field_name in schema.localized_fields():
        indices = [schema.index(f"{field_name}[{i}]") for i in range(LOCALE_COUNT)]
        flags = schema.index(f"{field_name}_flags")

        if indices != list(range(indices[0], indices[0] + LOCALE_COUNT)) or flags != indices[-1] + 1:
            raise RecParseError(f"{schema.name}: localized string {field_name} is not 16 offsets followed by flags")


def default_rec_dir() -> str | None:
    """WoW/Source/DB/Rec of the checkout RaceForge runs from, if it is there."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    path = os.path.join(root, "WoW", "Source", "DB", "Rec")
    return path if os.path.isdir(path) else None


def load_rec(rec_dir: str, name: str) -> TableSchema:
    with open(os.path.join(rec_dir, f"{name}Rec.h"), encoding="utf-8") as f:
        header = f.read()

    with open(os.path.join(rec_dir, f"{name}Rec.cpp"), encoding="utf-8") as f:
        source = f.read()

    return parse_rec(header, source, name)


def load_all(rec_dir: str) -> dict[str, TableSchema]:
    """Every table of the Rec folder."""
    out = {}

    for filename in sorted(os.listdir(rec_dir)):
        if filename.endswith("Rec.h"):
            name = filename[:-len("Rec.h")]

            if os.path.isfile(os.path.join(rec_dir, f"{name}Rec.cpp")):
                out[name] = load_rec(rec_dir, name)

    return out


# Tables RaceForge reads or writes. rflib/schemas.py is generated from them (raceforge.py schemas --write) so the
# tool also works without the decompilation next to it; tests/test_schemas.py checks it against the Rec files.
USED_TABLES = (
    "BarberShopStyle",
    "CharBaseInfo",
    "CharHairGeosets",
    "CharSections",
    "CharStartOutfit",
    "CharacterFacialHairStyles",
    "ChrClasses",
    "ChrRaces",
    "CreatureDisplayInfo",
    "CreatureModelData",
    "DanceMoves",
    "EmotesTextSound",
    "Faction",
    "FactionGroup",
    "FactionTemplate",
    "HelmetGeosetVisData",
    "ItemDisplayInfo",
    "NameGen",
    "SkillLineAbility",
    "SkillRaceClassInfo",
    "SoundFilter",
    "TalentTab",
    "VocalUISounds",
)


def emit_schemas_module(rec_dir: str) -> str:
    """Source text of rflib/schemas.py for USED_TABLES."""
    lines = [
        '"""DBC layouts of the tables RaceForge uses, generated from WoW/Source/DB/Rec by `raceforge.py schemas --write`.',
        "",
        "Do not edit by hand: tests/test_schemas.py regenerates this from the client's Rec classes and compares.",
        "Each entry: file name, s_numColumns, s_rowSize, s_generatedID, columns as (name, kind, size).",
        '"""',
        "",
        "SCHEMAS = {",
    ]

    for name in USED_TABLES:
        schema = load_rec(rec_dir, name)
        lines.append(f"    {name!r}: ({schema.filename!r}, {schema.num_columns}, {schema.row_size}, {schema.generated_id}, (")

        for column in schema.columns:
            lines.append(f"        ({column.name!r}, {column.kind!r}, {column.size}),")

        lines.append("    )),")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)
