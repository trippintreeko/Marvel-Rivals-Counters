function withCors(handler) {
  return async (req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") {
      res.status(204).end();
      return;
    }

    if (req.method !== "GET") {
      res.status(405).json({ error: `Method ${req.method} not allowed. Use GET.` });
      return;
    }

    try {
      await handler(req, res);
    } catch (err) {
      console.error(err);
      res.status(500).json({ error: "Internal server error", detail: err.message });
    }
  };
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

module.exports = { withCors, safeDecode };
