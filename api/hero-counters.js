const { withCors, safeDecode } = require("./_lib/http");
const { findHero, rankHeroCounters, suggestHeroNames } = require("./_lib/data");

module.exports = withCors((req, res) => {
  const heroParam = safeDecode(req.query.hero || "");
  const hero = findHero(heroParam);

  if (!hero) {
    res.status(404).json({
      error: `Hero "${heroParam}" was not found.`,
      did_you_mean: suggestHeroNames(heroParam),
    });
    return;
  }

  res.status(200).json(rankHeroCounters(heroParam));
});
