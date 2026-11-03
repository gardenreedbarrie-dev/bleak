"""Access to the generated table layouts (rflib/schemas.py) as TableSchema objects."""

from __future__ import annotations

from . import recparse
from .schemas import SCHEMAS

_cache: dict[str, recparse.TableSchema] = {}


def get(name: str) -> recparse.TableSchema:
    """The layout of a table; the column count and row size are checked against the client constants."""
    if name not in _cache:
        filename, num_columns, row_size, generated_id, columns = SCHEMAS[name]
        schema = recparse.TableSchema(name, filename, num_columns, row_size, generated_id, [recparse.Column(*c) for c in columns])
        recparse.check_schema(schema)
        _cache[name] = schema

    return _cache[name]


def names() -> list[str]:
    return list(SCHEMAS)
