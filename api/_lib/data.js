const fs = require("fs");
const path = require("path");

const CSV_PATH = path.join(
  process.cwd(),
  "counters",
  "marvel_rivals_hero_abilities_counters.csv"
);

let cache = null;

function normalize(value) {
  return (value || "").toString().toLowerCase().trim();
}

function normalizeKey(hero, ability) {
  return `${normalize(hero)}::${normalize(ability)}`;
}

/**
 * Minimal RFC4180-ish CSV parser (no dependency). Handles quoted fields,
 * embedded commas/newlines inside quotes, and "" escaped quotes — which is
 * all this dataset uses.
 */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\r") {
      // skip, \n (or end of text) closes the row
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

function rowsToObjects(rows) {
  if (!rows.length) return [];
  const header = rows[0];
  const objects = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (r.length === 1 && r[0] === "") continue; // trailing blank line
    const obj = {};
    header.forEach((key, idx) => {
      obj[key] = r[idx] !== undefined ? r[idx] : "";
    });
    objects.push(obj);
  }
  return objects;
}

function splitList(raw) {
  return (raw || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Counter-column entries look like "Hero - Ability Name[ - Upgraded]".
 * Hero names in this dataset never contain " - ", so splitting on the
 * FIRST occurrence correctly separates hero from ability even when the
 * ability name itself contains a dash (e.g. "Skill Issue - UPGRADED").
 */
function splitHeroAbility(raw) {
  const trimmed = (raw || "").trim();
  const idx = trimmed.indexOf(" - ");
  if (idx === -1) return null;
  const hero = trimmed.slice(0, idx).trim();
  const ability = trimmed.slice(idx + 3).trim();
  if (!hero || !ability) return null;
  return { hero, ability };
}

function loadDataset() {
  if (cache) return cache;

  const raw = fs.readFileSync(CSV_PATH, "utf8").replace(/^\uFEFF/, "");
  const rows = rowsToObjects(parseCsv(raw));

  const heroes = new Map(); // normalized hero -> { name, abilities: Map }
  const abilityIndex = new Map(); // "hero::ability" -> record

  // Some heroes (e.g. Deadpool) have the same named ability repeated across
  // multiple role-variant rows (Vanguard/Duelist/Strategist), each
  // independently annotated with slightly different counter lists. Rows
  // are merged (not overwritten) into one record per (hero, ability) so no
  // counter data is silently dropped.
  for (const row of rows) {
    const heroName = (row.hero || "").trim();
    const abilityName = (row.ability_name || "").trim();
    if (!heroName || !abilityName) continue;

    const hKey = normalize(heroName);
    if (!heroes.has(hKey)) {
      heroes.set(hKey, { name: heroName, abilities: new Map() });
    }
    const bucket = heroes.get(hKey).abilities;
    const aKey = normalize(abilityName);

    const newCounteredBy = splitList(row.counter)
      .map(splitHeroAbility)
      .filter(Boolean);
    const newPreferred = splitList(row["Counters (prefered Heros)"]);
    const newWeakness = (row.Weaknesses || "").trim();

    if (bucket.has(aKey)) {
      const existing = bucket.get(aKey);

      const seenCounters = new Set(
        existing.countered_by.map((e) => normalizeKey(e.hero, e.ability))
      );
      for (const entry of newCounteredBy) {
        const key = normalizeKey(entry.hero, entry.ability);
        if (!seenCounters.has(key)) {
          seenCounters.add(key);
          existing.countered_by.push(entry);
        }
      }

      const seenPreferred = new Set(
        existing.preferred_counters.map((p) => normalize(p))
      );
      for (const name of newPreferred) {
        if (!seenPreferred.has(normalize(name))) {
          seenPreferred.add(normalize(name));
          existing.preferred_counters.push(name);
        }
      }

      if (!existing.weaknesses && newWeakness) existing.weaknesses = newWeakness;
      if (!existing.ability_icon && row.ability_icon) {
        existing.ability_icon = row.ability_icon;
      }
      if (!existing.ability_description && row.ability_description) {
        existing.ability_description = row.ability_description;
      }
      if (!existing.source_url && row.source_url) {
        existing.source_url = row.source_url;
      }
      continue;
    }

    const record = {
      hero: heroName,
      ability: abilityName,
      ability_icon: row.ability_icon || "",
      ability_description: row.ability_description || "",
      source_url: row.source_url || "",
      weaknesses: newWeakness,
      preferred_counters: newPreferred,
      // Abilities (from other heroes) that counter THIS ability.
      countered_by: newCounteredBy,
      // Abilities (from other heroes) that THIS ability counters.
      // Filled in during the resolve pass below.
      counters: [],
    };

    bucket.set(aKey, record);
    abilityIndex.set(normalizeKey(heroName, abilityName), record);
  }

  // Resolve cross-references now that every ability is known: canonicalize
  // hero casing, attach icon/description metadata, and build the reverse
  // ("counters") index from the forward ("countered_by") data.
  for (const record of abilityIndex.values()) {
    record.preferred_counters = record.preferred_counters.map((name) => {
      const match = heroes.get(normalize(name));
      return match ? match.name : name;
    });

    record.countered_by = record.countered_by.map((entry) => {
      const sourceRecord = abilityIndex.get(
        normalizeKey(entry.hero, entry.ability)
      );

      if (!sourceRecord) {
        // ~0.3% of entries in the source data have minor typos/punctuation
        // (e.g. trailing "?!?") that don't match any known ability. We
        // still return the raw hero/ability text, just without enrichment.
        return { hero: entry.hero, ability: entry.ability, resolved: false };
      }

      sourceRecord.counters.push({
        hero: record.hero,
        ability: record.ability,
        ability_icon: record.ability_icon,
        ability_description: record.ability_description,
      });

      return {
        hero: sourceRecord.hero,
        ability: sourceRecord.ability,
        ability_icon: sourceRecord.ability_icon,
        ability_description: sourceRecord.ability_description,
        resolved: true,
      };
    });
  }

  cache = { heroes, abilityIndex };
  return cache;
}

function findHero(heroNameRaw) {
  return loadDataset().heroes.get(normalize(heroNameRaw)) || null;
}

function findAbility(heroNameRaw, abilityNameRaw) {
  return (
    loadDataset().abilityIndex.get(normalizeKey(heroNameRaw, abilityNameRaw)) ||
    null
  );
}

function listHeroes() {
  return Array.from(loadDataset().heroes.values())
    .map((h) => ({ hero: h.name, ability_count: h.abilities.size }))
    .sort((a, b) => a.hero.localeCompare(b.hero));
}

function serializeAbility(record) {
  return {
    hero: record.hero,
    ability: record.ability,
    ability_icon: record.ability_icon,
    ability_description: record.ability_description,
    source_url: record.source_url,
    weaknesses: record.weaknesses,
    preferred_counters: record.preferred_counters,
    countered_by: record.countered_by,
    counters: record.counters,
  };
}

function listAbilitiesForHero(heroNameRaw) {
  const hero = findHero(heroNameRaw);
  if (!hero) return null;
  return Array.from(hero.abilities.values()).map(serializeAbility);
}

/**
 * Aggregate, hero-level view of counters: every hero whose abilities show
 * up in this hero's "countered_by" lists, ranked by how many of this
 * hero's abilities they counter, plus the union of "ideal" preferred
 * counters called out per-ability in the source data.
 */
function rankHeroCounters(heroNameRaw) {
  const hero = findHero(heroNameRaw);
  if (!hero) return null;

  const counts = new Map(); // normalized hero -> { hero, count }
  const preferred = new Map(); // normalized hero -> display name

  for (const ability of hero.abilities.values()) {
    for (const entry of ability.countered_by) {
      const key = normalize(entry.hero);
      if (!counts.has(key)) counts.set(key, { hero: entry.hero, count: 0 });
      counts.get(key).count += 1;
    }
    for (const name of ability.preferred_counters) {
      preferred.set(normalize(name), name);
    }
  }

  return {
    hero: hero.name,
    ranked_counters: Array.from(counts.values()).sort(
      (a, b) => b.count - a.count || a.hero.localeCompare(b.hero)
    ),
    preferred_counters: Array.from(preferred.values()).sort((a, b) =>
      a.localeCompare(b)
    ),
  };
}

function suggestHeroNames(query, limit = 5) {
  const q = normalize(query);
  return Array.from(loadDataset().heroes.values())
    .map((h) => h.name)
    .filter((name) => normalize(name).includes(q))
    .slice(0, limit);
}

function suggestAbilityNames(heroNameRaw, query, limit = 5) {
  const hero = findHero(heroNameRaw);
  if (!hero) return [];
  const q = normalize(query);
  return Array.from(hero.abilities.values())
    .map((a) => a.ability)
    .filter((name) => normalize(name).includes(q))
    .slice(0, limit);
}

module.exports = {
  normalize,
  loadDataset,
  findHero,
  findAbility,
  listHeroes,
  listAbilitiesForHero,
  serializeAbility,
  rankHeroCounters,
  suggestHeroNames,
  suggestAbilityNames,
};
