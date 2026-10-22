"use strict";
// Browser-Test des Drag-and-drop-Editors (Headless-Chrome, echter Server, Wegwerf-HOME).
//   node --experimental-websocket test_editor.js     (Node unter 22 braucht das Flag)
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execSync } = require("child_process");

const root = __dirname;
const port = Number(process.env.PORT || 8796);
const debugPort = Number(process.env.DEBUG_PORT || 9346);
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
      // Die Gamepad-Brücke (ws://localhost:8765) gibt es nur mit Knopf-Hardware.
      if (String(e.url || "").indexOf(":8765") !== -1 || String(e.text || "").indexOf("8765") !== -1) return;
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


const sleep2 = sleep;
const ergebnisse = [];
function pruefe(name, bedingung, detail) {
  ergebnisse.push({ name, ok: !!bedingung, detail });
  if (!bedingung) console.error("FEHLER:", name, detail === undefined ? "" : JSON.stringify(detail));
}
function aufraeumen() {
  for (const n of ["config.json", "config.json.bak"]) { try { fs.unlinkSync(path.join(root, n)); } catch (err) {} }
}
const pfadDatei = path.join(home, ".config", "omaclusive", "pfad-b.json");
const ev2 = (client, expr, wait) => ev(client, expr, wait);

async function lauf(sprache) {
  aufraeumen();
  const c = JSON.parse(fs.readFileSync(path.join(root, sprache === "en" ? "config.example.en.json" : "config.example.json"), "utf8"));
  c.einrichtung = { fertig: true, stand: 2 }; c.modus = "b"; c.zurueck.sekunden = 0;
  fs.writeFileSync(cfgPfad, JSON.stringify(c, null, 2));
  try { fs.unlinkSync(pfadDatei); } catch (err) {}
  const xdg = path.join(home, "xdg");
  fs.mkdirSync(xdg, { recursive: true, mode: 0o700 });
  const server = spawn("python3", ["server.py"], { cwd: root, env: Object.assign({}, process.env, { PORT: String(port), HOME: home, XDG_RUNTIME_DIR: xdg, PATH: bin + ":" + process.env.PATH }), stdio: "ignore" });
  await waitJson("http://127.0.0.1:" + port + "/api/bereit");
  const token = execSync("python3 " + JSON.stringify(path.join(root, "sitzung.py")) + " lesen " + port, { encoding: "utf8", env: Object.assign({}, process.env, { XDG_RUNTIME_DIR: xdg, HOME: home }) }).trim();
  fs.rmSync("/tmp/omaclusive-chrome-editor", { recursive: true, force: true });
  const chrome = spawn(chromeBin(), ["--headless=new", "--disable-gpu", "--no-first-run", "--disable-dev-shm-usage", "--remote-allow-origins=*", "--window-size=1400,2200", "--user-data-dir=/tmp/omaclusive-chrome-editor", "--remote-debugging-port=" + debugPort, "about:blank"], { stdio: "ignore" });
  const t = sprache.toUpperCase() + " Editor";
  const fehler = [];
  let client = null;
  try {
    const list = await waitJson("http://127.0.0.1:" + debugPort + "/json/list");
    const tab = list.find(item => item.webSocketDebuggerUrl && item.type === "page");
    client = cdp(tab.webSocketDebuggerUrl, fehler);
    await client.opened;
    for (const m of ["Page.enable", "Runtime.enable", "Log.enable"]) await client.send(m);
    await client.send("Emulation.setFocusEmulationEnabled", { enabled: true });
    await client.send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 2200, deviceScaleFactor: 1, mobile: false });
    await client.send("Network.setCookie", { name: "omaclusive", value: token, url: "http://127.0.0.1:" + port + "/", httpOnly: true, sameSite: "Lax" });
    await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/editor.html" });
    for (let i = 0; i < 60; i++) { if (await ev(client, "window.__ready === true")) break; await sleep(100); }
    await sleep(300);
    const zeilen = () => ev(client, "document.querySelectorAll('.zeile').length");
    const woerter = id => ev(client, "JSON.stringify(modell.screens['" + id + "'].liste.map(k=>k.wort))").then(JSON.parse);
    pruefe(t + ": feste Datei wird angezeigt", (await ev(client, "document.getElementById('datei').textContent")) === pfadDatei, await ev(client, "document.getElementById('datei').textContent"));
    pruefe(t + ": Pfad als Baum: drei Ebenen (Modus b)", (await ev(client, "document.querySelectorAll('.ebene').length")) === 3);
    pruefe(t + ": Karten sichtbar", (await zeilen()) >= 10, await zeilen());
    pruefe(t + ": Vorschau zeigt zwei Kacheln", (await ev(client, "document.querySelectorAll('#vorschau .kachel').length")) === 2 && (await ev(client, "document.getElementById('vL').textContent.length>0 && document.getElementById('vR').textContent.length>0")));
    pruefe(t + ": Hinweis Vorlage", (await ev(client, "document.getElementById('modusInfo').textContent")).length > 5);
    const start0 = await woerter("start");
    // ▼ auf der ersten Karte
    await ev(client, "document.querySelector('.ebene[data-ebene=\"start\"] .zeile button[aria-label]').click(); 0");
    // erster button ist ▲ (disabled); der zweite ▼
    await ev(client, "document.querySelectorAll('.ebene[data-ebene=\"start\"] .zeile')[0].querySelectorAll('button')[1].click(); 0");
    const start1 = await woerter("start");
    pruefe(t + ": ▼ tauscht die Reihenfolge", start1[0] === start0[1] && start1[1] === start0[0], { start0, start1 });
    pruefe(t + ": ungespeichert gemerkt", (await ev(client, "document.getElementById('status').textContent")).length > 3);
    // Tastatur: Alt+Pfeil hoch auf zweiter Zeile
    await ev(client, "document.querySelectorAll('.ebene[data-ebene=\"start\"] .zeile')[1].focus(); 0");
    await client.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38, modifiers: 1 });
    await client.send("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38, modifiers: 1 });
    await sleep(100);
    const start2 = await woerter("start");
    pruefe(t + ": Alt+Pfeil hoch (Tastatur) verschiebt zurück", start2[0] === start0[0], { start0, start2 });
    // Drag and drop mit der Maus: erste Karte von Start in die Ebene "steuern"
    const grab = await ev(client, "(()=>{const g=document.querySelector('.ebene[data-ebene=\"start\"] .zeile .griff');g.scrollIntoView({block:'center'});const r=g.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()");
    const ziel = await ev(client, "(()=>{const z=[...document.querySelectorAll('.ebene[data-ebene=\"steuern\"] .zeile')].pop();z.scrollIntoView({block:'center'});const r=z.getBoundingClientRect();return [r.left+r.width/2,r.bottom-4]})()");
    const grab2 = await ev(client, "(()=>{const g=document.querySelector('.ebene[data-ebene=\"start\"] .zeile .griff');const r=g.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()");
    const erstesWort = start2[0];
    const nSteuern = (await woerter("steuern")).length;
    await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: grab2[0], y: grab2[1] });
    await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: grab2[0], y: grab2[1], button: "left", buttons: 1, clickCount: 1 });
    await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: grab2[0] + 20, y: grab2[1] + 20, buttons: 1 });
    const zielNeu = await ev(client, "(()=>{const z=[...document.querySelectorAll('.ebene[data-ebene=\"steuern\"] .zeile')].pop();const r=z.getBoundingClientRect();return [r.left+r.width/2,r.bottom-4]})()");
    await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: zielNeu[0], y: zielNeu[1], buttons: 1 });
    pruefe(t + ": Ziehen zeigt Einfügemarke", await ev(client, "!!document.querySelector('.einfuegen')") && (await ev(client, "document.getElementById('ghost').style.display")) === "block");
    await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: zielNeu[0], y: zielNeu[1], button: "left", buttons: 0, clickCount: 1 });
    await sleep(150);
    const steuernNeu = await woerter("steuern");
    pruefe(t + ": Drag and drop verschiebt die Karte in eine andere Ebene", steuernNeu.length === nSteuern + 1 && steuernNeu[steuernNeu.length - 1] === erstesWort && !(await woerter("start")).includes(erstesWort), { steuernNeu, erstesWort });
    // Zurück in die Ebene über das Auswahlfeld
    await ev(client, "(()=>{const z=[...document.querySelectorAll('.ebene[data-ebene=\"steuern\"] .zeile')].pop();const s=z.querySelector('select');s.value='start';s.onchange();return 1})()");
    pruefe(t + ": Auswahlfeld „Ebene“ verschiebt zurück", (await woerter("start")).includes(erstesWort) && (await woerter("steuern")).length === nSteuern, await woerter("start"));
    // ausblenden: zweite Karte von Start
    await ev(client, "document.querySelectorAll('.ebene[data-ebene=\"start\"] .zeile')[1].querySelectorAll('button')[2].click(); 0");
    pruefe(t + ": Auge blendet aus", await ev(client, "modell.screens.start.liste[1].aus === true && document.querySelectorAll('.ebene[data-ebene=\"start\"] .zeile')[1].classList.contains('aus')"));
    // hinzufügen: Palette in Ebene "sagen"
    const vorher = (await woerter("sagen")).length;
    await ev(client, "(()=>{const s=document.getElementById('zielEbene');s.value='sagen';s.onchange();return 1})()");
    await ev(client, "[...document.querySelectorAll('#palette button')].find(b=>/Lauter|Louder|Bell|Klingel/.test(b.textContent)).click(); 0");
    pruefe(t + ": Karte aus der Bibliothek hinzufügen", (await woerter("sagen")).length === vorher + 1);
    // neue Ebene
    await ev(client, "(()=>{document.getElementById('neuName').value='Familie';neueEbene();return 1})()");
    pruefe(t + ": neue Ebene angelegt", await ev(client, "Object.keys(modell.screens).includes('familie')"));
    pruefe(t + ": Ebene ist im Baum", (await ev(client, "document.querySelectorAll('.ebene').length")) === 4);
    // Fehler beim Speichern: Ebene b darf nur 2 Ebenen haben; "familie" ist in "sagen" (Tiefe 2): ok. Test: alle Start-Karten ausblenden → Fehler
    const sichern = await ev(client, "JSON.stringify(modell)");
    await ev(client, "modell.screens.start.liste.forEach(k=>k.aus=true); speichern(); 0");
    await sleep(400);
    pruefe(t + ": ungültig → Fehler angezeigt, nichts geschrieben", (await ev(client, "document.getElementById('status').className")) === "fehler" && !fs.existsSync(pfadDatei), await ev(client, "document.getElementById('status').textContent"));
    await ev(client, "modell=JSON.parse(" + JSON.stringify(JSON.stringify(sichern)) + "); modell=JSON.parse(modell); zeichne(); 0").catch(() => {});
    await ev(client, "(()=>{modell.screens.start.liste.forEach((k,i)=>{if(i!==1)delete k.aus});zeichne();return 1})()");
    await ev(client, "speichern(); 0");
    await sleep(500);
    pruefe(t + ": Speichern klappt", (await ev(client, "document.getElementById('status').className")) === "ok" && fs.existsSync(pfadDatei), await ev(client, "document.getElementById('status').textContent"));
    const datei = JSON.parse(fs.readFileSync(pfadDatei, "utf8"));
    pruefe(t + ": Datei enthält Änderungen (ausgeblendet, neue Ebene)", datei.screens.start.liste[1].aus === true && !!datei.screens.familie, Object.keys(datei.screens));
    pruefe(t + ": Hinweis „eigener Pfad“", (await ev(client, "document.getElementById('modusInfo').textContent")).length > 5);
    // Die App benutzt den eigenen Pfad
    await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/" });
    for (let i = 0; i < 60; i++) { if (await ev(client, "window.__ready === true")) break; await sleep(100); }
    await sleep(500);
    const app = JSON.parse(await ev(client, "JSON.stringify({q:window.__pfadQuelle,m:window.__modus,n:C.screens.start.liste.length,familie:!!C.screens.familie,sichtbar:Pfad.karten(C.screens.start).length})"));
    pruefe(t + ": App nimmt den eigenen Pfad", app.q === "datei" && app.m === "b" && app.familie && app.sichtbar === app.n - 1, app);
    // Einstellungen zeigen Modus und Pfad
    await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/setup.html" });
    for (let i = 0; i < 60; i++) { if (await ev(client, "window.__ready === true")) break; await sleep(100); }
    await sleep(300);
    pruefe(t + ": Einstellungen zeigen den festen Pfad", (await ev(client, "document.getElementById('pfadDatei').textContent")) === pfadDatei);
    pruefe(t + ": Einstellungen zeigen den Modus", (await ev(client, "document.getElementById('modusBtn').textContent")).length > 5);
    // Zurücksetzen
    await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/editor.html" });
    for (let i = 0; i < 60; i++) { if (await ev(client, "window.__ready === true")) break; await sleep(100); }
    await sleep(300);
    await ev(client, "window.confirm=()=>true; zuruecksetzen(); 0");
    await sleep(500);
    pruefe(t + ": Zurücksetzen löscht die Datei und lädt die Vorlage", !fs.existsSync(pfadDatei) && (await ev(client, "Object.keys(modell.screens).length")) === 3 && (await ev(client, "document.getElementById('status').className")) === "ok");
    // Der absichtlich ungültige Speicherversuch (400) steht auch im Browser-Log: das ist kein Fehler der Seite.
    const f = fehler.filter((x, i, a) => a.indexOf(x) === i && !/status of 400.*\/api\/pfad$/.test(x));
    pruefe(t + ": keine JS-Fehler in der Konsole", f.length === 0, f);
  } catch (err) {
    pruefe(t + ": läuft durch", false, String(err && err.stack || err));
  } finally {
    if (client) client.close();
    chrome.kill("SIGTERM"); await sleep(300); try { chrome.kill("SIGKILL"); } catch (err) {}
    server.kill("SIGTERM"); await sleep(200); try { server.kill("SIGKILL"); } catch (err) {}
    aufraeumen();
  }
}

(async () => {
  const T0 = Date.now();
  for (const sprache of ["de", "en"]) await lauf(sprache);
  const schlecht = ergebnisse.filter(r => !r.ok);
  console.log(ergebnisse.length + " Prüfungen, " + schlecht.length + " Fehler, " + Math.round((Date.now() - T0) / 1000) + " s");
  if (schlecht.length) { schlecht.forEach(r => console.log(" - " + r.name)); process.exitCode = 1; } else console.log("EDITOR_OK");
})().catch(err => { console.error(err && err.stack || err); aufraeumen(); process.exit(1); });
process.on("exit", () => { aufraeumen(); try { fs.rmSync(home, { recursive: true, force: true }); } catch (err) {} });
