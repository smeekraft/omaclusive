"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn, execSync } = require("child_process");
const os = require("os");
const { startUrl } = require("./tools/token.js");

function chromeBin() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["chromium", "google-chrome", "google-chrome-stable"]) {
    try { return execSync("command -v " + name, { encoding: "utf8" }).trim(); } catch (err) {}
  }
  throw new Error("kein Chrome gefunden");
}

const root = __dirname;
const port = Number(process.env.PORT || 8799);
const debugPort = Number(process.env.DEBUG_PORT || 9333);
// Eigener Server mit Wegwerf-HOME, Start über den echten Startweg (Einmal-Code, kein Geheimnis in der Adresse).
const home = fs.mkdtempSync(path.join(os.tmpdir(), "omaclusive-bild-"));
let server = null;
const cfgPfad = path.join(root, "config.json");
let cfgAlt = null;
async function serverStarten() {
  cfgAlt = fs.existsSync(cfgPfad) ? fs.readFileSync(cfgPfad) : null;
  const c = JSON.parse(fs.readFileSync(path.join(root, "config.example.json"), "utf8"));
  c.einrichtung = { fertig: true, stand: 2 };
  fs.writeFileSync(cfgPfad, JSON.stringify(c, null, 2));
  const bin = path.join(home, "bin");
  fs.mkdirSync(bin, { recursive: true });
  fs.writeFileSync(path.join(bin, "pw-play"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  const env = Object.assign({}, process.env, { PORT: String(port), HOME: home, PATH: bin + ":" + process.env.PATH });
  delete env.XDG_RUNTIME_DIR;
  server = spawn("python3", ["server.py"], { cwd: root, env, stdio: "ignore" });
  await waitJson("http://127.0.0.1:" + port + "/api/bereit");
}
function seite() {
  const alt = process.env.XDG_RUNTIME_DIR; delete process.env.XDG_RUNTIME_DIR;
  try { return startUrl(port, home, root, "index.html?selftest=1"); }
  finally { if (alt !== undefined) process.env.XDG_RUNTIME_DIR = alt; }
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, res => {
      let body = "";
      res.on("data", chunk => { body += chunk; });
      res.on("end", () => {
        try { resolve(JSON.parse(body)); }
        catch (err) { reject(new Error(body.slice(0, 240))); }
      });
    });
    req.on("error", reject);
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitJson(url) {
  let last = "";
  for (let i = 0; i < 50; i++) {
    try { return await getJson(url); }
    catch (err) { last = err.message; await sleep(150); }
  }
  throw new Error("keine Antwort von " + url + " (" + last + ")");
}

function cdp(wsUrl) {
  let id = 0;
  const pending = new Map();
  const ws = new WebSocket(wsUrl);
  const opened = new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve());
    ws.addEventListener("error", () => reject(new Error("DevTools nicht verbunden")));
  });
  ws.addEventListener("message", ev => {
    const msg = JSON.parse(ev.data);
    if (msg.method === "Runtime.exceptionThrown") {
      console.error("SEITE", JSON.stringify(msg.params.exceptionDetails));
    }
    if (msg.id && pending.has(msg.id)) {
      const job = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) job.reject(new Error(JSON.stringify(msg.error)));
      else job.resolve(msg.result);
    }
  });
  return {
    opened,
    send(method, params) {
      const mine = ++id;
      ws.send(JSON.stringify({ id: mine, method, params: params || {} }));
      return new Promise((resolve, reject) => pending.set(mine, { resolve, reject }));
    },
    close() { try { ws.close(); } catch (err) {} },
  };
}

async function evalValue(client, expression, awaitPromise) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: !!awaitPromise,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(JSON.stringify(result.exceptionDetails));
  }
  return result.result && result.result.value;
}

async function shot(client, name) {
  const image = await client.send("Page.captureScreenshot", { format: "png" });
  const file = path.join(root, "screenshots", name);
  fs.writeFileSync(file, Buffer.from(image.data, "base64"));
  return file;
}

async function main() {
  await serverStarten();
  fs.rmSync("/tmp/omaclusive-chrome-test", { recursive: true, force: true });
  const chrome = spawn(chromeBin(), [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    "--remote-allow-origins=*",
    "--window-size=1480,780",
    "--user-data-dir=/tmp/omaclusive-chrome-test",
    "--remote-debugging-port=" + debugPort,
    seite(),
  ], { stdio: "ignore" });
  let client = null;
  try {
    const list = await waitJson("http://127.0.0.1:" + debugPort + "/json/list");
    const tab = list.find(item => item.webSocketDebuggerUrl && item.type === "page") || list.find(item => item.webSocketDebuggerUrl);
    if (!tab) throw new Error("keine Testseite in " + JSON.stringify(list).slice(0, 400));
    client = cdp(tab.webSocketDebuggerUrl);
    await client.opened;
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: 1480,
      height: 780,
      deviceScaleFactor: 1,
      mobile: false,
    });
    let ready = false;
    for (let i = 0; i < 50; i++) {
      ready = await evalValue(client, "window.__ready === true");
      if (ready) break;
      await sleep(100);
    }
    if (!ready) throw new Error("Seite nicht bereit");
    await shot(client, "p2-start.png");
    const bilder = await evalValue(client, "window.__shot('bilder')");
    if (bilder !== "ordner-bilder") throw new Error("Screenshot Bilder: " + bilder);
    await shot(client, "p2-bilder.png");
    const steuern = await evalValue(client, "window.__shot('steuern')");
    if (steuern !== "steuern") throw new Error("Screenshot Steuern: " + steuern);
    await shot(client, "p2-steuern.png");
    await evalValue(client, "window.__shot('start')");
    const ergebnis = await evalValue(client, "window.__runSelftest()", true);
    console.log(ergebnis);
    if (ergebnis !== "SELFTEST PASS") process.exitCode = 1;
  } finally {
    if (client) client.close();
    chrome.kill("SIGTERM");
    await sleep(300);
    try { chrome.kill("SIGKILL"); } catch (err) {}
    if (server) server.kill("SIGTERM");
    if (cfgAlt) fs.writeFileSync(cfgPfad, cfgAlt);
    else for (const n of ["config.json", "config.json.bak"]) { try { fs.unlinkSync(path.join(root, n)); } catch (err) {} }
    fs.rmSync(home, { recursive: true, force: true });
  }
}

main().catch(err => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
