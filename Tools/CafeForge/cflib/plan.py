"""Where each café table must go so that every player's client reads the café's rows (section 6.4).

The rules are RaceForge's `update` and MapForge's `"dbc": "auto"` (Tools/MapForge/dbc/patches.py has the client's
archive order): for every table the café changes and for every combination of the launcher's optional packs, the
archive whose copy the client reads today is found, the café's rows are forged into that copy, and that archive is
rebuilt with everything else kept, so players with and without a pack each keep the copy they load today plus the
café's rows. A combination where no patch holds the table gets the stock copy (--dbc, the server's data/dbc) with the
rows, in the café's own patch-4.MPQ.

The loop is RaceForge update.make_plan's per-table winner loop, written for the café's four tables here rather than
factored out of RaceForge (its loop is interleaved with the racials' server rows, and its messages are tested word
for word). Everything it stands on is imported: PatchSet, outranks and pack_of (MapForge), read_table and
archive_file's rules (RaceForge), the DBC reader and the spell rows.

make_plan() never raises for what it finds: every refusal is collected in Plan.problems, so `doctor` can show them
all; `build` refuses a plan with problems.
"""

import functools
from dataclasses import dataclass, field

from . import config as cfgmod
from . import dbcrows, schemas

from rflib import update  # noqa: E402  (Tools/RaceForge)
from rflib.forge import find_dbc  # noqa: E402


@dataclass
class Source:
    """One copy of a table that some players read: the winning archive's (archive) or the stock one (None)."""
    table: str
    archive: object      # the winning archive's name, or None for the stock copy
    labels: list
    original: bytes
    forged: object       # the DbcTable after forge_rows
    result: object       # dbcrows.Forged
    max_id: int = 0

    @functools.cached_property
    def data(self):
        return self.forged.to_bytes()

    @property
    def changed(self):
        return bool(self.result.changed) and self.data != self.original

    def where(self):
        return self.archive or "no patch (stock)"

    def target(self, own):
        """The archive this copy goes into: its own archive, or the café's for the stock copy."""
        return self.archive or own


@dataclass
class Plan:
    configurations: list = field(default_factory=list)    # pack-combination labels, all packs on first
    sources: dict = field(default_factory=dict)            # table -> [Source]
    targets: dict = field(default_factory=dict)            # archive name -> {archive file: bytes}
    references: dict = field(default_factory=dict)         # table -> DbcTable, the copy every pack on reads
    reference_where: dict = field(default_factory=dict)    # table -> where that copy came from
    indices: dict = field(default_factory=dict)            # (column, wanted) -> dbcrows.Index
    rows: object = None                                    # dbcrows.Rows
    own: str = cfgmod.OWN_ARCHIVE                          # patch-4.MPQ as the patch folder spells it
    own_state: str = "new"                                 # new, the café's, or refused
    drops: set = field(default_factory=set)                # tables the café's archive holds and must lose
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    def line(self, source, done=False):
        """'all packs: Spell.dbc from Patch-R.MPQ -> Patch-R.MPQ (26 added)' or 'GameObjectDisplayInfo.dbc: no patch
        (stock) -> patch-4.MPQ (24 added)' (section 6.7): one copy of a table, without the label when that copy serves
        every combination. done False: what a build would do ('26 to add')."""
        prefix = "" if len(self.sources[source.table]) == 1 else "%s: " % ", ".join(source.labels)
        where = " from %s" % source.archive if source.archive else ": no patch (stock)"
        return "%s%s%s -> %s (%s)" % (prefix, schemas.file_name(source.table), where, source.target(self.own),
                                      source.result.summary(done))

    def table_lines(self, done=False):
        return [self.line(s, done) for sources in self.sources.values() for s in sources]


def read_reference(name, patchset, stock_dir, packs_on):
    """(table, where) of a reference table as the client reads it with packs_on (RaceForge update.read_table)."""
    try:
        return update.read_table(name, patchset, stock_dir, packs_on)
    except Exception as ex:  # noqa: BLE001 - a broken copy is reported, not raised
        return None, "unreadable (%s)" % ex


def own_problems(cfg, patchset):
    """(state, problems) of the café's own archive in the patch folder: new, the café's (an earlier CafeForge build),
    or refused (another tool's archive, or ModelForge's test patch)."""
    patches = update.patch_tools()
    existing = patchset.find(cfg.own)
    own_path = existing.client_path if existing is not None else "Data\\" + cfg.own
    problems = []
    pack = patches.pack_of(own_path, patchset.packs)
    if pack is not None:
        problems.append("%s is in the optional pack %s: the players without it would not load the café" % (cfg.own,
                                                                                                         pack))
    if existing is None:
        return "new", problems
    if existing.reader is None:
        return "refused", problems + ["%s: %s" % (existing.name, existing.error)]
    if not existing.has(cfgmod.MARKER_FILE):
        return "refused", problems + ["%s is in %s but was not written by CafeForge (no %s): it is another patch's "
                                      "name; nothing of it may be replaced" % (existing.name, patchset.folder,
                                                                               cfgmod.MARKER_FILE)]
    try:
        marker = existing.read(cfgmod.MARKER_FILE).decode("utf-8", "replace")
    except Exception as ex:  # noqa: BLE001
        return "refused", problems + ["%s: its %s cannot be read (%s)" % (existing.name, cfgmod.MARKER_FILE, ex)]
    if marker.strip().lower() == "test":
        return "refused", problems + ["%s is ModelForge's test patch (testpatch): it belongs in one Windows client "
                                      "only; take it out of %s" % (existing.name, patchset.folder)]
    return "the café's", problems


def collisions(cfg, patchset):
    """Archives other than the café's that hold café paths (MapForge package.py collisions(): new paths must be
    new): a later copy would hide the café's, an earlier one would be hidden."""
    problems = []
    for archive in patchset.archives:
        if archive.name.lower() == cfg.own.lower() or archive.reader is None:
            continue
        names = [n for n in archive.reader.names() if cfgmod.is_cafe_path(n)]
        if names:
            problems.append("%s already holds café paths (%s%s); only %s may" % (
                archive.name, ", ".join(names[:3]), ", ..." if len(names) > 3 else "", cfg.own))
    return problems


def make_plan(cfg, patchset, stock_dir, bounds=None):
    """The plan for every café table. bounds: ModelForge's {display: (min, max)} (None: identity only)."""
    plan = Plan()
    patches = update.patch_tools()
    configurations = patchset.configurations()
    plan.configurations = [label for label, _ in configurations]
    existing = patchset.find(cfg.own)
    plan.own = existing.name if existing is not None else cfg.own
    own_path = existing.client_path if existing is not None else "Data\\" + cfg.own
    plan.own_state, problems = own_problems(cfg, patchset)
    plan.problems += problems
    plan.problems += ["cannot read %s: %s" % (a.name, a.error) for a in patchset.unreadable()]
    plan.problems += collisions(cfg, patchset)

    # The spells' cast times, durations and range: resolved from the copies every pack on reads, the same rows in
    # every other combination.
    per_label = {}
    for label, packs_on in configurations:
        tables = {}
        for name in cfgmod.REFERENCE_TABLES:
            table, where = read_reference(name, patchset, stock_dir, packs_on)
            if table is not None:
                tables[name] = table
            if label == configurations[0][0]:
                plan.reference_where[name] = where or "nowhere (in no patch and not in --dbc)"
                if table is None and where:
                    plan.problems.append("%s.dbc: %s" % (name, where))
        per_label[label] = tables
    plan.references = per_label[configurations[0][0]]
    plan.indices, unresolved = dbcrows.resolve_indices(cfg, plan.references)
    plan.problems += unresolved
    for label, tables in per_label.items():
        if label != configurations[0][0]:
            plan.problems += dbcrows.index_problems(plan.indices, tables, label)
    plan.warnings += ["%s: %s" % (i.key_name(), i.text()) for i in plan.indices.values() if not i.exact]
    plan.problems += visual_problems(cfg, plan.references.get("SpellVisual"), plan)

    try:
        defs = dbcrows.spell_defs(cfg, plan.indices) if not unresolved else None
    except dbcrows.RowError as ex:
        plan.problems.append(str(ex))
        defs = None
    plan.rows = dbcrows.Rows(cfg, defs or {}, bounds)

    for name in cfgmod.TABLES:
        if name == "Spell" and defs is None:
            continue
        plan_table(plan, name, cfg, patchset, stock_dir, configurations, own_path, patches)
    return plan


def visual_problems(cfg, visuals, plan):
    """Every café spell's SpellVisual must be a row of the copy the players read (0 is none)."""
    wanted = sorted({s.data.get("visual") or 0 for s in cfg.spells} - {0})
    if visuals is None:
        plan.warnings.append("SpellVisual.dbc is in no patch and not in --dbc: visuals %s not checked" % wanted)
        return []
    missing = [v for v in wanted if v not in visuals.ids()]
    return ["SpellVisual.dbc (%s) has no visual %s" % (plan.reference_where.get("SpellVisual"), v) for v in missing]


def plan_table(plan, name, cfg, patchset, stock_dir, configurations, own_path, patches):
    archive_file = schemas.archive_file(name)
    by_winner, winners = {}, {}
    for label, packs_on in configurations:
        holders = patchset.holders(archive_file, packs_on)
        top = holders[-1] if holders else None
        if top is not None and top.name.lower() == plan.own.lower() and len(holders) > 1:
            # The café's earlier copy (a stock copy, from a build when no patch held the table) loads over a realm
            # archive's: the realm's copy decides, and the café's goes (it would hide the realm's later changes).
            top = holders[-2]
            plan.drops.add(archive_file)
        by_winner.setdefault(top.name if top else None, []).append(label)
        if top is not None:
            winners[top.name] = top

    stock = [w for w in by_winner if w is None or w.lower() == plan.own.lower()]
    if stock:
        # Only pack archives hold the file: its stock copy goes into the café's archive, which every player must
        # load, and which must not load over a pack archive's copy (it cannot: a digit sorts below every letter).
        labels = ", ".join(label for w in stock for label in by_winner[w])
        own_pack = patches.pack_of(own_path, patchset.packs)
        if own_pack is not None:
            plan.problems.append("no patch holds %s for %s, so its stock copy with the café's rows would go into %s, "
                                 "which is in the optional pack %s" % (archive_file, labels, plan.own, own_pack))
        hidden = sorted(w for w, archive in winners.items()
                        if w.lower() != plan.own.lower() and patches.outranks(own_path, [archive]))
        if hidden:
            plan.problems.append("no patch holds %s for %s, so its stock copy with the café's rows would go into %s, "
                                 "which loads over %s: the players with that pack would lose its copy"
                                 % (archive_file, labels, plan.own, ", ".join(hidden)))

    sources = []
    for winner, labels in by_winner.items():
        if winner is None:
            path = find_dbc(stock_dir, name) if stock_dir else None
            if path is None:
                plan.problems.append("no patch holds %s for %s, and --dbc has no %s to start from"
                                     % (archive_file, ", ".join(labels), schemas.file_name(name)))
                continue
            with open(path, "rb") as f:
                original = f.read()
        else:
            try:
                original = patchset.find(winner).read(archive_file)
            except Exception as ex:  # noqa: BLE001 - MapForge's PatchError: reported, not raised
                plan.problems.append(str(ex))
                continue
        try:
            table = dbcrows.table_from(original, name, "%s: %s" % (winner or "stock", name))
        except dbcrows.RowError as ex:
            plan.problems.append(str(ex))
            continue
        max_id = table.max_id()
        result = dbcrows.forge_rows(name, table, plan.rows)
        plan.problems += ["%s (%s): %s" % (winner or "stock", ", ".join(labels), p) for p in result.problems]
        sources.append(Source(name, winner, labels, original, table, result, max_id))
    plan.sources[name] = sources

    for source in sources:
        if not source.changed or source.result.problems:
            continue
        target = source.target(plan.own)
        files = plan.targets.setdefault(target, {})
        if archive_file in files and files[archive_file] != source.data:
            plan.problems.append("%s would need two different copies of %s" % (target, archive_file))
            continue
        files[archive_file] = source.data
