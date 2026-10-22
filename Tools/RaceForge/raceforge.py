#!/usr/bin/env python3
"""RaceForge: add the Bleakhold races (High Elf, Eredar) to your own 3.3.5a DBCs, for the client and AzerothCore.

    python3 -I raceforge.py build --dbc <your DBFilesClient folder> --out <output folder> [--mpq]
    python3 -I raceforge.py validate --dbc <same folder> --out <output folder>
    python3 -I raceforge.py schemas --check
    python3 -I raceforge.py [<DBC folder>]       (double-click or drop a folder: builds next to it)

RaceForge ships no game data: it reads the DBC files of your own client and writes patched copies of the tables it
changes, the AzerothCore SQL and a report. See README.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# python3 -I leaves the script's folder off sys.path; add it (and MpqPack next to it) explicitly.
for path in (HERE, os.path.join(os.path.dirname(HERE), "MpqPack")):
    if path not in sys.path:
        sys.path.insert(0, path)

from rflib import config as configmod  # noqa: E402
from rflib import recparse, schema_access, sqlgen, validate  # noqa: E402
from rflib.dbc import DbcError  # noqa: E402
from rflib.forge import Forge, ForgeError  # noqa: E402

DEFAULT_CONFIG = os.path.join(HERE, "races.json")
DEFAULT_MPQ = "patch-R.MPQ"
OUTPUT_ENTRIES = ("client", "server", "report.txt")


def prepare_out_dir(out_dir: str, force: bool):
    if os.path.isdir(out_dir):
        existing = [e for e in os.listdir(out_dir) if e in OUTPUT_ENTRIES]

        if existing and not force:
            raise ForgeError(f"{out_dir} already holds RaceForge output ({', '.join(existing)}); use --force to replace it")

        for entry in existing:
            path = os.path.join(out_dir, entry)

            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    os.makedirs(out_dir, exist_ok=True)


def build_mpq(out_dir: str, name: str, extra: str | None = None) -> str:
    import mpqpack

    source = os.path.join(out_dir, "client", "mpq-staging")

    if os.path.isdir(source):
        shutil.rmtree(source)

    # Extra files first (art aliases and the like, with their archive paths as folders), then the DBCs.
    if extra:
        if not os.path.isdir(extra):
            raise ForgeError(f"--mpq-extra {extra} is not a folder")

        shutil.copytree(extra, source)

    target = os.path.join(source, "DBFilesClient")
    os.makedirs(target, exist_ok=True)
    dbc_dir = os.path.join(out_dir, "client", "DBFilesClient")

    for entry in sorted(os.listdir(dbc_dir)):
        if os.path.exists(os.path.join(target, entry)):
            shutil.rmtree(source)
            raise ForgeError(f"--mpq-extra has its own DBFilesClient\\{entry}; RaceForge writes that file")

        shutil.copyfile(os.path.join(dbc_dir, entry), os.path.join(target, entry))

    path = os.path.join(out_dir, "client", name)

    try:
        mpqpack.pack_folder(source, path)
    except mpqpack.MpqError as e:
        raise ForgeError(f"packing {path}: {e}") from None
    finally:
        shutil.rmtree(source)

    return path


def format_report(forge: Forge, config: configmod.Config, written: dict, sql_files: list[str], mpq_path: str | None, result: validate.Validation, out_dir: str) -> str:
    lines = ["RaceForge report", "================", ""]
    lines.append(f"Input DBCs: {os.path.abspath(forge.input_dir)}")
    lines.append(f"Config:     {os.path.abspath(config.path) if config.path else '(built in)'}")
    lines.append(f"Faction masks of the stock playable races: Alliance 0x{forge.faction_masks.alliance:X}, Horde 0x{forge.faction_masks.horde:X} (from {forge.faction_masks.source})")
    lines.append("")

    lines.append("Races")
    lines.append("-----")

    for race in config.races:
        s = forge.summaries[race.id]
        lines.append(f"{race.id} {race.name}: ClientFileString {race.client_file_string}, template race {race.template_race}, {race.faction} (like race {race.faction_race}), "
                     f"FactionTemplate {s.faction_template}, displays {s.male_display}/{s.female_display}, classes {s.classes}")

    lines.append("")
    lines.append("Changes")
    lines.append("-------")

    for name in sorted(forge.changes):
        change = forge.changes[name]
        lines.append(f"{name}: {change.rows_added} rows added, {change.values_changed} mask values changed")

        for note in change.notes:
            lines.append(f"    {note}")

    if forge.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("--------")
        lines.extend(f"- {w}" for w in forge.warnings)

    lines.append("")
    lines.append("Validation")
    lines.append("----------")

    for check in result.checks:
        lines.append(f"[{check.status}] {check.name}" + (f" -- {check.detail}" if check.detail and check.status != "PASS" else ""))

    failed = len(result.failed)
    lines.append("")
    lines.append(f"{len(result.checks)} checks, {failed} failed" + (", " + str(sum(1 for c in result.checks if c.status == 'SKIP')) + " skipped" if any(c.status == "SKIP" for c in result.checks) else ""))
    lines.append("")
    lines.append("Output")
    lines.append("------")
    lines.append(f"Client DBCs: {os.path.join(out_dir, 'client', 'DBFilesClient')} ({len(written['client'])} files)")

    if mpq_path:
        lines.append(f"Client archive: {mpq_path}")

    lines.append(f"Server DBCs: {os.path.join(out_dir, 'server', 'dbc')} (identical copies)")

    for path in sql_files:
        lines.append(f"Server SQL: {path}")

    lines.append("")
    lines.append("Next steps")
    lines.append("----------")
    lines.append(f"1. Client: put {mpq_path or 'the DBFilesClient folder packed with MpqPack'} into the client's Data folder as Data\\{os.path.basename(mpq_path) if mpq_path else DEFAULT_MPQ}.")
    lines.append("   The client reads DBCs only from archives, and a Data\\patch-<letter>.MPQ later in the alphabet wins over earlier ones.")
    lines.append("2. Server: copy server/dbc/*.dbc over AzerothCore's data/dbc, run server/sql/bleakhold_races.sql on the world")
    lines.append("   database (optionally bleakhold_races_content_masks.sql), restart worldserver.")
    lines.append("3. Character creation also needs the Bleakhold glue UI for more than 10 races.")
    return "\n".join(lines) + "\n"


def cmd_build(args) -> int:
    config = configmod.load(args.config)
    forge = Forge(args.dbc, config)
    forge.load()
    forge.run()

    out_dir = os.path.abspath(args.out)
    prepare_out_dir(out_dir, args.force)
    written = forge.write(out_dir)

    sql_dir = os.path.join(out_dir, "server", "sql")
    os.makedirs(sql_dir, exist_ok=True)
    template_displays = {}
    races = forge.tables["ChrRaces"].by_id()

    for race in config.races:
        template = races[race.template_race]
        template_displays[race.id] = (forge.tables["ChrRaces"].get(template, "maleDisplayID"), forge.tables["ChrRaces"].get(template, "femaleDisplayID"))

    sql_files = []

    for filename, text in (
        ("bleakhold_races.sql", sqlgen.world_sql(config, forge.summaries, forge.faction_masks, template_displays)),
        ("bleakhold_races_content_masks.sql", sqlgen.content_sql(config, forge.summaries, forge.faction_masks)),
        ("bleakhold_races_remove.sql", sqlgen.remove_sql(config)),
    ):
        path = os.path.join(sql_dir, filename)

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        sql_files.append(path)

    if args.mpq_extra and not args.mpq:
        args.mpq = DEFAULT_MPQ

    mpq_path = build_mpq(out_dir, args.mpq, args.mpq_extra) if args.mpq else None
    result = validate.validate(out_dir, args.dbc, config, mpq_path)
    report = format_report(forge, config, written, sql_files, mpq_path, result, out_dir)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    return 1 if result.failed else 0


def cmd_validate(args) -> int:
    config = configmod.load(args.config)
    result = validate.validate(os.path.abspath(args.out), args.dbc, config, args.mpq)

    for check in result.checks:
        print(f"[{check.status}] {check.name}" + (f" -- {check.detail}" if check.detail and check.status != "PASS" else ""))

    print(f"{len(result.checks)} checks, {len(result.failed)} failed")
    return 1 if result.failed else 0


def cmd_schemas(args) -> int:
    rec_dir = args.rec_dir or recparse.default_rec_dir()

    if not rec_dir:
        print("error: WoW/Source/DB/Rec not found; pass --rec-dir", file=sys.stderr)
        return 1

    tables = recparse.load_all(rec_dir)
    print(f"{len(tables)} Rec classes parsed from {rec_dir}; every column count and row size matches s_numColumns/s_rowSize")
    text = recparse.emit_schemas_module(rec_dir)
    path = os.path.join(HERE, "rflib", "schemas.py")

    if args.write:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {path}")
        return 0

    with open(path, encoding="utf-8") as f:
        current = f.read()

    if current != text:
        print(f"error: {path} differs from the Rec classes; run `raceforge.py schemas --write`", file=sys.stderr)
        return 1

    for name in schema_access.names():
        schema = schema_access.get(name)
        print(f"  {name:28} {schema.num_columns:3} columns {schema.row_size:4} bytes{'  generated ids' if schema.generated_id else ''}")

    print(f"{path} matches the client's Rec classes")
    return 0


EASY_OUT = "Bleakhold-RaceForge-Output"
COMMANDS = ("build", "validate", "schemas", "-h", "--help")


def easy_mode(argv: list[str]) -> int:
    """Double-click or drag and drop: no command given. The DBC folder is the dropped folder, or asked for;
    the output goes next to it, in a folder RaceForge owns, so running it again replaces its own output."""
    print("Bleakhold RaceForge: adds High Elf and Eredar to your own DBC files.\n")

    if argv and os.path.isdir(argv[0]):
        dbc = argv[0]
    else:
        try:
            dbc = input("Drag your DBC folder (the client's DBFilesClient, or the server's data\\dbc) into this window and press Enter:\n> ")
        except EOFError:
            dbc = ""

        dbc = dbc.strip().strip('"')

    if not os.path.isdir(dbc):
        print(f"error: '{dbc}' is not a folder", file=sys.stderr)
        return 1

    out = os.path.join(os.path.dirname(os.path.abspath(dbc)), EASY_OUT)
    args = argparse.Namespace(dbc=dbc, out=out, config=DEFAULT_CONFIG, mpq=DEFAULT_MPQ, mpq_extra=None, force=True)

    try:
        result = cmd_build(args)
    except (configmod.ConfigError, ForgeError, DbcError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if result == 0:
        print(f"Done. Everything is in {out}:")
        print(f"  client\\{DEFAULT_MPQ}            -> copy into the game's Data folder")
        print("  server\\dbc\\*.dbc              -> copy into the server's data\\dbc folder")
        print("  server\\sql\\bleakhold_races.sql -> run on the world database")
    else:
        print(f"Some checks failed; see {os.path.join(out, 'report.txt')}. Nothing needs to be copied yet.")

    return result


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] not in COMMANDS:
        result = easy_mode(argv)

        # A double-clicked window closes as soon as the program ends; keep it open to read the result.
        if sys.stdin and sys.stdin.isatty() and (getattr(sys, "frozen", False) or os.name == "nt"):
            input("\nPress Enter to close.")

        return result

    parser = argparse.ArgumentParser(prog="raceforge.py", description="Add the Bleakhold races to your own 3.3.5a DBCs and write the AzerothCore SQL.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="patch the DBCs, write the SQL and the report")
    p.add_argument("--dbc", required=True, help="folder with your stock 3.3.5a DBC files (DBFilesClient, or the server's data/dbc)")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="races config (default: races.json next to raceforge.py)")
    p.add_argument("--mpq", nargs="?", const=DEFAULT_MPQ, help=f"also pack the client DBCs into an archive (default name {DEFAULT_MPQ})")
    p.add_argument("--mpq-extra", help="folder of extra client files to pack into the archive too (its subfolders are the archive paths)")
    p.add_argument("--force", action="store_true", help="replace earlier RaceForge output in --out")

    p = sub.add_parser("validate", help="check an output folder again")
    p.add_argument("--dbc", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--mpq", help="archive to check as well")

    p = sub.add_parser("schemas", help="check (or regenerate) rflib/schemas.py against the client's Rec classes")
    p.add_argument("--rec-dir", help="WoW/Source/DB/Rec of the decompilation (default: found next to Tools/)")
    p.add_argument("--write", action="store_true", help="regenerate rflib/schemas.py")
    p.add_argument("--check", action="store_true", help="only check (the default)")

    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            return cmd_build(args)
        if args.command == "validate":
            return cmd_validate(args)
        if args.command == "schemas":
            return cmd_schemas(args)
    except (configmod.ConfigError, ForgeError, DbcError, recparse.RecParseError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
