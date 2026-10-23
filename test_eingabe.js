"use strict";
// Echter Browser-Test der Eingabe (Headless-Chrome, echter Server, Tastatur und Maus über DevTools).
// Prüft Einrichtung und App, Zwei-Knopf und Ein-Knopf, DE und EN. Legt kurz eine config.json an und
// löscht sie danach wieder. Spielt keinen Ton (kleiner Ersatz-Player), nutzt ein Wegwerf-HOME.
//   node test_eingabe.js            (Chrome: Umgebungsvariable CHROME, sonst chromium oder google-chrome)
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execSync } = require("child_process");
const { token } = require("./tools/token.js");

const root = __dirname;
const port = Number(process.env.PORT || 8798);
const debugPort = Number(process.env.DEBUG_PORT || 9344);
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

const TASTEN = {
  ArrowLeft: { key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 },
  ArrowRight: { key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 },
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 },
  ArrowUp: { key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38 },
  Space: { key: " ", code: "Space", windowsVirtualKeyCode: 32, text: " " },
  Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" },
};

async function taste(client, name, halteMs) {
  const t = TASTEN[name];
  await client.send("Input.dispatchKeyEvent", Object.assign({ type: t.text ? "keyDown" : "rawKeyDown" }, t));
  if (halteMs) await sleep(halteMs);
  await client.send("Input.dispatchKeyEvent", { type: "keyUp", key: t.key, code: t.code, windowsVirtualKeyCode: t.windowsVirtualKeyCode });
}

async function maus(client, x, y, knopf, halteMs) {
  const b = knopf === "rechts" ? "right" : "left";
  const buttons = knopf === "rechts" ? 2 : 1;
  await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: b, buttons, clickCount: 1 });
  if (halteMs) await sleep(halteMs);
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: b, buttons: 0, clickCount: 1 });
}

const zustand = client => ev(client, "JSON.stringify({phase:window.__phase,screen:window.__screen,paar:window.__paar,fokus:window.__fokus,frage:window.__frage,schritt:window.__schritt,verworfen:window.__verworfen||0,eingaben:window.__eingaben||0,scan:window.__scan,url:location.pathname})").then(JSON.parse);

function schreibeConfig(sprache, aendern) {
  const quelle = sprache === "en" ? "config.example.en.json" : "config.example.json";
  const c = JSON.parse(fs.readFileSync(path.join(root, quelle), "utf8"));
  c.hilferuf = Object.assign({}, c.hilferuf, { testTage: 0 });
  c.zurueck.sekunden = 2; // alter Fehler: die erste Einrichtung endete nach dieser Zeit von selbst
  c.zurueck.hinweisVorherSekunden = 1;
  c.radio = { modus: "browser", name: "Radio", url: "", stream: "" }; // Tests dürfen nie einen Browser öffnen
  c.erinnerungPruefSekunden = 300; // Erinnerungen haben einen eigenen Lauf
  c.waehlSekunden = 0; // die Wahl-Wartezeit hat einen eigenen Lauf, sonst wartet jeder Test 3 s
  c.modus = "c"; // der Pfad gleicht der Vorlage "mehr Auswahl" (wie der alte Standard); Modi prüft ein eigener Lauf
  aendern(c);
  if (c.einrichtung && c.einrichtung.sprache === undefined) c.einrichtung.sprache = true; // die Sprachfrage hat eigene Läufe
  if (c.einrichtung && c.einrichtung.fertig === true && c.einrichtung.stand === undefined) c.einrichtung.stand = 2;
  fs.writeFileSync(cfgPfad, JSON.stringify(c, null, 2));
}

function aufraeumen() {
  for (const n of ["config.json", "config.json.bak"]) {
    try { fs.unlinkSync(path.join(root, n)); } catch (err) {}
  }
  // Testdaten (Bilder, Filme, Erinnerungen) bleiben nie für den nächsten Lauf liegen
  for (const d of ["Bilder", "Videos"]) { try { fs.rmSync(path.join(home, d), { recursive: true, force: true }); } catch (err) {} }
  try { fs.unlinkSync(path.join(home, ".config", "omaclusive", "pflege.json")); } catch (err) {}
}

let server = null;
let chrome = null;
let sitzungToken = "";
async function startUmgebung(url) {
  server = spawn("python3", ["server.py"], {
    cwd: root,
    env: Object.assign({}, process.env, { PORT: String(port), HOME: home, PATH: bin + ":" + process.env.PATH }),
    stdio: "ignore",
  });
  await waitJson("http://127.0.0.1:" + port + "/api/bereit");
  sitzungToken = token(port, home, root);
  fs.rmSync("/tmp/omaclusive-chrome-eingabe", { recursive: true, force: true });
  chrome = spawn(chromeBin(), [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
    "--remote-allow-origins=*", "--window-size=1480,780", "--user-data-dir=/tmp/omaclusive-chrome-eingabe",
    "--remote-debugging-port=" + debugPort, "about:blank",
  ], { stdio: "ignore" });
  const list = await waitJson("http://127.0.0.1:" + debugPort + "/json/list");
  const tab = list.find(item => item.webSocketDebuggerUrl && item.type === "page");
  const fehler = [];
  const client = cdp(tab.webSocketDebuggerUrl, fehler);
  await client.opened;
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Log.enable");
  await client.send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await client.send("Emulation.setDeviceMetricsOverride", { width: 1480, height: 780, deviceScaleFactor: 1, mobile: false });
  await client.send("Page.addScriptToEvaluateOnNewDocument", { source: "window.__ctx=[];addEventListener('contextmenu',e=>window.__ctx.push(e));" });
  await client.send("Page.navigate", { url: "http://127.0.0.1:" + port + "/" + (url || "") + "#" + sitzungToken });
  for (let i = 0; i < 60; i++) {
    if (await ev(client, "window.__ready === true")) break;
    await sleep(100);
  }
  if (!(await ev(client, "window.__ready === true"))) throw new Error("Seite nicht bereit");
  await sleep(300);
  return { client, fehler };
}

async function stopUmgebung(umg) {
  if (umg && umg.client) umg.client.close();
  if (chrome) { chrome.kill("SIGTERM"); await sleep(300); try { chrome.kill("SIGKILL"); } catch (err) {} chrome = null; }
  if (server) { server.kill("SIGTERM"); await sleep(200); try { server.kill("SIGKILL"); } catch (err) {} server = null; }
  aufraeumen();
}

const ergebnisse = [];
function pruefe(name, bedingung, detail) {
  ergebnisse.push({ name, ok: !!bedingung, detail });
  if (!bedingung) console.error("FEHLER:", name, detail === undefined ? "" : JSON.stringify(detail));
}

const SPAET = 380; // etwas mehr als die Sperrzeit von 300 ms

// Gemeinsamer Ablauf: Pfeiltasten und Mausklicks auf die Wahl "links/rechts".
async function szenario(titel, sprache, aendern, url, ablauf) {
  if (process.env.NUR && titel.indexOf(process.env.NUR) === -1) return; // zum schnellen Eingrenzen
  aufraeumen();
  schreibeConfig(sprache, aendern);
  let umg = null;
  try {
    umg = await startUmgebung(url);
    await ablauf(umg.client, titel);
    const f = umg.fehler.filter((x, i, a) => a.indexOf(x) === i && !/404 \(Not Found\) http:\/\/127\.0\.0\.1:\d+\/api\/medium\?name=/.test(x) && !/400 \(Bad Request\) http:\/\/127\.0\.0\.1:\d+\/api\/pflege/.test(x));
    pruefe(titel + ": keine JS-Fehler in der Konsole", f.length === 0, f);
  } catch (err) {
    pruefe(titel + ": läuft durch", false, String(err && err.stack || err));
  } finally {
    await stopUmgebung(umg);
  }
}

const LEER = [700, 14];  // freie Stelle in der oberen Leiste (keine Kachel, nicht die Einstellungstaste)
const LINKE = [370, 400];
const RECHTE = [1110, 400];

const FRAGE = {
  de: { bedienung: "Wie willst du bedienen?", knopf: "Wie viele Knöpfe?", modus: "Wie viel Auswahl?", autostart: "Mit dem Rechner starten?" },
  en: { bedienung: "How do you want to control it?", knopf: "How many buttons?", modus: "How many choices?", autostart: "Start at login?" },
};
const WORT = {
  de: { stimme: "Stimme", knoepfe: "Knöpfe, Maus, Tasten", zwei: "Zwei Knöpfe", ein: "Ein Knopf", b: "Einfach", a: "Ganz einfach", c: "Mehr Auswahl", nein: "Nein", ja: "Ja" },
  en: { stimme: "Voice", knoepfe: "Buttons, mouse, keys", zwei: "Two buttons", ein: "One button", b: "Simple", a: "Very simple", c: "More choices", nein: "No", ja: "Yes" },
};
const kacheln = client => ev(client, "document.querySelectorAll('button.karte').length");
const ebene = client => ev(client, "document.getElementById('ebene').textContent");
const gesprochen = client => ev(client, "JSON.stringify(window.__sprache||[])").then(JSON.parse);
const autostartDa = () => fs.existsSync(path.join(home, ".config", "autostart", "omaclusive.desktop")) || (fs.existsSync(path.join(home, ".config", "autostart")) && fs.readdirSync(path.join(home, ".config", "autostart")).length > 0);

// Zwei Knöpfe: Pfeiltasten und Linksklick. Wählt "Ganz einfach" (Modus a).
async function setupAblauf(client, t, ein, sprache) {
  const W = WORT[sprache], F = FRAGE[sprache];
  let z = await zustand(client);
  pruefe(t + ": startet als Allererstes in der Einrichtung", z.phase === "setup" && z.schritt === "bedienung", z);
  pruefe(t + ": Einrichtungsansicht ohne Einstellungstaste", await ev(client, "getComputedStyle(document.getElementById('setup')).display === 'none'"));
  pruefe(t + ": Frage steht da: " + F.bedienung, (await ebene(client)) === F.bedienung, await ebene(client));
  pruefe(t + ": Frage wird angesagt", (await gesprochen(client)).some(x => x.indexOf(F.bedienung) === 0));
  pruefe(t + ": Stimme links, Knöpfe/Maus/Tasten rechts", z.paar.links === W.stimme && z.paar.rechts === W.knoepfe, z.paar);
  pruefe(t + ": nur zwei Kacheln", (await kacheln(client)) === 2);
  if (!ein) {
    await sleep(4500); // Konfiguration hat 2 s Auto-Zurück: früher endete die Einrichtung dadurch
    z = await zustand(client);
    pruefe(t + ": Einrichtung wartet ohne Zeitlimit und ohne stilles Überspringen", z.phase === "setup" && z.schritt === "bedienung", z);
  } else {
    pruefe(t + ": Scan läuft in der Einrichtung", z.scan === true && z.fokus === "links", z);
    await sleep(2800);
    z = await zustand(client);
    pruefe(t + ": Markierung wandert auf rechts", z.fokus === "rechts" && z.schritt === "bedienung", z);
  }
  // Wählt die linke oder rechte Kachel. Ein-Knopf: warten, bis die Markierung dort steht, dann eine Taste.
  const waehle = async seite => {
    if (ein) {
      for (let i = 0; i < 160; i++) { if ((await zustand(client)).fokus === seite) break; await sleep(50); }
      await taste(client, "Space");
    } else {
      await taste(client, seite === "rechts" ? "ArrowRight" : "ArrowLeft");
    }
    await sleep(SPAET);
  };
  // Frage 1: Knöpfe, Maus, Tasten (rechts)
  await waehle("rechts");
  z = await zustand(client);
  pruefe(t + ": Frage 2 Knöpfe", z.schritt === "knopf" && z.paar.links === W.zwei && z.paar.rechts === W.ein && (await kacheln(client)) === 2, z);
  pruefe(t + ": Frage 2 steht da", (await ebene(client)) === F.knopf, await ebene(client));
  // Frage 2: Zwei Knöpfe (links)
  await waehle("links");
  z = await zustand(client);
  pruefe(t + ": Frage 3 Auswahl: Einfach ist vorn", z.schritt === "modus" && z.paar.links === W.b && z.paar.sonderR === "andere", z);
  pruefe(t + ": Frage 3 steht da", (await ebene(client)) === F.modus, await ebene(client));
  // Andere: Ganz einfach
  await waehle("rechts");
  z = await zustand(client);
  pruefe(t + ": Andere zeigt Ganz einfach", z.paar.links === W.a && (await kacheln(client)) === 2, z);
  // Linksklick auf freie Fläche = Knopf 1 = linke Kachel (Ein-Knopf: markierte Kachel)
  if (ein) {
    for (let i = 0; i < 160; i++) { if ((await zustand(client)).fokus === "links") break; await sleep(50); }
  }
  await maus(client, LEER[0], LEER[1], "links");
  await sleep(SPAET + 600);
  z = await zustand(client);
  pruefe(t + ": Linksklick wählt, dann kommt die Autostart-Frage", z.phase === "setup" && z.schritt === "autostart", z);
  pruefe(t + ": Autostart-Frage steht da und wird angesagt", (await ebene(client)) === F.autostart && (await gesprochen(client)).some(x => x.indexOf(F.autostart) === 0), await ebene(client));
  pruefe(t + ": Autostart-Frage: Nein links (Standard), Ja rechts, zwei Kacheln", z.paar.links === W.nein && z.paar.rechts === W.ja && (await kacheln(client)) === 2, z.paar);
  pruefe(t + ": nach dem Modus ist noch nichts angelegt", !autostartDa());
  await waehle("links"); // Nein
  z = await zustand(client);
  pruefe(t + ": Nein beendet die Einrichtung", z.phase === "app", z);
  pruefe(t + ": Modus a: Start ist sehr klein (Hilferuf)", z.paar.links === (sprache === "en" ? "Call for help" : "Hilferuf"), z.paar);
  const g = JSON.parse(fs.readFileSync(cfgPfad, "utf8"));
  pruefe(t + ": Einrichtung gespeichert (fertig, Stand 2)", g.einrichtung && g.einrichtung.fertig === true && g.einrichtung.stand === 2, g.einrichtung);
  pruefe(t + ": Modus a gespeichert, Zeit 45 s, Autostart aus", g.modus === "a" && g.zurueck.sekunden === 45 && g.autostart !== true, { modus: g.modus, z: g.zurueck, a: g.autostart });
  pruefe(t + ": kein stiller Autostart-Eintrag", !autostartDa());
  pruefe(t + ": Mikrofon bleibt aus", g.hoeren !== true);
  pruefe(t + ": Einstellungstaste nach der Einrichtung da", await ev(client, "getComputedStyle(document.getElementById('setup')).display !== 'none'"));
}

// Allererster Schritt der Einrichtung: Sprache. wahl = "links" | "rechts"; erwartet = Sprache nach der Wahl.
async function spracheZuerst(client, t, sprache, system, wahl, erwartet) {
  let z = await zustand(client);
  pruefe(t + ": Einrichtung beginnt mit der Sprache", z.phase === "setup" && z.schritt === "sprache", z);
  pruefe(t + ": zweisprachige Frage", (await ebene(client)) === "Sprache · Language", await ebene(client));
  pruefe(t + ": Frage wird angesagt", (await gesprochen(client)).some(x => x.indexOf("Sprache · Language") === 0));
  const erst = system === "de" ? "Deutsch" : "English", zweit = system === "de" ? "English" : "Deutsch";
  pruefe(t + ": Systemsprache steht links (vorgewählt), zwei große Kacheln", z.paar.links === erst && z.paar.rechts === zweit && (await kacheln(client)) === 2, z.paar);
  await sleep(2500);
  pruefe(t + ": wartet ohne Zeitlimit", (await zustand(client)).schritt === "sprache");
  await taste(client, wahl === "links" ? "ArrowLeft" : "ArrowRight");
  let ok = false;
  for (let i = 0; i < 400 && !ok; i++) {
    await sleep(150);
    try { z = await zustand(client); ok = z.phase === "setup" && z.schritt === "bedienung"; } catch (err) {}
  }
  pruefe(t + ": weiter mit der ersten Frage", ok, z);
  const g = JSON.parse(fs.readFileSync(cfgPfad, "utf8"));
  pruefe(t + ": Sprache gespeichert: " + erwartet, g.language === erwartet && g.einrichtung.sprache === true && g.einrichtung.fertig === false, { l: g.language, e: g.einrichtung });
  pruefe(t + ": erste Frage in " + erwartet, (await ebene(client)) === FRAGE[erwartet].bedienung, await ebene(client));
  pruefe(t + ": Stimme passt", erwartet === "en" ? g.stimmeModell === undefined || g.stimmeModell === "en_US-john-medium" : g.stimmeModell === undefined || g.stimmeModell === "de_DE-thorsten-medium", g.stimmeModell);
}

// Einstellungen: die Sprachwahl ist immer erreichbar, zweisprachig beschriftet, mit John als erster englischer Kachel.
async function spracheInEinstellungen(client, t, sprache) {
  const knopf = JSON.parse(await ev(client, "JSON.stringify({t:document.getElementById('sprachBtn').textContent,vis:getComputedStyle(document.getElementById('sprachBtn')).display!=='none'})"));
  pruefe(t + ": Sprach-Knopf sichtbar, zweisprachig beschriftet", knopf.vis && knopf.t.indexOf("Sprache") !== -1 && knopf.t.indexOf("Language") !== -1, knopf);
  await ev(client, "document.getElementById('sprachBtn').click()");
  await sleep(800);
  const k = JSON.parse(await ev(client, "JSON.stringify([...document.querySelectorAll('#sprachen button')].map(b=>b.firstChild.textContent))"));
  pruefe(t + ": Sprachliste mit Deutsch und English", k.includes("Deutsch") && k.some(x => x.indexOf("English") === 0) && k.length >= 3, k);
  const reihe = k.filter(x => x.indexOf("English") === 0);
  pruefe(t + ": erste englische Kachel ist die männliche Standardstimme", reihe[0] === "English (US), male", reihe);
}

// Maus: Rechtsklick = rechte Kachel, direkter Klick auf Kacheln. Wählt Ein Knopf und "Mehr Auswahl" (Modus c).
async function setupRechtsklick(client, t, sprache) {
  const W = WORT[sprache];
  let z = await zustand(client);
  pruefe(t + ": startet in der Einrichtung", z.phase === "setup" && z.schritt === "bedienung", z);
  await maus(client, RECHTE[0], RECHTE[1], "rechts"); // Rechtsklick = Knopf 2 = Knöpfe, Maus, Tasten
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Rechtsklick wählt die rechte Kachel", z.schritt === "knopf", z);
  await maus(client, RECHTE[0], RECHTE[1], "links"); // direkt auf die rechte Kachel: Ein Knopf
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Ein Knopf gewählt, nächste Frage", z.schritt === "modus" && z.paar.links === W.b, z);
  await maus(client, RECHTE[0], RECHTE[1], "rechts"); // Andere
  await sleep(SPAET);
  await maus(client, RECHTE[0], RECHTE[1], "rechts"); // Andere
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Rechtsklick blättert zu Mehr Auswahl", z.paar.links === W.c && z.phase === "setup", z);
  await maus(client, LINKE[0], LINKE[1], "links");
  await sleep(SPAET + 300);
  z = await zustand(client);
  pruefe(t + ": Klick auf die Kachel wählt, Autostart-Frage folgt", z.phase === "setup" && z.schritt === "autostart", z);
  await maus(client, RECHTE[0], RECHTE[1], "links"); // direkt auf die rechte Kachel = Ja (Ein-Knopf-Modus gewählt)
  await sleep(SPAET + 900);
  z = await zustand(client);
  pruefe(t + ": Ja beendet die Einrichtung", z.phase === "app", z);
  const desk = path.join(home, ".config", "autostart", "omaclusive.desktop");
  pruefe(t + ": Ja legt den Autostart-Eintrag an (Exec = start-talker.sh)", fs.existsSync(desk) && /^Exec=.*start-talker\.sh$/m.test(fs.readFileSync(desk, "utf8")), fs.existsSync(desk));
  const g = JSON.parse(fs.readFileSync(cfgPfad, "utf8"));
  pruefe(t + ": config.autostart ist true (gleicht der Datei)", g.autostart === true, g.autostart);
  try { fs.unlinkSync(desk); } catch (err) {}
  pruefe(t + ": Ein Knopf und Modus c gespeichert", g.knopf && g.knopf.modus === "ein" && g.modus === "c" && g.zurueck.sekunden === 60, { k: g.knopf, m: g.modus });
  pruefe(t + ": Pfad kommt vom Server (Vorlage c)", await ev(client, "window.__modus === 'c' && window.__pfadQuelle === 'vorlage'"));
}

// Alte Einrichtung (fertig ohne Stand, so wie sie vom ersten Stand blieb) fragt neu.
async function alteConfigFragtNeu(client, t, sprache) {
  const z = await zustand(client);
  pruefe(t + ": alte Einrichtung (fertig ohne Stand) fragt neu", z.phase === "setup" && z.schritt === "bedienung", z);
}

// Stimme: Mikrofon wird erst nach ausdrücklicher Wahl eingeschaltet.
async function setupStimme(client, t, sprache) {
  const W = WORT[sprache];
  await taste(client, "ArrowLeft"); // Stimme
  await sleep(SPAET);
  let z = await zustand(client);
  pruefe(t + ": Stimme führt direkt zur Auswahl-Frage", z.schritt === "modus" && z.paar.links === W.b, z);
  await taste(client, "ArrowLeft"); // Einfach (Standard, ausdrücklich gewählt)
  await sleep(SPAET);
  pruefe(t + ": danach die Autostart-Frage", (await zustand(client)).schritt === "autostart");
  await taste(client, "ArrowLeft"); // Nein
  await sleep(SPAET + 600);
  z = await zustand(client);
  const g = JSON.parse(fs.readFileSync(cfgPfad, "utf8"));
  pruefe(t + ": Stimme gespeichert, Modus b", z.phase === "app" && g.hoeren === true && g.modus === "b" && g.knopf.modus === "zwei", { hoeren: g.hoeren, modus: g.modus });
  pruefe(t + ": Modus b: Start Sagen, Bilder, Filme, Steuern", await ev(client, "Object.keys(C.screens).sort().join(',')") === "sagen,start,steuern", await ev(client, "Object.keys(C.screens).join(',')"));
}

// Modi als feste Pfade: a, b, c mit echtem Server.
async function modusPfad(client, t, sprache, modus) {
  const z = await zustand(client);
  pruefe(t + ": startet direkt in der App", z.phase === "app" && z.screen === "start", z);
  const info = JSON.parse(await ev(client, "JSON.stringify({m:window.__modus,q:window.__pfadQuelle,screens:Object.keys(C.screens).sort(),n:C.screens.start.liste.length})"));
  pruefe(t + ": Modus " + modus + " aus dem Server", info.m === modus && info.q === "vorlage", info);
  const erwartet = { a: ["start"], b: ["sagen", "start", "steuern"], c: ["lautstaerke", "sagen", "start", "steuern"] }[modus];
  const eigene = info.screens.filter(x => x.indexOf("plugin-") !== 0 && x.indexOf("ordner-") !== 0);
  pruefe(t + ": Ebenen von Modus " + modus, JSON.stringify(eigene) === JSON.stringify(erwartet), info.screens);
  pruefe(t + ": immer nur zwei Kacheln", (await kacheln(client)) === 2);
  const plugin = info.screens.some(x => x.indexOf("plugin-") === 0);
  pruefe(t + ": Zusatzpaket nur in Modus c", plugin === (modus === "c"), info.screens);
  const maxTiefe = await ev(client, "(()=>{const s=C.screens;let m=0;const w=(id,d)=>{m=Math.max(m,d);(s[id].liste||[]).forEach(k=>{const a=Pfad.aktionVon(k);if(a&&a.typ==='untermenue'&&s[a.ziel])w(a.ziel,d+1)})};w(C.start,1);return m})()");
  pruefe(t + ": Tiefe passt (a 1, b 2, c höchstens 3)", maxTiefe <= { a: 1, b: 2, c: 3 }[modus] && (modus !== "b" || maxTiefe === 2), maxTiefe);
}

// "Gleich zurück": Ansage genau einmal, Zahl und Balken, Eingabe bricht ab, sonst zurück zum Start.
async function gleichZurueck(client, t, sprache) {
  const text = sprache === "en" ? "Going back to the start in a moment." : "Gleich zurück zum Start.";
  await ev(client, "(()=>{window.__sprache=[];return 1})()");
  await taste(client, "ArrowLeft"); // öffnet "Ich will was sagen"
  await sleep(SPAET);
  let z = await zustand(client);
  pruefe(t + ": unterwegs (nicht am Start)", z.screen !== "start", z);
  await ev(client, "(()=>{window.__sprache=[];return 1})()");
  await sleep(3300); // Hinweis kommt 5 s vor dem Zurückspringen (Zeit 8 s)
  pruefe(t + ": Hinweis sichtbar", await ev(client, "!document.getElementById('hinweis').hidden"));
  pruefe(t + ": Zahl und Balken sichtbar", await ev(client, "document.getElementById('hinweis').classList.contains('zeit') && getComputedStyle(document.getElementById('zahl')).display !== 'none'"));
  const zahl1 = await ev(client, "Number(document.getElementById('zahl').textContent)");
  pruefe(t + ": Zahl zählt von 5 abwärts", zahl1 >= 3 && zahl1 <= 5, zahl1);
  const b1 = await ev(client, "document.getElementById('fuell').getBoundingClientRect().width");
  await sleep(1500);
  const b2 = await ev(client, "document.getElementById('fuell').getBoundingClientRect().width");
  const zahl2 = await ev(client, "Number(document.getElementById('zahl').textContent)");
  pruefe(t + ": Balken wird kürzer, Zahl kleiner", b2 < b1 && zahl2 < zahl1, { b1, b2, zahl1, zahl2 });
  const gesagt = (await gesprochen(client)).filter(x => x === text).length;
  pruefe(t + ": Ansage genau einmal", gesagt === 1, await gesprochen(client));
  // Eingabe bricht ab: kein Zurückspringen, Hinweis weg
  await taste(client, "ArrowRight");
  await sleep(SPAET);
  pruefe(t + ": Eingabe schließt den Hinweis", await ev(client, "document.getElementById('hinweis').hidden"));
  await sleep(2500);
  pruefe(t + ": nach Abbruch läuft nichts mehr von allein zurück", await ev(client, "document.getElementById('hinweis').hidden"));
  // nichts tun: Hinweis kommt wieder, dann Start
  await ev(client, "(()=>{window.__sprache=[];return 1})()");
  await sleep(4500);
  pruefe(t + ": neuer Hinweis nach neuer Wartezeit", await ev(client, "!document.getElementById('hinweis').hidden"));
  await sleep(5600);
  z = await zustand(client);
  pruefe(t + ": Timer läuft ab: zurück am Start", z.screen === "start", z);
  const gesagt2 = (await gesprochen(client)).filter(x => x === text).length;
  pruefe(t + ": zweite Ansage auch nur einmal", gesagt2 === 1, await gesprochen(client));
}

async function appZwei(client, t, sprache) {
  let z = await zustand(client);
  pruefe(t + ": startet in der App", z.phase === "app" && z.screen === "start", z);
  const sagen = sprache === "en" ? "I want to say something" : "Ich will was sagen";
  pruefe(t + ": Start: Ich will was sagen links, Andere rechts", z.paar.links === sagen && z.paar.sonderR === "andere", z.paar);
  pruefe(t + ": nur zwei Kacheln, keine Ecken", (await ev(client, "document.querySelectorAll('button.karte').length")) === 2 && (await ev(client, "!document.getElementById('hilfe') && !document.getElementById('ja') && !document.getElementById('nein') && !document.getElementById('zurueck')")));
  pruefe(t + ": ohne Scan keine Markierung", z.scan === false && !(await ev(client, "document.querySelector('.karte.an')")));
  pruefe(t + ": Fenster hat Fokus", await ev(client, "document.hasFocus()"));
  // Pfeil rechts = rechte Kachel (Andere): links zeigt die nächste Karte
  await taste(client, "ArrowRight");
  await sleep(SPAET);
  const nach = await zustand(client);
  pruefe(t + ": Pfeil rechts = rechte Kachel", nach.paar.links !== z.paar.links && nach.screen === "start", nach);
  // Leertaste, Enter, Pfeil hoch tun im Zwei-Knopf-Modus nichts
  const ein0 = nach.eingaben;
  await taste(client, "Space"); await sleep(SPAET);
  await taste(client, "Enter"); await sleep(SPAET);
  await taste(client, "ArrowUp"); await sleep(SPAET);
  const still = await zustand(client);
  pruefe(t + ": Leertaste/Enter/Hoch tun im Zwei-Knopf-Modus nichts", still.eingaben === ein0 && still.paar.links === nach.paar.links, still);
  // Zu schnell hintereinander: nur ein Druck zählt, der andere leuchtet
  await taste(client, "ArrowRight");
  await taste(client, "ArrowRight");
  await sleep(60);
  const blink = await ev(client, "!!document.querySelector('.karte.verworfen')");
  await sleep(SPAET);
  const schnell = await zustand(client);
  pruefe(t + ": schneller zweiter Druck wird verworfen und sichtbar", schnell.eingaben === still.eingaben + 1 && schnell.verworfen === still.verworfen + 1 && blink, { schnell, blink });
  // Pfeil links = linke Kachel: wählt die angezeigte Karte
  const links = schnell.paar.links;
  await taste(client, "ArrowLeft");
  await sleep(SPAET);
  const geoeffnet = await zustand(client);
  pruefe(t + ": Pfeil links = linke Kachel wählt " + links, geoeffnet.screen !== "start", geoeffnet);
  // Zurück ist eine normale Kachel
  let versuche = 0;
  while ((await zustand(client)).screen !== "start" && versuche++ < 8) {
    const zz = await zustand(client);
    await taste(client, zz.paar.sonderR === "zurueck" || zz.paar.sonderL === "zurueck" ? (zz.paar.sonderR === "zurueck" ? "ArrowRight" : "ArrowLeft") : "ArrowRight");
    await sleep(SPAET);
  }
  pruefe(t + ": Zurück als Kachel führt zum Start", (await zustand(client)).screen === "start", await zustand(client));
  // Maus: Linksklick und Rechtsklick auf freie Fläche
  const m0 = await zustand(client);
  await maus(client, LEER[0], LEER[1], "rechts");
  await sleep(SPAET);
  const m1 = await zustand(client);
  pruefe(t + ": Rechtsklick = rechte Kachel", m1.paar.links !== m0.paar.links && m1.screen === "start", m1);
  pruefe(t + ": Kontextmenü unterdrückt", (await ev(client, "window.__ctx.length > 0 && window.__ctx.every(e => e.defaultPrevented)")), await ev(client, "window.__ctx.length"));
  // zwei Karten weiter (Radio und Aufgaben überspringen) bis "Steuern", das ein Untermenü öffnet
  for (let k = 0; k < 2; k++) { await maus(client, LEER[0], LEER[1], "rechts"); await sleep(SPAET); }
  await maus(client, LEER[0], LEER[1], "links");
  await sleep(SPAET);
  const m2 = await zustand(client);
  pruefe(t + ": Linksklick = linke Kachel", m2.screen !== "start", m2);
  // zurück zum Start über die Kachel-Klicks: erst Zurück erreichen
  let n = 0;
  while ((await zustand(client)).screen !== "start" && n++ < 8) {
    const zz = await zustand(client);
    if (zz.paar.sonderL === "zurueck") await maus(client, LINKE[0], LINKE[1], "links");
    else if (zz.paar.sonderR === "zurueck") await maus(client, RECHTE[0], RECHTE[1], "links");
    else await maus(client, RECHTE[0], RECHTE[1], "links");
    await sleep(SPAET);
  }
  pruefe(t + ": direkter Klick auf Kacheln, Zurück erreichbar", (await zustand(client)).screen === "start", await zustand(client));
  const k0 = await zustand(client);
  await maus(client, LINKE[0], LINKE[1], "rechts"); // Rechtsklick auch auf die linke Kachel = Knopf 2
  await sleep(SPAET);
  const k1 = await zustand(client);
  pruefe(t + ": Rechtsklick auf linke Kachel = Knopf 2", k1.screen === "start" && k1.paar.links !== k0.paar.links, k1);
  // Mittlere Maustaste und Seitentasten zählen nicht
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: 700, y: 14, button: "middle", buttons: 4, clickCount: 1 });
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 700, y: 14, button: "middle", buttons: 0, clickCount: 1 });
  await sleep(SPAET);
  pruefe(t + ": Mittlere Maustaste ignoriert", (await zustand(client)).eingaben === k1.eingaben, await zustand(client));
}

async function appEin(client, t, sprache) {
  let z = await zustand(client);
  pruefe(t + ": Ein-Knopf: Scan an, links markiert", z.phase === "app" && z.scan === true && z.fokus === "links" && await ev(client, "document.getElementById('links').classList.contains('an')"), z);
  await sleep(3000);
  z = await zustand(client);
  pruefe(t + ": Markierung wandert nach rechts", z.fokus === "rechts" && await ev(client, "document.getElementById('rechts').classList.contains('an')"), z);
  const vor = z.paar.links;
  await taste(client, "Space"); // wählt Andere
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Leertaste wählt die markierte Kachel (Andere)", z.paar.links !== vor && z.fokus === "links" && z.screen === "start", z);
  const v2 = z.paar.links;
  await sleep(1000);
  await taste(client, "ArrowUp"); // markierte Kachel ist links: öffnet die Karte
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Pfeil hoch wählt die markierte Kachel", z.screen !== "start", z);
  // zurück zum Start: Zurück ist eine Kachel; die Markierung läuft von selbst
  for (let i = 0; i < 6 && (await zustand(client)).screen !== "start"; i++) {
    const zz = await zustand(client);
    if (zz.paar.sonderL === "zurueck" && zz.fokus === "links") await taste(client, "Enter");
    else if (zz.paar.sonderR === "zurueck" && zz.fokus === "rechts") await taste(client, "Enter");
    else await sleep(3100);
    await sleep(SPAET);
  }
  pruefe(t + ": Ein-Knopf: Enter wählt, Zurück erreichbar", (await zustand(client)).screen === "start", await zustand(client));
  // Maus im Ein-Knopf-Modus: jeder Klick auf freie Fläche wählt, Klick auf Kachel wählt diese
  await sleep(SPAET);
  const a = await zustand(client);
  await maus(client, LEER[0], LEER[1], "rechts"); // markiert ist links: wählt links
  await sleep(SPAET);
  const b = await zustand(client);
  pruefe(t + ": Rechtsklick wählt im Ein-Knopf-Modus die markierte Kachel", b.screen !== "start" || b.paar.links !== a.paar.links, b);
  await taste(client, "ArrowLeft"); // jede Taste wählt
  await sleep(SPAET);
  const c = await zustand(client);
  pruefe(t + ": Pfeil links wählt im Ein-Knopf-Modus", c.eingaben === b.eingaben + 1, c);
}

async function haltetaste(client, t) {
  let z = await zustand(client);
  pruefe(t + ": Einstellungstaste sichtbar", await ev(client, "getComputedStyle(document.getElementById('setup')).display !== 'none'"));
  const pos = await ev(client, "(()=>{const r=document.getElementById('setup').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()");
  // kurz halten: nichts
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: pos[0], y: pos[1], button: "left", buttons: 1, clickCount: 1 });
  await sleep(900);
  pruefe(t + ": Balken läuft beim Halten", await ev(client, "document.getElementById('setup').classList.contains('h')"));
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: pos[0], y: pos[1], button: "left", buttons: 0, clickCount: 1 });
  await sleep(300);
  pruefe(t + ": kurzes Halten (Maus) öffnet nichts", !(await ev(client, "document.getElementById('setup').classList.contains('h')")) && (await zustand(client)).url === "/", await zustand(client));
  await sleep(2600);
  pruefe(t + ": auch nach der Wartezeit nichts", (await zustand(client)).url === "/", await zustand(client));
  // 3 Sekunden halten: öffnet die Einstellungen
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: pos[0], y: pos[1], button: "left", buttons: 1, clickCount: 1 });
  await sleep(3500);
  z = await zustand(client);
  pruefe(t + ": 3 Sekunden halten öffnet die Einrichtung", z.url === "/setup.html", z);
}

async function halteTasten(client, t) {
  await client.send("Input.dispatchKeyEvent", Object.assign({ type: "rawKeyDown" }, TASTEN.ArrowLeft));
  await client.send("Input.dispatchKeyEvent", Object.assign({ type: "rawKeyDown" }, TASTEN.ArrowRight));
  await sleep(1000);
  pruefe(t + ": beide Pfeiltasten: Balken läuft", await ev(client, "document.getElementById('setup').classList.contains('h')"));
  await sleep(2700);
  const z = await zustand(client);
  pruefe(t + ": beide Pfeiltasten 3 Sekunden öffnen die Einrichtung", z.url === "/setup.html", z);
}

// Wahl-Wartezeit: gewählte Kachel wird vergrößert, bleibt stehen, erst dann läuft die Eingabe; andere Taste bricht ab.
async function wahlWartezeit(client, t, sprache) {
  const gewaehlt = id => ev(client, "document.getElementById('" + id + "').classList.contains('gewaehlt')");
  const skala = id => ev(client, "new DOMMatrix(getComputedStyle(document.getElementById('" + id + "')).transform).a");
  let z = await zustand(client);
  pruefe(t + ": startet am Start", z.phase === "app" && z.screen === "start", z);
  await taste(client, "ArrowLeft"); // "Ich will was sagen"
  await sleep(150);
  pruefe(t + ": Kachel sofort als gewählt markiert", await gewaehlt("links"));
  await sleep(900);
  const s = await skala("links");
  pruefe(t + ": Kachel ist auf 1,15x vergrößert (" + s.toFixed(3) + ")", Math.abs(s - 1.15) < 0.01, s);
  const rand = await ev(client, "parseFloat(getComputedStyle(document.getElementById('links')).borderTopWidth)");
  pruefe(t + ": Rahmen der gewählten Kachel ist dick", rand >= 10, rand);
  pruefe(t + ": rechte Kachel bleibt normal", Math.abs((await skala("rechts")) - 1) < 0.001 && !(await gewaehlt("rechts")));
  z = await zustand(client);
  pruefe(t + ": nach 1 s ist die Eingabe noch nicht ausgeführt", z.screen === "start", z);
  const aufRechts = await ev(client, "(()=>{const l=document.getElementById('links').getBoundingClientRect(),r=document.getElementById('rechts').getBoundingClientRect(),w=innerWidth,h=innerHeight;return JSON.stringify([l.left,l.top,l.bottom,r.right,w,h])})()");
  const [bl, bt, bb, br, bw, bh] = JSON.parse(aufRechts);
  pruefe(t + ": vergrößerte Kachel bleibt im Bild", bl >= 0 && bt >= 0 && bb <= bh && br <= bw, aufRechts);
  // andere Taste bricht ab
  await taste(client, "ArrowRight");
  await sleep(300);
  pruefe(t + ": andere Taste bricht ab (nichts mehr markiert)", !(await gewaehlt("links")) && !(await gewaehlt("rechts")));
  await sleep(3500);
  z = await zustand(client);
  pruefe(t + ": nach Abbruch passiert auch später nichts", z.screen === "start", z);
  // gleiche Taste nochmal während des Wartens startet nichts neu; nach 3 s läuft die Eingabe
  await taste(client, "ArrowLeft");
  await sleep(1200);
  await taste(client, "ArrowLeft");
  await sleep(1000);
  z = await zustand(client);
  pruefe(t + ": noch nicht ausgeführt nach 2,2 s", z.screen === "start" && (await gewaehlt("links")), z);
  await sleep(1500);
  z = await zustand(client);
  pruefe(t + ": nach 3 s läuft die Eingabe", z.screen !== "start" && !(await gewaehlt("links")), z);
}

// Betreuerbereich: Haken "Mit dem Rechner starten" liest die Datei und legt sie an / entfernt sie.
async function autostartSchalter(client, t, sprache) {
  const desk = path.join(home, ".config", "autostart", "omaclusive.desktop");
  const box = () => ev(client, "document.getElementById('autoBox').checked");
  // Über Node statt über die Seite: absichtlich falsche Aufrufe sollen nicht als Konsolenfehler der Seite zählen
  const api = (m, body, host) => new Promise(res => {
    const rq = require("http").request({ host: "127.0.0.1", port, path: "/api/autostart", method: m, headers: { Host: host || ("127.0.0.1:" + port), "Content-Type": "application/json", "X-Omaclusive-Token": sitzungToken } }, a => {
      let d = ""; a.on("data", x => d += x); a.on("end", () => { let b = null; try { b = JSON.parse(d); } catch (err) {} res({ s: a.statusCode, b }); });
    });
    rq.on("error", () => res({ s: 0, b: null })); rq.end(body === undefined ? undefined : JSON.stringify(body));
  });
  pruefe(t + ": Haken ist ein Kontrollkästchen und zeigt aus (keine Datei)", (await ev(client, "document.getElementById('autoBox').type")) === "checkbox" && !(await box()) && !fs.existsSync(desk));
  pruefe(t + ": Text neben dem Haken", (await ev(client, "document.getElementById('autoText').textContent")) === (sprache === "en" ? "Start at login" : "Mit dem Rechner starten"));
  await ev(client, "document.getElementById('autoBox').click()");
  await sleep(500);
  pruefe(t + ": Haken an legt die Datei an", fs.existsSync(desk) && (await box()));
  const text = fs.existsSync(desk) ? fs.readFileSync(desk, "utf8") : "";
  pruefe(t + ": Exec zeigt auf start-talker.sh des Ordners", text.split("\n").some(l => l === "Exec=" + path.join(root, "start-talker.sh")), text);
  pruefe(t + ": config.autostart folgt (true)", JSON.parse(fs.readFileSync(cfgPfad, "utf8")).autostart === true);
  await ev(client, "document.getElementById('autoBox').click()");
  await sleep(500);
  pruefe(t + ": Haken aus entfernt die Datei", !fs.existsSync(desk) && !(await box()));
  pruefe(t + ": config.autostart folgt (false)", JSON.parse(fs.readFileSync(cfgPfad, "utf8")).autostart === false);
  // Zustand kommt aus der Datei, auch wenn sie von außen angelegt wurde
  fs.mkdirSync(path.dirname(desk), { recursive: true });
  fs.writeFileSync(desk, "[Desktop Entry]\nType=Application\nName=Omaclusive\nExec=x\n");
  let r = await api("GET");
  pruefe(t + ": GET /api/autostart liest die Datei", r.s === 200 && r.b.an === true, r);
  pruefe(t + ": GET gleicht config.autostart an", JSON.parse(fs.readFileSync(cfgPfad, "utf8")).autostart === true);
  r = await api("POST", {});
  pruefe(t + ": POST ohne boolesches 'an' wird abgelehnt", r.s === 400 && fs.existsSync(desk), r);
  r = await api("POST", { an: "ja", pfad: "/tmp/x" });
  pruefe(t + ": POST mit Text statt Boolean abgelehnt, kein Pfad nutzbar", r.s === 400 && fs.existsSync(desk), r);
  r = await api("POST", { an: false, pfad: "../../etc/passwd" });
  pruefe(t + ": POST an=false entfernt nur die feste Datei", r.s === 200 && r.b.an === false && !fs.existsSync(desk), r);
  // fremde Host-Kopfzeile wird abgelehnt (nur 127.0.0.1)
  const fremd = (await api("POST", { an: true }, "evil.example:" + port)).s;
  pruefe(t + ": fremder Host wird abgelehnt (403)", fremd === 403 && !fs.existsSync(desk), fremd);
}

// ---- Bühne, Listenseite, Radio, Aufgaben, Erinnerungen ----
const PFLEGE = path.join(home, ".config", "omaclusive", "pflege.json");
function schreibePflege(daten) { fs.mkdirSync(path.dirname(PFLEGE), { recursive: true }); fs.writeFileSync(PFLEGE, JSON.stringify(daten)); }
function lesePflege() { return JSON.parse(fs.readFileSync(PFLEGE, "utf8")); }
function seedBilder(n) {
  const dir = path.join(home, "Bilder", "Omaclusive"); fs.mkdirSync(dir, { recursive: true });
  ["p2-start.png", "p2-bilder.png", "p2-steuern.png", "p2-start.png"].slice(0, n).forEach((q, i) => fs.copyFileSync(path.join(root, "screenshots", q), path.join(dir, "bild" + (i + 1) + ".png")));
}
function seedFilme(namen) {
  const dir = path.join(home, "Videos", "Omaclusive"); fs.mkdirSync(dir, { recursive: true });
  namen.forEach(n => execSync((n === "ton" ? "ffmpeg -loglevel error -y -f lavfi -i sine=duration=60 -c:a libopus " : "ffmpeg -loglevel error -y -f lavfi -i testsrc=duration=40:size=160x90:rate=5 -c:v libvpx -b:v 50k ") + " " + JSON.stringify(path.join(dir, n + ".webm"))));
}
// Auf dem Start so lange nach rechts, bis die linke Kachel das Wort zeigt, dann links = wählen
async function waehleKarteMitWort(client, wort) {
  for (let i = 0; i < 9; i++) {
    const z = await zustand(client);
    if (z.paar.links === wort) { await taste(client, "ArrowLeft"); await sleep(SPAET); return true; }
    await taste(client, "ArrowRight"); await sleep(SPAET);
  }
  return false;
}
const bildSrc = client => ev(client, "document.getElementById('buehneBild').src");
const buehneStand = client => ev(client, "window.__buehne");

async function diashow(client, t, sprache) {
  const W = sprache === "en" ? { bilder: "Pictures", zurueck: "Back", pause: "Pause", weiter: "Continue" } : { bilder: "Bilder", zurueck: "Zurück", pause: "Pause", weiter: "Weiter" };
  pruefe(t + ": Bilder auf dem Start gefunden", await waehleKarteMitWort(client, W.bilder));
  await sleep(700);
  let z = await zustand(client);
  pruefe(t + ": Ordnerwahl startet gleich die Diashow", (await buehneStand(client)) === "schau" && z.screen === "start", { b: await buehneStand(client), z });
  pruefe(t + ": nur zwei große Kacheln: Zurück und Pause", (await kacheln(client)) === 2 && z.paar.links === W.zurueck && z.paar.rechts === W.pause, z.paar);
  pruefe(t + ": Bild steht groß da", /api\/datei/.test(await bildSrc(client)) && await ev(client, "getComputedStyle(document.getElementById('buehneBild')).display === 'block'"), await bildSrc(client));
  const erstes = await bildSrc(client);
  await sleep(2400);
  pruefe(t + ": nach der Bildzeit (3 s) kommt das nächste Bild", (await bildSrc(client)) !== erstes, { erstes, jetzt: await bildSrc(client) });
  await taste(client, "ArrowRight"); // Pause
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Pause: Zurück und Weiter", (await buehneStand(client)) === "schau:pause" && z.paar.links === W.zurueck && z.paar.rechts === W.weiter, z.paar);
  const pausiert = await bildSrc(client);
  await sleep(3800);
  pruefe(t + ": bei Pause bleibt das Bild stehen", (await bildSrc(client)) === pausiert);
  await taste(client, "ArrowRight"); // Weiter
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Weiter: wieder Zurück und Pause", (await buehneStand(client)) === "schau" && z.paar.rechts === W.pause, z.paar);
  await sleep(3400);
  pruefe(t + ": nach Weiter läuft die Diashow", (await bildSrc(client)) !== pausiert);
  await taste(client, "ArrowLeft"); // Zurück zum Start
  await sleep(SPAET + 300);
  z = await zustand(client);
  pruefe(t + ": Zurück führt zum Start, Bühne weg", z.screen === "start" && (await buehneStand(client)) === "" && !(await ev(client, "document.body.classList.contains('buehne')")), z);
}

async function filmListe(client, t, sprache) {
  const W = sprache === "en" ? { filme: "Movies", zurueck: "Back", pause: "Pause", weiter: "Continue", blaettern: "Next page" } : { filme: "Filme", zurueck: "Zurück", pause: "Pause", weiter: "Weiter", blaettern: "Weiter blättern" };
  pruefe(t + ": Filme auf dem Start gefunden", await waehleKarteMitWort(client, W.filme));
  await sleep(700);
  let z = await zustand(client);
  pruefe(t + ": Listenseite zeigt zwei Filme gleichzeitig", z.paar.links === "film1" && z.paar.rechts === "film2", { p: z.paar, k: await kacheln(client) });
  pruefe(t + ": Fußzeile mit Zurück und Weiter blättern", await ev(client, "document.getElementById('fuss-blaettern').textContent.trim() === " + JSON.stringify(W.blaettern) + " && document.getElementById('fuss-zurueck').textContent.trim() === " + JSON.stringify(W.zurueck) + " && getComputedStyle(document.getElementById('fuss')).display !== 'none'"));
  pruefe(t + ": nur zwei große Kacheln (Fußkacheln sind klein)", await ev(client, "(()=>{const l=document.getElementById('links').getBoundingClientRect(),f=document.getElementById('fuss-blaettern').getBoundingClientRect();return l.height>f.height*3&&l.width>f.height*3})()"));
  await taste(client, "ArrowDown"); // Weiter blättern
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": Weiter blättern zeigt die nächsten zwei (Film drei und Zurück)", z.paar.links === "film3" && z.paar.sonderR === "zurueck", z.paar);
  await taste(client, "ArrowDown");
  await sleep(SPAET);
  z = await zustand(client);
  pruefe(t + ": nach der letzten Seite wieder die erste", z.paar.links === "film1", z.paar);
  // Film starten: linke Kachel
  await taste(client, "ArrowLeft");
  await sleep(1200);
  pruefe(t + ": Film läuft im Fenster mit Zurück und Pause", (await buehneStand(client)) === "video" && !(await ev(client, "document.getElementById('buehneVideo').paused")) && (await kacheln(client)) === 2 && (await zustand(client)).paar.rechts === W.pause, await zustand(client));
  pruefe(t + ": Film hat Bild und Ton-Quelle vom Server (Range)", await ev(client, "document.getElementById('buehneVideo').readyState >= 2 && document.getElementById('buehneVideo').videoWidth > 0"), await ev(client, "document.getElementById('buehneVideo').error && document.getElementById('buehneVideo').error.message"));
  pruefe(t + ": beim Film keine Fußzeile, nur zwei Kacheln", await ev(client, "getComputedStyle(document.getElementById('fuss')).display === 'none'"));
  await taste(client, "ArrowRight"); // Pause
  await sleep(SPAET + 200);
  z = await zustand(client);
  pruefe(t + ": Pause hält den Film an, dann Zurück und Weiter", (await ev(client, "document.getElementById('buehneVideo').paused")) && z.paar.rechts === W.weiter && (await buehneStand(client)) === "video:pause", z.paar);
  await taste(client, "ArrowRight"); // Weiter
  await sleep(SPAET + 300);
  pruefe(t + ": Weiter spielt weiter", !(await ev(client, "document.getElementById('buehneVideo').paused")));
  await taste(client, "ArrowLeft"); // Zurück
  await sleep(SPAET + 300);
  z = await zustand(client);
  pruefe(t + ": Zurück beendet den Film und zeigt wieder die Liste", (await buehneStand(client)) === "" && z.paar.links === "film1" && !(await ev(client, "!!document.getElementById('buehneVideo').getAttribute('src')")), z);
  // Maus: Klick auf die kleine Kachel "Weiter blättern"
  const pos = await ev(client, "(()=>{const r=document.getElementById('fuss-blaettern').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()");
  await maus(client, pos[0], pos[1], "links");
  await sleep(SPAET);
  pruefe(t + ": Mausklick auf Weiter blättern", (await zustand(client)).paar.links === "film3", (await zustand(client)).paar);
  // Zurück (Fußkachel) führt zum Start
  const pz = await ev(client, "(()=>{const r=document.getElementById('fuss-zurueck').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()");
  await maus(client, pz[0], pz[1], "links");
  await sleep(SPAET + 300);
  pruefe(t + ": Fußkachel Zurück führt zum Start", (await zustand(client)).screen === "start", await zustand(client));
}

// Ein-Knopf: die Abtastung läuft über beide Filme, "Weiter blättern" und "Zurück"
async function filmScan(client, t, sprache) {
  const W = sprache === "en" ? { filme: "Movies" } : { filme: "Filme" };
  pruefe(t + ": Filme gefunden (Scan)", await (async () => {
    for (let i = 0; i < 80; i++) {
      const z = await zustand(client);
      if (z.paar.links === W.filme && z.fokus === "links") { await taste(client, "Space"); await sleep(SPAET + 300); return true; }
      if (z.paar.links !== W.filme && z.fokus === "rechts") { await taste(client, "Space"); await sleep(SPAET + 300); }
      await sleep(150);
    }
    return false;
  })());
  const gesehen = [];
  for (let i = 0; i < 40 && gesehen.length < 4; i++) {
    const f = (await zustand(client)).fokus;
    if (gesehen[gesehen.length - 1] !== f) gesehen.push(f);
    await sleep(200);
  }
  pruefe(t + ": Scan geht links, rechts, Weiter blättern, Zurück", JSON.stringify(gesehen) === JSON.stringify(["links", "rechts", "blaettern", "zurueck"]) || JSON.stringify(gesehen.slice(-4)) === JSON.stringify(["links", "rechts", "blaettern", "zurueck"]), gesehen);
  // beim Zurück-Schritt wählen
  for (let i = 0; i < 60; i++) { if ((await zustand(client)).fokus === "zurueck") break; await sleep(100); }
  await taste(client, "Space");
  await sleep(SPAET + 300);
  pruefe(t + ": Zurück per Ein-Knopf führt zum Start", (await zustand(client)).screen === "start", await zustand(client));
}

async function radioStream(client, t, sprache) {
  const W = sprache === "en" ? { radio: "Radio", zurueck: "Back", pause: "Pause", weiter: "Continue" } : { radio: "Radio", zurueck: "Zurück", pause: "Pause", weiter: "Weiter" };
  pruefe(t + ": Radio ist eine Hauptkachel auf dem Start", await waehleKarteMitWort(client, W.radio));
  await sleep(1200);
  let z = await zustand(client);
  pruefe(t + ": Radio spielt im Fenster, zwei Kacheln Zurück und Pause", (await buehneStand(client)) === "radio" && !(await ev(client, "document.getElementById('buehneTon').paused")) && z.paar.links === W.zurueck && z.paar.rechts === W.pause && (await kacheln(client)) === 2, { b: await buehneStand(client), z });
  pruefe(t + ": Sendername steht groß da", (await ev(client, "document.getElementById('buehneText').textContent")) === "Testsender" && await ev(client, "getComputedStyle(document.getElementById('buehneText')).display === 'block'"));
  await taste(client, "ArrowRight");
  await sleep(SPAET + 200);
  pruefe(t + ": Pause hält das Radio an", (await ev(client, "document.getElementById('buehneTon').paused")) && (await zustand(client)).paar.rechts === W.weiter);
  await taste(client, "ArrowRight");
  await sleep(SPAET + 300);
  pruefe(t + ": Weiter spielt weiter", !(await ev(client, "document.getElementById('buehneTon').paused")));
  await taste(client, "ArrowLeft");
  await sleep(SPAET + 300);
  z = await zustand(client);
  pruefe(t + ": Zurück stoppt das Radio, zurück auf dem Start", (await buehneStand(client)) === "" && z.screen === "start" && (await ev(client, "document.getElementById('buehneTon').paused")), z);
}

// Radio ohne Stream: Link im Browser (hier ohne Adresse: ehrliche Ansage, nichts wird geöffnet)
async function radioOhneQuelle(client, t, sprache) {
  const W = { radio: "Radio" };
  await waehleKarteMitWort(client, W.radio);
  await sleep(500);
  const text = sprache === "en" ? "This is not set up yet." : "Das ist noch nicht eingerichtet.";
  pruefe(t + ": ohne Radio-Adresse sagt es ehrlich, dass es nicht eingerichtet ist", (await gesprochen(client)).some(x => x.indexOf(text) === 0) && (await zustand(client)).screen === "start" && (await buehneStand(client)) === "", await gesprochen(client));
}

// Fernsehen: eine Kachel je Sender, ein Druck startet mpv (hier ein Ersatz-mpv), danach zurück zum Start.
// Geht ein Sender nicht: ruhiges Bild, kurzes Wort, Start. Der Ersatz-mpv schreibt seinen Aufruf auf.
function ersatzMpv(an) {
  const f = path.join(bin, "mpv");
  if (!an) { try { fs.unlinkSync(f); } catch (err) {} return; }
  fs.writeFileSync(f, "#!/bin/sh\necho \"$@\" > \"$HOME/mpv-aufruf.txt\"\ncase \"$*\" in *kaputt*) sleep 1; exit 2;; esac\nsleep 3\nexit 0\n", { mode: 0o755 });
}

async function fernsehenAblauf(client, t, sprache) {
  const W = sprache === "en" ? { tv: "TV", meldung: "Not working now" } : { tv: "Fernsehen", meldung: "Geht gerade nicht" };
  try {
    pruefe(t + ": Fernsehen ist eine Kachel auf dem Start", await waehleKarteMitWort(client, W.tv));
    await sleep(600);
    let z = await zustand(client);
    // zwei Sender und Zurück sind drei Karten: links der erste Sender, rechts "Andere" (wie in jeder Unterebene)
    pruefe(t + ": je Sender eine Kachel, höchstens zwei auf einmal", z.screen === "ordner-fernsehen" && z.paar.links === "Testsender" && z.paar.sonderR === "andere" && (await kacheln(client)) === 2, z);
    await taste(client, "ArrowLeft");
    await sleep(SPAET + 1200);
    const aufruf = fs.existsSync(path.join(home, "mpv-aufruf.txt")) ? fs.readFileSync(path.join(home, "mpv-aufruf.txt"), "utf8") : "";
    pruefe(t + ": Sender startet sofort im Vollbild, ruhig (ohne Bedienleiste und Texte)", ["--fs", "--osc=no", "--osd-level=0", "--no-osd-bar", "-- http://127.0.0.1:9/test.m3u8"].every(x => aufruf.indexOf(x) !== -1) && await ev(client, "tvAn === true"), aufruf);
    await sleep(3500);
    z = await zustand(client);
    pruefe(t + ": Ende des Senders führt zum Start", z.screen === "start" && await ev(client, "tvAn === false && document.getElementById('hinweis').hidden"), z);
    pruefe(t + ": Fernsehen wieder gefunden", await waehleKarteMitWort(client, W.tv));
    await sleep(600);
    pruefe(t + ": zweiter Sender über Andere", await waehleKarteMitWort(client, "Kaputt"));
    await sleep(SPAET + 3000);
    z = await zustand(client);
    const wort = await ev(client, "document.querySelector('#hinweis .wort').textContent");
    pruefe(t + ": Sender geht nicht: ruhiges Bild und kurzes Wort, dann Start", z.screen === "start" && !(await ev(client, "document.getElementById('hinweis').hidden")) && wort === W.meldung && await ev(client, "window.__hinweisBild === 'img/fernsehen.svg'"), { z, wort });
    await taste(client, "ArrowLeft");
    await sleep(SPAET + 200);
    pruefe(t + ": ein Druck schließt die Meldung", await ev(client, "document.getElementById('hinweis').hidden"));
  } finally {
    ersatzMpv(false);
  }
}

async function ohneSender(client, t, sprache) {
  const W = sprache === "en" ? { tv: "TV" } : { tv: "Fernsehen" };
  pruefe(t + ": ohne Sender gibt es keine Fernsehen-Kachel", !(await waehleKarteMitWort(client, W.tv)));
}

async function aufgabenListe(client, t, sprache) {
  const W = sprache === "en" ? { aufgaben: "Tasks", nichts: "Nothing to do" } : { aufgaben: "Aufgaben", nichts: "Nichts zu tun" };
  pruefe(t + ": Aufgaben auf dem Start gefunden", await waehleKarteMitWort(client, W.aufgaben));
  await sleep(900);
  let z = await zustand(client);
  pruefe(t + ": zeigt die erste offene Aufgabe (zwei Kacheln)", z.paar.links === "Fenster schließen" && (await kacheln(client)) === 2, z.paar);
  await taste(client, "ArrowLeft"); // abhaken
  await sleep(1200);
  z = await zustand(client);
  const p = lesePflege();
  pruefe(t + ": Kachel hakt ab (gespeichert)", p.aufgaben.find(a => a.id === "a1").erledigt === true && p.aufgaben.find(a => a.id === "a2").erledigt === false, p.aufgaben);
  pruefe(t + ": danach die nächste offene Aufgabe", z.paar.links === "Tabletten bereitlegen", z.paar);
  await taste(client, "ArrowLeft");
  await sleep(1200);
  z = await zustand(client);
  pruefe(t + ": am Ende steht Nichts zu tun", z.paar.links === W.nichts && lesePflege().aufgaben.every(a => a.erledigt), z.paar);
}

async function erinnerungAblauf(client, t, sprache) {
  await sleep(2600);
  pruefe(t + ": fällige Erinnerung erscheint sichtbar", (await buehneStand(client)) === "erinnerung" && (await ev(client, "document.getElementById('buehneText').textContent")).indexOf("Tabletten nehmen") >= 0, await buehneStand(client));
  pruefe(t + ": nur eine Kachel (Okay)", await ev(client, "getComputedStyle(document.getElementById('rechts')).display === 'none' && document.getElementById('links').textContent.trim() === " + JSON.stringify(sprache === "en" ? "Okay" : "Okay")));
  const g = await gesprochen(client);
  const wort = sprache === "en" ? "Reminder." : "Erinnerung.";
  pruefe(t + ": wird vorgelesen", g.some(x => x.indexOf(wort) === 0 && x.indexOf("Tabletten nehmen") >= 0), g);
  pruefe(t + ": Server liefert sie bis zur Bestätigung weiter", true);
  await taste(client, "ArrowRight"); // jede Taste bestätigt die eine Kachel
  await sleep(1000);
  pruefe(t + ": Bestätigen schließt die Erinnerung", (await buehneStand(client)) === "" && (await ev(client, "getComputedStyle(document.getElementById('rechts')).display !== 'none'")), await buehneStand(client));
  const p = lesePflege();
  pruefe(t + ": Bestätigung ist gespeichert (heute)", /^\d{4}-\d{2}-\d{2}$/.test(p.bestaetigt.e1 || ""), p.bestaetigt);
  await sleep(3500);
  pruefe(t + ": danach kommt sie heute nicht wieder", (await buehneStand(client)) === "");
}

// Betreuerseite: Erinnerung und Aufgabe anlegen und speichern
async function pflegeSeite(client, t, sprache) {
  await ev(client, "(()=>{document.getElementById('eZeit').value='07:30';document.getElementById('eText').value='Tee trinken';document.getElementById('eWdh').value='werktags';erinnerungNeu();document.getElementById('aText').value='Post holen';aufgabeNeu();return 1})()");
  await ev(client, "speichern()", true);
  await sleep(500);
  const p = lesePflege();
  pruefe(t + ": Erinnerung gespeichert", p.erinnerungen.length === 1 && p.erinnerungen[0].zeit === "07:30" && p.erinnerungen[0].text === "Tee trinken" && p.erinnerungen[0].wiederholen === "werktags", p.erinnerungen);
  pruefe(t + ": Aufgabe gespeichert", p.aufgaben.length === 1 && p.aufgaben[0].text === "Post holen" && p.aufgaben[0].erledigt === false, p.aufgaben);
  pruefe(t + ": Liste zeigt beides", (await ev(client, "document.getElementById('erinnerungen').textContent")).indexOf("Tee trinken") >= 0 && (await ev(client, "document.getElementById('aufgaben').textContent")).indexOf("Post holen") >= 0);
  const antwort = JSON.parse(await ev(client, "fetch('/api/pflege',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({erinnerungen:[{zeit:'25:00',text:'x'}],aufgaben:[]})}).then(async r=>JSON.stringify({s:r.status}))", true));
  pruefe(t + ": falsche Uhrzeit wird abgelehnt (400)", antwort.s === 400, antwort);
  await ev(client, "document.querySelector('#erinnerungen .zeile button.klein:last-child').click()");
  await ev(client, "speichern()", true);
  await sleep(400);
  pruefe(t + ": Löschen und Speichern", lesePflege().erinnerungen.length === 0);
}

// Ordner-Ansicht: eine Datei im Ordner Filme, die der Browser nicht spielen kann, fällt auf den externen Player zurück (hier nicht testbar), die Datei selbst kommt mit Range
async function rangeTest(client, t, sprache) {
  const r = JSON.parse(await ev(client, "fetch('/api/medium?name=film1.webm',{headers:{Range:'bytes=0-99'}}).then(async r=>JSON.stringify({s:r.status,cr:r.headers.get('Content-Range'),l:(await r.arrayBuffer()).byteLength,ar:r.headers.get('Accept-Ranges')}))", true));
  pruefe(t + ": Film kommt mit Range (206, 100 Byte)", r.s === 206 && r.l === 100 && /^bytes 0-99\//.test(r.cr || "") && r.ar === "bytes", r);
  const ende = JSON.parse(await ev(client, "fetch('/api/medium?name=film1.webm',{headers:{Range:'bytes=-10'}}).then(async r=>JSON.stringify({s:r.status,l:(await r.arrayBuffer()).byteLength}))", true));
  pruefe(t + ": Range vom Ende (letzte 10 Byte)", ende.s === 206 && ende.l === 10, ende);
  const pfad = JSON.parse(await ev(client, "Promise.all(['../config.json','..%2Fconfig.json','/etc/passwd','film1.webm/../x','.hidden'].map(n=>fetch('/api/medium?name='+encodeURIComponent(n)).then(r=>r.status))).then(a=>JSON.stringify(a))", true));
  pruefe(t + ": Pfadtricks liefern 404", pfad.every(s => s === 404), pfad);
}

async function main() {
  const T = Date.now();
  const stimmenOrdner = path.join(root, "voices");
  const quellen = ["/workspace/_tts/voices/de_DE-thorsten-medium", "/workspace/hoerproben-en/modelle/en_US-john-medium"];
  const modelleDa = quellen.every(q => fs.existsSync(q + ".onnx") && fs.existsSync(q + ".onnx.json"));
  const angelegt = [];
  try {
    for (const sprache of ["de", "en"]) {
      const L = sprache.toUpperCase();
      const frei = c => { c.einrichtung.fertig = false; c.einrichtung.sprache = false; c.knopf.modus = "zwei"; };
      await szenario(L + " Sprachwahl zuerst (System de, gleiche Sprache)", sprache, frei, "?navlang=de", (cl, t) => spracheZuerst(cl, t, sprache, "de", sprache === "de" ? "links" : "rechts", sprache));
      await szenario(L + " Sprachwahl zuerst (System en, gleiche Sprache)", sprache, frei, "?navlang=en", (cl, t) => spracheZuerst(cl, t, sprache, "en", sprache === "en" ? "links" : "rechts", sprache));
      await szenario(L + " Sprache in den Einstellungen", sprache, c => { c.einrichtung.fertig = true; c.zurueck.sekunden = 0; }, "setup.html", (cl, t) => spracheInEinstellungen(cl, t, sprache));
    }
    if (modelleDa) {
      fs.mkdirSync(stimmenOrdner, { recursive: true });
      for (const q of quellen) for (const e of [".onnx", ".onnx.json"]) {
        const ziel = path.join(stimmenOrdner, path.basename(q) + e);
        if (!fs.existsSync(ziel)) { fs.copyFileSync(q + e, ziel); angelegt.push(ziel); }
      }
      const frei = c => { c.einrichtung.fertig = false; c.einrichtung.sprache = false; c.knopf.modus = "zwei"; };
      await szenario("DE Sprachwahl zuerst: English wählen stellt um", "de", frei, "?navlang=de", (cl, t) => spracheZuerst(cl, t, "de", "de", "rechts", "en"));
      await szenario("EN Sprachwahl zuerst: Deutsch wählen stellt um", "en", frei, "?navlang=en", (cl, t) => spracheZuerst(cl, t, "en", "en", "rechts", "de"));
    } else {
      console.log("Hinweis: Stimmen für den Umstell-Test fehlen, übersprungen");
    }
  } finally {
    angelegt.forEach(f => { try { fs.unlinkSync(f); } catch (err) {} });
  }
  for (const sprache of ["de", "en"]) {
    const L = sprache.toUpperCase();
    await szenario(L + " Einrichtung Zwei-Knopf (Tasten, Linksklick)", sprache, c => { c.einrichtung.fertig = false; c.knopf.modus = "zwei"; }, "", (cl, t) => setupAblauf(cl, t, false, sprache));
    await szenario(L + " Einrichtung Zwei-Knopf (Maus rechts/Kacheln)", sprache, c => { c.einrichtung.fertig = false; c.knopf.modus = "zwei"; }, "", (cl, t) => setupRechtsklick(cl, t, sprache));
    await szenario(L + " Einrichtung Ein-Knopf (Scan)", sprache, c => { c.einrichtung.fertig = false; c.knopf.modus = "ein"; c.knopf.scanMs = 2500; }, "", (cl, t) => setupAblauf(cl, t, true, sprache));
    await szenario(L + " Einrichtung Stimme", sprache, c => { c.einrichtung.fertig = false; c.knopf.modus = "zwei"; }, "", (cl, t) => setupStimme(cl, t, sprache));
    await szenario(L + " alte Einrichtung fragt neu", sprache, c => { c.einrichtung = { fertig: true, modus: "duo", stand: 0 }; }, "", (cl, t) => alteConfigFragtNeu(cl, t, sprache));
    for (const m of ["a", "b", "c"]) {
      await szenario(L + " Modus " + m, sprache, c => { c.einrichtung.fertig = true; c.modus = m; c.zurueck.sekunden = 0; }, "", (cl, t) => modusPfad(cl, t, sprache, m));
    }
    await szenario(L + " Gleich zurück", sprache, c => { c.einrichtung.fertig = true; c.knopf.modus = "zwei"; c.zurueck.sekunden = 8; c.zurueck.hinweisVorherSekunden = 5; c.zurueck.hinweis = "ansage"; }, "", (cl, t) => gleichZurueck(cl, t, sprache));
    await szenario(L + " App Zwei-Knopf", sprache, c => { c.einrichtung.fertig = true; c.knopf.modus = "zwei"; c.zurueck.sekunden = 0; }, "", (cl, t) => appZwei(cl, t, sprache));
    await szenario(L + " App Ein-Knopf", sprache, c => { c.einrichtung.fertig = true; c.knopf.modus = "ein"; c.knopf.scanMs = 3000; c.zurueck.sekunden = 0; }, "", (cl, t) => appEin(cl, t, sprache));
    await szenario(L + " Wahl-Wartezeit 3 s", sprache, c => { c.einrichtung.fertig = true; c.knopf.modus = "zwei"; c.zurueck.sekunden = 0; c.waehlSekunden = 3; }, "", (cl, t) => wahlWartezeit(cl, t, sprache));
    await szenario(L + " Autostart-Haken im Betreuerbereich", sprache, c => { c.einrichtung.fertig = true; c.zurueck.sekunden = 0; c.autostart = false; }, "setup.html", (cl, t) => autostartSchalter(cl, t, sprache));
    const basis = c => { c.einrichtung.fertig = true; c.knopf.modus = "zwei"; c.zurueck.sekunden = 0; c.modus = "b"; };
    await szenario(L + " Bilder-Diashow", sprache, c => { basis(c); c.bildSekunden = 3; seedBilder(3); }, "", (cl, t) => diashow(cl, t, sprache));
    await szenario(L + " Filme Listenseite und Player", sprache, c => { basis(c); seedFilme(["film1", "film2", "film3"]); }, "", async (cl, t) => { await filmListe(cl, t, sprache); await rangeTest(cl, t, sprache); });
    await szenario(L + " Filme Ein-Knopf-Scan", sprache, c => { basis(c); c.knopf.modus = "ein"; c.knopf.scanMs = 700; seedFilme(["film1", "film2", "film3"]); }, "", (cl, t) => filmScan(cl, t, sprache));
    await szenario(L + " Radio im Fenster", sprache, c => { basis(c); seedFilme(["ton"]); c.radio = { modus: "stream", name: "Testsender", url: "", stream: "http://127.0.0.1:" + port + "/api/medium?name=ton.webm" }; }, "", (cl, t) => radioStream(cl, t, sprache));
    await szenario(L + " Radio ohne Adresse", sprache, c => { basis(c); }, "", (cl, t) => radioOhneQuelle(cl, t, sprache));
    await szenario(L + " Fernsehen", sprache, c => { basis(c); ersatzMpv(true); c.fernsehen = { sender: [{ name: "Testsender", stream: "http://127.0.0.1:9/test.m3u8" }, { name: "Kaputt", stream: "http://127.0.0.1:9/kaputt.m3u8" }] }; }, "", (cl, t) => fernsehenAblauf(cl, t, sprache));
    await szenario(L + " Fernsehen ohne Sender", sprache, c => { basis(c); c.fernsehen = { sender: [] }; }, "", (cl, t) => ohneSender(cl, t, sprache));
    await szenario(L + " Aufgaben abhaken", sprache, c => { basis(c); schreibePflege({ erinnerungen: [], aufgaben: [{ id: "a1", text: "Fenster schließen", erledigt: false }, { id: "a2", text: "Tabletten bereitlegen", erledigt: false }], bestaetigt: {} }); }, "", (cl, t) => aufgabenListe(cl, t, sprache));
    await szenario(L + " Erinnerung", sprache, c => { basis(c); c.erinnerungPruefSekunden = 1; schreibePflege({ erinnerungen: [{ id: "e1", zeit: "00:00", text: "Tabletten nehmen", wiederholen: "taeglich", tage: [], datum: "", aktiv: true }], aufgaben: [], bestaetigt: {} }); }, "", (cl, t) => erinnerungAblauf(cl, t, sprache));
    await szenario(L + " Betreuerseite Erinnerungen und Aufgaben", sprache, c => { basis(c); }, "pflege.html", (cl, t) => pflegeSeite(cl, t, sprache));
    if (sprache === "de") {
      await szenario(L + " Einstellungstaste (Maus 3 s)", sprache, c => { c.einrichtung.fertig = true; c.zurueck.sekunden = 0; }, "", haltetaste);
      await szenario(L + " Einstellungstaste (beide Pfeiltasten)", sprache, c => { c.einrichtung.fertig = true; c.zurueck.sekunden = 0; }, "", halteTasten);
    }
  }
  const schlecht = ergebnisse.filter(r => !r.ok);
  console.log(ergebnisse.length + " Prüfungen, " + schlecht.length + " Fehler, " + Math.round((Date.now() - T) / 1000) + " s");
  if (schlecht.length) {
    schlecht.forEach(r => console.log(" - " + r.name));
    process.exitCode = 1;
  } else {
    console.log("EINGABE_OK");
  }
}

process.on("exit", () => { aufraeumen(); try { fs.rmSync(home, { recursive: true, force: true }); } catch (err) {} });
main().catch(err => { console.error(err && err.stack || err); aufraeumen(); process.exit(1); });
