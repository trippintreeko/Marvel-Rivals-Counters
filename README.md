# Marvel Rivals Hero Counter Site

This project includes a static website to showcase every hero ability, quick hero search, and cross-hero counter pairings.

## Files

- `index.html` - main page
- `styles.css` - Marvel Rivals-inspired styling
- `app.js` - UI logic and data rendering
- `abilities-data.json` - generated abilities dataset (from your CSV)
- `counters-notes.json` - where you write weaknesses/counters and counter ability pairings
- `build_site_data.py` - regenerates JSON files from `marvel_rivals_hero_abilities.csv`

## How to run locally

Use a local web server (required because the page fetches local JSON files).

```bash
python -m http.server 8000
```

Then open:

`http://localhost:8000`

## Add your hero counters

Edit `counters-notes.json`.

Structure:

```json
{
  "hero_notes": {
    "BLACK CAT": {
      "FELINE FURY": {
        "weaknesses": "Short range and commits movement.",
        "counters": "Keep distance and punish during cooldown.",
        "notes": "Best countered by peel and stuns.",
        "counter_abilities": [
          {
            "hero": "LUNA SNOW",
            "ability": "FATE OF BOTH WORLDS",
            "reason": "Freeze interrupt stops engage."
          }
        ]
      }
    }
  },
  "counter_pairs": [
    {
      "from_hero": "MANTIS",
      "from_ability": "SPORE SLUMBER",
      "to_hero": "BLACK CAT",
      "to_ability": "CALLING CARD",
      "reason": "Sleep can punish dash entry."
    }
  ]
}
```

Refresh browser after saving.

## Search and pairing behavior

- Use **Quick hero jump** in the header to jump directly to a hero.
- Sidebar search still filters the hero list.
- Each ability card now shows **Counter Abilities (Other Heroes)** from:
  - Ability-local `counter_abilities`
  - Global `counter_pairs` relations

## If CSV changes

Rebuild JSON data (this keeps your existing notes/pairs and only fills missing defaults):

```bash
python build_site_data.py
```


Things to run: 

to pull new info from rivals website:

python .\scrape_marvel_rivals.py

to add counter information to comunity guide: 
