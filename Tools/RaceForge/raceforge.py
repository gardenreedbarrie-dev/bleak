#!/usr/bin/env python3
"""RaceForge: add the Bleakhold races (High Elf, Eredar) to your own 3.3.5a DBCs, for the client and AzerothCore.

    python3 -I raceforge.py build --dbc <your DBFilesClient folder> --out <output folder> [--mpq] [--customization <package>]
    python3 -I raceforge.py validate --dbc <same folder> --out <output folder>
    python3 -I raceforge.py update --patches <the realm's patch folder> --dbc <the server's data/dbc> --out <output folder>
                                   [--server-sql-out <the server's generated-SQL folder>]
    python3 -I raceforge.py skins --patches <the realm's patch folder> --client <the launcher's game folder>
                                  --out <output folder> [--preview]
    python3 -I raceforge.py customize --package <the Ascension package checkout> --patches <the realm's patch folder>
                                      --client <the launcher's game folder> --out <output folder> [--marks <manifest>]
    python3 -I raceforge.py picker-data [--package <the package checkout>] [--check]
    python3 -I raceforge.py install --from <output folder of update or skins> --patches <the realm's patch folder>
                                    [--dry-run] [--restore]
    python3 -I raceforge.py find --patches <the realm's patch folder> --client <the launcher's game folder>
                                 [<file path in the archives>] [--grep <text>] [--after <n>] [--out <file>]
                                 [--list <folder in the archives>]
    python3 -I raceforge.py schemas --check
    python3 -I raceforge.py [<DBC folder> [<customization package>]]   (double-click or drop folders: builds next to it)

RaceForge ships no game data: it reads the DBC files of your own client and writes patched copies of the tables it
changes, the AzerothCore SQL and a report. See README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))

# python3 -I leaves the script's folder off sys.path; add it (and MpqPack next to it) explicitly.
for path in (HERE, os.path.join(os.path.dirname(HERE), "MpqPack")):
    if path not in sys.path:
        sys.path.insert(0, path)

from rflib import config as configmod  # noqa: E402
from rflib import customize, patchnames, recparse, schema_access, spells as spellmod, sqlgen, update, validate  # noqa: E402
from rflib import install  # noqa: E402
from rflib.dbc import DbcError, DbcTable  # noqa: E402
from rflib.forge import OPTIONAL_TABLES, REQUIRED_TABLES, Forge, ForgeError, find_dbc  # noqa: E402

DEFAULT_CONFIG = os.path.join(HERE, "races.json")
DEFAULT_SKINS = os.path.join(HERE, "skins.json")
CUSTOMIZE_DIR = os.path.join(HERE, "customize")
DEFAULT_CURATION = os.path.join(CUSTOMIZE_DIR, "curation.json")
DEFAULT_CATALOGUE = os.path.join(CUSTOMIZE_DIR, "catalogue.json")
DEFAULT_COUNTS = os.path.join(CUSTOMIZE_DIR, "package_counts.json")
DEFAULT_BASE = "/root/wowdata/customize-base"
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_MPQ = "patch-R.MPQ"
OUTPUT_ENTRIES = ("client", "server", "customization", "report.txt")
# Art archives of a customization package (build --customization): patch-<character>.MPQ. Every letter but W belongs
# to a patch the realm ships (taken_patches.json); the digits 4-9 load after the stock patch-3.MPQ and below every
# lettered patch (rflib/patchnames.py); 4 and 5 are CafeForge's and MapForge's, 6 and 7 the realm's customize
# archives. The client reads MPQ v1 offsets as unsigned 32-bit (InitializeTables), and MpqPack writes v1, so an
# archive stays below 4 GiB: 3500 MB (MiB) of files leaves room for the tables, and the two default archives hold
# 7000 MB.
DEFAULT_ART_LETTERS = "89"
DEFAULT_ART_MAX_MB = 3500
MAX_ART_MB = 4000
TAKEN_PATCHES = os.path.join(HERE, patchnames.TAKEN_FILE)
BASE_DBC = os.path.join("customization", "base-dbc")


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


def merge_customization(dbc_dir: str, package_dir: str, config: configmod.Config) -> customize.MergeResult:
    """The user's tables merged with the package's (in memory)."""
    base = {}

    for name in ("ChrRaces",) + customize.TABLES:
        path = find_dbc(dbc_dir, name)

        if path:
            base[name] = DbcTable.read(path, schema_access.get(name))

    if "ChrRaces" not in base:
        raise ForgeError(f"{dbc_dir}: missing ChrRaces.dbc (point --dbc at the DBFilesClient folder of your 3.3.5a client)")

    return customize.merge(base, package_dir, {r.id for r in config.races})


def write_base_dbc(out_dir: str, dbc_dir: str, merged_bytes: dict[str, bytes]) -> str:
    """The user's DBCs with the package merged in (merged_bytes, taken before the races were added), as RaceForge's
    starting point: the validation compares the output with this folder. Only the tables RaceForge uses are written."""
    folder = os.path.join(out_dir, BASE_DBC)
    os.makedirs(folder, exist_ok=True)

    for name in REQUIRED_TABLES + OPTIONAL_TABLES + customize.TABLES:
        base = os.path.basename(schema_access.get(name).filename.replace("\\", "/"))

        if name in merged_bytes:
            with open(os.path.join(folder, base), "wb") as f:
                f.write(merged_bytes[name])
            continue

        path = find_dbc(dbc_dir, name)

        if path and not os.path.exists(os.path.join(folder, base)):
            shutil.copyfile(path, os.path.join(folder, base))

    return folder


def choose_art_names(letters: str, dbc_mpq: str | None, patches_dir: str | None, force: bool) -> tuple[list[str], str, list[str]]:
    """The art archive names, checked against taken_patches.json and, with --patches-dir, the names already in the
    realm's patch folder. A taken name is refused unless force. Returns (names, what was checked, warnings)."""
    try:
        names = patchnames.art_archive_names(letters, dbc_mpq)
        present = patchnames.scan_patches_dir(patches_dir) if patches_dir else None
    except patchnames.PatchNameError as e:
        raise ForgeError(str(e)) from None

    found = []

    try:
        taken = patchnames.load_taken(TAKEN_PATCHES)
    except patchnames.PatchNameError as e:
        if not force:
            raise ForgeError(str(e)) from None

        taken = {}
        found.append(str(e))

    found += patchnames.problems(names, taken, present)
    checked = f"{patchnames.TAKEN_FILE} ({len(taken)} names)"

    if present is not None:
        checked += f" and --patches-dir {patches_dir} ({len(present)} names)"

    if not found:
        return names, checked, []

    if not force:
        free = " ".join(patchnames.free_characters(taken, present, dbc_mpq)) or "none"
        raise ForgeError("refusing to write the customization art over names other patches use:\n  " + "\n  ".join(found)
                         + "\nPlayers who copy these archives would replace those patches. Choose other characters with "
                         f"--art-letters (free: {free}), or pass --force-letters if you really mean to replace them.")

    banner = "!" * 100
    print(f"{banner}\nWARNING: --force-letters: the customization art takes names other patches use:\n  " + "\n  ".join(found)
          + "\nPlayers who copy these archives replace those patches, and the launcher publishes files by name.\n"
          f"Do not publish them next to the realm's patches.\n{banner}", file=sys.stderr, flush=True)
    return names, checked, [f"--force-letters: {p}" for p in found]


def build_art_archives(out_dir: str, package_dir: str, names: list[str], max_mb: int) -> list[tuple[str, list[str]]]:
    """Pack the package's art into client/<name> archives (names from choose_art_names). Returns (path, archive
    names) per archive."""
    import mpqpack

    files = customize.art_files(package_dir)

    if not files:
        return []

    groups = mpqpack.plan_split(files, max_mb * 1024 * 1024)

    if len(groups) > len(names):
        raise ForgeError(f"the art needs {len(groups)} archives of at most {max_mb} MB but there are only {len(names)} names "
                         f"({', '.join(names)}); add characters to --art-letters or raise --art-max-mb (at most {MAX_ART_MB})")

    archives = []
    total = sum(len(g) for g in groups)
    done_before = 0

    for group, name in zip(groups, names):
        path = os.path.join(out_dir, "client", name)
        print(f"Packing {len(group)} art files into {name} ...", flush=True)

        def progress(done, count, before=done_before):
            if done % 2000 == 0 or done == count:
                print(f"  {before + done} / {total} files", flush=True)

        try:
            mpqpack.write_archive_streaming(path, [(n, p) for n, p, _ in group], progress=progress)
        except mpqpack.MpqError as e:
            raise ForgeError(f"packing {path}: {e}") from None

        archives.append((path, [n for n, _, _ in group]))
        done_before += len(group)

    return archives


def check_art_archives(v: validate.Validation, archives: list[tuple[str, list[str]]]):
    import mpqpack

    for path, expected in archives:
        try:
            with mpqpack.MpqArchive(path) as archive:
                report = archive.verify()
                listed = {mpqpack.name_key(n) for n in archive.names()}
        except (mpqpack.MpqError, OSError) as e:
            v.add("FAIL", f"{os.path.basename(path)}: art archive opens", str(e))
            continue

        missing = [n for n in expected if mpqpack.name_key(n) not in listed]
        problems = report.problems + ([f"{len(missing)} files missing, e.g. {missing[0]}"] if missing else [])

        if len(listed) != len(expected) and not missing:
            problems.append(f"{len(listed)} files listed, {len(expected)} packed")

        v.expect(not problems, f"{os.path.basename(path)}: {len(expected)} art files, passes the client's archive checks", "; ".join(problems[:5]))


def format_report(forge: Forge, config: configmod.Config, written: dict, sql_files: list[str], mpq_path: str | None, result: validate.Validation, out_dir: str,
                  merged: customize.MergeResult | None = None, package_dir: str | None = None, art: list | None = None) -> str:
    lines = ["RaceForge report", "================", ""]
    lines.append(f"Input DBCs: {os.path.abspath(forge.input_dir)}")

    if package_dir:
        lines.append(f"Customization package: {os.path.abspath(package_dir)}")
    lines.append(f"Config:     {os.path.abspath(config.path) if config.path else '(built in)'}")
    lines.append(f"Faction masks of the stock playable races: Alliance 0x{forge.faction_masks.alliance:X}, Horde 0x{forge.faction_masks.horde:X} (from {forge.faction_masks.source})")
    lines.append("")

    lines.append("Races")
    lines.append("-----")

    for race in config.races:
        s = forge.summaries[race.id]
        lines.append(f"{race.id} {race.name}: ClientFileString {race.client_file_string}, template race {race.template_race}, {race.faction} (like race {race.faction_race}), "
                     f"FactionTemplate {s.faction_template}, displays {s.male_display}/{s.female_display}, classes {s.classes}")

    if merged:
        lines.append("")
        lines.append("Customization merged first")
        lines.append("--------------------------")

        for name in sorted(merged.notes):
            for note in merged.notes[name]:
                lines.append(f"{name}: {note}")

        for warning in merged.warnings:
            lines.append(f"- {warning}")

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

    for path, files in art or []:
        lines.append(f"Client art archive: {path} ({len(files)} files)")

    lines.append(f"Server DBCs: {os.path.join(out_dir, 'server', 'dbc')} (identical copies)")

    for path in sql_files:
        lines.append(f"Server SQL: {path}")

    lines.append("")
    lines.append("Next steps")
    lines.append("----------")
    lines.append(f"1. Client: put {mpq_path or 'the DBFilesClient folder packed with MpqPack'} into the client's Data folder as Data\\{os.path.basename(mpq_path) if mpq_path else DEFAULT_MPQ}.")

    if art:
        lines.append(f"   Put the art archives ({', '.join(os.path.basename(p) for p, _ in art)}) into the Data folder as well.")

        if all(os.path.basename(p)[6].isdigit() for p, _ in art):
            lines.append("   Digits sort before letters: every lettered patch outranks them, so a realm patch holding the same file wins.")
    lines.append("   The client reads DBCs only from archives, and a Data\\patch-<letter>.MPQ later in the alphabet wins over earlier ones.")
    lines.append("2. Server: copy server/dbc/*.dbc over AzerothCore's data/dbc, run server/sql/bleakhold_races.sql on the world")
    lines.append("   database (optionally bleakhold_races_content_masks.sql), restart worldserver.")
    lines.append("3. Character creation also needs the Bleakhold glue UI for more than 10 races.")
    return "\n".join(lines) + "\n"


def cmd_build(args) -> int:
    config = configmod.load(args.config)
    package_dir = getattr(args, "customization", None)
    merged = None

    if args.mpq_extra and not args.mpq:
        args.mpq = DEFAULT_MPQ

    art_names, art_checked, art_warnings = [], "", []

    # Checked before the long work: the art goes only to names no other patch uses.
    if package_dir and args.mpq and not getattr(args, "no_art", False):
        if not 1 <= args.art_max_mb <= MAX_ART_MB:
            raise ForgeError(f"--art-max-mb {args.art_max_mb}: give 1 to {MAX_ART_MB} (MpqPack writes MPQ v1, which addresses less than 4 GiB per archive)")

        art_names, art_checked, art_warnings = choose_art_names(args.art_letters, args.mpq, getattr(args, "patches_dir", None), getattr(args, "force_letters", False))

    if package_dir:
        try:
            merged = merge_customization(args.dbc, package_dir, config)
        except customize.CustomizeError as e:
            raise ForgeError(str(e)) from None

    # The forge changes the merged tables in place; the starting point is kept for the base folder.
    merged_bytes = {name: table.to_bytes() for name, table in merged.tables.items()} if merged else {}
    forge = Forge(args.dbc, config, merged.tables if merged else None)
    forge.load()
    forge.run()

    out_dir = os.path.abspath(args.out)

    if package_dir and os.path.commonpath([out_dir, os.path.abspath(package_dir)]) == os.path.abspath(package_dir):
        raise ForgeError("the output folder must not be inside the customization package")

    prepare_out_dir(out_dir, args.force)
    stock_dir = args.dbc

    if merged:
        stock_dir = write_base_dbc(out_dir, args.dbc, merged_bytes)
        forge.warnings.extend(merged.warnings)

    written = forge.write(out_dir)

    # Merged tables RaceForge itself does not change (CreatureDisplayInfoExtra) still differ from the user's.
    for name, table in (merged.tables.items() if merged else ()):
        if name in forge.tables:
            continue

        base = os.path.basename(table.schema.filename.replace("\\", "/"))

        for kind, folder in (("client", os.path.join(out_dir, "client", "DBFilesClient")), ("server", os.path.join(out_dir, "server", "dbc"))):
            os.makedirs(folder, exist_ok=True)
            table.write(os.path.join(folder, base))
            written[kind].append(os.path.join(folder, base))

    sql_dir = os.path.join(out_dir, "server", "sql")
    os.makedirs(sql_dir, exist_ok=True)
    template_displays = {}
    races = forge.tables["ChrRaces"].by_id()

    for race in config.races:
        template = races[race.template_race]
        template_displays[race.id] = (forge.tables["ChrRaces"].get(template, "maleDisplayID"), forge.tables["ChrRaces"].get(template, "femaleDisplayID"))

    sql_files = []
    spell_rows_sql = ""

    if config.server_sql_spell_ids():
        spells = forge.tables["Spell"]
        by_id = spells.by_id()
        spell_rows_sql = spellmod.spell_sql(spells, [by_id[i] for i in config.server_sql_spell_ids()])

    for filename, text in (
        ("bleakhold_races.sql", sqlgen.world_sql(config, forge.summaries, forge.faction_masks, template_displays, spell_rows_sql)),
        ("bleakhold_races_content_masks.sql", sqlgen.content_sql(config, forge.summaries, forge.faction_masks)),
        ("bleakhold_races_remove.sql", sqlgen.remove_sql(config)),
    ):
        path = os.path.join(sql_dir, filename)

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        sql_files.append(path)

    mpq_path = build_mpq(out_dir, args.mpq, args.mpq_extra) if args.mpq else None
    art = []

    if art_names:
        art = build_art_archives(out_dir, package_dir, art_names, args.art_max_mb)

    result = validate.validate(out_dir, stock_dir, config, mpq_path)

    if package_dir:
        for status, name, detail in customize.check(stock_dir, args.dbc, package_dir, {r.id for r in config.races}):
            result.add(status, name, detail)

        if art_names:
            written_names = ", ".join(os.path.basename(p) for p, _ in art) or "none needed"
            result.add("WARN" if art_warnings else "PASS", f"art archive names ({written_names}) checked against {art_checked}",
                       "; ".join(art_warnings))
            forge.warnings.extend(art_warnings)

        check_art_archives(result, art)

    report = format_report(forge, config, written, sql_files, mpq_path, result, out_dir, merged, package_dir, art)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    return 1 if result.failed else 0


def cmd_validate(args) -> int:
    config = configmod.load(args.config)
    out_dir = os.path.abspath(args.out)
    stock_dir = args.dbc
    base_dir = os.path.join(out_dir, BASE_DBC)

    # A build with a customization package started from the merged tables it kept in the output.
    if os.path.isdir(base_dir):
        print(f"note: comparing with the merged starting point {base_dir}")
        stock_dir = base_dir

    result = validate.validate(out_dir, stock_dir, config, args.mpq)

    for check in result.checks:
        print(f"[{check.status}] {check.name}" + (f" -- {check.detail}" if check.detail and check.status != "PASS" else ""))

    print(f"{len(result.checks)} checks, {len(result.failed)} failed")
    return 1 if result.failed else 0


def format_update_report(config: configmod.Config, patches_dir: str, plan: update.UpdatePlan, written: list, sql_path: str,
                         server_files: list[str], result: validate.Validation, warnings: list[str], server_sql_out: str | None = None,
                         rev: tuple[str, bool] | None = None, rev_error: str = "", out_dir: str = "") -> str:
    lines = ["RaceForge update report", "=======================", ""]
    lines.append(f"Realm patches: {os.path.abspath(patches_dir)}")
    lines.append(f"Config:        {os.path.abspath(config.path) if config.path else '(built in)'}")
    lines.append(f"Pack combinations: {', '.join(plan.configurations)}")
    lines.append("")
    lines.append("Racials")
    lines.append("-------")

    for race in config.races:
        spells = ", ".join(f"{s} {config.spells[s].name}" for s in race.racial_spells) or "none"
        moved = f" (races.json id {race.build_id}; the realm has it at {race.id})" if race.build_id and race.build_id != race.id else ""
        lines.append(f"{race.id} {race.name}{moved}: drops template skill lines {race.drop_skill_lines or 'none'}; racial spells {spells}")

    lines.append("")
    lines.append("Where each table goes")
    lines.append("---------------------")

    for name, sources in plan.sources.items():
        for source in sources:
            target = source.archive or plan.own
            action = (f"merged into {target} (rebuilt)" if source.archive else f"stock copy + change, into {target}") if source.changed else "already up to date"
            lines.append(f"{update.archive_file(name)}: the copy in {source.where()} for {', '.join(source.labels)}: {action}")

            for note in source.notes:
                lines.append(f"    {note}")

    for note in plan.notes:
        lines.append(f"  {note}")

    if warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("--------")
        lines.extend(f"- {w}" for w in warnings)

    lines.append("")
    lines.append("Validation")
    lines.append("----------")

    for check in result.checks:
        lines.append(f"[{check.status}] {check.name}" + (f" -- {check.detail}" if check.detail and check.status != "PASS" else ""))

    lines.append("")
    lines.append(f"{len(result.checks)} checks, {len(result.failed)} failed")
    lines.append("")
    lines.append("Output")
    lines.append("------")

    for target, path, files in written:
        lines.append(f"Client archive: {path} ({', '.join(files)})")

    if not written:
        lines.append("Client archives: none (every copy is up to date)")

    for path in server_files:
        lines.append(f"Server DBC (optional, for data/dbc): {path}")

    lines.append(f"Server SQL: {sql_path}")

    if server_sql_out:
        if rev is not None:
            lines.append(f"Server SQL rev: {rev[0]} ({'written' if rev[1] else 'already there with the same SQL: nothing written'})")
        elif rev_error:
            lines.append(f"Server SQL rev: not written ({rev_error})")
        else:
            lines.append(f"Server SQL rev: not written to {server_sql_out} (a check failed)")

    lines.append("")
    lines.append("Next steps")
    lines.append("----------")
    lines.append("1. Client: put every archive of client/ into the realm's patch folder at the same place")
    lines.append("   (client/enUS/ into enUS/):")
    lines.append(f"   python3 -I {os.path.join(HERE, 'raceforge.py')} install --from {os.path.abspath(out_dir or '.')} "
                 f"--patches {os.path.abspath(patches_dir)}")
    lines.append("   (it replaces the file a link points at and keeps the old archives in old-patches/),")
    lines.append("   then publish it at once (the hourly run can come after step 2):")
    lines.append("   bash /root/bleakserv/deploy/launcher/publish.sh, and wait for \"Published build ...\".")
    lines.append("   Players need the new archives and a client restart: give them time before step 2.")
    lines += textwrap.wrap(f"2. Server: {SQL_NOTE}", 117, subsequent_indent="   ")
    high_elf = next((r for r in config.races if r.client_file_string.lower() == "highelf"), None)
    eredar = next((r for r in config.races if r.client_file_string.lower() == "eredar"), None)

    if high_elf and eredar:
        lines.append(f"3. Settings for these race ids, in the server's etc/modules: mod_bleakhold.conf Bleakhold.Racials.HighElfRace = {high_elf.id}")
        lines.append(f"   and Bleakhold.Racials.EredarRace = {eredar.id}; mod_bleakhold_ui.conf BleakholdUi.Glide.Races = \"{high_elf.id}\" (the update")
        lines.append("   script keeps a value the server already has).")

    return "\n".join(lines) + "\n"


SQL_NOTE = ("the world rows are server/sql/bleakhold_racials.sql, written from this realm's own rows. Run update with --server-sql-out "
            "/root/bleakhold-generated-sql/pending_db_world, which writes it there as a new rev_<nanoseconds>.sql (or copy it there under "
            "such a name); deploy/update-bleakhold-ui.sh of bleakserv deploys that folder like the repository's pending SQL, and "
            "ac-db-import applies each file once. Then: cd /root/bleakserv && git pull && bash deploy/update-bleakhold-ui.sh --check, "
            "then bash deploy/update-bleakhold-ui.sh (it rebuilds the world server, and ac-db-import applies the SQL before it starts; "
            "a plain worldserver restart does neither). data/dbc can stay as it is: the rows override it by id.")


def cmd_update(args) -> int:
    # the races at their ids on the realm (realm_id), checked against the realm's ChrRaces before anything is written
    config = configmod.load(args.config).for_realm()
    tables = update.changed_tables(config)

    if not tables:
        raise ForgeError("races.json has no racials to put in (racials.drop_template_skill_lines, racials.spells)")

    # build checks the spells' fields in Forge; update would only meet them in a copy, after --force cleared --out
    spell_layout = DbcTable.empty(schema_access.get("Spell"))

    for spell_id in config.spell_ids():
        problems = spellmod.field_problems(spell_layout, config.spells[spell_id])

        if problems:
            raise ForgeError(f"spell {spell_id} ({config.spells[spell_id].name}): " + "; ".join(problems))

    patches = update.patch_tools()

    try:
        patchset = patches.PatchSet.scan(args.patches, config.archives.optional_packs)
    except patches.PatchError as e:
        raise ForgeError(str(e)) from None

    unreadable = [f"{a.name}: {a.error}" for a in patchset.unreadable()]

    if unreadable:
        patchset.close()
        # An archive RaceForge cannot read might hold a later copy of a table, so the placement could be wrong.
        raise ForgeError("cannot read every archive of the patch folder, so the winning copies are unknown: " + "; ".join(unreadable))

    # the archives as read, for install.json: install refuses a file that changed since
    read_at = {a.client_path.lower(): install.fingerprint(a.path) for a in patchset.archives}
    warnings = []

    try:
        out_dir = os.path.abspath(args.out)
        plan = update.make_plan(config, patchset, args.dbc)
        problems, skipped = update.check_spells(plan, config)

        if problems:
            raise ForgeError("; ".join(problems))

        # only now: a refusal above leaves an earlier output folder as it was
        update.clean_out_dir(out_dir, args.force)
        # until the run is complete, install refuses this folder (a full disk or Ctrl-C leaves it unfinished)
        install.write_manifest(out_dir, "raceforge.py update", patchset.folder, None, [], False)

        warnings += [f"not checked: {s}" for s in skipped]
        written = update.write_archives(plan, patchset, out_dir)
    except (update.UpdateError, patches.PatchError, spellmod.SpellError) as e:
        patchset.close()
        raise ForgeError(str(e)) from None

    try:
        server_dir = os.path.join(out_dir, "server", "dbc")
        server_files = []

        for name, table in plan.server.items():
            if any(s.changed for s in plan.sources[name]):
                path = os.path.join(server_dir, os.path.basename(schema_access.get(name).filename.replace("\\", "/")))
                table.write(path)
                server_files.append(path)

        sql_dir = os.path.join(out_dir, "server", "sql")
        os.makedirs(sql_dir, exist_ok=True)
        sql_text = update.racials_sql(config, plan)
        sql_path = os.path.join(sql_dir, update.SQL_FILE)

        with open(sql_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql_text)

        result = validate.Validation()
        import mpqpack

        for name, sources in plan.sources.items():
            for source in sources:
                problems = update.copy_problems(name, source.forged, config)
                result.expect(not problems, f"{update.archive_file(name)} for {', '.join(source.labels)} ({source.where()}): holds the racials", "; ".join(problems))

        for target, path, files in written:
            with mpqpack.MpqArchive(path) as archive:
                report = archive.verify()
                result.expect(not report.problems, f"{target}: passes the client reader's checks", "; ".join(report.problems))

                for archive_name in files:
                    result.expect(archive.read(archive_name) == plan.targets[target][archive_name], f"{target}: {archive_name} is the forged copy")

                original = patchset.find(target)

                if original is not None and original.reader is not None:
                    before = {mpqpack.name_key(n) for n in original.reader.names()}
                    after = {mpqpack.name_key(n) for n in archive.names()}
                    result.expect(before <= after, f"{target}: every file of the realm's archive is still there ({len(before)} before, {len(after)} after)")

        for name, sql_table, columns in (("Spell", "spell_dbc", spellmod.SERVER_SPELL_COLUMNS),
                                         ("SkillRaceClassInfo", "skillraceclassinfo_dbc", spellmod.server_columns(spellmod.SERVER_SKILL_RACE_CLASS_COLUMNS)),
                                         ("SkillLineAbility", "skilllineability_dbc", spellmod.server_columns(spellmod.SERVER_SKILL_LINE_ABILITY_COLUMNS))):
            sources = update.server_rows(plan, name)
            rows = spellmod.parse_sql_rows(sql_text, sql_table)

            if not sources or not rows:
                continue

            differences = []

            for row_id, sql_row in rows.items():
                if row_id not in sources:
                    differences.append(f"{row_id} is in no copy of {name}.dbc")
                    continue

                table, row = sources[row_id]
                differences += [f"{row_id} {d}" for d in spellmod.compare_row(table, row, sql_row, columns)]
                differences += [f"{row_id}: race {r.id} still has its bit" for r in config.races if name != "Spell" and update.has_dropped_bit(name, table, row, r)]

            result.expect(not differences, f"{sql_table}: {len(rows)} rows match {name}.dbc (the server copy) field for field ({len(columns)} columns)"
                          + (", without the races' bits" if name != "Spell" else ""), "; ".join(differences[:5]))

        server_spells = plan.server.get("Spell")

        for spell_id in config.spell_ids():
            spell = config.spells[spell_id]

            if spell.server_row and server_spells is not None:
                status, detail = spellmod.server_row_check(server_spells, server_spells.by_id()[spell_id], spell)
                label = f"{configmod.CAST_BY_TEXT.get(spell.cast_by, spell.cast_by)} spell {spell_id} {spell.name}"
                result.add(status, f"{label}: the spell_dbc row of {spell.server_row} matches Spell.dbc field for field", detail)

        if args.server_sql:
            with open(args.server_sql, encoding="utf-8") as f:
                other = f.read()

            differences = update.compare_sql(sql_text, other)
            result.expect(not differences, f"{args.server_sql}: holds the same spell_dbc, skillraceclassinfo_dbc and skilllineability_dbc rows", "; ".join(differences[:8]))
    finally:
        patchset.close()

    rev = None
    rev_error = ""

    # A rev file reaches the server with the next update-bleakhold-ui.sh: only when every check passed.
    if args.server_sql_out and not result.failed:
        try:
            rev = update.write_rev(args.server_sql_out, sql_text)
        except (update.UpdateError, OSError) as e:
            rev_error = str(e)

    entries = []

    for target, path, _ in written:
        archive = patchset.find(target)
        rel = os.path.relpath(path, os.path.join(out_dir, "client")).replace(os.sep, "/")

        if archive is not None:
            size, mtime_ns = read_at[archive.client_path.lower()]
            entries.append(install.entry(rel, archive.client_path, "patches", archive.path, size, mtime_ns, path))
        else:
            entries.append(install.entry(rel, "Data\\" + target, "new", "", None, None, path))

    install.write_manifest(out_dir, "raceforge.py update", patchset.folder, None, entries, not result.failed)
    report_text = format_update_report(config, args.patches, plan, written, sql_path, server_files, result, warnings, args.server_sql_out, rev, rev_error,
                                       out_dir)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)

    if rev_error:
        print(f"error: {rev_error}", file=sys.stderr)

    return 1 if result.failed or rev_error else 0


def cmd_skins(args) -> int:
    from rflib import skins  # noqa: E402  (loads Tools/MapForge's archive code)

    # the races at their ids on the realm (realm_id), checked against the realm's ChrRaces before anything is written
    config = configmod.load(args.config).for_realm()
    out_dir = os.path.abspath(args.out)

    for flag, folder in (("--patches", args.patches), ("--client", args.client)):
        real = os.path.realpath(folder)

        try:
            inside = os.path.commonpath([os.path.realpath(out_dir), real]) == real
        except ValueError:  # another drive
            inside = False

        if inside:
            raise ForgeError(f"--out {out_dir} is inside {flag} {folder}: the launcher would publish it; give a folder "
                             "elsewhere")

    try:
        races = skins.load(args.skins, config)
        game = skins.game_archives(args.client, args.patches, config.archives.optional_packs, args.locale)
    except skins.SkinsError as e:
        raise ForgeError(str(e)) from None

    try:
        plan = skins.make_plan(game, config, races, args.art_archive)
        up_to_date = not plan.writes
        need = skins.space_needed(plan) if plan.writes else 0
        free = skins.free_space(out_dir) + (skins.entries_size(out_dir, skins.OUT_ENTRIES) if args.force else 0)

        if need > free:
            raise ForgeError(f"--out {out_dir} needs {skins.gb(need)} free for the rebuilt archives "
                             f"({', '.join(t.archive.name for t in plan.writes)}), has {skins.gb(free)}")

        # only now: a refusal above leaves an earlier output folder as it was
        update.clean_out_dir(out_dir, args.force, skins.OUT_ENTRIES)
        # until the run is complete, install refuses this folder (a full disk or Ctrl-C leaves it unfinished)
        install.write_manifest(out_dir, "raceforge.py skins", game.patches_dir, game.client_data, [], False)
        written = skins.write(plan, out_dir)
        result = skins.check(plan, written)
        previews = skins.write_previews(plan, out_dir) if args.preview else []
    except (skins.SkinsError, update.UpdateError) as e:
        raise ForgeError(str(e)) from None
    finally:
        game.close()

    report = skins.format_report(plan, args, written, result, previews, up_to_date)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report)

    install.write_manifest(out_dir, "raceforge.py skins", game.patches_dir, game.client_data,
                           skins.manifest_entries(plan, written), not result.failed)
    print(skins.summary(plan, out_dir, written, result, up_to_date))

    for warning in game.warnings + plan.leftovers:
        print(f"warning: {warning}")

    if result.failed:
        print("Some checks failed: do not install this output.", file=sys.stderr)
    elif up_to_date:
        print("already up to date")
    else:
        print(f"Next: python3 -I {os.path.join(HERE, 'raceforge.py')} install --from {out_dir} "
              f"--patches {os.path.abspath(args.patches)}")

    return 1 if result.failed else 0


def cmd_customize(args) -> int:
    from rflib import realm_customize as rc  # noqa: E402  (loads Tools/MapForge's archive code)

    config = configmod.load(args.config).for_realm()
    art = tuple(f"patch-{c}.MPQ" for c in args.art_letters.upper())
    names = list(art) + [args.models_archive, args.marks_archive] + ([args.move_art] if args.move_art else [])
    taken = patchnames.load_taken(TAKEN_PATCHES)
    owners = {patchnames.name_key(n): taken.get(patchnames.name_key(n), "") for n in names}
    wrong = [n for n in names if "customize" not in owners[patchnames.name_key(n)].lower()]

    if wrong:
        raise ForgeError(f"{', '.join(wrong)}: not a name taken_patches.json gives to customize; the archives of "
                         f"customize are {', '.join(n for n, o in taken.items() if 'customize' in o.lower())}")

    opts = rc.Options(package=args.package, patches=args.patches, client=args.client, out=args.out, base=args.base,
                      curation=args.curation, catalogue=args.catalogue, marks=args.marks, server_dbc=args.dbc,
                      move_art=args.move_art, art_names=art, art_max_mb=args.art_max_mb,
                      models_archive=args.models_archive, marks_archive=args.marks_archive, locale=args.locale,
                      any_package=args.any_package, run_id=args.run_id or "", base_from=args.base_from,
                      keep_free_gb=args.keep_free_gb, marks_partial=args.marks_partial)
    out_dir = os.path.abspath(args.out)

    try:
        update.clean_out_dir(out_dir, args.force, rc.OUT_ENTRIES)
        plan, written, problems = rc.run(opts, config)
    except (rc.CustomizeError, update.UpdateError) as e:
        raise ForgeError(str(e)) from None

    for combo in plan.combos:
        print(f"{combo.label}: " + ", ".join(f"{n} {combo.holders[n].name}" for n in rc.TABLES))

    print(f"CharSections: {plan.hashes.get('charsections_rows')} rows; BarberShopStyle: "
          f"{plan.hashes.get('barbershopstyle_rows')} rows; hidden {len(plan.server.merged.hidden)}; rebuilt "
          f"{len(plan.rebuilt)}; remapped pairs {sum(len(m.moved) for m in plan.mappings.values())}")

    for archive in plan.new_archives:
        print(f"{archive.name} ({archive.role}): {len(archive.files) + len(archive.blobs)} files, "
              f"{archive.size() / 1e6:.1f} MB{' (unchanged)' if archive.unchanged else ''}")

    for path in sorted(written.values()):
        print(f"written: {path}")

    for warning in plan.warnings + plan.game.warnings:
        print(f"warning: {warning}")

    print(f"{len(problems)} checks failed" if problems else "every check passed")

    for problem in problems[:40]:
        print(f"  [FAIL] {problem}", file=sys.stderr)

    if problems:
        print(f"Some checks failed (report: {os.path.join(out_dir, 'report.txt')}): do not install this output.",
              file=sys.stderr)
        return 1

    print(f"Next: python3 -I {os.path.join(HERE, 'raceforge.py')} install --from {out_dir} "
          f"--patches {os.path.abspath(args.patches)}")
    return 0


def cmd_picker_data(args) -> int:
    from rflib import curation as curmod, marksrows, picker  # noqa: E402

    try:
        cur = curmod.load(args.curation)
        catalogue = marksrows.load_catalogue(args.catalogue)

        if args.package:
            from rflib import realm_customize as rc  # noqa: E402

            commit = rc.package_commit(args.package)

            if commit != cur.commit and not args.any_package:
                raise ForgeError(f"{args.package} is at commit {commit or '(not a git checkout)'}, the curation pins "
                                 f"{cur.commit}: check out that commit (--any-package skips this check)")

            tables = rc.load_package_tables(args.package)
            counts_text = picker.counts_text(picker.counts_from_tables(tables["CharSections"],
                                                                       tables["CharacterFacialHairStyles"],
                                                                       commit or cur.commit))
            counts = json.loads(counts_text)
        else:
            counts = picker.load_counts(args.counts)
            counts_text = None

        if counts.get("package") != cur.commit:
            raise ForgeError(f"{args.counts}: made from package commit {counts.get('package')}, the curation pins "
                             f"{cur.commit}: run picker-data --package <the pinned checkout>")

        files = picker.outputs(args.repo, counts, cur, catalogue)

        if counts_text is not None:
            files[os.path.abspath(args.counts)] = counts_text
    except (curmod.CurationError, marksrows.MarksError, picker.PickerError) as e:
        raise ForgeError(str(e)) from None

    stale = []

    for path, text in sorted(files.items()):
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = None

        if current == text:
            print(f"up to date: {path}")
            continue

        if args.check:
            stale.append(path)
            continue

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        print(f"wrote {path}")

    if stale:
        for path in stale:
            print(f"error: {path} is not what picker-data makes; run raceforge.py picker-data", file=sys.stderr)

        return 1

    return 0


def cmd_find(args) -> int:
    from rflib import find  # noqa: E402  (loads Tools/MapForge's archive code)

    try:
        return find.run(args)
    except find.FindError as e:
        raise ForgeError(str(e)) from None


def cmd_install(args) -> int:
    try:
        return install.run(args.source, args.patches, args.dry_run, args.restore)
    except install.InstallError as e:
        raise ForgeError(str(e)) from None


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
COMMANDS = ("build", "validate", "update", "skins", "customize", "picker-data", "install", "find", "schemas", "-h",
            "--help")


def easy_mode(argv: list[str]) -> int:
    """Double-click or drag and drop: no command given. The DBC folder is the dropped folder, or asked for;
    the output goes next to it, in a folder RaceForge owns, so running it again replaces its own output."""
    print("Bleakhold RaceForge: adds High Elf and Eredar to your own DBC files.\n")

    package = None

    if argv and os.path.isdir(argv[0]):
        dbc = argv[0]

        if len(argv) > 1 and os.path.isdir(argv[1]):
            package = argv[1]
    else:
        try:
            dbc = input("Drag your DBC folder (the client's DBFilesClient, or the server's data\\dbc) into this window and press Enter:\n> ")
        except EOFError:
            dbc = ""

        dbc = dbc.strip().strip('"')

    if not os.path.isdir(dbc):
        print(f"error: '{dbc}' is not a folder", file=sys.stderr)
        return 1

    if package is None and not argv:
        try:
            package = input("\nOptional: drag a character customization package (for example Ascension Character Customization) into this\n"
                            "window and press Enter, or just press Enter to skip:\n> ")
        except EOFError:
            package = ""

        package = package.strip().strip('"') or None

        if package and not os.path.isdir(package):
            print(f"error: '{package}' is not a folder", file=sys.stderr)
            return 1

    out = os.path.join(os.path.dirname(os.path.abspath(dbc)), EASY_OUT)
    args = argparse.Namespace(dbc=dbc, out=out, config=DEFAULT_CONFIG, mpq=DEFAULT_MPQ, mpq_extra=None, force=True,
                              customization=package, no_art=False, art_letters=DEFAULT_ART_LETTERS, art_max_mb=DEFAULT_ART_MAX_MB,
                              patches_dir=None, force_letters=False)

    try:
        result = cmd_build(args)
    except (configmod.ConfigError, ForgeError, DbcError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if result == 0:
        print(f"Done. Everything is in {out}:")
        print(f"  client\\{DEFAULT_MPQ}            -> copy into the game's Data folder")

        art = [n for n in patchnames.art_archive_names(DEFAULT_ART_LETTERS, DEFAULT_MPQ) if os.path.isfile(os.path.join(out, "client", n))]

        if art:
            print(f"  client\\{', '.join(art)} -> the customization art: copy into the game's Data folder too")
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
    p.add_argument("--customization", help="character customization package to merge first (a folder with DBFilesClient\\ and art folders)")
    p.add_argument("--no-art", action="store_true", help="with --customization: merge the tables only, do not pack the package's art")
    p.add_argument("--art-letters", default=DEFAULT_ART_LETTERS,
                   help=f"characters (A-Z, 4-9) of the art archives patch-<c>.MPQ (default {DEFAULT_ART_LETTERS}); names in {patchnames.TAKEN_FILE} are refused")
    p.add_argument("--art-max-mb", type=int, default=DEFAULT_ART_MAX_MB, help=f"file data per art archive in MB, at most {MAX_ART_MB} (default {DEFAULT_ART_MAX_MB})")
    p.add_argument("--patches-dir", help="the realm's patch folder (or a client's Data folder): also refuse art names already there")
    p.add_argument("--force-letters", action="store_true", help="write the art even over taken names (prints a warning; never publish such archives)")

    p = sub.add_parser("validate", help="check an output folder again")
    p.add_argument("--dbc", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--mpq", help="archive to check as well")

    p = sub.add_parser("update", help="put races.json's racials into a realm that already has the races (merges into the winning archives)")
    p.add_argument("--patches", required=True, help="the realm's patch folder (patch-?.MPQ, <locale>/patch-<locale>-?.MPQ) or a client's Data folder")
    p.add_argument("--dbc", required=True, help="the server's data/dbc: the copy of a table no patch holds, and the server's own rows of the dropped skill lines")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--force", action="store_true", help="replace earlier output in --out")
    p.add_argument("--server-sql", help="an SQL file to compare (the bleakserv pending_db_world file): its DBC rows must match field for field")
    p.add_argument("--server-sql-out", help="also write the server SQL as a world-database update of its own when every check passed: a folder "
                   "(a new rev_<nanoseconds>.sql goes there, e.g. /root/bleakhold-generated-sql/pending_db_world) or a .sql path; a file of "
                   "the folder with the same SQL is kept and nothing is written, a different file at the path stops it")

    p = sub.add_parser("skins", help="recolour the skins of races.json's races on the realm (skins.json: High Elf "
                                     "purple) into new textures")
    p.add_argument("--patches", required=True, help="the realm's patch folder (/srv/bleakhold-launcher/patches): its "
                                                    "archives load over --client's")
    p.add_argument("--client", required=True, help="the game folder the launcher ships (/srv/bleakhold-launcher/base, "
                                                   "holding Data/common.MPQ)")
    p.add_argument("--out", required=True, help="output folder (not inside --patches or --client)")
    p.add_argument("--force", action="store_true", help="replace earlier output in --out")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="races config (default: races.json next to raceforge.py)")
    p.add_argument("--skins", default=DEFAULT_SKINS, help="skin colours (default: skins.json next to raceforge.py)")
    p.add_argument("--locale", help="the client's locale (default: the one of Data/<locale>/locale-<locale>.MPQ)")
    p.add_argument("--preview", action="store_true", help="also write PNG contact sheets of every skin colour, before "
                                                          "and after, to --out/preview")
    p.add_argument("--art-archive", metavar="ARCHIVE", help="put the recoloured textures into this archive "
                                                            "(patch-F.MPQ on the realm) instead of the tables' one, "
                                                            "so a skins change rebuilds a small archive")

    p = sub.add_parser("customize", help="merge the Ascension customization package into the realm's tables for races "
                                         "1-11, High Elf 15 and Eredar 19 (and the marks and eyes with --marks)")
    p.add_argument("--package", required=True, help="the package checkout (/root/wowdata/ascc), at the commit "
                                                    "customize/curation.json pins")
    p.add_argument("--patches", required=True, help="the realm's patch folder (/srv/bleakhold-launcher/patches)")
    p.add_argument("--client", required=True, help="the game folder the launcher ships (/srv/bleakhold-launcher/base)")
    p.add_argument("--out", required=True, help="output folder (not inside --patches or --client)")
    p.add_argument("--base", default=DEFAULT_BASE, help=f"the saved base: the realm's tables from before the package "
                                                        f"and the barber id ledger (default {DEFAULT_BASE})")
    p.add_argument("--marks", help="MarkForge's marks_manifest.json: add the mark (features) and eye (face) rows "
                                   "and pack them (stage 2)")
    p.add_argument("--marks-partial", action="store_true", help="a dev run only: accept a --marks manifest without "
                                                                "every race-sex, all 12 looks and eyes 1-5")
    p.add_argument("--dbc", help="the server's data/dbc, to compare its BarberShopStyle.dbc with the client's")
    p.add_argument("--move-art", metavar="ARCHIVE", help="also move the table archives' other files into this "
                                                         "archive (patch-O.MPQ, once), leaving them tables only")
    p.add_argument("--art-letters", default="67", help="characters of the package art archives (default 67)")
    p.add_argument("--art-max-mb", type=int, default=3500, help="file data per art archive in MB (default 3500)")
    p.add_argument("--models-archive", default="patch-~.MPQ", help="the archive of the package's models (default "
                                                                    "patch-~.MPQ, above every lettered patch)")
    p.add_argument("--marks-archive", default="patch-K.MPQ", help="the archive of the marks and eyes (default "
                                                                   "patch-K.MPQ)")
    p.add_argument("--curation", default=DEFAULT_CURATION, help="default: customize/curation.json")
    p.add_argument("--catalogue", default=DEFAULT_CATALOGUE, help="default: customize/catalogue.json")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="races config (default: races.json next to raceforge.py)")
    p.add_argument("--locale", help="the client's locale (default: the one of Data/<locale>/locale-<locale>.MPQ)")
    p.add_argument("--run-id", help="the id of this run in the remap SQL (default: customize-<UTC time>)")
    p.add_argument("--base-from", metavar="FOLDER", help="the realm's archives from before the package, laid out as "
                                                         "the patch folder (an install's old-patches): the saved base "
                                                         "for tables that are merged already and have none")
    p.add_argument("--keep-free-gb", type=float, default=5.0, help="refuse to write when less than this would stay "
                                                                   "free on --out's disk (default 5)")
    p.add_argument("--any-package", action="store_true", help="take a package at another commit than the pinned one")
    p.add_argument("--force", action="store_true", help="replace earlier output in --out")

    p = sub.add_parser("picker-data", help="write the glue picker's and the barbershop hook's numbers "
                                           "(BleakholdCustomizeData.lua, BarberData.lua) from the curation, the "
                                           "catalogue and the package counts")
    p.add_argument("--package", help="the pinned package checkout: also make customize/package_counts.json from its "
                                     "tables")
    p.add_argument("--check", action="store_true", help="write nothing; fail when a file is not what picker-data "
                                                        "makes (CI)")
    p.add_argument("--counts", default=DEFAULT_COUNTS, help="default: customize/package_counts.json")
    p.add_argument("--curation", default=DEFAULT_CURATION)
    p.add_argument("--catalogue", default=DEFAULT_CATALOGUE)
    p.add_argument("--repo", default=REPO_ROOT, help="the repository the Interface files are written into")
    p.add_argument("--any-package", action="store_true", help="take a package at another commit than the pinned one")

    p = sub.add_parser("install", help="put the archives of an update or skins output folder into the realm's patch "
                                       "folder")
    p.add_argument("--from", dest="source", required=True, help="the output folder of update or skins")
    p.add_argument("--patches", required=True, help="the realm's patch folder the archives go into")
    p.add_argument("--dry-run", action="store_true", help="only list what it would do")
    p.add_argument("--restore", action="store_true", help="put the archives of --from's old-patches back (undo an "
                                                          "install)")

    p = sub.add_parser("find", help="which archive the client reads a file from, for every pack combination; its "
                                    "lines (--grep), the file itself (--out), or every file of a folder (--list)")
    p.add_argument("path", nargs="?", help="the file's path in the archives, with / or \\ (Interface/GlueXML/"
                                           "CharacterCreate.xml); any case")
    p.add_argument("--patches", required=True, help="the realm's patch folder (/srv/bleakhold-launcher/patches)")
    p.add_argument("--client", required=True, help="the game folder the launcher ships (/srv/bleakhold-launcher/base)")
    p.add_argument("--grep", action="append", metavar="TEXT", help="print the lines of the copy the client reads that "
                                                                  "contain TEXT, in any case (repeat for more texts)")
    p.add_argument("--after", type=int, default=0, metavar="N", help="with --grep: also the N lines after each one")
    p.add_argument("--out", help="write the copy the client reads to this file (or into this folder)")
    p.add_argument("--list", metavar="FOLDER", help="list every file under FOLDER (Interface/GlueXML) with the "
                                                    "archive the client reads it from; * marks the patches folder's")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="races config, for its optional packs (default: races.json)")
    p.add_argument("--locale", help="the client's locale (default: the one of Data/<locale>/locale-<locale>.MPQ)")

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
        if args.command == "update":
            return cmd_update(args)
        if args.command == "skins":
            return cmd_skins(args)
        if args.command == "customize":
            return cmd_customize(args)
        if args.command == "picker-data":
            return cmd_picker_data(args)
        if args.command == "install":
            return cmd_install(args)
        if args.command == "find":
            return cmd_find(args)
        if args.command == "schemas":
            return cmd_schemas(args)
    except (configmod.ConfigError, ForgeError, DbcError, recparse.RecParseError, spellmod.SpellError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
