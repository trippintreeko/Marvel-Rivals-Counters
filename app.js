

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Failed to load ${path}: ${response.status}`);
  return response.json();
}

function normalize(text) {
  return (text || "").toLowerCase().trim();
}

function normalizeKey(hero, ability) {
  return `${normalize(hero)}::${normalize(ability)}`;
}

function renderHeroButtons(heroes, heroListEl, onPick, query = "") {
  const q = normalize(query);
  heroListEl.innerHTML = "";
  const filtered = heroes.filter((h) => normalize(h.hero).includes(q));

  for (const hero of filtered) {
    const btn = document.createElement("button");
    btn.className = "hero-btn";
    btn.type = "button";
    btn.textContent = `${hero.hero} (${hero.abilities.length})`;
    btn.addEventListener("click", () => onPick(hero.hero));
    heroListEl.appendChild(btn);
  }
}

function renderHeroIcons(heroes, iconGridEl, onPick) {
  iconGridEl.innerHTML = "";
  for (const hero of heroes) {
    if (!hero.hero_icon) continue;
    const btn = document.createElement("button");
    btn.className = "hero-icon-btn";
    btn.type = "button";
    btn.title = hero.hero;
    const img = document.createElement("img");
    img.src = hero.hero_icon;
    img.alt = hero.hero;
    btn.appendChild(img);
    btn.addEventListener("click", () => onPick(hero.hero));
    iconGridEl.appendChild(btn);
  }
}

function normalizedDisplayIcon(value) {
  return (value || "").toLowerCase() === "hero" ? "hero" : "ability";
}

function buildPairLookup(counterPairs) {
  const incomingByTarget = new Map();
  for (const pair of counterPairs || []) {
    const targetHero = pair.to_hero || pair.target_hero || "";
    const targetAbility = pair.to_ability || pair.target_ability || "";
    const fromHero = pair.from_hero || pair.counter_hero || "";
    const fromAbility = pair.from_ability || pair.counter_ability || "";
    const reason = pair.reason || "";
    if (!targetHero || !targetAbility || !fromHero || !fromAbility) continue;
    const key = normalizeKey(targetHero, targetAbility);
    if (!incomingByTarget.has(key)) incomingByTarget.set(key, []);
    incomingByTarget.get(key).push({
      hero: fromHero,
      ability: fromAbility,
      reason,
      ability_icon: pair.ability_icon || "",
      ability_description: pair.ability_description || "",
      hero_icon: pair.hero_icon || "",
      display_icon: normalizedDisplayIcon(pair.display_icon || pair.counter_display_icon),
    });
  }
  return incomingByTarget;
}

function buildOutgoingPairLookup(counterPairs, abilityMetaByKey, iconByHero) {
  const outgoingBySource = new Map();
  for (const pair of counterPairs || []) {
    const targetHero = pair.to_hero || pair.target_hero || "";
    const targetAbility = pair.to_ability || pair.target_ability || "";
    const sourceHero = pair.from_hero || pair.counter_hero || "";
    const sourceAbility = pair.from_ability || pair.counter_ability || "";
    if (!targetHero || !targetAbility || !sourceHero || !sourceAbility) continue;
    const sourceKey = normalizeKey(sourceHero, sourceAbility);
    if (!outgoingBySource.has(sourceKey)) outgoingBySource.set(sourceKey, []);
    const targetMeta = abilityMetaByKey.get(normalizeKey(targetHero, targetAbility)) || {};
    outgoingBySource.get(sourceKey).push({
      hero: targetHero,
      ability: targetAbility,
      hero_icon: targetMeta.hero_icon || iconByHero.get(normalize(targetHero)) || "",
      ability_icon: targetMeta.ability_icon || "",
      ability_description: targetMeta.ability_description || "",
      reason: pair.reason || "",
    });
  }
  return outgoingBySource;
}

function buildAbilityMetaByKey(heroes) {
  const map = new Map();
  for (const hero of heroes || []) {
    const heroName = hero.hero || "";
    for (const ability of hero.abilities || []) {
      const abilityName = ability.ability_name || "";
      if (!heroName || !abilityName) continue;
      map.set(normalizeKey(heroName, abilityName), {
        hero: heroName,
        ability: abilityName,
        hero_icon: hero.hero_icon || "",
        ability_icon: ability.ability_icon || "",
        ability_description: ability.ability_description || "",
      });
    }
  }
  return map;
}

function buildOutgoingNoteLookup(notesByHero, abilityMetaByKey, iconByHero) {
  const outgoingBySource = new Map();
  for (const [targetHero, heroNotes] of Object.entries(notesByHero || {})) {
    for (const [targetAbility, note] of Object.entries(heroNotes || {})) {
      for (const counter of note.counter_abilities || []) {
        const sourceHero = counter.hero || "";
        const sourceAbility = counter.ability_name || counter.ability || "";
        if (!sourceHero || !sourceAbility) continue;
        const sourceKey = normalizeKey(sourceHero, sourceAbility);
        if (!outgoingBySource.has(sourceKey)) outgoingBySource.set(sourceKey, []);
        const targetMeta = abilityMetaByKey.get(normalizeKey(targetHero, targetAbility)) || {};
        outgoingBySource.get(sourceKey).push({
          hero: targetHero,
          ability: targetAbility,
          hero_icon: targetMeta.hero_icon || iconByHero.get(normalize(targetHero)) || "",
          ability_icon: targetMeta.ability_icon || "",
          ability_description: targetMeta.ability_description || "",
          reason: counter.reason || "",
        });
      }
    }
  }
  return outgoingBySource;
}

function mergeOutgoingEntries(directList, pairList) {
  const merged = [];
  const seen = new Set();
  for (const item of [...(directList || []), ...(pairList || [])]) {
    const hero = item.hero || "";
    const ability = item.ability || item.ability_name || "";
    if (!hero || !ability) continue;
    const key = normalizeKey(hero, ability);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({
      hero,
      ability,
      hero_icon: item.hero_icon || "",
      ability_icon: item.ability_icon || "",
      ability_description: item.ability_description || "",
      reason: item.reason || "",
    });
  }
  return merged;
}

function summarizeCounteredHeroes(entries) {
  const seen = new Set();
  const summary = [];
  for (const entry of entries) {
    const key = normalize(entry.hero);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    summary.push({
      hero: entry.hero,
      hero_icon: entry.hero_icon || "",
    });
  }
  return summary;
}

function renderLookupResults(resultsEl, entries) {
  resultsEl.innerHTML = "";
  if (!entries.length) {
    const empty = document.createElement("article");
    empty.className = "lookup-empty";
    empty.textContent = "No countered abilities were found for this ability yet.";
    resultsEl.appendChild(empty);
    return;
  }

  for (const entry of entries) {
    const card = document.createElement("article");
    card.className = "ability-card";

    const head = document.createElement("div");
    head.className = "lookup-card-head";

    if (entry.hero_icon) {
      const heroIcon = document.createElement("img");
      heroIcon.className = "lookup-hero-icon";
      heroIcon.src = entry.hero_icon;
      heroIcon.alt = entry.hero;
      heroIcon.loading = "lazy";
      head.appendChild(heroIcon);
    }

    if (entry.ability_icon) {
      const abilityIcon = document.createElement("img");
      abilityIcon.className = "lookup-ability-icon";
      abilityIcon.src = entry.ability_icon;
      abilityIcon.alt = `${entry.hero} ${entry.ability}`;
      abilityIcon.loading = "lazy";
      head.appendChild(abilityIcon);
    }

    const titleWrap = document.createElement("div");
    const title = document.createElement("h3");
    title.className = "lookup-card-title";
    title.textContent = entry.ability;
    const subtitle = document.createElement("p");
    subtitle.className = "lookup-card-subtitle";
    subtitle.textContent = entry.hero;
    titleWrap.appendChild(title);
    titleWrap.appendChild(subtitle);
    head.appendChild(titleWrap);
    card.appendChild(head);

    const description = document.createElement("p");
    description.className = "lookup-card-description";
    description.textContent = entry.ability_description || "No ability description available.";
    card.appendChild(description);
    resultsEl.appendChild(card);
  }
}

function mergeCounterEntries(directList, pairList) {
  const merged = [];
  const seen = new Set();

  for (const item of [...(directList || []), ...(pairList || [])]) {
    const hero = item.hero || item.counter_hero || "";
    const ability =
      item.ability || item.counter_ability || item.ability_name || "";
    const reason = item.reason || "";
    const ability_icon = item.ability_icon || "";
    const ability_description = item.ability_description || "";
    const hero_icon = item.hero_icon || "";
    const display_icon = normalizedDisplayIcon(
      item.display_icon || item.counter_display_icon
    );
    if (!hero || !ability) continue;
    const key = `${normalize(hero)}::${normalize(ability)}::${normalize(reason)}::${display_icon}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({
      hero,
      ability,
      reason,
      ability_icon,
      hero_icon,
      ability_description,
      display_icon,
    });
  }
  return merged;
}

/**
 * listIconMode: site-wide viewer choice ("ability" | "hero") from the header toggle.
 * Per-entry display_icon in data is ignored on the page so the toggle is the single control.
 */
function pickCounterImageSrc(entry, listIconMode) {
  const mode = normalizedDisplayIcon(listIconMode);
  const abilityIcon = entry.ability_icon || "";
  const heroIcon = entry.hero_icon || "";
  if (mode === "hero") {
    if (heroIcon) return { src: heroIcon, portrait: true };
    if (abilityIcon) return { src: abilityIcon, portrait: false };
    return { src: "", portrait: false };
  }
  if (abilityIcon) return { src: abilityIcon, portrait: false };
  if (heroIcon) return { src: heroIcon, portrait: true };
  return { src: "", portrait: false };
}

/** Same counter hero repeated: pick first usable image in the list. */
function pickCounterImageSrcForGroup(entries, listIconMode) {
  const mode = normalizedDisplayIcon(listIconMode);
  const tryOrder = mode === "hero" ? ["hero", "ability"] : ["ability", "hero"];
  for (const prefer of tryOrder) {
    for (const e of entries) {
      const { src, portrait } = pickCounterImageSrc(e, prefer);
      if (src) return { src, portrait };
    }
  }
  return { src: "", portrait: false };
}

/**
 * Preserve merged list order: first time we see a counter hero, open a group;
 * later rows with the same hero append to that group.
 */
function groupCounterEntriesByHero(merged) {
  const order = [];
  const buckets = new Map();
  for (const entry of merged) {
    const hk = normalize(entry.hero);
    if (!buckets.has(hk)) {
      buckets.set(hk, []);
      order.push(hk);
    }
    buckets.get(hk).push(entry);
  }
  return order.map((hk) => buckets.get(hk));
}

function uniqueAbilityNamesInOrder(entries) {
  const seen = new Set();
  const names = [];
  for (const e of entries) {
    const raw = (e.ability || "").trim();
    if (!raw) continue;
    const k = normalize(raw);
    if (seen.has(k)) continue;
    seen.add(k);
    names.push(e.ability);
  }
  return names;
}

function buildGroupedCounterLabel(hero, entries) {
  const names = uniqueAbilityNamesInOrder(entries);
  const abilityPart = names.join(", ");
  if (entries.length === 1 && entries[0].reason) {
    return `${hero} - ${abilityPart}: ${entries[0].reason}`;
  }
  return `${hero} - ${abilityPart}`;
}

function buildGroupedCounterTooltip(hero, entries) {
  const names = uniqueAbilityNamesInOrder(entries);
  const header = `${hero} — ${names.join(", ")}`;
  const blocks = [];
  for (const e of entries) {
    const ab = (e.ability || "").trim();
    const lines = [];
    if (ab) lines.push(ab);
    if (e.reason) lines.push(`(${e.reason})`);
    const desc = (e.ability_description || "").trim();
    if (desc) lines.push(desc);
    if (lines.length) blocks.push(lines.join("\n"));
  }
  if (!blocks.length) return header;
  return `${header}\n\n${blocks.join("\n\n")}`;
}

function buildSingleCounterTooltip(entry) {
  const label = entry.reason
    ? `${entry.hero} - ${entry.ability}: ${entry.reason}`
    : `${entry.hero} - ${entry.ability}`;
  const desc = (entry.ability_description || "").trim();
  return desc ? `${entry.hero} - ${entry.ability}\n\n${desc}` : label;
}

function renderCounterAbilities(listEl, directList, pairList, listIconMode) {
  const merged = mergeCounterEntries(directList, pairList);
  listEl.innerHTML = "";
  if (!merged.length) {
    return;
  }

  const groups = groupCounterEntriesByHero(merged);

  for (const entries of groups) {
    const li = document.createElement("li");
    li.className = "counter-ability-item";
    const hero = entries[0].hero;
    const label =
      entries.length === 1
        ? entries[0].reason
          ? `${entries[0].hero} - ${entries[0].ability}: ${entries[0].reason}`
          : `${entries[0].hero} - ${entries[0].ability}`
        : buildGroupedCounterLabel(hero, entries);
    const tip =
      entries.length === 1
        ? buildSingleCounterTooltip(entries[0])
        : buildGroupedCounterTooltip(hero, entries);
    li.title = tip;

    const row = document.createElement("div");
    row.className = "counter-ability-row";

    const { src: imageSrc, portrait } =
      entries.length === 1
        ? pickCounterImageSrc(entries[0], listIconMode)
        : pickCounterImageSrcForGroup(entries, listIconMode);
    if (imageSrc) {
      const img = document.createElement("img");
      img.className = "counter-ability-icon";
      if (portrait) img.classList.add("counter-ability-icon--portrait");
      img.src = imageSrc;
      img.alt =
        entries.length === 1
          ? `${entries[0].hero}: ${entries[0].ability}`
          : `${hero}: ${uniqueAbilityNamesInOrder(entries).join(", ")}`;
      img.loading = "lazy";
      img.title = tip;
      row.appendChild(img);
    }

    const span = document.createElement("span");
    span.className = "counter-ability-label";
    span.textContent = label;
    span.title = tip;
    row.appendChild(span);
    li.appendChild(row);
    listEl.appendChild(li);
  }
}

function setCounterBlockVisible(markerEl, visible) {
  const block = markerEl.closest(".counter-block");
  if (!block) return;
  block.classList.toggle("hidden", !visible);
}

function syncCounterFieldsVisibility(counterFieldsEl) {
  if (!counterFieldsEl) return;
  const blocks = counterFieldsEl.querySelectorAll(".counter-block");
  const anyVisible = [...blocks].some((b) => !b.classList.contains("hidden"));
  counterFieldsEl.classList.toggle("hidden", !anyVisible);
}

/**
 * When a counter hero filter is active, return abilities with matching cards first
 * (stable: preserves relative order within matched and within non-matched).
 * When cleared, returns a shallow copy of the original list order.
 */
function orderAbilitiesForCounterFilter(
  abilities,
  targetHero,
  heroNotes,
  pairLookup,
  selectedCounterHero
) {
  const list = abilities.slice();
  if (!selectedCounterHero || !normalize(selectedCounterHero)) {
    return list;
  }
  const sel = normalize(selectedCounterHero);
  const matching = [];
  const nonMatching = [];
  for (const ability of list) {
    const note = heroNotes[ability.ability_name] || {};
    const pairKey = normalizeKey(targetHero, ability.ability_name);
    const merged = mergeCounterEntries(
      note.counter_abilities || [],
      pairLookup.get(pairKey) || []
    );
    const isMatch = merged.some((entry) => normalize(entry.hero) === sel);
    if (isMatch) matching.push(ability);
    else nonMatching.push(ability);
  }
  return [...matching, ...nonMatching];
}

function renderCounterRankedHeroes(targetHero, targetAbilities, heroNotes, pairLookup, iconByHero) {
  const countsByHero = new Map();

  for (const ability of targetAbilities) {
    const note = heroNotes[ability.ability_name] || {};
    const directCounterAbilities = note.counter_abilities || [];
    const pairKey = normalizeKey(targetHero, ability.ability_name);
    const pairedCounterAbilities = pairLookup.get(pairKey) || [];
    const merged = mergeCounterEntries(directCounterAbilities, pairedCounterAbilities);

    for (const entry of merged) {
      const heroName = entry.hero;
      countsByHero.set(heroName, (countsByHero.get(heroName) || 0) + 1);
    }
  }

  return Array.from(countsByHero.entries())
    .map(([hero, count]) => ({
      hero,
      count,
      icon: iconByHero.get(normalize(hero)) || "",
    }))
    .sort((a, b) => b.count - a.count || a.hero.localeCompare(b.hero));
}

function renderHero(
  heroName,
  allHeroes,
  notesByHero,
  pairLookup,
  iconByHero,
  selectedCounterHero,
  listIconMode,
  onToggleCounterHero,
  heroMetaEl,
  gridEl,
  templateEl
) {
  const hero = allHeroes.find((h) => h.hero === heroName);
  if (!hero) return;

  const heroNotes = notesByHero[hero.hero] || {};
  const rankedCounters = renderCounterRankedHeroes(hero.hero, hero.abilities, heroNotes, pairLookup, iconByHero);

  heroMetaEl.classList.remove("hidden");
  const rankedHtml = rankedCounters.length
    ? rankedCounters
        .map(
          (item) => `
          <div class="counter-hero-chip" title="${item.hero}: ${item.count} counters">
            ${item.icon ? `<img src="${item.icon}" alt="${item.hero}" />` : ""}
            <span>${item.hero}</span>
            <strong>${item.count}</strong>
          </div>
        `
        )
        .join("")
    : `<p class="counter-rank-empty">No counter pairings ranked yet.</p>`;

  const portraitHtml = hero.hero_icon
    ? `<img class="hero-meta-portrait" src="${hero.hero_icon}" alt="${hero.hero}" />`
    : "";

  heroMetaEl.innerHTML = `
    <div class="hero-meta-row">
      <div>
        <div class="hero-meta-title-row">
          ${portraitHtml}
          <h2>${hero.hero}</h2>
        </div>
        <p>${hero.abilities.length} abilities listed</p>
      </div>
      <div class="counter-rank-wrap">
        <h3>Counters Ranked</h3>
        <div class="counter-hero-row">${rankedHtml}</div>
        ${
          selectedCounterHero
            ? `<p class="counter-filter-active">Showing abilities countered by <strong>${selectedCounterHero}</strong> (matched first). <button type="button" class="clear-counter-filter">Clear</button></p>`
            : ""
        }
      </div>
    </div>
  `;
  for (const chip of heroMetaEl.querySelectorAll(".counter-hero-chip")) {
    const heroLabel = chip.querySelector("span")?.textContent || "";
    chip.classList.add("is-clickable");
    chip.classList.toggle("active", !!selectedCounterHero && normalize(heroLabel) === normalize(selectedCounterHero));
    chip.addEventListener("click", () => onToggleCounterHero(heroLabel));
  }
  const clearBtn = heroMetaEl.querySelector(".clear-counter-filter");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => onToggleCounterHero(""));
  }
  gridEl.innerHTML = "";

  const abilitiesToRender = orderAbilitiesForCounterFilter(
    hero.abilities,
    hero.hero,
    heroNotes,
    pairLookup,
    selectedCounterHero
  );

  for (const ability of abilitiesToRender) {
    const card = templateEl.content.firstElementChild.cloneNode(true);
    card.querySelector(".ability-name").textContent = ability.ability_name || "Unknown Ability";
    card.querySelector(".ability-description").textContent =
      ability.ability_description || "No in-game description scraped yet.";

    const sourceLink = card.querySelector(".source-link");
    sourceLink.href = ability.source_url || "#";
    sourceLink.textContent = "Official Hero Page";

    const icon = card.querySelector(".ability-icon");
    if (ability.ability_icon) {
      icon.src = ability.ability_icon;
      icon.alt = `${hero.hero} ${ability.ability_name}`;
    } else {
      icon.style.display = "none";
    }

    const note = heroNotes[ability.ability_name] || {};
    const weaknessesEl = card.querySelector(".js-weaknesses");
    const countersEl = card.querySelector(".js-counters");
    const notesEl = card.querySelector(".js-notes");
    const weaknessesText = (note.weaknesses || "").trim();
    const countersText = (note.counters || "").trim();
    const notesText = (note.notes || "").trim();
    weaknessesEl.textContent = weaknessesText;
    countersEl.textContent = countersText;
    notesEl.textContent = notesText;
    setCounterBlockVisible(weaknessesEl, !!weaknessesText);
    setCounterBlockVisible(countersEl, !!countersText);
    setCounterBlockVisible(notesEl, !!notesText);

    const directCounterAbilities = note.counter_abilities || [];
    const pairKey = normalizeKey(hero.hero, ability.ability_name);
    const pairedCounterAbilities = pairLookup.get(pairKey) || [];
    const counterListEl = card.querySelector(".js-counter-abilities");
    const mergedCounterEntries = mergeCounterEntries(directCounterAbilities, pairedCounterAbilities);
    renderCounterAbilities(counterListEl, directCounterAbilities, pairedCounterAbilities, listIconMode);
    setCounterBlockVisible(counterListEl, mergedCounterEntries.length > 0);
    const isMatch =
      !selectedCounterHero ||
      mergedCounterEntries.some((entry) => normalize(entry.hero) === normalize(selectedCounterHero));
    card.classList.toggle("ability-card-muted", !isMatch);
    card.classList.toggle("ability-card-highlight", !!selectedCounterHero && isMatch);

    syncCounterFieldsVisibility(card.querySelector(".counter-fields"));

    gridEl.appendChild(card);
  }
}

async function main() {
  const abilityData = await loadJson("./abilities-data.json");
  const notesData = await loadJson("./counters-notes.json");

  const heroes = abilityData.heroes || [];
  const notesByHero = (notesData && notesData.hero_notes) || {};
  const abilityMetaByKey = buildAbilityMetaByKey(heroes);
  const pairLookup = buildPairLookup((notesData && notesData.counter_pairs) || []);
  const iconByHero = new Map(heroes.map((h) => [normalize(h.hero), h.hero_icon || ""]));
  const outgoingNoteLookup = buildOutgoingNoteLookup(notesByHero, abilityMetaByKey, iconByHero);
  const outgoingPairLookup = buildOutgoingPairLookup(
    (notesData && notesData.counter_pairs) || [],
    abilityMetaByKey,
    iconByHero
  );

  const heroListEl = document.getElementById("heroList");
  const heroIconGridEl = document.getElementById("heroIconGrid");
  const heroSearchEl = document.getElementById("heroSearch");
  const quickHeroSearchEl = document.getElementById("quickHeroSearch");
  const quickHeroBtnEl = document.getElementById("quickHeroBtn");
  const heroNamesEl = document.getElementById("heroNames");
  const heroMetaEl = document.getElementById("heroMeta");
  const abilityGridEl = document.getElementById("abilityGrid");
  const templateEl = document.getElementById("abilityCardTemplate");
  const counterIconAbilityBtn = document.getElementById("counterIconAbility");
  const counterIconHeroBtn = document.getElementById("counterIconHero");
  const viewMainBtn = document.getElementById("viewMainBtn");
  const viewLookupBtn = document.getElementById("viewLookupBtn");
  const mainSidebar = document.getElementById("mainSidebar");
  const mainContent = document.getElementById("mainContent");
  const lookupContent = document.getElementById("lookupContent");
  const lookupHeroIconGrid = document.getElementById("lookupHeroIconGrid");
  const lookupAbilityCards = document.getElementById("lookupAbilityCards");
  const lookupSelectionMeta = document.getElementById("lookupSelectionMeta");
  const lookupResults = document.getElementById("lookupResults");

  const COUNTER_LIST_ICON_STORAGE_KEY = "marvelRivalsCounterListIconMode";

  function readStoredListIconMode() {
    try {
      const v = localStorage.getItem(COUNTER_LIST_ICON_STORAGE_KEY);
      if (v === "hero") return "hero";
    } catch {
      /* ignore */
    }
    return "ability";
  }

  function writeStoredListIconMode(mode) {
    try {
      localStorage.setItem(COUNTER_LIST_ICON_STORAGE_KEY, mode);
    } catch {
      /* ignore */
    }
  }

  function syncCounterIconToggleUi(mode) {
    const isAbility = mode === "ability";
    if (counterIconAbilityBtn) {
      counterIconAbilityBtn.setAttribute("aria-pressed", isAbility ? "true" : "false");
      counterIconAbilityBtn.classList.toggle("is-active", isAbility);
    }
    if (counterIconHeroBtn) {
      counterIconHeroBtn.setAttribute("aria-pressed", !isAbility ? "true" : "false");
      counterIconHeroBtn.classList.toggle("is-active", !isAbility);
    }
  }

  let selectedHero = heroes[0] ? heroes[0].hero : null;
  let selectedCounterHero = "";
  let selectedLookupHero = heroes[0] ? heroes[0].hero : "";
  let selectedLookupAbility = "";
  let counterListIconMode = readStoredListIconMode();
  syncCounterIconToggleUi(counterListIconMode);

  const setCounterListIconMode = (mode) => {
    const next = normalizedDisplayIcon(mode);
    if (next === counterListIconMode) return;
    counterListIconMode = next;
    writeStoredListIconMode(counterListIconMode);
    syncCounterIconToggleUi(counterListIconMode);
    if (selectedHero) pickHero(selectedHero);
  };

  const setActiveView = (view) => {
    const lookup = view === "lookup";
    mainSidebar.classList.toggle("hidden", lookup);
    mainContent.classList.toggle("hidden", lookup);
    lookupContent.classList.toggle("hidden", !lookup);
    viewMainBtn.classList.toggle("is-active", !lookup);
    viewLookupBtn.classList.toggle("is-active", lookup);
    viewMainBtn.setAttribute("aria-selected", lookup ? "false" : "true");
    viewLookupBtn.setAttribute("aria-selected", lookup ? "true" : "false");
  };

  if (counterIconAbilityBtn) {
    counterIconAbilityBtn.addEventListener("click", () => setCounterListIconMode("ability"));
  }
  if (counterIconHeroBtn) {
    counterIconHeroBtn.addEventListener("click", () => setCounterListIconMode("hero"));
  }

  heroNamesEl.innerHTML = "";
  for (const hero of heroes) {
    const option = document.createElement("option");
    option.value = hero.hero;
    heroNamesEl.appendChild(option);
  }

  const renderLookupDetails = () => {
    if (!selectedLookupHero || !selectedLookupAbility) {
      lookupSelectionMeta.textContent = "Select a hero and ability to view detailed counters.";
      renderLookupResults(lookupResults, []);
      return;
    }
    lookupSelectionMeta.textContent = `${selectedLookupHero} - ${selectedLookupAbility}`;
    const key = normalizeKey(selectedLookupHero, selectedLookupAbility);
    const merged = mergeOutgoingEntries(
      outgoingNoteLookup.get(key) || [],
      outgoingPairLookup.get(key) || []
    );
    renderLookupResults(lookupResults, merged);
  };

  const renderLookupAbilities = () => {
    const hero = heroes.find((h) => h.hero === selectedLookupHero);
    lookupAbilityCards.innerHTML = "";
    const abilities = (hero && hero.abilities) || [];
    if (!abilities.length) {
      lookupAbilityCards.innerHTML = `<article class="lookup-empty">No abilities found for this hero.</article>`;
      selectedLookupAbility = "";
      renderLookupDetails();
      return;
    }
    if (!selectedLookupAbility) {
      selectedLookupAbility = abilities[0].ability_name || "";
    }
    const hasSelected = abilities.some((ability) => ability.ability_name === selectedLookupAbility);
    if (!hasSelected) selectedLookupAbility = abilities[0].ability_name || "";

    for (const ability of abilities) {
      const abilityName = ability.ability_name || "Unknown Ability";
      const key = normalizeKey(selectedLookupHero, abilityName);
      const merged = mergeOutgoingEntries(
        outgoingNoteLookup.get(key) || [],
        outgoingPairLookup.get(key) || []
      );
      const heroSummary = summarizeCounteredHeroes(merged);

      const card = document.createElement("button");
      card.type = "button";
      card.className = "lookup-ability-card";
      card.classList.toggle("active", abilityName === selectedLookupAbility);

      const head = document.createElement("div");
      head.className = "lookup-ability-head";
      if (ability.ability_icon) {
        const icon = document.createElement("img");
        icon.className = "lookup-ability-icon";
        icon.src = ability.ability_icon;
        icon.alt = `${selectedLookupHero} ${abilityName}`;
        icon.loading = "lazy";
        head.appendChild(icon);
      }
      const name = document.createElement("h3");
      name.className = "lookup-ability-name";
      name.textContent = abilityName;
      head.appendChild(name);
      card.appendChild(head);

      const summaryText = document.createElement("p");
      summaryText.className = "lookup-ability-summary";
      summaryText.textContent = merged.length
        ? `Counters ${merged.length} ${merged.length === 1 ? "ability" : "abilities"}`
        : "No recorded counters yet";
      card.appendChild(summaryText);

      if (heroSummary.length) {
        const icons = document.createElement("div");
        icons.className = "lookup-counter-hero-icons";
        for (const summary of heroSummary.slice(0, 10)) {
          if (!summary.hero_icon) continue;
          const img = document.createElement("img");
          img.src = summary.hero_icon;
          img.alt = summary.hero;
          img.title = summary.hero;
          img.loading = "lazy";
          icons.appendChild(img);
        }
        if (icons.children.length) card.appendChild(icons);
      }

      card.addEventListener("click", () => {
        selectedLookupAbility = abilityName;
        renderLookupAbilities();
        renderLookupDetails();
      });
      lookupAbilityCards.appendChild(card);
    }
    renderLookupDetails();
  };

  const renderLookupHeroIcons = () => {
    lookupHeroIconGrid.innerHTML = "";
    for (const hero of heroes) {
      if (!hero.hero_icon) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hero-icon-btn";
      btn.classList.toggle("active", hero.hero === selectedLookupHero);
      btn.title = hero.hero;
      const img = document.createElement("img");
      img.src = hero.hero_icon;
      img.alt = hero.hero;
      btn.appendChild(img);
      btn.addEventListener("click", () => {
        selectedLookupHero = hero.hero;
        selectedLookupAbility = "";
        renderLookupHeroIcons();
        renderLookupAbilities();
      });
      lookupHeroIconGrid.appendChild(btn);
    }
  };
  renderLookupHeroIcons();
  renderLookupAbilities();

  const pickHero = (heroName) => {
    selectedHero = heroName;
    renderHero(
      selectedHero,
      heroes,
      notesByHero,
      pairLookup,
      iconByHero,
      selectedCounterHero,
      counterListIconMode,
      (counterHeroName) => {
        const next = normalize(counterHeroName);
        const current = normalize(selectedCounterHero);
        selectedCounterHero = next && next === current ? "" : counterHeroName;
        pickHero(selectedHero);
      },
      heroMetaEl,
      abilityGridEl,
      templateEl
    );
    for (const btn of heroListEl.querySelectorAll(".hero-btn")) {
      btn.classList.toggle("active", btn.textContent.startsWith(heroName + " "));
    }
    for (const btn of heroIconGridEl.querySelectorAll(".hero-icon-btn")) {
      const img = btn.querySelector("img");
      btn.classList.toggle("active", !!img && img.alt === heroName);
    }
    quickHeroSearchEl.value = heroName;
  };

  renderHeroIcons(heroes, heroIconGridEl, pickHero);
  renderHeroButtons(heroes, heroListEl, pickHero, "");
  if (selectedHero) pickHero(selectedHero);

  setActiveView("main");

  const jumpToHero = () => {
    const query = normalize(quickHeroSearchEl.value);
    if (!query) return;
    const exact = heroes.find((h) => normalize(h.hero) === query);
    const partial = heroes.find((h) => normalize(h.hero).includes(query));
    const target = exact || partial;
    if (!target) return;
    selectedCounterHero = "";
    heroSearchEl.value = target.hero;
    renderHeroButtons(heroes, heroListEl, pickHero, target.hero);
    pickHero(target.hero);
  };

  heroSearchEl.addEventListener("input", (event) => {
    renderHeroButtons(heroes, heroListEl, pickHero, event.target.value);
    if (selectedHero) {
      const exists = Array.from(heroListEl.querySelectorAll(".hero-btn")).some((btn) =>
        btn.textContent.startsWith(selectedHero + " ")
      );
      if (!exists) {
        const first = heroListEl.querySelector(".hero-btn");
        if (first) first.click();
      } else {
        selectedCounterHero = "";
        pickHero(selectedHero);
      }
    }
  });

  quickHeroBtnEl.addEventListener("click", jumpToHero);
  quickHeroSearchEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") jumpToHero();
  });
  viewMainBtn.addEventListener("click", () => setActiveView("main"));
  viewLookupBtn.addEventListener("click", () => setActiveView("lookup"));
}

main().catch((err) => {
  const container = document.getElementById("abilityGrid");
  container.innerHTML = `<article class="ability-card"><h3>Failed to load data</h3><p>${err.message}</p></article>`;
});
