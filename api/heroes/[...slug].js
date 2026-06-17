const { withCors, safeDecode } = require("../_lib/http");
const {
  findHero,
  findAbility,
  listAbilitiesForHero,
  rankHeroCounters,
  serializeAbility,
  suggestHeroNames,
  suggestAbilityNames,
  listHeroes, // Add this import
} = require("../_lib/data");

function sendHeroNotFound(res, heroParam) {
  res.status(404).json({
    error: `Hero "${heroParam}" was not found.`,
    did_you_mean: suggestHeroNames(heroParam),
  });
}

module.exports = withCors((req, res) => {
  // Parse URL path manually (not using req.query.slug)
  const urlParts = req.url.split('/').filter(Boolean);
  const heroesIndex = urlParts.indexOf('heroes');
  const slugParam = urlParts.slice(heroesIndex + 1);
  
  const parts = (Array.isArray(slugParam) ? slugParam : [slugParam])
    .filter(Boolean)
    .map(safeDecode);

  // If no hero is specified, return the full hero list (like index.js)
  if (parts.length === 0) {
    res.status(200).json({ heroes: listHeroes() });
    return;
  }

  const heroParam = parts[0];
  const hero = findHero(heroParam);
  if (!hero) {
    sendHeroNotFound(res, heroParam);
    return;
  }

  // GET /api/heroes/:hero
  if (parts.length === 1) {
    res.status(200).json({ hero: hero.name, abilities: listAbilitiesForHero(heroParam) });
    return;
  }

  // GET /api/heroes/:hero/counters
  if (parts.length === 2 && parts[1] === "counters") {
    res.status(200).json(rankHeroCounters(heroParam));
    return;
  }

  // GET /api/heroes/:hero/abilities/:ability
  if (parts.length === 3 && parts[1] === "abilities") {
    const abilityParam = parts[2];
    const ability = findAbility(heroParam, abilityParam);
    if (!ability) {
      res.status(404).json({
        error: `Ability "${abilityParam}" was not found for ${hero.name}.`,
        did_you_mean: suggestAbilityNames(heroParam, abilityParam),
      });
      return;
    }
    res.status(200).json(serializeAbility(ability));
    return;
  }

  res.status(404).json({ error: "Unknown route." });
});