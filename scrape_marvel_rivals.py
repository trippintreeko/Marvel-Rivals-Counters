import csv
from pathlib import Path
from typing import Dict, List

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


BASE_URL = "https://www.marvelrivals.com/heroes/"
OUTPUT_CSV = Path("marvel_rivals_hero_abilities.csv")
OUTPUT_XLSX = Path("marvel_rivals_hero_abilities.xlsx")


def get_html(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def parse_hero_links(page_html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(page_html, "html.parser")
    heroes = []
    for anchor in soup.select(".heroesNewsLists a[data-id][data-url][data-name]"):
        hero_id = (anchor.get("data-id") or "").strip()
        hero_name = (anchor.get("data-name") or "").strip()
        hero_url = (anchor.get("data-url") or "").strip()
        if hero_id and hero_name and hero_url:
            heroes.append({"hero_id": hero_id, "hero_name": hero_name, "hero_url": hero_url})
    return heroes


def parse_ability_rows(hero_name: str, hero_url: str, html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    abilities: List[Dict[str, str]] = []
    seen = set()
    for row in soup.select(".art-inner-content tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        idx_raw = cells[0].get_text(" ", strip=True)
        if not idx_raw.isdigit() or int(idx_raw) < 1:
            continue

        ability_name = cells[1].get_text(" ", strip=True)
        if not ability_name:
            continue

        icon_el = cells[2].select_one("img")
        ability_icon = (icon_el.get("src") or "").strip() if icon_el else ""
        ability_description = cells[3].get_text(" ", strip=True)

        key = (hero_name, ability_name, ability_description, ability_icon)
        if key in seen:
            continue
        seen.add(key)

        abilities.append(
            {
                "hero": hero_name,
                "ability_name": ability_name,
                "ability_icon": ability_icon,
                "ability_description": ability_description,
                "source_url": hero_url,
            }
        )

    return abilities


def write_xlsx(rows: List[Dict[str, str]], output_path: Path) -> None:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Hero Abilities"
    headers = ["hero", "ability_name", "ability_icon", "ability_description", "source_url"]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    workbook.save(output_path)


def main() -> None:
    heroes_html = get_html(BASE_URL)
    hero_links = parse_hero_links(heroes_html)

    rows: List[Dict[str, str]] = []
    for hero in hero_links:
        hero_name = hero["hero_name"]
        hero_url = hero["hero_url"]
        try:
            detail_html = get_html(hero_url)
            rows.extend(parse_ability_rows(hero_name, hero_url, detail_html))
        except Exception as exc:
            print(f"Failed to parse {hero_name} ({hero_url}): {exc}")

    fieldnames = ["hero", "ability_name", "ability_icon", "ability_description", "source_url"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    write_xlsx(rows, OUTPUT_XLSX)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV.resolve()}")
    print(f"Wrote {len(rows)} rows to {OUTPUT_XLSX.resolve()}")


if __name__ == "__main__":
    main()
