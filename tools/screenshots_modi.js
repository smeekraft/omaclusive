"use strict";
// Erzeugt die Screenshots für README und Handzettel (Einrichtung, Modi, Editor, Gleich zurück).
//   node --experimental-websocket tools/screenshots_modi.js
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execSync } = require("child_process");
const { token } = require("./token.js");

const root = path.resolve(__dirname, "..");
const port = Number(process.env.PORT || 8794);
const debugPort = Number(process.env.DEBUG_PORT || 9345);
const cfgPfad = path.join(root, "config.json");
const home = fs.mkdtempSync(path.join(os.tmpdir(), "omaclusive-home-"));
const bin = path.join(home, "bin");
fs.mkdirSync(bin);
fs.writeFileSync(path.join(bin, "pw-play"), "#!/bin/sh\nsleep 0.3\n", { mode: 0o755 });

function chromeBin() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["chromium", "google-chrome", "google-chrome-stable"]) {
    try { return execSync("command -v " + name, { encoding: "utf8" }).trim(); } catch (err) {}
  }
  throw new Error("kein Chrome gefunden");
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let body = "";
      res.on("data", chunk => { body += chunk; });
      res.on("end", () => { try { resolve(JSON.parse(body)); } catch (err) { reject(new Error(body.slice(0, 200))); } });
    }).on("error", reject);
  });
}

async function waitJson(url) {
  let last = "";
  for (let i = 0; i < 60; i++) {
    try { return await getJson(url); } catch (err) { last = err.message; await sleep(150); }
  }
  throw new Error("keine Antwort von " + url + " (" + last + ")");
}

function cdp(wsUrl, fehler) {
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
      fehler.push("Ausnahme: " + JSON.stringify(msg.params.exceptionDetails).slice(0, 300));
    }
    if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      fehler.push("console.error: " + msg.params.args.map(a => a.value || a.description).join(" ").slice(0, 300));
    }
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      const e = msg.params.entry;
      fehler.push("Log: " + e.text + " " + (e.url || ""));
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

async function ev(client, expression, awaitPromise) {
  const r = await client.send("Runtime.evaluate", { expression, awaitPromise: !!awaitPromise, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300));
  return r.result && r.result.value;
}



async function lauf(sprache, praefix) {
  const c = JSON.parse(fs.readFileSync(path.join(root, sprache === "en" ? "config.example.en.json" : "config.example.json"), "utf8"));
  c.hilferuf.testTage = 0;
  fs.writeFileSync(cfgPfad, JSON.stringify(c, null, 2));
  const server = spawn("python3", ["server.py"], { cwd: root, env: Object.assign({}, process.env, { PORT: String(port), HOME: home, PATH: bin + ":" + process.env.PATH }), stdio: "ignore" });
  await waitJson("http://127.0.0.1:" + port + "/api/bereit");
  const geheim = token(port, home, root);
  fs.rmSync("/tmp/omaclusive-chrome-shots", { recursive: true, force: true });
  const chrome = spawn(chromeBin(), ["--headless=new", "--disable-gpu", "--no-first-run", "--disable-dev-shm-usage", "--remote-allow-origins=*", "--window-size=1480,780", "--user-data-dir=/tmp/omaclusive-chrome-shots", "--remote-debugging-port=" + debugPort, "about:blank"], { stdio: "ignore" });
  let client = null;
  try {
    const list = await waitJson("http://127.0.0.1:" + debugPort + "/json/list");
    client = cdp(list.find(i => i.type === "page").webSocketDebuggerUrl, []);
    await client.opened;
    for (const m of ["Page.enable", "Runtime.enable"]) await client.send(m);
    const shot = async (name, w, h) => {
      await client.send("Emulation.setDeviceMetricsOverride", { width: w || 1480, height: h || 780, deviceScaleFactor: 1, mobile: false });
      await sleep(250);
      const img = await client.send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(root, "screenshots", praefix + name + ".png"), Buffer.from(img.data, "base64"));
    };
    const gehe = async url => { await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/" + url + "#" + geheim }); for (let i = 0; i < 60; i++) { if (await ev(client, "window.__ready === true")) break; await sleep(100); } await sleep(500); };
    const klick = async (x, y) => { await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 }); await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 }); await sleep(500); };
    await gehe("");
    await shot("einrichtung-1-bedienung");
    await klick(1110, 400); await shot("einrichtung-2-knoepfe");
    await klick(370, 400); await shot("einrichtung-3-auswahl");
    await klick(370, 400); // Einfach (Modus b)
    await sleep(800);
    await shot("start-modus-b");
    // Gleich zurück
    await ev(client, "C.zurueck.sekunden=12; C.zurueck.hinweisVorherSekunden=5; clearIdle(); aktiviere('links'); 0");
    await sleep(7600);
    await shot("gleich-zurueck");
    await gehe("editor.html");
    await shot("editor", 1480, 1500);
  } finally {
    if (client) client.close();
    chrome.kill("SIGTERM"); await sleep(300); try { chrome.kill("SIGKILL"); } catch (e) {}
    server.kill("SIGTERM"); await sleep(200); try { server.kill("SIGKILL"); } catch (e) {}
    for (const n of ["config.json", "config.json.bak"]) { try { fs.unlinkSync(path.join(root, n)); } catch (e) {} }
  }
}
(async () => { await lauf("de", "p3-"); await lauf("en", "p3-en-"); console.log("SHOTS_OK"); })().catch(e => { console.error(e); process.exit(1); });
process.on("exit", () => { try { fs.rmSync(home, { recursive: true, force: true }); } catch (e) {} });
