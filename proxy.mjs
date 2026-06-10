/**
 * Thin Node.js HTTP proxy — forwards all requests to the FastAPI server on port 8001.
 * Used by preview_start so the Claude preview tool can reach the app.
 */
import http from "http";

const UPSTREAM = "http://127.0.0.1:8001";
const PORT = 8000;

const server = http.createServer((req, res) => {
  const url = new URL(req.url, UPSTREAM);
  const options = {
    hostname: "127.0.0.1",
    port: 8001,
    path: url.pathname + url.search,
    method: req.method,
    headers: req.headers,
  };

  const proxy = http.request(options, (upRes) => {
    res.writeHead(upRes.statusCode, upRes.headers);
    upRes.pipe(res);
  });

  proxy.on("error", (err) => {
    res.writeHead(502);
    res.end(`Upstream error: ${err.message}`);
  });

  req.pipe(proxy);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Proxy listening on http://0.0.0.0:${PORT} → ${UPSTREAM}`);
});
