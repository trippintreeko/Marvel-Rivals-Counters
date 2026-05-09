import csv
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


CSV_PATH = Path("marvel_rivals_hero_abilities.csv")
ABILITIES_JSON = Path("abilities-data.json")
COUNTERS_JSON = Path("counters-notes.json")
HEROES_PAGE_URL = "https://www.marvelrivals.com/heroes/"


def normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def scrape_hero_icons() -> dict[str, str]:
    hero_icons: dict[str, str] = {}
    try:
        html = requests.get(HEROES_PAGE_URL, timeout=30).text
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.select(".heroesNewsLists a[data-name]"):
            hero_name = (anchor.get("data-name") or "").strip()
            first_img = anchor.select_one("img")
            hero_icon = (first_img.get("src") or "").strip() if first_img else ""
            if hero_name and hero_icon:
                hero_icons[hero_name] = hero_icon
    except Exception:
        return {}
    return hero_icons


def main() -> None:
    grouped = {}
    notes_template = {}
    existing_notes = {}
    existing_pairs = []
    hero_icons = scrape_hero_icons()

    if COUNTERS_JSON.exists():
        try:
            current = json.loads(COUNTERS_JSON.read_text(encoding="utf-8"))
            existing_notes = current.get("hero_notes", {})
            existing_pairs = current.get("counter_pairs", [])
        except Exception:
            existing_notes = {}
            existing_pairs = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hero = (row.get("hero") or "").strip()
            ability_name = (row.get("ability_name") or "").strip()
            icon = (row.get("ability_icon") or "").strip()
            description = (row.get("ability_description") or "").strip()
            source_url = (row.get("source_url") or "").strip()

            if not hero or not ability_name:
                continue

            grouped.setdefault(hero, {})
            # Deduplicate by hero + ability_name. Keep first non-empty fields.
            if ability_name not in grouped[hero]:
                grouped[hero][ability_name] = {
                    "ability_name": ability_name,
                    "ability_icon": icon,
                    "ability_description": description,
                    "source_url": source_url,
                }
            else:
                existing = grouped[hero][ability_name]
                if not existing["ability_icon"] and icon:
                    existing["ability_icon"] = icon
                if not existing["ability_description"] and description:
                    existing["ability_description"] = description
                if not existing["source_url"] and source_url:
                    existing["source_url"] = source_url

            notes_template.setdefault(hero, {})
            notes_template[hero].setdefault(
                ability_name,
                {
                    "weaknesses": "",
                    "counters": "",
                    "notes": "",
                    "counter_abilities": [],
                },
            )

    heroes = []
    for hero_name in sorted(grouped):
        abilities = sorted(grouped[hero_name].values(), key=lambda x: x["ability_name"])
        exact_icon = hero_icons.get(hero_name, "")
        if not exact_icon:
            hero_key = normalize_name(hero_name)
            for source_name, source_icon in hero_icons.items():
                if normalize_name(source_name) == hero_key:
                    exact_icon = source_icon
                    break
        heroes.append({"hero": hero_name, "hero_icon": exact_icon, "abilities": abilities})

    ABILITIES_JSON.write_text(
        json.dumps({"heroes": heroes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    merged_notes = {}
    for hero_name, ability_map in notes_template.items():
        merged_notes.setdefault(hero_name, {})
        for ability_name, defaults in ability_map.items():
            existing = ((existing_notes.get(hero_name) or {}).get(ability_name) or {})
            merged_notes[hero_name][ability_name] = {
                "weaknesses": existing.get("weaknesses", defaults["weaknesses"]),
                "counters": existing.get("counters", defaults["counters"]),
                "notes": existing.get("notes", defaults["notes"]),
                "counter_abilities": existing.get("counter_abilities", defaults["counter_abilities"]),
            }

    COUNTERS_JSON.write_text(
        json.dumps({"hero_notes": merged_notes, "counter_pairs": existing_pairs}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {ABILITIES_JSON.resolve()}")
    print(f"Wrote {COUNTERS_JSON.resolve()}")


if __name__ == "__main__":
    main()
