# Marvel Rivals Counters API

A small read-only REST API that serves hero ability counter data — built
as Vercel serverless functions, parsing the CSV directly at request time
(no database, no build step, no runtime dependencies).

## Endpoints

All endpoints are `GET`, return JSON, and are open to cross-origin
requests (CORS `*`).

### `GET /api/heroes`
List every hero and how many abilities are on file for them.

```json
{ "heroes": [{ "hero": "Hela", "ability_count": 9 }, ...] }
```

### `GET /api/heroes/:hero`
All abilities for one hero, each with its full counter data (see "Counter
data shape" below).

```
GET /api/heroes/Hela
```

### `GET /api/heroes/:hero/counters`
A hero-level rollup: every other hero who counters *any* of this hero's
abilities, ranked by how many abilities they counter, plus the union of
"ideal counter" heroes called out in the source data.

```
GET /api/heroes/Hela/counters
```

```json
{
  "hero": "Hela",
  "ranked_counters": [
    { "hero": "Deadpool", "count": 18 },
    { "hero": "Groot", "count": 9 }
  ],
  "preferred_counters": ["Doctor Strange", "Phoenix", "The Punisher"]
}
```

### `GET /api/heroes/:hero/abilities/:ability`
Full counter detail for a single ability, in both directions.

```
GET /api/heroes/Hela/abilities/Nightsword%20Thorn
```

```json
{
  "hero": "Hela",
  "ability": "Nightsword Thorn",
  "ability_icon": "https://...",
  "ability_description": "Throw Nightsword thorns",
  "source_url": "https://...",
  "weaknesses": "",
  "preferred_counters": ["Doctor Strange", "The Punisher", "Phoenix"],
  "countered_by": [
    { "hero": "Emma Frost", "ability": "MIND'S AEGIS", "ability_icon": "...", "ability_description": "...", "resolved": true }
  ],
  "counters": [
    { "hero": "...", "ability": "...", "ability_icon": "...", "ability_description": "..." }
  ]
}
```

Hero and ability names are matched case-insensitively; spaces and
punctuation should be URL-encoded (`encodeURIComponent`).

### Errors
Unknown heroes/abilities return `404` with a `did_you_mean` array of
close substring matches, e.g.:

```json
{ "error": "Hero \"Wolverin\" was not found.", "did_you_mean": ["Wolverine"] }
```

## Counter data shape

Each ability carries two distinct lists, since "counters" is a directional
relationship:

- **`countered_by`** — other heroes' abilities that counter *this*
  ability (this is what the source CSV's `counter` column records).
- **`counters`** — the reverse: abilities *this* ability counters. Built
  by inverting `countered_by` across the whole dataset, so it's only as
  complete as the forward data is.
- **`preferred_counters`** — hero names (no ability detail) called out in
  the source CSV as the go-to picks against this ability.

## Data caveats

- About 0.3% of `counter` column entries have minor typos/punctuation
  (e.g. a trailing `?!?`) that don't match any known ability name. These
  still come through in `countered_by` as `{ hero, ability, resolved: false }`
  — just without icon/description enrichment.
- A few heroes (Deadpool, etc.) list the same ability name across
  multiple "form" rows (Vanguard/Duelist/Strategist) with slightly
  different counter lists per row. These are merged into one record per
  (hero, ability) rather than overwritten, so no counter data is lost.
- The CSV has no hero-level icon column, only per-ability icons, so there
  is no `hero_icon` field at the hero level.

## Project layout

```
api/
  index.js              GET /api
  heroes/
    index.js             GET /api/heroes
  hero-detail.js          /api/heroes/:hero        (via rewrite below)
  hero-counters.js        /api/heroes/:hero/counters
  ability-detail.js       /api/heroes/:hero/abilities/:ability
  _lib/
    data.js              CSV parsing + in-memory indices (no deps)
    http.js              CORS headers + method guard + error handling
data/
  marvel_rivals_hero_abilities_counters.csv
vercel.json              rewrites + ensures the CSV is bundled with the functions
```

Note on routing: Vercel's file-system `[param].js` dynamic segments only
reliably support a single path segment for plain (non-Next.js) serverless
functions — the Next.js-style `[...slug].js` catch-all convention for
multi-segment paths is not supported outside Next.js and silently fails
to populate `req.query`. So the two- and three-segment routes
(`:hero/counters`, `:hero/abilities/:ability`) are handled by explicit
`rewrites` in `vercel.json`, which map those URL shapes onto flat
function files and pass the captured values as ordinary query params
(`?hero=...&ability=...`) — no file-system routing magic involved.

## Deploy

```
npm install -g vercel   # if you don't already have it
vercel                  # follow the prompts, or `vercel --prod` to ship
```

No environment variables or build step needed. The CSV is read with
`fs.readFileSync` at cold start and cached in memory for the life of that
function instance — Vercel's bundler detects this automatically and
packages the file; `vercel.json` is just a safety net.

## Local dev

```
vercel dev
```

or, without the Vercel CLI, run the handlers directly in Node against a
minimal mock `req`/`res` — each file in `api/` exports a plain
`(req, res) => {}` function.

## Integrating with the existing site

This is a standalone, deployable folder. If you'd rather merge it into
the existing `index.html` / `app.js` / `styles.css` repo (which already
has `marvel_rivals_hero_abilities_counters.csv` at its root), drop in the
`api/` folder and `vercel.json`, skip the `data/` folder, and change the
one path in `api/_lib/data.js`:

```js
const CSV_PATH = path.join(process.cwd(), "marvel_rivals_hero_abilities_counters.csv");
```

Vercel serves static files and `api/` functions from the same deployment
automatically, so the existing site and this API would ship together.

## Selling this on RapidAPI

RapidAPI issues API keys and enforces request quotas for you based on
whatever pricing plans you configure — you don't need to build your own
key/token system. The one thing your backend needs to do is reject
requests that didn't come through RapidAPI's gateway, so people can't
just call your Vercel URL directly for free.

This is already wired up in `api/_lib/http.js`, gated behind an env var
so nothing changes until you turn it on:

1. In RapidAPI's Studio (`My APIs`), add a new API and point its base
   URL at this deployment, e.g. `https://marvelrivals.guide/api`.
2. Go to **Hub Listing → Gateway tab → Security** and copy the
   `X-RapidAPI-Proxy-Secret` value RapidAPI generated for your listing.
3. In your Vercel project, add an environment variable
   `RAPIDAPI_PROXY_SECRET` set to that value, and redeploy.

From that point on, every request is checked against that header; the
public deployment now only works when called through RapidAPI's gateway.
Before doing this, double check the URL still works directly so you
don't lock yourself out before the RapidAPI listing is live.

For pricing, go to **Hub Listing → Monetize tab** and set up plans (a
free tier with a low request cap is standard, plus paid tiers with
higher monthly quotas). RapidAPI bills subscribers and pays you out;
your code doesn't need to know which plan a caller is on.

If you'd like, I can also generate an OpenAPI/Swagger spec for these
four endpoints — RapidAPI's Definitions tab uses it to auto-generate the
docs and sample code shown to subscribers.

`openapi.yaml` (in this folder) is that spec — paste it directly into
Studio's Definitions tab (or import the file) and it'll populate all
four endpoints, parameters, response schemas, and examples.

## Updating the data

Replace `data/marvel_rivals_hero_abilities_counters.csv` with a newer
export (same column names: `hero, ability_name, ability_icon,
ability_description, source_url, counter, Weaknesses, Counters (prefered
Heros)`) and redeploy — nothing else needs to change.
