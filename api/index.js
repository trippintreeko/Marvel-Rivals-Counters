const { withCors } = require("./_lib/http");
const { listHeroes } = require("./_lib/data");

module.exports = withCors((req, res) => {
  const heroes = listHeroes();
  res.status(200).json({
    name: "Marvel Rivals Counters API",
    hero_count: heroes.length,
    ability_count: heroes.reduce((sum, h) => sum + h.ability_count, 0),
    endpoints: [
      "GET /api/heroes",
      "GET /api/heroes/:hero",
      "GET /api/heroes/:hero/counters",
      "GET /api/heroes/:hero/abilities/:ability",
    ],
  });
});
