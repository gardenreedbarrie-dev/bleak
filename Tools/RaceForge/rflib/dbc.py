"""WDBC files as the 3.3.5a client reads them (WowClientDB_Common::Load).

Layout: 'WDBC', record count, column count, row size, string block size, the rows, then the string block. Every
column is 4 bytes except int8_t ones (CharBaseInfo, the race/class/sex/outfit bytes of CharStartOutfit). Strings
are offsets into the string block; offset 0 is the empty string.

Rows are kept as lists of raw column values (unsigned 32- or 8-bit; floats keep their bit pattern), so a value
RaceForge does not touch is written back unchanged. The original string block is kept byte for byte and new strings
are appended to it: every offset already in the file stays valid, including any the server reads as a string where
the client reads a number. A table that is not changed is written back identical to the file it came from.
"""

from __future__ import annotations

import os
import struct

from .recparse import TableSchema

MAGIC = b"WDBC"
HEADER = struct.Struct("<4sIIII")


class DbcError(Exception):
    pass


def to_signed(value: int) -> int:
    return value - 0x100000000 if value & 0x80000000 else value


def to_unsigned(value: int) -> int:
    return value & 0xFFFFFFFF


class DbcTable:
    def __init__(self, schema: TableSchema, rows: list[list[int]], strings: bytes, source: str = "", original: bytes | None = None):
        self.schema = schema
        self.rows = rows
        self.strings = bytearray(strings)
        self.source = source
        self.original = original
        self.warnings: list[str] = []
        self._string_offsets: dict[bytes, int] | None = None
        self._original_string_size = len(strings)

    # --- reading and writing ---

    @classmethod
    def from_bytes(cls, data: bytes, schema: TableSchema, source: str = "") -> "DbcTable":
        where = source or schema.filename

        if len(data) < HEADER.size:
            raise DbcError(f"{where}: too short for a DBC header")

        magic, records, fields, record_size, string_size = HEADER.unpack_from(data)

        if magic != MAGIC:
            raise DbcError(f"{where}: not a WDBC file (magic {magic!r})")

        # The client aborts on either mismatch ("has wrong number of columns" / "has wrong row size").
        if fields != schema.num_columns:
            raise DbcError(f"{where}: {fields} columns, the client expects {schema.num_columns} (is this a 3.3.5a 12340 DBC?)")

        if record_size != schema.row_size:
            raise DbcError(f"{where}: row size {record_size}, the client expects {schema.row_size} (is this a 3.3.5a 12340 DBC?)")

        expected = HEADER.size + records * record_size + string_size

        if len(data) < expected:
            raise DbcError(f"{where}: file is cut off ({len(data)} bytes, header announces {expected})")

        fmt = struct.Struct(schema.struct_format())
        rows = [list(fmt.unpack_from(data, HEADER.size + i * record_size)) for i in range(records)]
        strings = data[HEADER.size + records * record_size:expected]
        table = cls(schema, rows, strings, source, data)

        if len(data) > expected:
            table.warnings.append(f"{where}: {len(data) - expected} bytes after the string block are ignored")

        string_columns = [i for i, c in enumerate(schema.columns) if c.is_string]

        for r, row in enumerate(rows):
            for i in string_columns:
                if row[i] and row[i] >= len(strings):
                    table.warnings.append(f"{where}: row {r} column {schema.columns[i].name} points past the string block")
                    break

        return table

    @classmethod
    def read(cls, path: str, schema: TableSchema) -> "DbcTable":
        with open(path, "rb") as f:
            return cls.from_bytes(f.read(), schema, path)

    @classmethod
    def empty(cls, schema: TableSchema) -> "DbcTable":
        return cls(schema, [], b"\0")

    def to_bytes(self) -> bytes:
        fmt = struct.Struct(self.schema.struct_format())
        strings = bytes(self.strings)

        # A table with string columns needs at least the empty string at offset 0.
        if not strings and any(c.is_string for c in self.schema.columns) and self.rows:
            strings = b"\0"

        out = bytearray(HEADER.pack(MAGIC, len(self.rows), self.schema.num_columns, self.schema.row_size, len(strings)))

        for row in self.rows:
            if len(row) != len(self.schema.columns):
                raise DbcError(f"{self.schema.name}: a row has {len(row)} values, the table has {len(self.schema.columns)} columns")

            out += fmt.pack(*row)

        out += strings
        return bytes(out)

    def write(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        with open(path, "wb") as f:
            f.write(self.to_bytes())

    def is_modified(self) -> bool:
        return self.original is None or self.to_bytes() != self.original

    # --- columns ---

    def col(self, name: str) -> int:
        return self.schema.index(name)

    def get(self, row: list[int], name: str) -> int:
        return row[self.schema.index(name)]

    def get_signed(self, row: list[int], name: str) -> int:
        return to_signed(row[self.schema.index(name)])

    def set(self, row: list[int], name: str, value: int):
        column = self.schema.columns[self.schema.index(name)]
        limit = 0xFF if column.size == 1 else 0xFFFFFFFF

        if value < 0:
            value &= limit

        if value > limit:
            raise DbcError(f"{self.schema.name}.{name}: value {value} does not fit {column.size} bytes")

        row[self.schema.index(name)] = value

    def float_value(self, row: list[int], name: str) -> float:
        return struct.unpack("<f", struct.pack("<I", row[self.schema.index(name)]))[0]

    # --- strings ---

    def string_at(self, offset: int) -> str:
        if offset >= len(self.strings):
            return ""

        end = self.strings.find(b"\0", offset)

        if end < 0:
            end = len(self.strings)

        return bytes(self.strings[offset:end]).decode("utf-8", "surrogateescape")

    def get_str(self, row: list[int], name: str) -> str:
        return self.string_at(row[self.schema.index(name)])

    def add_string(self, text: str) -> int:
        """Offset of text in the string block, appending it if it is not there yet."""
        if text == "":
            return 0

        data = text.encode("utf-8", "surrogateescape")

        if b"\0" in data:
            raise DbcError(f"{self.schema.name}: strings cannot contain NUL")

        if self._string_offsets is None:
            self._string_offsets = {}
            start = 0

            while start < len(self.strings):
                end = self.strings.find(b"\0", start)

                if end < 0:
                    break

                self._string_offsets.setdefault(bytes(self.strings[start:end]), start)
                start = end + 1

        offset = self._string_offsets.get(data)

        if offset is not None:
            return offset

        if not self.strings:
            self.strings += b"\0"

        offset = len(self.strings)
        self.strings += data + b"\0"
        self._string_offsets[data] = offset
        return offset

    def set_str(self, row: list[int], name: str, text: str):
        row[self.schema.index(name)] = self.add_string(text)

    def get_loc(self, row: list[int], field_name: str) -> list[str]:
        return [self.get_str(row, f"{field_name}[{i}]") for i in range(16)]

    def set_loc(self, row: list[int], field_name: str, texts: list[str]):
        if len(texts) != 16:
            raise DbcError("a localized string has 16 slots")

        for i, text in enumerate(texts):
            self.set_str(row, f"{field_name}[{i}]", text)

    # --- ids ---

    def max_id(self) -> int:
        if self.schema.generated_id:
            return len(self.rows) - 1

        return max((to_signed(row[0]) for row in self.rows), default=0)

    def ids(self) -> set[int]:
        if self.schema.generated_id:
            return set(range(len(self.rows)))

        return {to_signed(row[0]) for row in self.rows}

    def by_id(self) -> dict[int, list[int]]:
        if self.schema.generated_id:
            return dict(enumerate(self.rows))

        return {to_signed(row[0]): row for row in self.rows}

    def strings_appended(self) -> int:
        return len(self.strings) - self._original_string_size
