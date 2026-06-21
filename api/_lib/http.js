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

    // If RAPIDAPI_PROXY_SECRET is set (in Vercel's project env vars), only
    // requests that arrive through the RapidAPI gateway are allowed through.
    // RapidAPI stamps this secret on every request it proxies to you; the
    // value is shown in Studio > Hub Listing > Gateway tab > Security once
    // your API is listed. Leave the env var unset to keep the API open
    // (e.g. for local dev, or before you've listed it on RapidAPI).
    const expectedSecret = process.env.RAPIDAPI_PROXY_SECRET;
    if (expectedSecret) {
      const provided = req.headers["x-rapidapi-proxy-secret"];
      if (provided !== expectedSecret) {
        res.status(403).json({
          error: "Forbidden: this API can only be accessed through RapidAPI.",
        });
        return;
      }
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
