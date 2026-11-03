r"""raceforge.py find: which archive the client reads a file from, for every combination of the launcher's packs.

The game's files are the launcher's, read as skins reads them (skins.game_archives()): --client's Data folder with
--patches over it, in the client's order (the base archives of s_archives, patch.MPQ and patch-<locale>.MPQ, every
patch-?.MPQ and <locale>\patch-<locale>-?.MPQ above those, and alternate.MPQ above everything). For one file it tells,
for each combination of the optional packs, the archive whose copy the client reads (the highest that holds it) and
every archive that holds it, lowest first. With --grep it prints the lines of the copy the client reads that contain
the text, with --out it writes that copy to a file, and with --list it lists every file under a folder that the
archives' listfiles name, each with the archive it comes from.

The output is meant to be read on a phone: one short line per answer, archive names as they are in their folder.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import skins

patches = skins.patches
mpqpack = skins.mpqpack

MAX_LINES = 200
MAX_LINE_CHARS = 200
MAX_AFTER = 50
TEXT_PROBE = 8192


class FindError(Exception):
    pass


def archive_path(path: str) -> str:
    r"""A path as the archives name it: backslashes, no leading one (Interface/GlueXML/x.xml -> Interface\GlueXML\x.xml)."""
    name = re.sub(r"[\\/]+", r"\\", path.strip()).lstrip("\\")

    if not name:
        raise FindError("give a file path, for example Interface/GlueXML/CharacterCreate.xml")

    return name


def shell_hint(path: str) -> str | None:
    """A note when a path has lost its folders (a shell drops the backslashes of an unquoted path)."""
    if "\\" not in path and "/" not in path and re.match(r"(?i)(interface|dbfilesclient|character|fonts|sound)\w", path):
        return (f"{path} has no folder in it: a shell drops the backslashes of a path that is not in quotes. Write it "
                "with / (Interface/GlueXML/CharacterCreate.xml) or in single quotes.")

    return None


def where(archive: skins.GameArchive) -> str:
    """Patch-Y.MPQ (patches, hd pack); enUS/locale-enUS.MPQ (game)."""
    parts = ["patches" if archive.origin == "patches" else "game"]

    if archive.pack:
        parts.append(f"{archive.pack} pack")

    return f"{archive.rel} ({', '.join(parts)})"


def label_of(label: str, packs_on: frozenset) -> str:
    if label == "all packs" and packs_on:
        return f"all packs ({'+'.join(sorted(packs_on))})"

    return label


@dataclass
class Found:
    label: str
    packs_on: frozenset
    holders: list  # the archives holding the file in this combination, lowest first

    @property
    def winner(self) -> skins.GameArchive | None:
        return self.holders[-1] if self.holders else None


def open_game(client: str, patches_dir: str, packs: dict, locale: str | None) -> skins.Game:
    try:
        return skins.game_archives(client, patches_dir, packs, locale, alternate=True)
    except skins.SkinsError as e:
        raise FindError(str(e)) from None


def locate(game: skins.Game, name: str) -> list[Found]:
    return [Found(label_of(label, packs_on), packs_on, game.patchset.holders(name, packs_on))
            for label, packs_on in game.patchset.configurations()]


def by_winner(found: list[Found]) -> list[tuple[skins.GameArchive, list[str]]]:
    """Each copy the client reads in some combination, with those combinations, in the order of found."""
    out: dict[str, tuple[skins.GameArchive, list[str]]] = {}

    for f in found:
        if f.winner is not None:
            out.setdefault(f.winner.client_path.lower(), (f.winner, []))[1].append(f.label)

    return list(out.values())


LINE_END = re.compile(r"\r\n|\r|\n")


def text_lines(data: bytes) -> list[str] | None:
    """The lines of a text file, None for a binary one (a NUL byte, or many control bytes, near the start). Text that
    is not UTF-8 is read as Windows-1252, the code page such files are saved in. Lines end only where an editor, the
    client's Lua and its XML reader end them (CR LF, CR or LF; not at a form feed, NEL or U+2028, which
    str.splitlines also takes), so the line numbers are the editor's."""
    head = data[:TEXT_PROBE]

    if b"\0" in head or sum(1 for b in head if b < 32 and b not in (9, 10, 12, 13)) > len(head) // 20:
        return None

    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", "replace")

    lines = LINE_END.split(text)

    if lines and lines[-1] == "":
        lines.pop()  # the end of the last line, not a line of its own

    return lines


def shorten(line: str) -> str:
    line = line.strip()
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS - 3] + "..."


def grep(lines: list[str], texts: list[str], after: int = 0) -> tuple[list[str], int]:
    """The printed lines (`  35: match`; with after, `  36  following line` and `--` between blocks), at most
    MAX_LINES of them counting the `--`, and how many matching lines were left out."""
    wanted = [t.casefold() for t in texts if t]
    matches = [i for i, line in enumerate(lines) if any(t in line.casefold() for t in wanted)]
    show: dict[int, bool] = {}

    for i in matches:
        show[i] = True

        for j in range(i + 1, min(i + 1 + after, len(lines))):
            show.setdefault(j, False)

    out, last = [], None
    width = len(str(len(lines)))
    left_out = 0

    for i in sorted(show):
        separator = after > 0 and last is not None and i != last + 1

        if len(out) + separator + 1 > MAX_LINES:
            left_out = sum(1 for m in matches if m >= i)
            break

        if separator:
            out.append("--")

        out.append(f"{i + 1:>{width}}{':' if show[i] else ' '} {shorten(lines[i])}")
        last = i

    return out, left_out


def out_paths(out: str, name: str, copies: int) -> list[str]:
    """Where --out writes each distinct copy: the file given (or the file's name inside a folder given), then
    <name>-2<ext>, -3, ... for the copies of other pack combinations."""
    if os.path.isdir(out) or out.endswith(("/", "\\")):
        out = os.path.join(out, name.split("\\")[-1])

    stem, ext = os.path.splitext(out)
    return [out] + [f"{stem}-{n}{ext}" for n in range(2, copies + 1)]


def listed(game: skins.Game, folder: str) -> tuple[list[str], list[str]]:
    """Every file under folder that some archive's listfile names (and that archive holds), and the archives that
    have no listfile (their files cannot be listed)."""
    prefix = archive_path(folder).rstrip("\\") + "\\"
    names: dict[str, str] = {}
    unlisted = []

    for archive in game.archives:
        reader = archive.reader

        if reader is None:
            continue

        if not reader.has_file(mpqpack.LISTFILE):
            unlisted.append(where(archive))
            continue

        try:
            text = reader.read(mpqpack.LISTFILE)
        except mpqpack.MpqError:
            unlisted.append(where(archive))
            continue

        for raw in re.split(rb"[\r\n;]+", text):
            entry = re.sub(r"[\\/]+", r"\\", raw.decode("utf-8", "replace").strip()).lstrip("\\")
            key = entry.casefold()

            if key.startswith(prefix.casefold()) and key not in names and reader.has_file(entry):
                names[key] = entry

    return sorted(names.values(), key=str.casefold), unlisted


def run(args) -> int:
    """raceforge.py find. Prints its answers; returns the exit code (0: found)."""
    from . import config as configmod

    if not args.path and not args.list:
        raise FindError("give a file path (Interface/GlueXML/CharacterCreate.xml) or --list <folder>")

    if (args.grep or args.out) and not args.path:
        raise FindError("--grep and --out need a file path")

    if not 0 <= args.after <= MAX_AFTER:
        raise FindError(f"--after: 0 to {MAX_AFTER} lines")

    packs = configmod.load(args.config).archives.optional_packs
    game = open_game(args.client, args.patches, packs, args.locale)
    code = 0

    try:
        for archive in game.archives:
            if archive.reader is None:
                game.warnings.append(f"{where(archive)} {archive.error}: a file in it is not seen here")

        if args.path:
            code = max(code, find_file(game, args))

        if args.list:
            code = max(code, list_folder(game, args.list))
    finally:
        game.close()

    for warning in game.warnings:
        print(f"note: {warning}")

    return code


def find_file(game: skins.Game, args) -> int:
    hint = shell_hint(args.path)

    if hint:
        print(f"note: {hint}")

    name = archive_path(args.path)
    found = locate(game, name)
    print(name)

    if not any(f.holders for f in found):
        print("  not in any archive the client loads")
        return 1

    for f in found:
        if f.winner is None:
            print(f"  {f.label}: not in any archive the client loads")
            continue

        print(f"  {f.label}: from {where(f.winner)}")

        if len(f.holders) > 1:
            print(f"    in, lowest first: {', '.join(where(a) for a in f.holders)}")

    copies = by_winner(found)
    code = 0

    if args.grep:
        for archive, labels in copies:
            code = max(code, print_grep(archive, labels, name, args.grep, args.after))

    if args.out:
        for path, (archive, labels) in zip(out_paths(args.out, name, len(copies)), copies):
            try:
                data = archive.read(name)
            except patches.PatchError as e:
                print(f"cannot read {name} from {where(archive)}: {e}")
                code = 1
                continue

            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            with open(path, "wb") as fh:
                fh.write(data)

            print(f"written: {path} ({len(data)} bytes, from {archive.rel}, for {', '.join(labels)})")

    return code


def print_grep(archive: skins.GameArchive, labels: list[str], name: str, texts: list[str], after: int) -> int:
    quoted = " or ".join(f'"{t}"' for t in texts)

    try:
        data = archive.read(name)
    except patches.PatchError as e:
        print(f"cannot read {name} from {where(archive)}: {e}")
        return 1

    lines = text_lines(data)
    print()
    print(f"{quoted} in the copy of {archive.rel} ({', '.join(labels)}):")

    if lines is None:
        print("  not a text file")
        return 1

    out, left_out = grep(lines, texts, after)

    if not out:
        print("  no line has it")

    for line in out:
        print(f"  {line}")

    if left_out:
        print(f"  ... {left_out} more matching lines not shown (give a longer --grep text)")

    return 0


def list_folder(game: skins.Game, folder: str) -> int:
    hint = shell_hint(folder)

    if hint:
        print(f"note: {hint}")

    names, unlisted = listed(game, folder)
    prefix = archive_path(folder).rstrip("\\") + "\\"
    configurations = game.patchset.configurations()
    first_label = label_of(*configurations[0])
    print()

    if not names:
        print(f"{prefix}: no file there in any archive's listfile")
    else:
        rows = []
        realm = 0

        for name in names:
            winners = [(label_of(label, on), game.patchset.top(name, on)) for label, on in configurations]
            top = winners[0][1]
            mark = "*" if top is not None and top.origin == "patches" else " "
            realm += mark == "*"
            other = [f"{label}: {a.rel if a else 'none'}" for label, a in winners[1:]
                     if (a and a.client_path) != (top and top.client_path)]
            rows.append((mark, name[len(prefix):], top.rel if top else "none (only other packs have it)", other))

        print(f"{prefix} for {first_label}: {len(names)} files, {realm} from the patches folder (*)")
        width = min(max(len(r[1]) for r in rows), 40)

        for mark, short, top, other in rows:
            extra = f"   ({'; '.join(other)})" if other else ""
            print(f"{mark} {short:<{width}}  {top}{extra}")

    for archive in unlisted:
        print(f"note: {archive} has no listfile: its files are not listed (find them by name)")

    return 0 if names else 1
