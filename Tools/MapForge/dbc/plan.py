r"""Where each modified DBC must go so that every player's client reads it.

The final copy of a DBC is the one in the archive with the highest priority that holds it (patches.py has the
order). The realm already ships modified DBCs in its patches, and some of its patches are optional (the launcher's
packs), so one letter is not automatically safe: a map patch that holds DBFilesClient\Map.dbc is ignored the moment
any archive sorting after it also holds Map.dbc, and an archive in a pack only exists for the players who have the
pack on.

The plan, per DBC file and per pack combination, finds the archive whose copy wins today. Each such archive is a
target: it is rebuilt with our rows forged into its own copy of the file, so whatever that archive changed stays,
and players with and without a pack each keep the copy they load today, plus our rows. A combination where no realm
patch holds the file gets the copy in the map archive, whose letter only has to beat the locale archives with the
stock copy (every Data\patch-<letter>.MPQ does). The input DBC folder must hold the same bytes as each file's
winner with every pack on (package.py pull writes exactly that), and the plan checks it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import layout
from .config import PATCH_NAME
from .patches import PatchSet, outranks, sort_key


class PlanError(Exception):
    pass


@dataclass
class FilePlan:
    name: str  # table name
    archive_file: str  # DBFilesClient\<file>.dbc
    targets: list[str] = field(default_factory=list)  # archives to merge our copy into (names)
    in_map_archive: bool = False  # ships in the map archive for at least one pack combination
    winners: dict[str, str] = field(default_factory=dict)  # pack-combination label -> archive name or ""


@dataclass
class Plan:
    files: dict[str, FilePlan] = field(default_factory=dict)
    targets: list[str] = field(default_factory=list)  # all archives to rebuild, in patch order
    map_archive: str = ""
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def target_tables(self, archive_name: str) -> list[str]:
        return [f.name for f in self.files.values() if archive_name in f.targets]

    def map_archive_tables(self) -> list[str]:
        return [f.name for f in self.files.values() if f.in_map_archive]


def check_map_archive_name(map_archive: str, patchset: PatchSet, reserved_letters: str) -> list[str]:
    """Problems with the chosen map archive name against the realm's patch folder."""
    problems = []
    match = PATCH_NAME.fullmatch(map_archive)
    letter = match.group(1).upper()

    if letter in reserved_letters.upper():
        problems.append(f"{map_archive}: the letter {letter} is reserved ({reserved_letters})")

    existing = patchset.find(map_archive)

    if existing and existing.reader and not existing.reader.has_file("MapForge\\mapforge.txt"):
        problems.append(f"{map_archive} already exists in {patchset.folder} and was not written by MapForge; "
                        "choose another letter in archives.map")

    return problems


def plan(patchset: PatchSet, tables: list[str], map_archive: str, dbc_mode: str,
         merge_into: str | None) -> Plan:
    """The placement of each modified table. dbc_mode: "auto" (merge where a patch holds the file, the map archive
    otherwise), "map" (everything into the map archive; refused when that would lose), "merge" (everything into
    merge_into or each file's winning archive)."""
    out = Plan(map_archive=map_archive)
    configurations = patchset.configurations()

    for name in tables:
        archive_file = layout.archive_name(name)
        fp = FilePlan(name, archive_file)
        out.files[name] = fp
        ours = patchset.find(map_archive)

        for label, packs_on in configurations:
            top = patchset.top(archive_file, packs_on)

            if top is not None and ours is not None and top.name.lower() == ours.name.lower():
                # Our own earlier output; the winner below it decides the placement.
                holders = patchset.holders(archive_file, packs_on)
                top = holders[-2] if len(holders) > 1 else None

            fp.winners[label] = top.name if top else ""

        winner_names = {w for w in fp.winners.values() if w}

        if dbc_mode == "map":
            fp.in_map_archive = True
            losing = [w for w in winner_names
                      if not outranks(f"Data\\{map_archive}", [patchset.find(w)])]

            if losing:
                out.problems.append(f"{archive_file}: {', '.join(sorted(losing))} would load over {map_archive}; "
                                    "use \"dbc\": \"auto\" (merge) or a later letter")
            continue

        if merge_into and dbc_mode == "merge":
            target = patchset.find(merge_into)

            if target is None:
                out.problems.append(f"archives.merge_into: {merge_into} is not in {patchset.folder}")
                continue

            fp.targets = [target.name]
            above = [w for w in winner_names if sort_key(f"data\\{w}") > sort_key(f"data\\{merge_into}")]

            if above:
                out.problems.append(f"{archive_file}: {', '.join(sorted(above))} loads over {merge_into}, so the "
                                    "merged rows would lose; merge into the winning archive instead (\"auto\")")

            if any(not w for w in fp.winners.values()):
                target_archive = patchset.find(merge_into)

                if target_archive and target_archive.pack:
                    out.problems.append(f"{archive_file}: {merge_into} is in the optional pack "
                                        f"'{target_archive.pack}', and no other archive holds the file for players "
                                        "without the pack")
            continue

        # auto (and merge without merge_into): merge into each winning archive; the map archive covers the
        # combinations where nothing holds the file.
        for winner in sorted(winner_names):
            archive = patchset.find(winner)

            if archive.reader is None:
                out.problems.append(f"{archive_file}: {winner} holds the winning copy and {archive.error}")
                continue

            if winner not in fp.targets:
                fp.targets.append(winner)

        if any(not w for w in fp.winners.values()):
            fp.in_map_archive = True

    order = {a.name: i for i, a in enumerate(patchset.archives)}
    out.targets = sorted({t for f in out.files.values() for t in f.targets}, key=lambda n: order.get(n, 0))

    for name, fp in out.files.items():
        where = []

        if fp.in_map_archive:
            where.append(map_archive)

        where += fp.targets
        pretty = ", ".join(where) if where else "nowhere"
        out.notes.append(f"{fp.archive_file}: {pretty}" + ("" if len(set(fp.winners.values())) == 1 else
                                                           f" (winners by packs: {fp.winners})"))

    return out


def check_inputs_current(patchset: PatchSet, plan_: Plan, input_bytes: dict[str, bytes]) -> list[str]:
    """The --dbc folder must hold, for each table, the bytes of its winning copy with every pack on (otherwise the
    build would drop the realm's changes). Files no archive holds (stock-only) cannot be checked here."""
    problems = []
    all_on = frozenset({a.pack for a in patchset.archives if a.pack})

    for name, data in input_bytes.items():
        fp = plan_.files.get(name)

        if fp is None:
            continue

        top = patchset.top(fp.archive_file, all_on)

        if top is None or patchset.find(plan_.map_archive) is top:
            continue

        try:
            current = top.read(fp.archive_file)
        except Exception as e:  # noqa: BLE001 - reported, not raised
            problems.append(f"{fp.archive_file}: cannot read the winning copy in {top.name} ({e})")
            continue

        if current != data:
            problems.append(f"{fp.archive_file}: the input file differs from the winning copy in {top.name}; "
                            f"extract the input DBCs from the realm's patches (package.py pull), not from stock")

    return problems
