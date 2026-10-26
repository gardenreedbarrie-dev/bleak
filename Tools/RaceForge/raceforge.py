#!/usr/bin/env python3
"""RaceForge: add the Bleakhold races (High Elf, Eredar) to your own 3.3.5a DBCs, for the client and AzerothCore.

    python3 -I raceforge.py build --dbc <your DBFilesClient folder> --out <output folder> [--mpq] [--customization <package>]
    python3 -I raceforge.py validate --dbc <same folder> --out <output folder>
    python3 -I raceforge.py update --patches <the realm's patch folder> --dbc <stock DBCs> --out <output folder>
    python3 -I raceforge.py schemas --check
    python3 -I raceforge.py [<DBC folder> [<customization package>]]   (double-click or drop folders: builds next to it)

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
from rflib import customize, patchnames, recparse, schema_access, spells as spellmod, sqlgen, update, validate  # noqa: E402
from rflib.dbc import DbcError, DbcTable  # noqa: E402
from rflib.forge import OPTIONAL_TABLES, REQUIRED_TABLES, Forge, ForgeError, find_dbc  # noqa: E402

DEFAULT_CONFIG = os.path.join(HERE, "races.json")
DEFAULT_MPQ = "patch-R.MPQ"
OUTPUT_ENTRIES = ("client", "server", "customization", "report.txt")
# Art archives of a customization package: patch-<character>.MPQ. Every letter but F K O W belongs to a patch the
# realm ships (taken_patches.json); the digits 4-9 load after the stock patch-3.MPQ and below every lettered patch
# (rflib/patchnames.py), and 5 is MapForge's server-side extract. The client reads MPQ v1 offsets as unsigned 32-bit
# (InitializeTables), and MpqPack writes v1, so an archive stays below 4 GiB: 3500 MB (MiB) of files leaves room for
# the tables, and the four default archives hold 14000 MB.
DEFAULT_ART_LETTERS = "6789"
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
                         server_files: list[str], result: validate.Validation, warnings: list[str]) -> str:
    lines = ["RaceForge update report", "=======================", ""]
    lines.append(f"Realm patches: {os.path.abspath(patches_dir)}")
    lines.append(f"Config:        {os.path.abspath(config.path) if config.path else '(built in)'}")
    lines.append(f"Pack combinations: {', '.join(plan.configurations)}")
    lines.append("")
    lines.append("Racials")
    lines.append("-------")

    for race in config.races:
        spells = ", ".join(f"{s} {config.spells[s].name}" for s in race.racial_spells) or "none"
        lines.append(f"{race.id} {race.name}: drops template skill lines {race.drop_skill_lines or 'none'}; racial spells {spells}")

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
    lines.append("")
    lines.append("Next steps")
    lines.append("----------")
    lines.append("1. Client: put every archive of client/ into the realm's patch folder, replacing the file of the same name")
    lines.append("   (upload it under another name, then mv it into place), then publish it at once (the hourly run can come after")
    lines.append("   step 2): bash /root/bleakserv/deploy/launcher/publish.sh, and wait for \"Published build ...\". Players need the")
    lines.append("   new archives and a client restart: give them time before step 2.")
    lines.append(f"2. Server: {SQL_NOTE}")
    return "\n".join(lines) + "\n"


SQL_NOTE = ("add server/sql/bleakhold_racials.sql to bleakserv as data/sql/updates/pending_db_world/rev_<timestamp>.sql (or compare it "
            "with the one there: --server-sql), commit and push it with mod-bleakhold's bh_racials.cpp, then deploy both on the realm: "
            "cd /root/bleakserv && git pull && bash deploy/update-bleakhold-ui.sh --check, then bash deploy/update-bleakhold-ui.sh "
            "(it rebuilds the world server, and ac-db-import applies the SQL before it starts; a plain worldserver restart does "
            "neither). data/dbc can stay as it is: the rows override it by id.")


def cmd_update(args) -> int:
    config = configmod.load(args.config)
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

    warnings = []

    try:
        out_dir = os.path.abspath(args.out)
        update.clean_out_dir(out_dir, args.force)
        plan = update.make_plan(config, patchset, args.dbc)
        problems, skipped = update.check_spells(plan, config)

        if problems:
            raise ForgeError("; ".join(problems))

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
            table = plan.server.get(name)
            rows = spellmod.parse_sql_rows(sql_text, sql_table)

            if table is None or not rows:
                continue

            by_id = table.by_id()
            differences = []

            for row_id, sql_row in rows.items():
                differences += [f"{row_id} {d}" for d in spellmod.compare_row(table, by_id[row_id], sql_row, columns)]

            result.expect(not differences, f"{sql_table}: {len(rows)} rows match {name}.dbc (the server copy) field for field ({len(columns)} columns)", "; ".join(differences[:5]))

        server_spells = plan.server.get("Spell")

        for spell_id in config.spell_ids():
            spell = config.spells[spell_id]

            if spell.server_row and server_spells is not None:
                status, detail = spellmod.server_row_check(server_spells, server_spells.by_id()[spell_id], spell)
                result.add(status, f"spell {spell_id} {spell.name}: the spell_dbc row of {spell.server_row} matches Spell.dbc field for field", detail)

        if args.server_sql:
            with open(args.server_sql, encoding="utf-8") as f:
                other = f.read()

            differences = update.compare_sql(sql_text, other)
            result.expect(not differences, f"{args.server_sql}: holds the same spell_dbc, skillraceclassinfo_dbc and skilllineability_dbc rows", "; ".join(differences[:8]))
    finally:
        patchset.close()

    report_text = format_update_report(config, args.patches, plan, written, sql_path, server_files, result, warnings)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)
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
COMMANDS = ("build", "validate", "update", "schemas", "-h", "--help")


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
    p.add_argument("--dbc", required=True, help="stock DBCs (the server's data/dbc) for tables no patch holds")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--force", action="store_true", help="replace earlier output in --out")
    p.add_argument("--server-sql", help="an SQL file to compare (the bleakserv pending_db_world file): its DBC rows must match field for field")

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
        if args.command == "schemas":
            return cmd_schemas(args)
    except (configmod.ConfigError, ForgeError, DbcError, recparse.RecParseError, spellmod.SpellError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
