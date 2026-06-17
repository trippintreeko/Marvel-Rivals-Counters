const { withCors, safeDecode } = require("./_lib/http");
const {
  findHero,
  findAbility,
  serializeAbility,
  suggestHeroNames,
  suggestAbilityNames,
} = require("./_lib/data");

module.exports = withCors((req, res) => {
  const heroParam = safeDecode(req.query.hero || "");
  const abilityParam = safeDecode(req.query.ability || "");

  const hero = findHero(heroParam);
  if (!hero) {
    res.status(404).json({
      error: `Hero "${heroParam}" was not found.`,
      did_you_mean: suggestHeroNames(heroParam),
    });
    return;
  }

  const ability = findAbility(heroParam, abilityParam);
  if (!ability) {
    res.status(404).json({
      error: `Ability "${abilityParam}" was not found for ${hero.name}.`,
      did_you_mean: suggestAbilityNames(heroParam, abilityParam),
    });
    return;
  }

  res.status(200).json(serializeAbility(ability));
});
