import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";
import http from "node:http";

const host = process.env.HOST || process.env.SERVER_HOST || "0.0.0.0";
const port = Number.parseInt(process.env.PORT || process.env.SERVER_PORT || "8080", 10);
const root = resolve(process.env.ACTIVITY_CLIENT_DIST || join(process.cwd(), "client", "dist"));
const indexPath = join(root, "index.html");

const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".ico", "image/x-icon"],
  [".wasm", "application/wasm"],
]);

function sendFile(res, path) {
  const type = contentTypes.get(extname(path).toLowerCase()) || "application/octet-stream";
  res.writeHead(200, {
    "Content-Type": type,
    "Cache-Control": path === indexPath ? "no-cache" : "public, max-age=31536000, immutable",
  });
  createReadStream(path).pipe(res);
}

function safeResolve(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0] || "/");
  const cleaned = normalize(decoded).replace(/^(\.\.[/\\])+/, "");
  const candidate = resolve(root, `.${sep}${cleaned}`);
  return candidate.startsWith(root) ? candidate : indexPath;
}

const server = http.createServer((req, res) => {
  if (req.url === "/healthz" || req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ ok: true, service: "activity-client", root }));
    return;
  }

  let target = safeResolve(req.url || "/");
  if (!existsSync(target) || statSync(target).isDirectory()) {
    target = indexPath;
  }
  if (!existsSync(target)) {
    res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Activity client build is missing. Run npm run build first.");
    return;
  }
  sendFile(res, target);
});

server.listen(port, host, () => {
  console.log(`Activity client serving ${root} on ${host}:${port}`);
});
