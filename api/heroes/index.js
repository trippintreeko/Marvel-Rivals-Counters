const { withCors } = require("../_lib/http");
const { listHeroes } = require("../_lib/data");

module.exports = withCors((req, res) => {
  res.status(200).json({ heroes: listHeroes() });
});
