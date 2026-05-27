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
--verbose-missing: print each missing ability-row lookup and missing hero portrait to stderr.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def default_paths(project_root: Path) -> tuple[Path, Path, Path]:
    return (
        project_root / "counters" / "marvel_rivals_hero_abilities_counters.csv",
        project_root / "counters-notes.json",
        project_root / "abilities-data.json",
    )


_DISPLAY_SUFFIX = re.compile(r"\s*@(hero|ability)\s*$", re.IGNORECASE)


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
        if " - " not in piece:
            out.append({"hero": piece, "ability_name": "", "display_icon": display_d})
            continue
        h, a = piece.split(" - ", 1)
        out.append({"hero": h.strip(), "ability_name": a.strip(), "display_icon": display_d})
    return out


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
        help="Log each missing counter ability CSV lookup and missing hero portrait (stderr)",
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
    ability_meta = build_ability_meta_map(csv_path)
    counter_map = build_counter_map(csv_path)
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
        f"missing-key warnings: {len(warnings)}"
    )

    if args.dry_run:
        print("dry-run: not writing", json_path)
        return

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
