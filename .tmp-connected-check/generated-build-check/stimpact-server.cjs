const { registerStimpactBrowserTokenRoute } = require("./stimpact-token-route.cjs");

const express = require("express");
const fs = require("node:fs");
const path = require("node:path");

const app = express();
registerStimpactBrowserTokenRoute(app);
const port = Number(process.env.PORT || 3000);

app.use(express.json());

function resolveStaticRoot() {
  const candidates = [
    process.env.STIMPACT_STATIC_ROOT,
    "client/dist",
    "dist",
    "build",
    "public",
  ].filter(Boolean);
  for (const candidate of candidates) {
    const absolutePath = path.resolve(__dirname, candidate);
    if (fs.existsSync(path.join(absolutePath, "index.html"))) {
      return absolutePath;
    }
  }
  return null;
}

const staticRoot = resolveStaticRoot();

if (staticRoot) {
  app.use(express.static(staticRoot, { index: false }));
  app.get("*", (_request, response) => {
    response.sendFile(path.join(staticRoot, "index.html"));
  });
} else {
  app.get("*", (_request, response) => {
    response.status(503).send(
      "Stimpact generated a backend surface, but no built frontend assets were found. Run the frontend build before starting this server."
    );
  });
}

app.listen(port, () => {
  console.log(`Stimpact browser token surface listening on :${port}`);
});
