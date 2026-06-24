#!/usr/bin/env python3
"""
Import the `counter` column from marvel_rivals_hero_abilities_counters.csv into
`hero_notes.<HERO>.<ABILITY>.counter_abilities` in counters-notes.json.

Each CSV counter cell is comma-separated entries like:
  Captain America - Living Legend, Scarlet Witch - Dark Seal

Optional per-entry image choice (suffix before the comma), case-insensitive:
  Captain America - Living Legend @hero     -> show counter hero portrait in the UI
  Scarlet Witch - Dark Seal @ability       -> show ability icon (same as default)

Each entry is split on the first \" - \" into counter hero + ability name (after stripping
the suffix). Icons and descriptions are resolved from the same CSV by matching
(hero, ability_name) with case-insensitive keys. Rows in counters-notes.json are matched
to CSV rows the same way, so hero/ability casing can differ between the spreadsheet and JSON.
Hero portraits come from abilities-data.json.

Each counter_abilities item is stored as:

  {
    \"hero\": \"Captain America\",
    \"ability_name\": \"Living Legend\",
    \"ability_icon\": \"https://...\",
    \"hero_icon\": \"https://...\",
    \"ability_description\": \"...\",
    \"display_icon\": \"ability\"
  }

display_icon is \"ability\" or \"hero\". Entries without @hero/@ability use --default-display-icon.

Paths default to this repo layout (counters/ next to counters-notes.json at project root).

Usage:
  python counters/import_counter_abilities_from_csv.py
  python counters/import_counter_abilities_from_csv.py --dry-run
  python counters/import_counter_abilities_from_csv.py --dry-run --verbose-missing
  python counters/import_counter_abilities_from_csv.py --default-display-icon hero
  python counters/import_counter_abilities_from_csv.py --csv path/to.csv --json path/to.json

--dry-run: parse and print the summary line; does not write counters-notes.json.
--verbose-missing: log missing lookups, bad counter delimiters, and spreadsheet
  issues in the new columns (preferred heroes, synergy, role picks).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def default_paths(project_root: Path) -> tuple[Path, Path, Path]:
    return (
        project_root / "counters" / "marvel_rivals_hero_abilities_counters.csv",
        project_root / "counters-notes.json",
        project_root / "abilities-data.json",
    )


_DISPLAY_SUFFIX = re.compile(r"\s*@(hero|ability)\s*$", re.IGNORECASE)
_COUNTER_DELIMITER = re.compile(r"\s*[–—]\s*")

PREFERRED_HEROES_COL = "Counters (prefered Heros)"
PREFERRED_SYNERGY_COL = "Prefered synergy "
ROLE_STRATEGIST_COL = "Strategist"
ROLE_DUELIST_COL = "Duelist"
ROLE_VANGUARD_COL = "Vanguard"
PLAYSTYLE_DIVE_COL = "Dive"
PLAYSTYLE_POKE_COL = "Poke"
PLAYSTYLE_BRAWL_COL = "Brawl"

HERO_LIST_COLUMNS = (PREFERRED_HEROES_COL, PREFERRED_SYNERGY_COL)
ROLE_COLUMNS = (ROLE_STRATEGIST_COL, ROLE_DUELIST_COL, ROLE_VANGUARD_COL)
PLAYSTYLE_COLUMNS = (PLAYSTYLE_DIVE_COL, PLAYSTYLE_POKE_COL, PLAYSTYLE_BRAWL_COL)
SINGLE_HERO_COLUMNS = ROLE_COLUMNS + PLAYSTYLE_COLUMNS
SPREADSHEET_HERO_COLUMNS = HERO_LIST_COLUMNS + SINGLE_HERO_COLUMNS

# Common shorthand typos seen in the sheet; used for suggestions only.
HERO_NAME_ALIASES: dict[str, str] = {
    "PUNISHER": "THE PUNISHER",
    "STARLORD": "STAR-LORD",
    "STAR LORD": "STAR-LORD",
    "JEFF THE LANDSHARK": "JEFF THE LAND SHARK",
    "SPIDERMAN": "SPIDER-MAN",
    "SPIDER MAN": "SPIDER-MAN",
    "MOONKNIGHT": "MOON KNIGHT",
    "IRONMAN": "IRON MAN",
    "CAPTAINAMERICA": "CAPTAIN AMERICA",
    "DOCTORSTRANGE": "DOCTOR STRANGE",
    "WINTERSOLDIER": "WINTER SOLDIER",
    "BLACKWIDOW": "BLACK WIDOW",
    "BLACKPANTHER": "BLACK PANTHER",
    "SCARLETWITCH": "SCARLET WITCH",
    "MISTERFANTASTIC": "MISTER FANTASTIC",
    "INVISIBLEWOMAN": "INVISIBLE WOMAN",
    "HUMANTORCH": "HUMAN TORCH",
    "ROCKETRACCOON": "ROCKET RACCOON",
    "ELSABLOODSTONE": "ELSA BLOODSTONE",
    "WHITEFOX": "WHITE FOX",
    "EMMAFROST": "EMMA FROST",
    "LUNASNOW": "LUNA SNOW",
    "PENIPARKER": "PENI PARKER",
    "SQUIRRELGIRL": "SQUIRREL GIRL",
    "ADAMWARLOCK": "ADAM WARLOCK",
    "DEVILDINOSAUR": "DEVIL DINOSAUR",
}


@dataclass(frozen=True)
class CsvValidationIssue:
    row: int
    column: str
    issue: str
    detail: str
    owner_hero: str = ""
    owner_ability: str = ""


def format_validation_issue(issue: CsvValidationIssue) -> str:
    owner = f"{issue.owner_hero} / {issue.owner_ability}  -->  " if issue.owner_hero else ""
    return f"line {issue.row} | {issue.column} | {issue.issue}: {owner}{issue.detail}"


def normalize_counter_delimiter(text: str) -> str:
    """Spreadsheet apps often replace hyphen separators with en/em dashes."""
    return _COUNTER_DELIMITER.sub(" - ", text or "")


def resolve_hero_name(name: str, canonical_hero_map: dict[str, str]) -> str | None:
    """Return canonical hero name if known, else None."""
    key = norm_hero(name)
    if not key or key == "WORK IN PROGRESS":
        return None
    if key in canonical_hero_map:
        return canonical_hero_map[key]
    alias = HERO_NAME_ALIASES.get(key)
    if alias and norm_hero(alias) in canonical_hero_map:
        return canonical_hero_map[norm_hero(alias)]
    return None


def suggest_hero_name(name: str, canonical_hero_map: dict[str, str]) -> str | None:
    resolved = resolve_hero_name(name, canonical_hero_map)
    if resolved:
        return resolved
    key = norm_hero(name)
    if not key:
        return None
    alias = HERO_NAME_ALIASES.get(key)
    if alias:
        return alias
    matches = [
        display
        for norm_key, display in canonical_hero_map.items()
        if key in norm_key or norm_key in key
    ]
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    return None


def split_hero_list_cell(cell: str) -> tuple[list[str], list[str]]:
    """
    Split a comma-separated hero list.
    Returns (hero_names, structural_issues).
    """
    text = (cell or "").strip()
    if not text:
        return [], []
    issues: list[str] = []
    parts = text.split(",")
    names: list[str] = []
    for index, part in enumerate(parts):
        piece = part.strip()
        if not piece:
            if index < len(parts) - 1:
                issues.append("empty_segment")
            continue
        names.append(piece)
    return names, issues


def validate_hero_reference(
    name: str,
    canonical_hero_map: dict[str, str],
) -> str | None:
    """Return an error message if the hero name is unknown or a known alias typo."""
    if not name or norm_hero(name) == "WORK IN PROGRESS":
        return None
    key = norm_hero(name)
    if key in canonical_hero_map:
        return None
    alias = HERO_NAME_ALIASES.get(key)
    if alias:
        canonical = canonical_hero_map.get(norm_hero(alias))
        if canonical:
            return f"hero {name!r} should be spelled {canonical!r}"
    suggestion = suggest_hero_name(name, canonical_hero_map)
    if suggestion:
        return f"unknown hero {name!r} (did you mean {suggestion!r}?)"
    return f"unknown hero {name!r}"


def validate_hero_list_cell_structure(cell: str) -> list[tuple[str, str]]:
    """Return structural issue codes and details for a hero list cell."""
    text = (cell or "").strip()
    if not text:
        return []
    issues: list[tuple[str, str]] = []
    if re.search(r",[^\s,]", text):
        issues.append(
            (
                "comma_spacing",
                f"add a space after each comma in {text[:80]!r}",
            )
        )
    parts = text.split(",")
    for index, part in enumerate(parts):
        if not part.strip() and index < len(parts) - 1:
            issues.append(
                ("empty_segment", f"empty name between commas in {text[:80]!r}")
            )
    return issues


def validate_spreadsheet_columns(
    csv_path: Path,
    canonical_hero_map: dict[str, str],
) -> list[CsvValidationIssue]:
    """Validate preferred/synergy/role/playstyle columns for typos and comma issues."""
    issues: list[CsvValidationIssue] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for col in SPREADSHEET_HERO_COLUMNS:
            if col not in fieldnames:
                issues.append(
                    CsvValidationIssue(
                        row=1,
                        column=col,
                        issue="missing_column",
                        detail=f"expected CSV header {col!r}",
                    )
                )
        if issues:
            return issues

        for row_num, row in enumerate(reader, start=2):
            owner_hero = (row.get("hero") or "").strip()
            owner_ability = (row.get("ability_name") or "").strip()

            for col in HERO_LIST_COLUMNS:
                cell = row.get(col) or ""
                names, _ = split_hero_list_cell(cell)
                for code, detail in validate_hero_list_cell_structure(cell):
                    issues.append(
                        CsvValidationIssue(
                            row=row_num,
                            column=col,
                            issue=code,
                            detail=detail,
                            owner_hero=owner_hero,
                            owner_ability=owner_ability,
                        )
                    )
                for name in names:
                    err = validate_hero_reference(name, canonical_hero_map)
                    if err:
                        issues.append(
                            CsvValidationIssue(
                                row=row_num,
                                column=col,
                                issue="unknown_hero",
                                detail=err,
                                owner_hero=owner_hero,
                                owner_ability=owner_ability,
                            )
                        )

            for col in SINGLE_HERO_COLUMNS:
                cell = (row.get(col) or "").strip()
                if not cell:
                    continue
                if "," in cell:
                    issues.append(
                        CsvValidationIssue(
                            row=row_num,
                            column=col,
                            issue="multiple_values",
                            detail=f"column should contain one hero, got {cell!r}",
                            owner_hero=owner_hero,
                            owner_ability=owner_ability,
                        )
                    )
                    continue
                err = validate_hero_reference(cell, canonical_hero_map)
                if err:
                    issues.append(
                        CsvValidationIssue(
                            row=row_num,
                            column=col,
                            issue="unknown_hero",
                            detail=err,
                            owner_hero=owner_hero,
                            owner_ability=owner_ability,
                        )
                    )
    return issues


def normalize_display_icon(value: str) -> str:
    return "hero" if (value or "").strip().lower() == "hero" else "ability"


def norm_hero(s: str) -> str:
    return (s or "").strip().upper()


def norm_ability(s: str) -> str:
    return (s or "").strip().upper()


def norm_key(hero: str, ability: str) -> tuple[str, str]:
    return (norm_hero(hero), norm_ability(ability))


def parse_counter_cell(cell: str, default_display_icon: str) -> list[dict[str, str]]:
    """Turn a CSV counter string into counter_ability dicts (hero, ability_name, display_icon)."""
    default_d = normalize_display_icon(default_display_icon)
    if not cell or not str(cell).strip():
        return []
    out: list[dict[str, str]] = []
    for part in str(cell).split(","):
        piece = part.strip()
        if not piece:
            continue
        display_d = default_d
        m = _DISPLAY_SUFFIX.search(piece)
        if m:
            display_d = normalize_display_icon(m.group(1))
            piece = piece[: m.start()].strip()
        piece = normalize_counter_delimiter(piece)
        if " - " not in piece:
            out.append({"hero": piece, "ability_name": "", "display_icon": display_d})
            continue
        h, a = piece.split(" - ", 1)
        out.append({"hero": h.strip(), "ability_name": a.strip(), "display_icon": display_d})
    return out


def validate_counter_cells(
    csv_path: Path,
    canonical_hero_map: dict[str, str],
    default_display_icon: str,
) -> list[CsvValidationIssue]:
    """Validate counter column formatting (delimiters, hero names)."""
    issues: list[CsvValidationIssue] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            owner_hero = (row.get("hero") or "").strip()
            owner_ability = (row.get("ability_name") or "").strip()
            cell = (row.get("counter") or "").strip()
            if not cell:
                continue
            if _COUNTER_DELIMITER.search(cell):
                issues.append(
                    CsvValidationIssue(
                        row=row_num,
                        column="counter",
                        issue="bad_delimiter",
                        detail="use ' - ' (hyphen) instead of en/em dash between hero and ability",
                        owner_hero=owner_hero,
                        owner_ability=owner_ability,
                    )
                )
            normalized = normalize_counter_delimiter(cell)
            for entry in parse_counter_cell(normalized, default_display_icon):
                hero = entry.get("hero") or ""
                ability = entry.get("ability_name") or ""
                if hero and not ability:
                    issues.append(
                        CsvValidationIssue(
                            row=row_num,
                            column="counter",
                            issue="missing_ability",
                            detail=f"counter entry {hero!r} is missing ' - ability' suffix",
                            owner_hero=owner_hero,
                            owner_ability=owner_ability,
                        )
                    )
                if hero:
                    err = validate_hero_reference(hero, canonical_hero_map)
                    if err:
                        issues.append(
                            CsvValidationIssue(
                                row=row_num,
                                column="counter",
                                issue="unknown_hero",
                                detail=err,
                                owner_hero=owner_hero,
                                owner_ability=owner_ability,
                            )
                        )
    return issues


def print_validation_report(issues: list[CsvValidationIssue]) -> None:
    if not issues:
        return
    grouped: dict[str, list[CsvValidationIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.issue, []).append(issue)
    order = (
        "missing_column",
        "comma_spacing",
        "empty_segment",
        "multiple_values",
        "bad_delimiter",
        "missing_ability",
        "unknown_hero",
    )
    for kind in order:
        bucket = grouped.get(kind)
        if not bucket:
            continue
        title = kind.replace("_", " ").title()
        print(f"\n=== Spreadsheet {title} ({len(bucket)}) ===", file=sys.stderr)
        for issue in sorted(bucket, key=lambda i: (i.row, i.column, i.detail)):
            print(format_validation_issue(issue), file=sys.stderr)


def build_ability_meta_map(csv_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """
    (norm_hero, norm_ability) -> {ability_icon, ability_description}.
    Last CSV row wins for duplicate keys.
    """
    required = {"hero", "ability_name", "ability_icon", "ability_description"}
    meta: dict[tuple[str, str], dict[str, str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise SystemExit(f"CSV missing columns: {sorted(missing)}")
        for row in reader:
            hero = (row.get("hero") or "").strip()
            ability = (row.get("ability_name") or "").strip()
            if not hero or not ability:
                continue
            key = (norm_hero(hero), norm_ability(ability))
            meta[key] = {
                "ability_icon": (row.get("ability_icon") or "").strip(),
                "ability_description": (row.get("ability_description") or "").strip(),
            }
    return meta


def parse_preferred_heroes_cell(cell: str) -> list[str]:
    """Turn a CSV preferred-heroes string into ordered unique hero names."""
    names, _ = split_hero_list_cell(cell)
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = norm_hero(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def build_preferred_heroes_map(csv_path: Path) -> dict[str, list[str]]:
    """norm_hero -> ordered unique preferred counter hero names from CSV."""
    result: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or PREFERRED_HEROES_COL not in reader.fieldnames:
            return result
        for row in reader:
            hero = (row.get("hero") or "").strip()
            prefs = parse_preferred_heroes_cell(row.get(PREFERRED_HEROES_COL) or "")
            if not hero or not prefs:
                continue
            owner_key = norm_hero(hero)
            if owner_key not in result:
                result[owner_key] = []
                seen[owner_key] = set()
            for pref in prefs:
                pref_key = norm_hero(pref)
                if pref_key in seen[owner_key]:
                    continue
                seen[owner_key].add(pref_key)
                result[owner_key].append(pref)
    return result


def _append_playstyle_cell(
    result: dict[str, dict[str, list[str]]],
    seen: dict[str, dict[str, set[str]]],
    owner_key: str,
    style_key: str,
    cell: str,
) -> None:
    names = parse_preferred_heroes_cell(cell)
    if not names:
        return
    if owner_key not in result:
        result[owner_key] = {"dive": [], "poke": [], "brawl": []}
        seen[owner_key] = {"dive": set(), "poke": set(), "brawl": set()}
    for name in names:
        pref_key = norm_hero(name)
        if pref_key in seen[owner_key][style_key]:
            continue
        seen[owner_key][style_key].add(pref_key)
        result[owner_key][style_key].append(name)


def build_playstyle_heroes_map(csv_path: Path) -> dict[str, dict[str, list[str]]]:
    """norm_hero -> {dive|poke|brawl} -> ordered unique counter hero names from CSV."""
    result: dict[str, dict[str, list[str]]] = {}
    seen: dict[str, dict[str, set[str]]] = {}
    style_cols = (
        ("dive", PLAYSTYLE_DIVE_COL),
        ("poke", PLAYSTYLE_POKE_COL),
        ("brawl", PLAYSTYLE_BRAWL_COL),
    )
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return result
        for row in reader:
            hero = (row.get("hero") or "").strip()
            if not hero:
                continue
            owner_key = norm_hero(hero)
            for style_key, col in style_cols:
                if col not in (reader.fieldnames or []):
                    continue
                _append_playstyle_cell(
                    result,
                    seen,
                    owner_key,
                    style_key,
                    row.get(col) or "",
                )
    return result


def build_canonical_hero_map(abilities_path: Path) -> dict[str, str]:
    """norm_hero -> canonical hero name from abilities-data.json."""
    data = json.loads(abilities_path.read_text(encoding="utf-8"))
    return {
        norm_hero(h.get("hero") or ""): (h.get("hero") or "").strip()
        for h in data.get("heroes") or []
        if isinstance(h, dict) and (h.get("hero") or "").strip()
    }


def apply_preferred_heroes(
    data: dict,
    preferred_map: dict[str, list[str]],
    hero_icon_map: dict[str, str],
    canonical_hero_map: dict[str, str],
    hero_notes: dict,
) -> int:
    """Store data['preferred_counter_heroes'][owner] = [{hero, hero_icon}, ...]."""
    owner_canonical = {norm_hero(h): h for h in hero_notes if isinstance(hero_notes.get(h), dict)}
    out: dict[str, list[dict[str, str]]] = {}
    for owner_key, pref_names in preferred_map.items():
        owner_name = owner_canonical.get(owner_key)
        if not owner_name:
            continue
        entries: list[dict[str, str]] = []
        for pref in pref_names:
            resolved = resolve_hero_name(pref, canonical_hero_map)
            pref_key = norm_hero(resolved or pref)
            canonical = canonical_hero_map.get(pref_key, (resolved or pref).strip())
            entries.append(
                {
                    "hero": canonical,
                    "hero_icon": hero_icon_map.get(pref_key, ""),
                }
            )
        out[owner_name] = entries
    data["preferred_counter_heroes"] = out
    return len(out)


def apply_playstyle_heroes(
    data: dict,
    playstyle_map: dict[str, dict[str, list[str]]],
    hero_icon_map: dict[str, str],
    canonical_hero_map: dict[str, str],
    hero_notes: dict,
) -> int:
    """Store data['playstyle_counter_heroes'][owner][style] = [{hero, hero_icon}, ...]."""
    owner_canonical = {norm_hero(h): h for h in hero_notes if isinstance(hero_notes.get(h), dict)}
    out: dict[str, dict[str, list[dict[str, str]]]] = {}
    for owner_key, styles in playstyle_map.items():
        owner_name = owner_canonical.get(owner_key)
        if not owner_name:
            continue
        style_out: dict[str, list[dict[str, str]]] = {}
        for style_key in ("dive", "poke", "brawl"):
            entries: list[dict[str, str]] = []
            for pref in styles.get(style_key) or []:
                resolved = resolve_hero_name(pref, canonical_hero_map)
                pref_key = norm_hero(resolved or pref)
                canonical = canonical_hero_map.get(pref_key, (resolved or pref).strip())
                entries.append(
                    {
                        "hero": canonical,
                        "hero_icon": hero_icon_map.get(pref_key, ""),
                    }
                )
            style_out[style_key] = entries
        out[owner_name] = style_out
    data["playstyle_counter_heroes"] = out
    return len(out)


def build_counter_map(csv_path: Path) -> dict[tuple[str, str], str]:
    """(norm_hero, norm_ability) -> last counter string in file order (may be empty)."""
    last: dict[tuple[str, str], str] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"hero", "ability_name", "counter"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise SystemExit(f"CSV missing columns: {sorted(missing)}")
        for row in reader:
            hero = (row.get("hero") or "").strip()
            ability = (row.get("ability_name") or "").strip()
            counter = (row.get("counter") or "").strip()
            if not hero or not ability:
                continue
            last[norm_key(hero, ability)] = counter
    return last


def build_hero_icon_map(abilities_path: Path) -> dict[str, str]:
    """norm_hero -> hero_icon URL from abilities-data.json."""
    if not abilities_path.is_file():
        raise SystemExit(f"abilities-data.json not found (need hero portraits): {abilities_path}")
    data = json.loads(abilities_path.read_text(encoding="utf-8"))
    m: dict[str, str] = {}
    for h in data.get("heroes") or []:
        if not isinstance(h, dict):
            continue
        hero = (h.get("hero") or "").strip()
        icon = (h.get("hero_icon") or "").strip()
        if hero:
            m[norm_hero(hero)] = icon
    return m


def enrich_counter_entries(
    parsed: list[dict[str, str]],
    ability_meta: dict[tuple[str, str], dict[str, str]],
    hero_icon_map: dict[str, str],
    *,
    owner_hero: str = "",
    owner_ability: str = "",
    missing_ability_log: list[str] | None = None,
    missing_hero_icon_log: list[str] | None = None,
) -> tuple[list[dict[str, str]], int, int]:
    """
    Attach ability_icon, ability_description, hero_icon, display_icon.
    Returns (list, missing_ability_meta_count, missing_hero_icon_count).
    """
    missing_ability = 0
    missing_hero_icon = 0
    out: list[dict[str, str]] = []
    for entry in parsed:
        hero = entry.get("hero") or ""
        ability_name = entry.get("ability_name") or ""
        display_icon = normalize_display_icon(entry.get("display_icon") or "ability")
        key = (norm_hero(hero), norm_ability(ability_name))
        raw = ability_meta.get(key)
        hit = raw or {}
        icon = hit.get("ability_icon") or ""
        desc = hit.get("ability_description") or ""
        if hero and ability_name and raw is None:
            missing_ability += 1
            if missing_ability_log is not None:
                missing_ability_log.append(
                    f"{owner_hero} / {owner_ability}  -->  counter pick missing CSV row: "
                    f"{hero!r} / {ability_name!r}"
                )
        hero_icon = hero_icon_map.get(norm_hero(hero), "") if hero else ""
        if hero and not hero_icon:
            missing_hero_icon += 1
            if missing_hero_icon_log is not None:
                missing_hero_icon_log.append(
                    f"{owner_hero} / {owner_ability}  -->  no hero_icon for counter hero: {hero!r}"
                )
        out.append(
            {
                "hero": hero,
                "ability_name": ability_name,
                "ability_icon": icon,
                "hero_icon": hero_icon,
                "ability_description": desc,
                "display_icon": display_icon,
            }
        )
    return out, missing_ability, missing_hero_icon


def apply_counters(
    data: dict,
    counter_map: dict[tuple[str, str], str],
    ability_meta: dict[tuple[str, str], dict[str, str]],
    hero_icon_map: dict[str, str],
    default_display_icon: str,
    *,
    missing_ability_log: list[str] | None = None,
    missing_hero_icon_log: list[str] | None = None,
) -> tuple[int, int, int, int, list[tuple[str, str, str]]]:
    """
    Mutate data['hero_notes'][hero][ability]['counter_abilities'].
    Returns (updated_non_empty, cleared, missing_ability_meta, missing_hero_icon, warnings).
    """
    warnings: list[tuple[str, str, str]] = []
    updated = 0
    cleared = 0
    missing_meta_total = 0
    missing_hero_icon_total = 0
    hero_notes = data.get("hero_notes")
    if not isinstance(hero_notes, dict):
        raise SystemExit("JSON root must contain object 'hero_notes'")

    for hero, abilities in hero_notes.items():
        if not isinstance(abilities, dict):
            continue
        for ability_name, block in abilities.items():
            if not isinstance(block, dict):
                continue
            key = norm_key(hero, ability_name)
            if key not in counter_map:
                warnings.append((hero, ability_name, "no CSV row for this key"))
                continue
            cell = counter_map.get(key, "")
            parsed = parse_counter_cell(cell, default_display_icon)
            new_list, miss_a, miss_h = enrich_counter_entries(
                parsed,
                ability_meta,
                hero_icon_map,
                owner_hero=hero,
                owner_ability=ability_name,
                missing_ability_log=missing_ability_log,
                missing_hero_icon_log=missing_hero_icon_log,
            )
            missing_meta_total += miss_a
            missing_hero_icon_total += miss_h
            old = block.get("counter_abilities")
            if old != new_list:
                block["counter_abilities"] = new_list
                if new_list:
                    updated += 1
                else:
                    cleared += 1
    return updated, cleared, missing_meta_total, missing_hero_icon_total, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (parent of counters/ and counters-notes.json)",
    )
    parser.add_argument("--csv", type=Path, help="Override counters CSV path")
    parser.add_argument("--json", type=Path, help="Override counters-notes.json path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report counts without writing counters-notes.json",
    )
    parser.add_argument(
        "--verbose-missing",
        action="store_true",
        help="Log missing lookups and spreadsheet validation issues (stderr)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when spreadsheet validation issues are found",
    )
    parser.add_argument(
        "--abilities-json",
        type=Path,
        help="Path to abilities-data.json (default: <project-root>/abilities-data.json)",
    )
    parser.add_argument(
        "--default-display-icon",
        choices=("ability", "hero"),
        default="ability",
        help='Default image for counters without @hero/@ability suffix (default: "ability")',
    )
    args = parser.parse_args()
    csv_path, json_path, abilities_default = default_paths(args.project_root)
    csv_path = args.csv or csv_path
    json_path = args.json or json_path
    abilities_path = args.abilities_json or abilities_default

    if not csv_path.is_file():
        sys.exit(f"CSV not found: {csv_path}")
    if not json_path.is_file():
        sys.exit(f"JSON not found: {json_path}")

    hero_icon_map = build_hero_icon_map(abilities_path)
    canonical_hero_map = build_canonical_hero_map(abilities_path)
    validation_issues = validate_spreadsheet_columns(csv_path, canonical_hero_map)
    validation_issues += validate_counter_cells(
        csv_path, canonical_hero_map, args.default_display_icon
    )
    ability_meta = build_ability_meta_map(csv_path)
    counter_map = build_counter_map(csv_path)
    preferred_map = build_preferred_heroes_map(csv_path)
    playstyle_map = build_playstyle_heroes_map(csv_path)
    text = json_path.read_text(encoding="utf-8")
    data = json.loads(text)

    missing_ability_lines: list[str] | None = [] if args.verbose_missing else None
    missing_hero_icon_lines: list[str] | None = [] if args.verbose_missing else None

    updated, cleared, missing_meta, missing_hero_icon, warnings = apply_counters(
        data,
        counter_map,
        ability_meta,
        hero_icon_map,
        args.default_display_icon,
        missing_ability_log=missing_ability_lines,
        missing_hero_icon_log=missing_hero_icon_lines,
    )
    preferred_hero_count = apply_preferred_heroes(
        data,
        preferred_map,
        hero_icon_map,
        canonical_hero_map,
        data.get("hero_notes") or {},
    )
    playstyle_hero_count = apply_playstyle_heroes(
        data,
        playstyle_map,
        hero_icon_map,
        canonical_hero_map,
        data.get("hero_notes") or {},
    )

    if args.verbose_missing:
        print_validation_report(validation_issues)

    if args.verbose_missing and missing_ability_lines:
        print(
            "\n=== Missing CSV rows for counter picks (hero + ability_name) ===",
            file=sys.stderr,
        )
        for line in sorted(missing_ability_lines):
            print(line, file=sys.stderr)

    if args.verbose_missing and missing_hero_icon_lines:
        print(
            "\n=== Counter heroes with no portrait in abilities-data.json ===",
            file=sys.stderr,
        )
        for line in sorted(missing_hero_icon_lines):
            print(line, file=sys.stderr)

    for hero, ability, msg in warnings:
        print(f"warning: {msg}: {hero} / {ability}", file=sys.stderr)

    print(
        f"counter map entries: {len(counter_map)} | "
        f"ability meta keys: {len(ability_meta)} | "
        f"heroes with portrait: {len(hero_icon_map)} | "
        f"default display: {args.default_display_icon} | "
        f"blocks updated (non-empty): {updated} | "
        f"blocks cleared (empty counter): {cleared} | "
        f"counter picks missing ability row lookup: {missing_meta} | "
        f"counter picks missing hero_icon: {missing_hero_icon} | "
        f"missing-key warnings: {len(warnings)} | "
        f"preferred counter heroes: {preferred_hero_count} | "
        f"playstyle counter heroes: {playstyle_hero_count} | "
        f"spreadsheet validation issues: {len(validation_issues)}"
    )

    if args.dry_run:
        print("dry-run: not writing", json_path)
    else:
        json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {json_path}")

    if validation_issues and (args.strict or args.verbose_missing):
        sys.exit(1)


if __name__ == "__main__":
    main()
