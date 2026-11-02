"use strict";
// Browser-Test zu omacom/omarchy-plugin-marketplace#12234: kein Geheimnis in Cookie, localStorage,
// Adresse oder Log, und eine Seite eines anderen lokalen Kontos auf einem anderen 127.0.0.1-Port im
// selben Browser kommt weder an das Token noch an die API (HTTP und WebSocket: 401/403).
//   node --experimental-websocket test_sitzung_browser.js     (Node unter 22 braucht das Flag)
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execSync, execFileSync } = require("child_process");
const { token, startUrl } = require("./tools/token.js");

const root = __dirname;
const port = Number(process.env.PORT || 8793);
const fremdPort = port + 1; // "anderes Konto"
const debugPort = Number(process.env.DEBUG_PORT || 9351);
const cfgPfad = path.join(root, "config.json");
const home = fs.mkdtempSync(path.join(os.tmpdir(), "omaclusive-browser-"));
const profil = fs.mkdtempSync(path.join(os.tmpdir(), "omaclusive-chrome-sitzung-"));
const bin = path.join(home, "bin");
fs.mkdirSync(bin);
fs.writeFileSync(path.join(bin, "pw-play"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function chromeBin() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["chromium", "google-chrome", "google-chrome-stable"]) {
    try { return execSync("command -v " + name, { encoding: "utf8" }).trim(); } catch (err) {}
  }
  throw new Error("kein Chrome gefunden");
}

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
  for (let i = 0; i < 80; i++) {
    try { return await getJson(url); } catch (err) { last = err.message; await sleep(150); }
  }
  throw new Error("keine Antwort von " + url + " (" + last + ")");
}

function cdp(wsUrl) {
  let id = 0;
  const pending = new Map();
  const handler = [];
  const ws = new WebSocket(wsUrl);
  const opened = new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve());
    ws.addEventListener("error", () => reject(new Error("DevTools nicht verbunden")));
  });
  ws.addEventListener("message", ev => {
    const msg = JSON.parse(ev.data);
    if (msg.method) handler.forEach(h => h(msg));
    if (msg.id && pending.has(msg.id)) {
      const job = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) job.reject(new Error(JSON.stringify(msg.error)));
      else job.resolve(msg.result);
    }
  });
  return {
    opened,
    on(h) { handler.push(h); },
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

const ergebnisse = [];
function pruefe(name, bedingung, detail) {
  ergebnisse.push({ name, ok: !!bedingung });
  if (!bedingung) console.error("FEHLER:", name, detail === undefined ? "" : JSON.stringify(detail));
}

// Die Seite des "anderen Kontos": liest, was sie kann, und versucht die private API (HTTP und WebSocket).
function angriffsSeite() {
  const ziel = "127.0.0.1:" + port;
  return `<!doctype html><meta charset="utf-8"><title>fremd</title><body><script>
window.__ergebnis = (async () => {
  const r = { cookie: document.cookie, local: JSON.stringify(Object.assign({}, localStorage)), session: JSON.stringify(Object.assign({}, sessionStorage)) };
  try { const a = await fetch("http://${ziel}/config.json", { credentials: "include" }); r.cors = "gelesen " + a.status; } catch (e) { r.cors = "blockiert"; }
  try { await fetch("http://${ziel}/api/pfad", { mode: "no-cors", credentials: "include" }); r.get = "gesendet"; } catch (e) { r.get = "fehler"; }
  try { await fetch("http://${ziel}/api/back", { method: "POST", mode: "no-cors", credentials: "include", body: "{}" }); r.post = "gesendet"; } catch (e) { r.post = "fehler"; }
  r.ws = await new Promise(res => {
    try {
      const w = new WebSocket("ws://${ziel}/api/eingabe", ["omaclusive"]);
      w.onopen = () => res("offen"); w.onerror = () => res("abgelehnt"); setTimeout(() => res("zeit"), 3000);
    } catch (e) { res("fehler"); }
  });
  r.wsTok = await new Promise(res => {
    try {
      const w = new WebSocket("ws://${ziel}/api/eingabe", ["omaclusive", "omaclusive-token." + "x".repeat(43)]);
      w.onopen = () => res("offen"); w.onerror = () => res("abgelehnt"); setTimeout(() => res("zeit"), 3000);
    } catch (e) { res("fehler"); }
  });
  // Die App im Rahmen: darf nicht eingebettet werden (X-Frame-Options/frame-ancestors).
  r.rahmen = await new Promise(res => {
    const f = document.createElement("iframe"); f.src = "http://${ziel}/index.html";
    f.onload = () => { try { res("lesbar " + f.contentWindow.sessionStorage.length); } catch (e) { res("gesperrt"); } };
    document.body.appendChild(f); setTimeout(() => res("zeit"), 3000);
  });
  return JSON.stringify(r);
})();
</script>`;
}

async function main() {
  // Config: Eingabekanal an, damit /api/eingabe wirklich prüft (sonst wäre es nur 404)
  const c = JSON.parse(fs.readFileSync(path.join(root, "config.example.json"), "utf8"));
  c.einrichtung = { fertig: true, stand: 2 }; c.zurueck.sekunden = 0; c.eingabe = { websocket: true };
  const cfgAlt = fs.existsSync(cfgPfad) ? fs.readFileSync(cfgPfad) : null;
  fs.writeFileSync(cfgPfad, JSON.stringify(c, null, 2));
  const bilder = path.join(home, "Bilder", "Omaclusive");
  fs.mkdirSync(bilder, { recursive: true });
  fs.writeFileSync(path.join(bilder, "a.png"), Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64"));

  const logPfad = path.join(home, "server.err");
  const logFd = fs.openSync(logPfad, "w");
  const env = Object.assign({}, process.env, { PORT: String(port), HOME: home, PATH: bin + ":" + process.env.PATH, PYTHONUNBUFFERED: "1" });
  delete env.XDG_RUNTIME_DIR;
  const server = spawn("python3", ["server.py"], { cwd: root, env, stdio: ["ignore", logFd, logFd] });
  const fremd = http.createServer((req, res) => { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end(angriffsSeite()); });
  await new Promise(r => fremd.listen(fremdPort, "127.0.0.1", r));
  let chrome = null;
  let app = null, angreifer = null;
  try {
    await waitJson("http://127.0.0.1:" + port + "/api/bereit");
    const alt = process.env.XDG_RUNTIME_DIR; delete process.env.XDG_RUNTIME_DIR;
    const geheim = token(port, home, root);
    const boot = startUrl(port, home, root, "");
    if (alt !== undefined) process.env.XDG_RUNTIME_DIR = alt;
    const bootPfad = decodeURIComponent(boot.replace(/^file:\/\//, ""));
    const bootHtml = fs.readFileSync(bootPfad, "utf8");
    const code = (bootHtml.match(/name="code" value="([A-Za-z0-9_-]+)"/) || [])[1] || "";
    pruefe("Startdatei trägt nur einen Code, nicht das Geheimnis", code && !bootHtml.includes(geheim) && !boot.includes(geheim) && !boot.includes(code));

    chrome = spawn(chromeBin(), ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
      "--remote-allow-origins=*", "--window-size=1200,800", "--user-data-dir=" + profil, "--remote-debugging-port=" + debugPort, "about:blank"], { stdio: "ignore" });
    const list = await waitJson("http://127.0.0.1:" + debugPort + "/json/list");
    const tab = list.find(item => item.webSocketDebuggerUrl && item.type === "page");
    app = cdp(tab.webSocketDebuggerUrl);
    await app.opened;
    const wsApp = [];
    app.on(m => { if (m.method === "Network.webSocketHandshakeResponseReceived") wsApp.push(m.params.response.status); });
    for (const m of ["Page.enable", "Runtime.enable", "Network.enable"]) await app.send(m);
    // Altes Cookie einer früheren Version: muss verschwinden und darf nichts öffnen
    await app.send("Network.setCookie", { name: "omaclusive_session", value: geheim, url: "http://127.0.0.1:" + port + "/" });

    await app.send("Page.navigate", { url: boot });
    for (let i = 0; i < 80; i++) { if (await ev(app, "window.__ready === true").catch(() => false)) break; await sleep(100); }
    pruefe("App ist über den Startweg bereit", await ev(app, "window.__ready === true"));
    const btoken = await ev(app, "sessionStorage.getItem('omaclusive-sitzung') || ''");
    pruefe("Browser-Token liegt in sessionStorage dieser Herkunft", /^[A-Za-z0-9_-]{40,}$/.test(btoken));
    pruefe("Browser bekommt nie das Datei-Geheimnis", btoken !== geheim);
    pruefe("Startdatei nach dem Einlösen gelöscht", !fs.existsSync(bootPfad));
    const href = await ev(app, "location.href");
    pruefe("Adresse ohne Token, Code oder Fragment", !href.includes(btoken) && !href.includes(geheim) && !href.includes(code) && !href.includes("#"), href);
    const verlauf = await app.send("Page.getNavigationHistory");
    const urls = verlauf.entries.map(e => e.url);
    pruefe("Verlauf ohne Token, Geheimnis oder Code", urls.every(u => !u.includes(btoken) && !u.includes(geheim) && !u.includes(code)), urls);
    pruefe("document.cookie ist leer (altes Cookie entfernt)", (await ev(app, "document.cookie")) === "", await ev(app, "document.cookie"));
    const kekse = (await app.send("Network.getAllCookies")).cookies;
    pruefe("keine Cookies für 127.0.0.1 im Browser", kekse.filter(k => k.domain === "127.0.0.1").length === 0, kekse);
    const lokal = await ev(app, "JSON.stringify(Object.assign({}, localStorage))");
    pruefe("localStorage leer", lokal === "{}", lokal);
    pruefe("kein Token als globale Variable", (await ev(app, "Object.keys(window).filter(k => { try { return String(window[k]).includes(sessionStorage.getItem('omaclusive-sitzung')); } catch (e) { return false; } }).length")) === 0);

    // HMAC im Browser = HMAC im Server
    const msg = "/api/datei?quelle=bilder&name=a%20b.png";
    const js = await ev(app, "Sitzung._hmac(sessionStorage.getItem('omaclusive-sitzung'), 'medien\\n' + " + JSON.stringify(msg) + ")");
    const py = execFileSync("python3", ["-c", "import sys, sitzung; print(sitzung.signatur(sys.argv[1], sys.argv[2]), end='')", btoken, msg], { cwd: root, encoding: "utf8" });
    pruefe("Signatur im Browser und im Server gleich", js === py, { js, py });
    // Bild mit Signatur lädt, ohne nicht
    const bild = await ev(app, `Promise.all([Sitzung.src('/api/datei?quelle=bilder&name=a.png'), '/api/datei?quelle=bilder&name=a.png'].map(u => new Promise(r => {
      const i = new Image(); i.onload = () => r('ok ' + u.includes('sig=')); i.onerror = () => r('fehler'); i.src = u; }))).then(a => JSON.stringify(a))`, true);
    pruefe("Bild mit Signatur lädt, ohne Signatur nicht", bild === JSON.stringify(["ok true", "fehler"]), bild);
    pruefe("Signierte Adresse enthält das Token nicht", !(await ev(app, "Sitzung.src('/api/medium?name=x.webm')")).includes(btoken));
    // Eigener WebSocket: Token im Unterprotokoll, nicht in der Adresse; Handshake 101
    await sleep(800);
    pruefe("eigener Eingabekanal: Handshake 101", wsApp.includes(101), wsApp);

    // Navigation in der App behält den Zugang (gleicher Tab, gleiche Herkunft), ohne Cookie
    await app.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/setup.html" });
    await sleep(1500);
    const pfadStatus = await ev(app, "fetch('/api/pfad').then(r => r.status)", true);
    pruefe("Einstellungen erreichen die API nach Navigation (200)", pfadStatus === 200, pfadStatus);
    const xss = await ev(app, `new Promise(r => { const b = document.createElement('button');
      kachelInhalt(b, 'img/glatt/sagen.svg', '<img src=x onerror="window.__xss=1">'); document.body.appendChild(b);
      setTimeout(() => r(JSON.stringify({ imgs: b.querySelectorAll('img').length, text: b.textContent, xss: !!window.__xss })), 400); })`, true);
    pruefe("Kachel-Wort aus Dateinamen wird nicht als HTML ausgeführt", xss === JSON.stringify({ imgs: 1, text: '<img src=x onerror="window.__xss=1">', xss: false }), xss);

    // --- Seite des anderen Kontos auf einem anderen Port, im selben Browser ---
    const ziel = await app.send("Target.createTarget", { url: "about:blank" });
    const liste2 = await getJson("http://127.0.0.1:" + debugPort + "/json/list");
    const tab2 = liste2.find(t => t.id === ziel.targetId);
    angreifer = cdp(tab2.webSocketDebuggerUrl);
    await angreifer.opened;
    const antworten = [];
    const anfragen = new Map();
    angreifer.on(m => {
      if (m.method === "Network.requestWillBeSent") anfragen.set(m.params.requestId, m.params.request.url);
      // ExtraInfo kommt auch für Antworten, die CORS dem Skript vorenthält (opak oder blockiert)
      if (m.method === "Network.responseReceivedExtraInfo") {
        const url = anfragen.get(m.params.requestId) || "";
        if (url.includes("127.0.0.1:" + port + "/")) antworten.push([url, m.params.statusCode]);
      }
      if (m.method === "Network.webSocketHandshakeResponseReceived") antworten.push(["ws", m.params.response.status]);
    });
    for (const m of ["Page.enable", "Runtime.enable", "Network.enable"]) await angreifer.send(m);
    await angreifer.send("Page.navigate", { url: "http://127.0.0.1:" + fremdPort + "/" });
    let roh = null;
    for (let i = 0; i < 50 && !roh; i++) { await sleep(200); roh = await ev(angreifer, "window.__ergebnis || null", true).catch(() => null); }
    const r = JSON.parse(roh || "{}");
    console.log("fremde Seite (Port " + fremdPort + "):", roh);
    await sleep(500);
    const alles = JSON.stringify(r);
    pruefe("fremde Seite: kein Geheimnis in document.cookie", r.cookie === "" && !alles.includes(btoken) && !alles.includes(geheim), r);
    pruefe("fremde Seite: kein Token in local/sessionStorage", r.local === "{}" && r.session === "{}", r);
    pruefe("fremde Seite: config.json nicht lesbar (CORS)", r.cors === "blockiert", r.cors);
    pruefe("fremde Seite: WebSocket abgelehnt", r.ws === "abgelehnt" && r.wsTok === "abgelehnt", r);
    pruefe("fremde Seite: App lässt sich nicht einbetten/auslesen", r.rahmen !== "lesbar 1" && !String(r.rahmen).startsWith("lesbar"), r.rahmen);
    const api = antworten.filter(a => a[0] !== "ws" && /\/(api\/|config\.json)/.test(a[0]));
    pruefe("fremde Seite: HTTP-Anfragen an die API bekommen 401/403", api.length >= 2 && api.every(a => a[1] === 401 || a[1] === 403), antworten);
    console.log("Antworten des Servers an die fremde Seite:", JSON.stringify(antworten));
    const ws = antworten.filter(a => a[0] === "ws");
    pruefe("fremde Seite: WebSocket-Handshakes bekommen 401/403 (kein 101)", ws.every(a => a[1] === 401 || a[1] === 403), antworten);
    const log = fs.readFileSync(logPfad, "utf8");
    pruefe("Server-Log ohne Geheimnis, Token oder Code", !log.includes(geheim) && !log.includes(btoken) && !log.includes(code));
  } finally {
    if (app) app.close();
    if (angreifer) angreifer.close();
    if (chrome) { chrome.kill("SIGTERM"); await sleep(300); try { chrome.kill("SIGKILL"); } catch (err) {} }
    server.kill("SIGTERM");
    fremd.close();
    await sleep(200);
    if (cfgAlt) fs.writeFileSync(cfgPfad, cfgAlt); else { for (const n of ["config.json", "config.json.bak"]) { try { fs.unlinkSync(path.join(root, n)); } catch (err) {} } }
    fs.rmSync(profil, { recursive: true, force: true });
    fs.rmSync(home, { recursive: true, force: true });
  }
  const fehler = ergebnisse.filter(e => !e.ok);
  console.log(ergebnisse.length + " Prüfungen, " + fehler.length + " Fehler");
  if (fehler.length) process.exit(1);
  console.log("SITZUNG_BROWSER_OK");
}

main().catch(err => { console.error(err && err.stack ? err.stack : err); process.exit(1); });
