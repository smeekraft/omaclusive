"use strict";
const params = new URLSearchParams(location.search);
if (params.has("selftest")) window.__selftest = true;
if (params.has("test")) {
  window.__test = true;
  document.title = "Omaclusive Test";
} else if (window.__selftest) {
  document.title = "Omaclusive Test";
} else {
  document.title = "Omaclusive";
}

const FESTE_STD = {
  zurueck: { wort: "Zurück", bild: "img/zurueck.svg" },
  nein: { wort: "Nein", bild: "img/nein.svg" },
  ja: { wort: "Ja", bild: "img/ja.svg" },
};

let C = null;
let cur = null;
let stack = [];
let index = {};
let fokus = "links";
let frage = null;
let away = false;
let dynToken = 0;
let lastAktiv = 0;
let keysDown = new Set();
let setupHalteT = null;
let sayNr = 0;
let idleTs = [];
let scanT = null;
let phase = "app";
let schritt = "bedienung";
let P = null;
let zaehlerT = null;
let bedienungWahl = "";
let hoerenWahl = false;
let wahlIndex = 0;
let anzeigeWert = "beides";
let paar = null;
let ohrToken = 0;
let hinweisFest = false;
let hinweisArtOffen = "";
let rufTimer = null;
let schauAn = false;
let schauTimer = null;
let schauGen = 0;
let filmTimer = null;
let filmToken = 0;
let knopfWahl = "";
let modusWahl = "";
let buehne = null; // Bild, Film oder Radio mit zwei Kacheln: { art: "schau"|"video"|"radio", pause: bool }
let erinnerung = null; // fällige Erinnerung: { id, tag, text, zeit, n, timer, fortsetzen }
let erinnerungenGesehen = {};
let schauListe = [];
let schauI = 0;
let schauFehler = 0;
let wahlWartet = null;
let tvAn = false; // ein Sender läuft im Vollbild (mpv)
let tvTimer = null;
let tvToken = 0; // gewählte Kachel, die noch vergrößert wartet: { seite, timer }

const el = id => document.getElementById(id);

function kartenVon(screen) {
  // Die Fernsehen-Kachel zeigt sich nur, wenn mindestens ein Sender eingetragen ist.
  return Pfad.karten(screen, C && C.ziele).filter(card => {
    const a = Pfad.aktionVon(card);
    return !(a && a.typ === "fernsehen" && !senderListe().length);
  });
}

function ohrStopp() {
  ohrToken += 1;
}

function hoerWoerter() {
  if (!C || !paar) return [];
  return [Pfad.wortVon(paar.links), Pfad.wortVon(paar.rechts)].filter(Boolean);
}

function ohrAn() {
  return !!(C && C.hoeren === true);
}

function starteOhr() {
  // Das Mikrofon ist standardmäßig aus ("hoeren": false). Bei Bluetooth-Kopfhörern
  // würde es den Ton auf das schlechte Telefonie-Profil umschalten.
  if (!ohrAn() || window.__selftest || window.__test || window.__ohr === "aus") return;
  const woerter = hoerWoerter();
  if (!woerter.length) return;
  const token = ++ohrToken;
  fetch("/api/hoeren", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ woerter: woerter }),
  }).then(r => r.json()).then(res => {
    if (token !== ohrToken) return;
    if (!res || res.ok === false) {
      window.__ohr = (res && res.grund) || "aus";
      return;
    }
    const treffer = Pfad.passend(res.text, woerter);
    if (!treffer) {
      starteOhr();
      return;
    }
    const vorher = ohrToken;
    spracheTrifft(treffer);
    if (ohrToken === vorher) starteOhr();
  }).catch(() => {
    if (token === ohrToken) window.__ohr = "aus";
  });
}

// Eine Ansage pro Aktion. Ein Text oder eine Liste kurzer Wörter ("Filme", "Bilder").
// Die neue Ansage stoppt die alte auf dem Server. Die Nummer verhindert, dass eine
// verspätete alte Anfrage nach der neuen noch einmal abgespielt wird.
function sprich(was) {
  const teile = (Array.isArray(was) ? was : [was])
    .map(t => String(t || "").replace(/\s+/g, " ").trim())
    .filter(Boolean);
  if (!teile.length) return;
  const text = teile.join(" ");
  window.__gesagt = text;
  (window.__sprache = window.__sprache || []).push(text);
  if (window.__selftest || !C || C.speak === false) return;
  ohrStopp();
  const nr = ++sayNr;
  fetch("/api/say", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(teile.length > 1
      ? { texte: teile, stimme: (C && C.stimme) || "", nr: nr }
      : { text: teile[0], stimme: (C && C.stimme) || "", nr: nr }),
  }).then(r => r.json()).then(res => {
    if (!res || !res.ok) console.warn("Ansage nicht abgespielt:", text);
  }).catch(err => console.warn("Ansage fehlgeschlagen:", text, err))
    .finally(() => { if (nr === sayNr) starteOhr(); });
}

function spracheTrifft(wort) {
  if (!paar) return;
  if (wort === Pfad.wortVon(paar.links)) return aktiviere("links");
  if (wort === Pfad.wortVon(paar.rechts)) return aktiviere("rechts");
}

function istZuhause() {
  return !!(C && cur === C.start && !frage && !away && stack.length === 0 && phase === "app");
}

function clearScan() {
  clearTimeout(scanT);
  scanT = null;
}

function clearIdle() {
  idleTs.forEach(clearTimeout);
  idleTs = [];
  clearScan();
}

function hinweisOffen() {
  const box = el("hinweis");
  return !!(box && !box.hidden);
}

function zaehlerStopp() {
  if (zaehlerT) clearInterval(zaehlerT);
  zaehlerT = null;
  const box = el("hinweis");
  if (box) box.classList.remove("zeit");
  window.__zaehler = null;
}

function versteckeHinweis() {
  zaehlerStopp();
  const box = el("hinweis");
  if (box) box.hidden = true;
  hinweisArtOffen = "";
}

// "Gleich zurück": Bild, Wort, große Zahl und ein Balken, der in der Restzeit leerläuft.
// Jede Eingabe schließt den Hinweis (versteckeHinweis) und startet die Zeit neu.
function zeigeHinweis(restMs) {
  const box = el("hinweis");
  if (!box) return;
  const bild = "img/zurueck.svg";
  zaehlerStopp();
  box.querySelector("img").src = bild;
  box.querySelector(".wort").textContent = T("Gleich zurück");
  box.hidden = false;
  hinweisArtOffen = "zurueck";
  window.__hinweisBild = bild;
  const rest = Math.max(1000, Number(restMs) || 5000);
  const ende = Date.now() + rest;
  const fuell = el("fuell");
  const zahl = el("zahl");
  if (fuell && zahl) {
    box.classList.add("zeit");
    fuell.style.transition = "none";
    fuell.style.width = "100%";
    void fuell.offsetWidth;
    fuell.style.transition = "width " + rest + "ms linear";
    fuell.style.width = "0%";
    const tick = () => {
      const noch = Math.max(0, Math.ceil((ende - Date.now()) / 1000));
      zahl.textContent = String(noch);
      window.__zaehler = noch;
    };
    tick();
    zaehlerT = setInterval(tick, 200);
  }
}

function einknopf() {
  return Pfad.knopfModus(C && C.knopf && C.knopf.modus) === "ein";
}

function armScan() {
  clearScan();
  window.__scan = false;
  if (!C || !einknopf() || erinnerung) return;
  window.__scan = true;
  const ms = Pfad.scanMs(C.knopf && C.knopf.scanMs);
  scanT = setTimeout(() => {
    if (hinweisOffen() || wahlWartet) {
      armScan();
      return;
    }
    weiter();
  }, ms);
}

function armIdle(opt) {
  opt = opt || {};
  clearIdle();
  if (!opt.behalten) {
    hinweisFest = false;
    versteckeHinweis();
  }
  if (!C || phase !== "app") return;
  if (opt.nurFest || buehne || erinnerung) {
    armScan();
    return;
  }
  const plan = Pfad.idlePlan(C.zurueck, istZuhause());
  window.__idle = plan;
  if (plan.aktiv) {
    if (plan.hinweisMs != null) idleTs.push(setTimeout(hinweis, plan.hinweisMs));
    idleTs.push(setTimeout(() => goStart("zeit"), plan.zurueckMs));
  }
  armScan();
}

function hinweis() {
  if (hinweisFest || hinweisOffen()) return; // nie zweimal ansagen
  window.__hinweis = (window.__hinweis || 0) + 1;
  const plan = window.__idle || {};
  zeigeHinweis((plan.zurueckMs || 0) - (plan.hinweisMs || 0));
  sprich(T("Gleich zurück zum Start."));
  if (plan.hinweis === "ton" && !window.__selftest) fetch("/api/hinweis", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
}

function clearSetup() {
  clearScan();
}

function zeigeRuf(art, name) {
  const box = el("hinweis");
  if (!box) return;
  const bilder = {
    unterwegs: "img/hilfe.svg",
    raus: "img/hilfe.svg",
    aus: "img/ruf-aus.svg",
    gesehen: "img/ruf-gesehen.svg",
    test: "img/ruf-test.svg",
  };
  const woerter = {
    unterwegs: T("Ich rufe"),
    raus: T("Ruf ist raus"),
    aus: T("Nicht raus"),
    gesehen: name || T("Gesehen"),
    test: T("Test"),
  };
  const bild = bilder[art] || bilder.aus;
  box.querySelector("img").src = bild;
  box.querySelector(".wort").textContent = woerter[art] || woerter.aus;
  box.hidden = false;
  hinweisFest = true;
  window.__hinweisBild = bild;
  window.__ruf = art;
}

function rufLokalAus() {
  zeigeRuf("aus");
  sprich(T("Der Ruf ist nicht rausgegangen."));
  armIdle({ behalten: true });
}

function rufBeobachten(seit) {
  if (window.__selftest || window.__test) return;
  if (rufTimer) clearTimeout(rufTimer);
  const start = Date.now();
  let warte = 4000;
  const tick = () => {
    if (Date.now() - start > 6 * 60 * 60 * 1000) {
      rufTimer = null;
      return;
    }
    fetch("/api/hilferuf/gesehen?since=" + encodeURIComponent(seit))
      .then(r => r.ok ? r.json() : null)
      .then(res => {
        if (res && res.gesehen) {
          rufTimer = null;
          zeigeRuf("gesehen", res.name);
          if (res.sagen) sprich(res.sagen);
          armIdle({ behalten: true });
          return;
        }
        warte = Math.min(20000, warte + 2000);
        rufTimer = setTimeout(tick, warte);
      })
      .catch(() => {
        warte = Math.min(20000, warte + 2000);
        rufTimer = setTimeout(tick, warte);
      });
  };
  rufTimer = setTimeout(tick, warte);
}

function rufSenden(art, nurWennFaellig) {
  const test = art === "test";
  if (window.__selftest || window.__test) {
    if (!nurWennFaellig) rufLokalAus();
    return;
  }
  if (!nurWennFaellig) {
    zeigeRuf(test ? "test" : "unterwegs");
    sprich(test ? T("Das ist ein Test.") : T("Ich rufe."));
  }
  const body = { art: test ? "test" : "ruf" };
  if (nurWennFaellig) body.nurWennFaellig = true;
  fetch("/api/hilferuf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => {
    if (!r.ok) {
      if (nurWennFaellig) return null;
      throw new Error("weg");
    }
    return r.json();
  }).then(res => {
    if (!res || (nurWennFaellig && res.faellig === false)) return;
    if (res.ok) {
      zeigeRuf(test ? "test" : "raus");
      if (res.sagen) sprich(res.sagen);
      if (res.seit != null) rufBeobachten(res.seit);
      armIdle({ behalten: true });
      return;
    }
    zeigeRuf("aus");
    sprich(res.sagen || (test ? T("Der Test ist nicht rausgegangen.") : T("Der Ruf ist nicht rausgegangen.")));
    armIdle({ behalten: true });
  }).catch(() => {
    if (nurWennFaellig) return;
    zeigeRuf("aus");
    sprich(test ? T("Der Test ist nicht rausgegangen.") : T("Der Ruf ist nicht rausgegangen."));
    armIdle({ behalten: true });
  });
}

function pruefeTest() {
  if (phase !== "app" || window.__selftest || window.__test) return;
  rufSenden("test", true);
}

// Die erste Einrichtung hat kein Zeitlimit: Sie wartet, bis jemand wählt.
function armSetup() {
  hinweisFest = false;
  versteckeHinweis();
  clearScan();
  if (phase !== "setup" || !C) return;
  armScan();
}


function anzeigeKlasse() {
  const art = phase === "setup" ? "beides" : ((C && C.anzeige) || "beides");
  document.body.classList.toggle("anzeige-bild", art === "bild");
  document.body.classList.toggle("anzeige-text", art === "text");
}

function festeDef(id) {
  const extra = (C && C.feste && C.feste[id]) || {};
  return {
    wort: extra.wort || T(FESTE_STD[id].wort),
    bild: extra.bild || FESTE_STD[id].bild,
  };
}

function viewOf(card) {
  card = card || {};
  return {
    wort: card.wort || card.label || "",
    bild: card.bild || card.image || "img/zurueck.svg",
  };
}

function mitZurueck() {
  return phase === "app" && !!C && cur !== C.start;
}


// Jede Frage der Einrichtung zeigt höchstens zwei Kacheln.
function setupPaar() {
  if (schritt === "sprache") {
    // Zweisprachig beschriftet. Die Sprache des Systems steht links (vorgewählt).
    const de = { wort: "Deutsch", sprechen: "Deutsch", bild: "img/sagen.svg", wert: "de" };
    const en = { wort: "English", sprechen: "English", bild: "img/sagen.svg", wert: "en" };
    return Pfad.duoPaar(systemSprache() === "de" ? [de, en] : [en, de], 0, false);
  }
  if (schritt === "bedienung") {
    return Pfad.duoPaar([
      { wort: T("Stimme"), sprechen: T("Stimme"), bild: "img/diktat.svg", wert: "stimme" },
      { wort: T("Knöpfe, Maus, Tasten"), sprechen: T("Knöpfe, Maus, Tasten"), bild: "img/zwei.svg", wert: "knoepfe" },
    ], 0, false);
  }
  if (schritt === "knopf") {
    return Pfad.duoPaar([
      { wort: T("Zwei Knöpfe"), sprechen: T("Zwei Knöpfe"), bild: "img/zwei.svg", wert: "zwei" },
      { wort: T("Ein Knopf"), sprechen: T("Ein Knopf"), bild: "img/einfach.svg", wert: "ein" },
    ], 0, false);
  }
  if (schritt === "autostart") {
    // Nein steht links (wie bei jeder Rückfrage) und ist der Standard.
    return Pfad.duoPaar([
      { wort: T("Nein"), sprechen: T("Nein"), bild: "img/nein.svg", wert: "nein" },
      { wort: T("Ja"), sprechen: T("Ja"), bild: "img/ja.svg", wert: "ja" },
    ], 0, false);
  }
  const namen = {
    b: { wort: T("Einfach"), bild: "img/sagen.svg" },
    a: { wort: T("Ganz einfach"), bild: "img/einfach.svg" },
    c: { wort: T("Mehr Auswahl"), bild: "img/mehr.svg" },
  };
  return Pfad.duoPaar(Pfad.MODI.map(id => ({ wort: namen[id].wort, sprechen: namen[id].wort, bild: namen[id].bild, wert: id })), wahlIndex, false);
}

function wortePaar(p) {
  return [Pfad.wortVon(p.links), Pfad.wortVon(p.rechts)];
}

function systemSprache() {
  const roh = String(params.get("navlang") || (navigator.languages && navigator.languages[0]) || navigator.language || "en");
  return roh.toLowerCase().indexOf("de") === 0 ? "de" : "en";
}

function setupFrage() {
  if (schritt === "sprache") return "Sprache · Language";
  if (schritt === "bedienung") return T("Wie willst du bedienen?");
  if (schritt === "knopf") return T("Wie viele Knöpfe?");
  if (schritt === "autostart") return T("Mit dem Rechner starten?");
  return T("Wie viel Auswahl?");
}

function setupAnsage() {
  return [setupFrage()].concat(wortePaar(setupPaar()));
}

// Kurze Ansage: nur die zwei Bildwörter. In der Rückfrage zuerst "Wirklich?".
function ansageJetzt() {
  if (phase === "setup") return setupAnsage();
  if (frage) return [T("Wirklich?"), Pfad.wortVon(frage.card)].concat(wortePaar(paar || Pfad.fragePaar(C && C.feste)));
  if (!paar) return [];
  return wortePaar(paar);
}

function sageZustand() {
  sprich(ansageJetzt());
}

function fuelle(id, card) {
  const knopf = el(id);
  knopf.querySelector("img").src = (card && (card.bild || card.image)) || "img/zurueck.svg";
  knopf.querySelector(".wort").textContent = (card && (card.wort || card.label)) || "";
}


// Kacheln: zwei große (links, rechts) und auf Listenseiten zwei kleine in der Fußzeile.
const KACHEL_IDS = { links: "links", rechts: "rechts", blaettern: "fuss-blaettern", zurueck: "fuss-zurueck" };
const kachelEl = seite => el(KACHEL_IDS[seite] || seite);

function markiereSichtbar() {
  // Markierung nur im Ein-Knopf-Scan. Sonst sind beide Kacheln gleich.
  const scan = einknopf();
  Object.keys(KACHEL_IDS).forEach(id => {
    const knopf = kachelEl(id);
    if (knopf) knopf.classList.toggle("an", scan && fokus === id);
  });
}

function buehnePaar() {
  const zurueck = { sonder: "buehne-zurueck", wort: T("Zurück"), sprechen: T("Zurück"), bild: "img/zurueck.svg" };
  const rechts = buehne.pause
    ? { sonder: "buehne-weiter", wort: T("Weiter"), sprechen: T("Weiter"), bild: "img/weiter.svg" }
    : { sonder: "buehne-pause", wort: T("Pause"), sprechen: T("Pause"), bild: "img/pause.svg" };
  return { links: zurueck, rechts: rechts, index: 0, blaettern: false, liste: [], buehne: true };
}

function erinnerungPaar() {
  const ok = { sonder: "erinnerung-ok", wort: T("Okay"), sprechen: T("Okay"), bild: "img/ja.svg" };
  return { links: ok, rechts: ok, index: 0, blaettern: false, liste: [], eine: true };
}

function buehneKlassen() {
  const b = document.body;
  if (!b) return;
  const art = erinnerung ? "text" : (buehne ? buehne.art : "");
  b.classList.toggle("buehne", !!art);
  b.classList.toggle("buehne-bild", art === "schau");
  b.classList.toggle("buehne-video", art === "video");
  b.classList.toggle("buehne-radio", art === "radio");
  b.classList.toggle("buehne-text", art === "text");
  b.classList.toggle("eine-kachel", !!erinnerung);
}

function renderDuo() {
  if (phase === "setup") paar = setupPaar();
  else if (erinnerung) paar = erinnerungPaar();
  else if (buehne) paar = buehnePaar();
  else if (frage) paar = Pfad.fragePaar(C && C.feste);
  else {
    const sc = (C && C.screens && C.screens[cur]) || { liste: [] };
    if (sc.seiten) paar = Pfad.seitenPaar(kartenVon(sc), index[cur] || 0, C && C.feste);
    else paar = Pfad.duoPaar(kartenVon(sc), index[cur] || 0, mitZurueck(), C && C.feste);
    index[cur] = paar.index;
  }
  fuelle("links", paar.links);
  fuelle("rechts", paar.rechts);
  if (paar.seitig) {
    fuelle("fuss-zurueck", paar.fussZ);
    fuelle("fuss-blaettern", paar.fussB);
  }
  document.body.classList.toggle("seiten", !!paar.seitig);
  window.__paar = {
    links: paar.links && paar.links.wort,
    rechts: paar.rechts && paar.rechts.wort,
    sonderL: (paar.links && paar.links.sonder) || "",
    sonderR: (paar.rechts && paar.rechts.sonder) || "",
  };
}


function renderSatz() {
  const satz = el("satz");
  if (phase === "app" && frage) {
    satz.hidden = false;
    satz.textContent = T("Wirklich?") + " " + (Pfad.wortVon(frage.card) || "");
  } else {
    satz.hidden = true;
    satz.textContent = "";
  }
}

function render() {
  buehneKlassen();
  document.body.classList.toggle("einrichtung", phase === "setup");
  document.body.classList.toggle("frage", !!(phase === "app" && frage));
  anzeigeKlasse();
  const sc = (C && C.screens && C.screens[cur]) || { name: "" };
  const ebene = el("ebene");
  if (ebene) {
    if (phase === "setup") ebene.textContent = setupFrage();
    else if (frage) ebene.textContent = "";
    else ebene.textContent = sc.name || "";
  }
  renderDuo();
  renderSatz();
  markiereSichtbar();
  window.__screen = cur;
  window.__fokus = fokus;
  window.__frage = !!frage;
  window.__index = index[cur] || 0;
  window.__phase = phase;
  window.__schritt = schritt;
  window.__buehne = erinnerung ? "erinnerung" : (buehne ? buehne.art + (buehne.pause ? ":pause" : "") : "");
}

function zeige(id, opt) {
  opt = opt || {};
  const sc = C.screens[id];
  if (!sc) return;
  cur = id;
  const cards = kartenVon(sc);
  if (!opt.behalteIndex) index[id] = 0;
  let i = index[id] || 0;
  if (!cards.length) i = 0;
  else if (i >= cards.length) i = 0;
  index[id] = i;
  fokus = "links";
  render();
  if (opt.ansage) sageZustand();
  if (phase === "setup") armSetup();
  else armIdle();
}

function schauStopp() {
  schauAn = false;
  schauGen += 1;
  if (schauTimer) clearTimeout(schauTimer);
  schauTimer = null;
  window.__schauEnde = false;
}

function filmStopp() {
  filmToken += 1;
  if (filmTimer) clearTimeout(filmTimer);
  filmTimer = null;
}

// ---- Bühne: Diashow, Film und Radio. Immer zwei Kacheln: Zurück und Pause (bei Pause: Zurück und Weiter) ----
function buehneBild(card, gen, beiFehler) {
  const img = el("buehneBild");
  if (!img) return;
  img.onload = null;
  img.onerror = () => {
    if (gen !== schauGen || !schauAn) return;
    beiFehler();
  };
  img.src = (card && card.bild) || "img/fotos.svg";
  window.__hinweisBild = img.src;
}

function mediumElement(art) {
  return el(art === "video" ? "buehneVideo" : "buehneTon");
}

function mediumHalt(elem) {
  if (!elem) return;
  try { elem.pause(); elem.removeAttribute("src"); elem.load(); } catch (err) {}
}

function buehneAus() {
  schauStopp();
  mediumHalt(el("buehneVideo"));
  mediumHalt(el("buehneTon"));
  const img = el("buehneBild");
  if (img) { img.onerror = null; img.onload = null; }
  buehne = null;
  buehneKlassen();
}

function schauNaechstes() {
  if (!schauAn || !buehne || buehne.art !== "schau") return;
  if (schauTimer) clearTimeout(schauTimer);
  schauTimer = null;
  if (schauI >= schauListe.length || schauFehler >= schauListe.length) {
    goStart("druck");
    return;
  }
  const card = schauListe[schauI];
  schauI += 1;
  const gen = ++schauGen;
  buehneBild(card, gen, () => {
    if (gen !== schauGen || !schauAn) return;
    schauGen += 1;
    schauFehler += 1;
    schauNaechstes();
  });
  if (!buehne.pause) schauZeitStarten(gen);
}

function schauZeitStarten(gen) {
  if (schauTimer) clearTimeout(schauTimer);
  schauTimer = setTimeout(() => {
    if (gen !== schauGen || !schauAn || !buehne || buehne.pause) return;
    schauNaechstes();
  }, Pfad.bildMs(C && C.bildSekunden));
}

function starteSchau(liste, von) {
  schauStopp();
  const fotos = (liste || []).filter(Boolean);
  if (!fotos.length) {
    sprich(T("Hier ist noch nichts."));
    goStart("druck");
    return;
  }
  schauListe = fotos;
  schauI = Math.max(0, von || 0);
  schauFehler = 0;
  schauAn = true;
  buehne = { art: "schau", pause: false };
  fokus = "links";
  render();
  schauNaechstes();
  sageZustand();
  armIdle({ behalten: true, nurFest: true });
}

function buehneWahl(card) {
  const s = card && card.sonder;
  if (s === "buehne-zurueck") return buehneZurueck();
  if (s === "buehne-pause") return buehnePause(true);
  if (s === "buehne-weiter") return buehnePause(false);
}

function buehnePause(an) {
  if (!buehne) return;
  buehne.pause = an;
  fokus = "links";
  if (buehne.art === "schau") {
    if (an) {
      if (schauTimer) clearTimeout(schauTimer);
      schauTimer = null;
    } else {
      schauZeitStarten(schauGen);
    }
  } else {
    const elem = mediumElement(buehne.art);
    try { if (an) elem.pause(); else elem.play().catch(() => {}); } catch (err) {}
  }
  render();
  sprich(an ? T("Pause.") : T("Weiter."));
  armIdle({ behalten: true, nurFest: true });
}

// Bilder: zurück zum Start. Film und Radio: zurück zur Seite, von der sie gestartet wurden.
function buehneZurueck() {
  if (!buehne) return;
  const art = buehne.art;
  if (art === "schau") {
    goStart("druck");
    return;
  }
  buehneAus();
  fokus = "links";
  render();
  sageZustand();
  armIdle();
}

function filmBeobachten() {
  const token = filmToken;
  const poll = () => {
    if (token !== filmToken || window.__selftest || window.__test) return;
    fetch("/api/film").then(r => r.ok ? r.json() : null).then(stand => {
      if (token !== filmToken) return;
      if (stand && stand.laeuft) {
        filmTimer = setTimeout(poll, 1000);
        return;
      }
      away = false;
      goStart("druck");
    }).catch(() => {
      if (token !== filmToken) return;
      filmTimer = setTimeout(poll, 2000);
    });
  };
  filmTimer = setTimeout(poll, 1000);
}

// Film: im Fenster mit Zurück und Pause. Geht das Format nicht im Browser, spielt der externe Player (mpv).
function starteFilm(name) {
  if (window.__selftest || window.__test) {
    sprich(T("Das geht hier nicht."));
    goStart("druck");
    return;
  }
  const video = el("buehneVideo");
  schauStopp();
  buehne = { art: "video", pause: false };
  video.onended = () => { if (buehne && buehne.art === "video") buehneZurueck(); };
  video.onerror = () => {
    if (!buehne || buehne.art !== "video") return;
    buehneAus();
    filmExtern(name);
  };
  video.src = "/api/medium?name=" + encodeURIComponent(name || "");
  const start = video.play();
  if (start && start.catch) start.catch(() => {});
  fokus = "links";
  render();
  sageZustand();
  armIdle({ behalten: true, nurFest: true });
}

function filmExtern(name) {
  fetch("/api/film", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || "" }),
  }).then(r => r.ok ? r.json() : null).then(res => {
    if (!res || !res.ok) {
      sprich(T("Das geht hier nicht."));
      goStart("druck");
      return;
    }
    away = true;
    filmToken += 1;
    filmBeobachten();
  }).catch(() => {
    sprich(T("Das geht hier nicht."));
    goStart("druck");
  });
}

// Radio: Quelle steht in config "radio". Stream (im Fenster, mit Zurück und Pause) oder Link im Browser.
function starteRadio() {
  const r = (C && C.radio) || {};
  const stream = String(r.stream || "").trim();
  const url = String(r.url || "").trim();
  const web = /^https?:\/\//i;
  if (r.modus === "stream" && web.test(stream)) {
    if (window.__selftest || window.__test) {
      sprich(T("Test. Nicht geöffnet."));
      armIdle();
      return;
    }
    const ton = el("buehneTon");
    schauStopp();
    buehne = { art: "radio", pause: false };
    const text = el("buehneText");
    text.textContent = r.name || T("Radio");
    ton.onerror = () => {
      if (!buehne || buehne.art !== "radio") return;
      buehneAus();
      render();
      sprich(T("Das geht hier nicht."));
      armIdle();
    };
    ton.src = stream;
    const start = ton.play();
    if (start && start.catch) start.catch(() => {});
    fokus = "links";
    render();
    sageZustand();
    armIdle({ behalten: true, nurFest: true });
    return;
  }
  if (web.test(url)) {
    if (window.__selftest || window.__test) {
      sprich(T("Test. Nicht geöffnet."));
      armIdle();
      return;
    }
    sprich(T("Ist offen."));
    oeffneZiel(url);
    armIdle();
    return;
  }
  sprich(T("Das ist noch nicht eingerichtet."));
  armIdle();
}

// Aufgaben: normale Liste, eine Karte je offener Aufgabe. Die Kachel antippen hakt ab.
function aufgabenKarten(liste) {
  const items = (liste || []).map(a => ({
    wort: a.text,
    sprechen: a.text,
    bild: "img/aufgabe.svg",
    aktion: { typ: "aufgabe", id: a.id },
  }));
  return items.length ? items : [{
    wort: T("Nichts zu tun"),
    sprechen: T("Nichts zu tun."),
    bild: "img/erledigt.svg",
    aktion: { typ: "sprechen", text: T("Nichts zu tun.") },
  }];
}

function aufgabenLaden(id, ansagen) {
  if (window.__selftest || window.__test) return;
  const token = ++dynToken;
  fetch("/api/aufgaben", { cache: "no-store" })
    .then(r => r.ok ? r.json() : null)
    .then(res => {
      if (token !== dynToken || cur !== id || !res || !res.ok) return;
      C.screens[id].liste = aufgabenKarten(res.offen);
      index[id] = 0;
      fokus = "links";
      render();
      if (ansagen) sageZustand();
      armIdle();
    })
    .catch(() => {});
}

function oeffneAufgaben() {
  const id = "ordner-aufgaben";
  stack.push(cur);
  C.screens[id] = { name: T("Aufgaben"), liste: aufgabenKarten([]) };
  zeige(id, { ansage: true });
  aufgabenLaden(id, true);
}

function aufgabeAbhaken(card) {
  const a = Pfad.aktionVon(card);
  const id = cur;
  fetch("/api/aufgaben/abhaken", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: a && a.id }),
  }).then(r => r.ok ? r.json() : null).then(res => {
    if (!res || !res.ok) {
      sprich(T("Das hat nicht geklappt."));
      armIdle();
      return;
    }
    sprich(T("Erledigt."));
    if (cur === id) aufgabenLaden(id, false);
  }).catch(() => {
    sprich(T("Das hat nicht geklappt."));
    armIdle();
  });
}

// ---- Erinnerungen: sichtbar und vorgelesen, bestätigt mit einer Kachel ----
function erinnerungAnsage() {
  if (!erinnerung) return;
  sprich([T("Erinnerung."), erinnerung.text]);
}

function medienPausieren() {
  if (!buehne || buehne.pause || (buehne.art !== "video" && buehne.art !== "radio")) return false;
  try { mediumElement(buehne.art).pause(); } catch (err) {}
  return true;
}

function erinnerungZeigen(e) {
  abbrechenWahl();
  if (tvAn) {
    // Fernsehen läuft im Vollbild: aus, damit die Erinnerung zu sehen ist
    tvStopp();
    away = false;
    if (!window.__selftest) fetch("/api/back", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
  }
  const wiederholS = Math.max(10, Math.min(600, Number(C && C.erinnerungWiederholSekunden) || 60));
  erinnerung = { id: e.id, tag: e.tag, text: e.text, zeit: e.zeit, n: 0, fortsetzen: medienPausieren() };
  const text = el("buehneText");
  text.textContent = "";
  const klein = document.createElement("small");
  klein.textContent = T("Erinnerung") + " " + (e.zeit || "");
  text.appendChild(klein);
  text.appendChild(document.createTextNode(e.text));
  fokus = "links";
  render();
  erinnerungAnsage();
  erinnerung.timer = setInterval(() => {
    if (!erinnerung || erinnerung.n >= 10) return;
    erinnerung.n += 1;
    erinnerungAnsage();
  }, wiederholS * 1000);
  armIdle();
}

function erinnerungOk() {
  const e = erinnerung;
  if (!e) return;
  clearInterval(e.timer);
  erinnerung = null;
  erinnerungenGesehen[e.id + "|" + e.tag] = true;
  fetch("/api/erinnerung/bestaetigen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: e.id }),
  }).catch(() => {});
  if (e.fortsetzen && buehne) {
    try { const m = mediumElement(buehne.art); const p = m.play(); if (p && p.catch) p.catch(() => {}); } catch (err) {}
  }
  fokus = "links";
  render();
  sprich(T("Okay."));
  armIdle();
}

function erinnerungenPruefen() {
  if (window.__selftest || window.__test || !C || phase !== "app" || erinnerung || frage || hinweisOffen()) return;
  fetch("/api/erinnerung", { cache: "no-store" })
    .then(r => r.ok ? r.json() : null)
    .then(res => {
      if (!res || !res.ok || !Array.isArray(res.faellig) || !res.faellig.length) return;
      if (erinnerung || phase !== "app" || frage) return;
      const e = res.faellig.find(x => !erinnerungenGesehen[x.id + "|" + x.tag]);
      if (e) erinnerungZeigen(e);
    })
    .catch(() => {});
}

function erinnerungenStarten() {
  if (window.__selftest || window.__test) return;
  const s = Math.max(1, Math.min(300, Number(C && C.erinnerungPruefSekunden) || 20));
  setInterval(erinnerungenPruefen, s * 1000);
  setTimeout(erinnerungenPruefen, 1500);
}

// Bilder im einfachen Modus (a, b): gleich die Diashow. Sonst die Listenseite.
function diashowAuto() {
  return (window.__modus || (C && C.modus)) !== "c" && !(window.__selftest || window.__test);
}

function oeffneOrdner(quelle) {
  quelle = quelle || "bilder";
  if (quelle === "bilder" && diashowAuto()) {
    const token = ++dynToken;
    fetch("/api/ordner?quelle=bilder")
      .then(r => r.ok ? r.json() : null)
      .then(res => {
        if (token !== dynToken) return;
        const fotos = ((res && res.liste) || []).filter(k => k && k.aktion && k.aktion.typ === "schau");
        if (fotos.length) starteSchau(fotos, 0);
        else ordnerListe(quelle);
      })
      .catch(() => { if (token === dynToken) ordnerListe(quelle); });
    return;
  }
  ordnerListe(quelle);
}

function ordnerListe(quelle) {
  const id = "ordner-" + (quelle || "bilder");
  const name = quelle === "filme" ? T("Filme") : T("Bilder");
  const bild = quelle === "filme" ? "img/fernsehen.svg" : "img/fotos.svg";
  stack.push(cur);
  C.screens[id] = {
    name: name,
    seiten: quelle === "filme",
    liste: [{
      wort: T("Noch leer"),
      sprechen: T("Hier ist noch nichts."),
      bild: bild,
      aktion: { typ: "sprechen", text: T("Hier ist noch nichts.") },
    }],
  };
  zeige(id, { ansage: true });
  if (window.__selftest || window.__test) return;
  const token = ++dynToken;
  fetch("/api/ordner?quelle=" + encodeURIComponent(quelle || ""))
    .then(r => r.ok ? r.json() : null)
    .then(res => {
      if (token !== dynToken || cur !== id) return;
      const items = res && Array.isArray(res.liste) ? res.liste : [];
      if (!items.length) return;
      C.screens[id].liste = items;
      index[id] = 0;
      fokus = "links";
      render();
      sageZustand();
      armIdle();
    })
    .catch(() => {});
}

function goStart(grund) {
  abbrechenWahl();
  buehneAus();
  filmStopp();
  tvStopp();
  const zuhause = istZuhause();
  if (grund === "zeit" && zuhause) {
    clearIdle();
    return;
  }
  dynToken += 1;
  frage = null;
  stack = [];
  away = false;
  if (!window.__selftest && grund !== "still") fetch("/api/back", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
  if (C && C.start) {
    index[C.start] = 0;
    zeige(C.start, { ansage: grund === "zeit" || grund === "druck" });
  }
}

function hoch() {
  if (frage) return abbruch();
  if (!stack.length) {
    render();
    sprich(cur === C.start ? T("Du bist am Start.") : ansageJetzt());
    armIdle();
    return;
  }
  zeige(stack.pop(), { ansage: true, behalteIndex: true });
}


function abbruch() {
  const text = (frage && frage.card && frage.card.abbruch) || T("Nicht gemacht.");
  frage = null;
  fokus = "links";
  render();
  sprich(T("Nein.") + " " + text);
  armIdle();
}

function zusage() {
  const card = Object.assign({}, frage.card, { _ja: true, bestaetigen: false, confirm: false });
  frage = null;
  fokus = "links";
  render();
  run(card);
}

// Ein-Knopf-Scan: die Markierung wandert zur anderen Kachel und sagt das Wort.
function weiter() {
  const ordnung = (paar && paar.seitig) ? ["links", "rechts", "blaettern", "zurueck"] : ["links", "rechts"];
  fokus = ordnung[(ordnung.indexOf(fokus) + 1) % ordnung.length];
  render();
  sprich(Pfad.wortVon(karteVon(fokus)));
  armIdle();
}

function karteVon(seite) {
  if (!paar) return null;
  if (seite === "blaettern") return paar.fussB || null;
  if (seite === "zurueck") return paar.fussZ || null;
  return seite === "rechts" ? paar.rechts : paar.links;
}

function seiteBlaettern() {
  index[cur] = Pfad.naechsteSeite(paar);
  fokus = "links";
  render();
  sageZustand();
  armIdle();
}

function waehleKarte(i) {
  const cards = kartenVon(C.screens[cur]);
  const card = cards[i];
  if (!card) return;
  index[cur] = i;
  fokus = "links";
  render();
  run(card);
}

function andereKarte() {
  const n = (paar && paar.liste && paar.liste.length) || 0;
  if (!n) return;
  index[cur] = (paar.index + 1) % n;
  fokus = "links";
  render();
  sageZustand();
  armIdle();
}

function abbrechenWahl() {
  if (!wahlWartet) return;
  clearTimeout(wahlWartet.timer);
  wahlWartet = null;
  Object.keys(KACHEL_IDS).forEach(id => kachelEl(id) && kachelEl(id).classList.remove("gewaehlt"));
  window.__wahlWartet = false;
}

// Die gewählte Kachel bleibt vergrößert stehen (Config "waehlSekunden", Standard 3 s),
// dann erst läuft die Eingabe. Eine andere Taste in dieser Zeit bricht ab.
function aktiviere(seite) {
  if (seite === "blaettern" || seite === "zurueck") {
    if (!(paar && paar.seitig)) return; // Fußkacheln gibt es nur auf Listenseiten
  } else {
    seite = seite === "rechts" ? "rechts" : "links";
  }
  const ms = (window.__selftest || window.__test) ? 0 : Pfad.waehlMs(C && C.waehlSekunden);
  if (wahlWartet) {
    if (wahlWartet.seite !== seite) abbrechenWahl();
    return;
  }
  if (ms <= 0) return aktiviereJetzt(seite);
  if (!paar) render();
  fokus = seite;
  markiereSichtbar();
  const knopf = kachelEl(seite);
  if (knopf) knopf.classList.add("gewaehlt");
  window.__wahlWartet = true;
  window.__wahlMs = ms;
  wahlWartet = {
    seite: seite,
    timer: setTimeout(() => {
      wahlWartet = null;
      if (knopf) knopf.classList.remove("gewaehlt");
      window.__wahlWartet = false;
      aktiviereJetzt(seite);
    }, ms),
  };
}

function aktiviereJetzt(seite) {
  if (!paar) render();
  fokus = seite;
  markiereSichtbar();
  const card = karteVon(seite);
  if (!card) return;
  if (erinnerung) return erinnerungOk();
  if (buehne) return buehneWahl(card);
  if (phase === "setup") return setupWahl(card);
  if (card.sonder === "blaettern") return seiteBlaettern();
  if (card.sonder === "andere") return andereKarte();
  if (card.sonder === "zurueck") return hoch();
  if (card.sonder === "nein") return abbruch();
  if (card.sonder === "ja") return zusage();
  run(card);
}


function setupNoetig() {
  if (window.__selftest || window.__test) return false;
  const e = (C && C.einrichtung) || {};
  return Pfad.einrichtungNoetig(e);
}

function configZumSpeichern() {
  const kopie = JSON.parse(JSON.stringify(C));
  delete kopie.pluginsAn;
  const screens = kopie.screens || {};
  Object.keys(screens).forEach(id => {
    if (id.indexOf("plugin-") === 0 || id.indexOf("ordner-") === 0 || id.indexOf("dyn-") === 0) delete screens[id];
  });
  const liste = screens.start && screens.start.liste;
  if (Array.isArray(liste)) {
    screens.start.liste = liste.filter(card => {
      const ziel = card && card.aktion && card.aktion.ziel;
      return !ziel || String(ziel).indexOf("plugin-") !== 0;
    });
  }
  return kopie;
}

function speichere() {
  if (window.__selftest || window.__test) return Promise.resolve(true);
  return fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configZumSpeichern()),
  }).then(r => {
    if (!r.ok) sprich(T("Nicht gespeichert."));
    return r.ok;
  }).catch(() => {
    sprich(T("Nicht gespeichert."));
    return false;
  });
}

// Der Pfad (Vorlage des Modus oder eigener Pfad der Angehörigen) kommt vom Server.
function pfadAnwenden(p) {
  C.screens = p.screens;
  C.start = p.start || "start";
  C.pluginsAn = p.plugins === true;
  window.__modus = p.modus;
  window.__pfadQuelle = p.quelle;
}

function pfadLaden() {
  if (window.__selftest || window.__test) return Promise.resolve(null);
  return fetch("/api/pfad", { cache: "no-store" })
    .then(r => (r.ok ? r.json() : null))
    .then(p => {
      if (!p || !p.ok || !p.screens || !p.screens[p.start || "start"]) return null;
      P = p;
      pfadAnwenden(p);
      return p;
    })
    .catch(() => null);
}

function modusWerte(id) {
  const liste = (P && P.modi) || [];
  return liste.find(m => m.id === id) || null;
}

// Ja: Eintrag anlegen. Sonst nur den Zustand der Datei lesen, damit "autostart" in der Config stimmt.
function autostartAbgleich(ja) {
  if (window.__selftest || window.__test) return Promise.resolve(ja);
  const aufruf = ja
    ? fetch("/api/autostart", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ an: true }) })
    : fetch("/api/autostart", { cache: "no-store" });
  return aufruf.then(r => (r.ok ? r.json() : null)).then(d => !!(d && d.an === true)).catch(() => false);
}

function setupFertig(entscheid) {
  if (phase !== "setup") return;
  phase = "app";
  clearSetup();
  entscheid = entscheid || Pfad.einrichtungStandard();
  const modus = entscheid.modus || "b";
  const knopf = entscheid.knopf || knopfWahl || (C.knopf && C.knopf.modus) || "zwei";
  C.einrichtung = { fertig: true, sprache: true, stand: Pfad.EINRICHTUNG_STAND, bedienung: entscheid.bedienung || bedienungWahl || "knoepfe" };
  C.modus = modus;
  C.hoeren = (entscheid.hoeren === true) || hoerenWahl === true;
  if (!C.knopf) C.knopf = { modus: "zwei", scanMs: 3000 };
  C.knopf.modus = Pfad.knopfModus(knopf);
  const werte = modusWerte(modus);
  if (werte) {
    if (!C.zurueck) C.zurueck = {};
    C.zurueck.sekunden = werte.zurueckSekunden;
    C.zurueck.hinweisVorherSekunden = 5;
    C.knopf.scanMs = werte.scanMs;
  }
  // Autostart nur nach ausdrücklichem Ja. Bei Nein/ohne Antwort wird nichts angelegt und nichts angefasst.
  const autostartJa = entscheid.autostart === true;
  C.autostart = false;
  const name = werte ? werte.name : modus;
  autostartAbgleich(autostartJa).then(an => {
    C.autostart = an;
    return speichere();
  }).then(() => pfadLaden()).then(() => {
    if (C.start && C.screens[C.start]) {
      stack = [];
      frage = null;
      index = {};
      if (C.pluginsAn !== false) pluginsHolen();
      zeige(C.start, { ansage: false });
    }
    sprich([name].concat(ansageJetzt()));
  });
}

// Erster Schritt: Sprache. Gleiche Sprache: nur merken. Andere: Texte und Stimme umstellen (Server), dann neu laden.
function spracheErstFlag(extra) {
  C.einrichtung = Object.assign({}, C.einrichtung, { sprache: true }, extra || {});
}

function spracheErstWeiter() {
  schritt = "bedienung";
  wahlIndex = 0;
  render();
  sprich(setupAnsage());
  armSetup();
}

function spracheErstFehler() {
  const text = "Das Laden hat nicht geklappt. Ist das Internet an? · Download failed. Is the internet on?";
  schritt = "sprache";
  wahlIndex = 0;
  render();
  el("ebene").textContent = text;
  sprich(text);
  armSetup();
}

function spracheErstWahl(sprache) {
  const gleich = String((C && C.language) || "de").split("-")[0] === sprache;
  if (window.__selftest || window.__test) {
    window.__spracheWahl = sprache;
    spracheErstFlag();
    return spracheErstWeiter();
  }
  if (gleich) {
    spracheErstFlag();
    return speichere().then(spracheErstWeiter);
  }
  el("ebene").textContent = "Einen Moment … · One moment …";
  fetch("/api/sprache", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: sprache }) })
    .then(r => { if (!r.ok) throw new Error("sprache"); })
    .then(() => new Promise((ok, nein) => {
      const t = setInterval(() => {
        fetch("/api/stimmen", { cache: "no-store" }).then(r => r.json()).then(z => {
          if (z.job.status === "laeuft") return;
          clearInterval(t);
          if (z.job.status === "fertig") ok(); else nein(new Error("laden"));
        }).catch(() => {});
      }, 800);
    }))
    .then(() => fetch("config.json", { cache: "no-store" }).then(r => r.json()))
    .then(c => {
      c.einrichtung = Object.assign({}, c.einrichtung, { sprache: true });
      return fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) });
    })
    .then(r => { if (!r.ok) throw new Error("speichern"); location.reload(); })
    .catch(spracheErstFehler);
}

function setupWahl(card) {
  clearSetup();
  fokus = "links";
  if (card.sonder === "andere") {
    wahlIndex += 1;
    render();
    sprich(setupAnsage());
    armSetup();
    return;
  }
  const entscheid = Pfad.einrichtungWahl(schritt, card.wert);
  if (entscheid.sprache) return spracheErstWahl(entscheid.sprache);
  if (entscheid.bedienung) bedienungWahl = entscheid.bedienung;
  if (entscheid.knopf) knopfWahl = entscheid.knopf;
  if (entscheid.modus) modusWahl = entscheid.modus;
  if (entscheid.hoeren !== undefined) hoerenWahl = entscheid.hoeren === true;
  if (entscheid.fertig) {
    if (!entscheid.knopf && knopfWahl) entscheid.knopf = knopfWahl;
    if (!entscheid.modus) entscheid.modus = modusWahl || "b";
    setupFertig(entscheid);
    return;
  }
  schritt = entscheid.schritt;
  wahlIndex = 0;
  render();
  sprich(setupAnsage());
  armSetup();
}

function openDynamic(quelle, opt) {
  const id = "dyn-" + quelle;
  const token = ++dynToken;
  const name = quelle === "bt.list" ? "Bluetooth" : "WLAN";
  const refresh = !!(opt && opt.refresh);
  if (!refresh) stack.push(cur);
  C.screens[id] = {
    name: name,
    dynamisch: quelle,
    liste: [{
      wort: T("Suche"),
      sprechen: T("Ich suche"),
      bild: "img/suche.svg",
      aktion: { typ: "sprechen", text: T("Ich suche.") },
    }],
  };
  cur = id;
  index[id] = 0;
  fokus = "links";
  render();
  sageZustand();
  armIdle();
  fetch("/api/liste?quelle=" + encodeURIComponent(quelle))
    .then(r => r.json())
    .then(res => {
      if (token !== dynToken || cur !== id) return;
      const items = (res && res.liste) || [];
      C.screens[id].liste = items.length ? items : [{
        wort: T("Keine"),
        sprechen: T("Nichts gefunden"),
        bild: "img/wlan-aus.svg",
        aktion: { typ: "sprechen", text: T("Nichts gefunden.") },
      }];
      index[id] = 0;
      fokus = "links";
      render();
      sageZustand();
      armIdle();
    })
    .catch(() => {
      if (token !== dynToken || cur !== id) return;
      C.screens[id].liste = [{
        wort: T("Geht nicht"),
        sprechen: T("Das hat nicht geklappt"),
        bild: "img/wlan-aus.svg",
        aktion: { typ: "sprechen", text: T("Das hat nicht geklappt.") },
      }];
      index[id] = 0;
      fokus = "links";
      render();
      sprich(T("Das hat nicht geklappt."));
      armIdle();
    });
}

// ---- Fernsehen: eine Kachel je Lieblingssender, ein Druck startet den Stream im Vollbild (mpv) ----
// Ruhig: kein Startbild, keine Bedienleiste, keine Texte, nichts blinkt (WCAG 2.3.1).
function senderListe() {
  const tv = (C && C.fernsehen) || {};
  // dieselben Regeln wie fernsehen.sender_liste im Server, damit die Nummern gleich zählen
  const url = /^https?:\/\/[^\s\x00-\x1f"'<>]{1,480}$/;
  const name = x => String(x == null ? "" : x).replace(/\s+/g, " ").trim();
  return (Array.isArray(tv.sender) ? tv.sender : [])
    .map((s, nr) => ({ s: s, nr: nr }))
    .filter(x => x.s && typeof x.s === "object" && x.s.aus !== true && name(x.s.name) && !/[\x00-\x1f\x7f]/.test(name(x.s.name))
      && url.test(String(x.s.stream || "").trim()))
    .slice(0, 6);
}

function oeffneFernsehen() {
  const id = "ordner-fernsehen";
  stack.push(cur);
  // nr zählt die gültigen Sender, genau wie der Server (fernsehen.sender_liste).
  C.screens[id] = {
    name: T("Fernsehen"),
    liste: senderListe().map((x, i) => ({
      wort: String(x.s.name).replace(/\s+/g, " ").trim().slice(0, 40),
      sprechen: String(x.s.name).replace(/\s+/g, " ").trim().slice(0, 40),
      bild: /^img\/[A-Za-z0-9_.-]+\.svg$/.test(String(x.s.bild || "")) ? x.s.bild : "img/fernsehen.svg",
      aktion: { typ: "sender", nr: i },
    })),
  };
  zeige(id, { ansage: true });
}

function tvStopp() {
  tvToken += 1;
  if (tvTimer) clearTimeout(tvTimer);
  tvTimer = null;
  tvAn = false;
}

// Geht ein Sender nicht: ein ruhiges Bild, ein kurzes Wort, dann der Start. Kein Fachtext.
function tvGehtNicht() {
  goStart("still");
  const box = el("hinweis");
  if (box) {
    box.querySelector("img").src = "img/fernsehen.svg";
    box.querySelector(".wort").textContent = T("Geht gerade nicht");
    box.hidden = false;
    hinweisFest = true;
    window.__hinweisBild = "img/fernsehen.svg";
  }
  // nach 8 Sekunden geht die Meldung still weg (jeder Druck schließt sie früher)
  setTimeout(() => {
    const b = el("hinweis");
    if (b && !b.hidden && window.__hinweisBild === "img/fernsehen.svg" && !tvAn) {
      hinweisFest = false;
      versteckeHinweis();
    }
  }, 8000);
  window.__tvFehler = (window.__tvFehler || 0) + 1;
  sprich(T("Das Fernsehen geht gerade nicht."));
  armIdle({ behalten: true });
}

function tvEnde(stand) {
  tvStopp();
  away = false;
  if (stand && stand.fehler) tvGehtNicht();
  else goStart("druck");
}

function tvBeobachten() {
  const token = tvToken;
  const poll = () => {
    if (token !== tvToken) return;
    fetch("/api/fernsehen", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(stand => {
      if (token !== tvToken) return;
      if (stand && stand.laeuft) {
        tvTimer = setTimeout(poll, 1000);
        return;
      }
      tvEnde(stand);
    }).catch(() => {
      if (token !== tvToken) return;
      tvTimer = setTimeout(poll, 2000);
    });
  };
  if (tvTimer) clearTimeout(tvTimer);
  tvTimer = setTimeout(poll, 1000);
}

function starteSender(nr) {
  if (window.__selftest || window.__test) {
    sprich(T("Test. Nicht geöffnet."));
    armIdle();
    return;
  }
  clearIdle();
  fetch("/api/fernsehen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nr: nr }),
  }).then(r => r.ok ? r.json() : null).then(res => {
    if (!res || !res.ok) {
      tvGehtNicht();
      return;
    }
    tvStopp();
    tvAn = true;
    away = true;
    tvBeobachten();
  }).catch(() => tvGehtNicht());
}

function oeffneZiel(wert) {
  away = true;
  const body = /^https?:/i.test(wert) ? { url: wert } : { path: wert };
  fetch("/api/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch(() => {});
}

function run(card) {
  const a = Pfad.aktionVon(card);
  const sc = C.screens[cur] || {};
  if (!a) {
    sageZustand();
    armIdle();
    return;
  }
  if (Pfad.brauchtRueckfrage(card)) {
    frage = { card: card, id: cur, index: index[cur] || 0 };
    fokus = "nein";
    lastAktiv = 0;
    render();
    sageZustand();
    armIdle();
    return;
  }
  if (a.typ === "untermenue") {
    if (!a.ziel || !C.screens[a.ziel]) {
      sprich(T("Das gibt es nicht."));
      armIdle();
      return;
    }
    if (!Pfad.darfTiefer(stack.length + 1)) {
      sprich(T("Das ist die letzte Ebene."));
      armIdle();
      return;
    }
    stack.push(cur);
    zeige(a.ziel, { ansage: true });
    return;
  }
  if (a.typ === "dynamisch") {
    if (!Pfad.darfTiefer(stack.length + 1)) {
      sprich(T("Das ist die letzte Ebene."));
      armIdle();
      return;
    }
    openDynamic(a.quelle || a.ziel);
    return;
  }
  if (a.typ === "ordner") {
    if (!Pfad.darfTiefer(stack.length + 1)) {
      sprich(T("Das ist die letzte Ebene."));
      armIdle();
      return;
    }
    oeffneOrdner(a.quelle || a.ziel);
    return;
  }
  if (a.typ === "schau") {
    const fotos = kartenVon(C.screens[cur]).filter(eintrag => {
      const aktion = Pfad.aktionVon(eintrag);
      return aktion && aktion.typ === "schau";
    });
    let von = fotos.indexOf(card);
    if (von < 0) {
      von = fotos.findIndex(eintrag => {
        const aktion = Pfad.aktionVon(eintrag);
        return aktion && aktion.name === a.name;
      });
    }
    starteSchau(fotos, von < 0 ? 0 : von);
    return;
  }
  if (a.typ === "film") {
    starteFilm(a.name || "");
    return;
  }
  if (a.typ === "radio") {
    starteRadio();
    return;
  }
  if (a.typ === "fernsehen") {
    if (!Pfad.darfTiefer(stack.length + 1)) {
      sprich(T("Das ist die letzte Ebene."));
      armIdle();
      return;
    }
    oeffneFernsehen();
    return;
  }
  if (a.typ === "sender") {
    starteSender(a.nr);
    return;
  }
  if (a.typ === "aufgaben") {
    if (!Pfad.darfTiefer(stack.length + 1)) {
      sprich(T("Das ist die letzte Ebene."));
      armIdle();
      return;
    }
    oeffneAufgaben();
    return;
  }
  if (a.typ === "aufgabe") {
    aufgabeAbhaken(card);
    return;
  }
  if (a.typ === "hilferuf") {
    rufSenden("ruf", false);
    return;
  }
  if (a.typ === "sprechen") {
    sprich(a.text || Pfad.wortVon(card));
    armIdle();
    return;
  }
  if (a.typ === "ziel") {
    const wert = String((C.ziele && C.ziele[a.name]) || "").trim();
    if (!wert) {
      sprich(a.leer || T("Das ist noch nicht eingerichtet."));
      armIdle();
      return;
    }
    if (window.__test || window.__selftest) {
      sprich(T("Test. Nicht geöffnet."));
      armIdle();
      return;
    }
    sprich(a.offen || T("Ist offen."));
    oeffneZiel(wert);
    armIdle();
    return;
  }
  if (a.typ === "link" || a.typ === "datei") {
    if (window.__test || window.__selftest) {
      sprich(T("Test. Nicht geöffnet."));
      armIdle();
      return;
    }
    const wert = a.typ === "link" ? a.url : a.pfad;
    sageZustand();
    if (wert) oeffneZiel(wert);
    armIdle();
    return;
  }
  if (a.typ === "baustein" || a.typ === "status") {
    ohrStopp();
    fetch("/api/baustein", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: a.name,
        bestaetigung: card._bestaetigung || "",
        ssid: a.ssid || "",
        mac: a.mac || "",
      }),
    }).then(r => r.json()).then(res => {
      window.__letzte = res;
      // Ja ist schon gedrückt: die Freigabe des Servers sofort zurückschicken, ohne eine zweite Frage.
      if (res && res.bestaetigen && card._ja && res.bestaetigung && !card._nonceVersuch) {
        run(Object.assign({}, card, {
          _ja: true,
          bestaetigen: false,
          confirm: false,
          _bestaetigung: res.bestaetigung,
          _nonceVersuch: true,
        }));
        return;
      }
      if (res && res.bestaetigen) {
        frage = { card: Object.assign({}, card, { bestaetigen: true, _bestaetigung: res.bestaetigung || "" }), id: cur, index: index[cur] || 0 };
        fokus = "nein";
        lastAktiv = 0;
        render();
        sageZustand();
        armIdle();
        return;
      }
      const serverSprach = !!(res && res.ok && res.sagen);
      if (res && res.sagen) {
        window.__gesagt = res.sagen;
        if (!res.ok) sprich(res.sagen);
      } else sageZustand();
      const wieder = {
        "wlan.on": "wlan.list",
        "wlan.off": "wlan.list",
        "wlan.connect": "wlan.list",
        "bt.on": "bt.list",
        "bt.off": "bt.list",
        "bt.connect": "bt.list",
      };
      if (res && res.ok && wieder[a.name] && cur === "dyn-" + wieder[a.name]) {
        openDynamic(wieder[a.name], { refresh: true });
        return;
      }
      if (serverSprach) starteOhr();
      armIdle();
    }).catch(() => {
      sprich(T("Das hat nicht geklappt."));
      armIdle();
    });
    return;
  }
  sageZustand();
  armIdle();
}

// In der Einrichtung gehört die Kachel zur Taste: Pfeil links = linke Kachel,
// Pfeil rechts = rechte Kachel. Rollen: links = weiter (Knopf 2), rechts = auswählen (Knopf 1).

// ---- Eingabe: eine Belegung für Einrichtung und App ----
// Pfeil links = linke Kachel, Pfeil rechts = rechte Kachel. Linksklick = Knopf 1 (links),
// Rechtsklick = Knopf 2 (rechts). Im Ein-Knopf-Scan wählt jede Taste die markierte Kachel.

function blinke(seite) {
  const ids = KACHEL_IDS[seite] ? [seite] : ["links", "rechts"];
  ids.forEach(id => {
    const knopf = kachelEl(id);
    if (!knopf) return;
    knopf.classList.add("verworfen");
    setTimeout(() => knopf.classList.remove("verworfen"), 250);
  });
  window.__verworfen = (window.__verworfen || 0) + 1;
}

// Mit Sperrzeit (Standard 300 ms). Zu schnelle Drücke leuchten kurz auf, statt still zu verschwinden.
function los(seite) {
  if (!C || !seite) return;
  const jetzt = Date.now();
  if (jetzt - lastAktiv < Pfad.entprellMs(C.debounceMs)) {
    blinke(seite);
    return;
  }
  lastAktiv = jetzt;
  window.__eingaben = (window.__eingaben || 0) + 1;
  aktiviere(seite);
}

// welche: "links", "rechts" oder "waehlen" (Ein-Knopf: markierte Kachel)
function eingabe(welche) {
  if (!C) return;
  if (hinweisOffen() && hinweisArtOffen !== "zurueck") {
    // Ruf-Anzeige: der erste Druck schließt sie nur.
    hinweisFest = false;
    versteckeHinweis();
    armIdle();
    return;
  }
  // "Gleich zurück" verschluckt keinen Druck: der Hinweis geht weg, der Druck zählt.
  if (hinweisOffen()) versteckeHinweis();
  if (einknopf()) {
    if (paar && paar.seitig && (fokus === "blaettern" || fokus === "zurueck")) return los(fokus);
    return los(fokus === "rechts" ? "rechts" : "links");
  }
  if (welche === "waehlen") return;
  los(welche);
}

function fokusiere() {
  try { window.focus(); } catch (err) {}
  if (document.body) {
    document.body.tabIndex = -1;
    try { document.body.focus(); } catch (err) {}
  }
}

function istEinrichten(e) {
  if (!e || e.repeat || !e.ctrlKey || !e.shiftKey || e.altKey || e.metaKey) return false;
  return e.key === "E" || e.key === "e" || e.code === "KeyE";
}

function zurEinrichtung() {
  if (window.__selftest || window.__test) {
    window.__einrichten = true;
    return;
  }
  location.href = "setup.html";
}

// Einstellungstaste: 3 Sekunden halten (Maus oder beide Pfeiltasten), gelber Balken läuft voll.
function halteStart() {
  abbrechenWahl();
  const knopf = el("setup");
  clearTimeout(setupHalteT);
  if (knopf) {
    knopf.style.setProperty("--halte", Pfad.halteMs(C && C.setupHoldMs) + "ms");
    knopf.classList.add("h");
  }
  setupHalteT = setTimeout(() => {
    setupHalteT = null;
    zurEinrichtung();
  }, Pfad.halteMs(C && C.setupHoldMs));
}

function halteStopp() {
  clearTimeout(setupHalteT);
  setupHalteT = null;
  const knopf = el("setup");
  if (knopf) knopf.classList.remove("h");
}

addEventListener("keydown", e => {
  if (!C) return;
  if (istEinrichten(e)) {
    e.preventDefault();
    zurEinrichtung();
    return;
  }
  if (e.key === "Escape") {
    e.preventDefault();
    if (phase === "app" && !e.repeat) goStart("druck");
    return;
  }
  const welche = Pfad.tasteVon(C.keys, e.key);
  if (!welche) return;
  e.preventDefault();
  if (e.repeat) return;
  keysDown.add(welche);
  if (keysDown.has("links") && keysDown.has("rechts") && phase === "app") halteStart();
  if (phase === "setup") armSetup();
  else armIdle({ behalten: true });
  eingabe(welche);
});
addEventListener("keyup", e => {
  const welche = C && Pfad.tasteVon(C.keys, e.key);
  if (welche) keysDown.delete(welche);
  if (!(keysDown.has("links") && keysDown.has("rechts"))) halteStopp();
});

addEventListener("pointerdown", e => {
  if (!C) return;
  const ziel = e.target && e.target.closest ? e.target : null;
  if (ziel && ziel.closest("#setup")) return;
  // Mausknopf 0 = links, 2 = rechts. Andere Tasten (Zurück/Vor) zählen nicht.
  const kachel = ziel && ziel.closest("#links") ? "links" : (ziel && ziel.closest("#rechts") ? "rechts"
    : (ziel && ziel.closest("#fuss-blaettern") ? "blaettern" : (ziel && ziel.closest("#fuss-zurueck") ? "zurueck" : "")));
  const welche = Pfad.mausWahl(e.button, kachel, einknopf());
  e.preventDefault();
  if (!welche) return;
  if (kachel && kachelEl(kachel)) {
    kachelEl(kachel).classList.add("gehalten");
    setTimeout(() => kachelEl(kachel) && kachelEl(kachel).classList.remove("gehalten"), 200);
  }
  if (phase === "setup") armSetup();
  else armIdle({ behalten: true });
  if (kachel && e.button === 0 && !hinweisOffen()) {
    // direkter Klick auf eine Kachel wählt genau diese Kachel, auch im Ein-Knopf-Modus
    los(kachel);
    return;
  }
  eingabe(welche);
}, true);
addEventListener("contextmenu", e => e.preventDefault());
addEventListener("auxclick", e => e.preventDefault());
addEventListener("blur", () => { keysDown.clear(); halteStopp(); });

function bindSetup() {
  const knopf = el("setup");
  if (!knopf) return;
  knopf.addEventListener("pointerdown", e => {
    e.preventDefault();
    if (e.button !== 0) return;
    halteStart();
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach(name => {
    knopf.addEventListener(name, () => halteStopp());
  });
}

function ws() {
  if (window.__selftest) return;
  try {
    const socket = new WebSocket("ws://localhost:8765");
    socket.onmessage = m => {
      const sd = String(m.data || "").trim();
      if (sd === "left") eingabe("links");
      if (sd === "right") eingabe("rechts");
      if (sd === "back" || sd === "hold") {
        if (phase === "app") goStart("druck");
      }
    };
    socket.onclose = () => setTimeout(ws, 5000);
  } catch (e) {}
}


function karteMitZiel(id, ziel) {
  return kartenVon(C.screens[id]).findIndex(card => {
    const a = Pfad.aktionVon(card);
    return a && a.ziel === ziel;
  });
}

function shot(ziel) {
  if (!C) return "nicht bereit";
  C.zurueck.sekunden = 0;
  clearIdle();
  clearSetup();
  phase = "app";
  C.einrichtung = Object.assign({}, C.einrichtung, { fertig: true, modus: "duo" });
  frage = null;
  if (!ziel || ziel === "start") {
    goStart("still");
    return cur;
  }
  stack = [];
  cur = C.start;
  index[C.start] = 0;
  const i = karteMitZiel(C.start, ziel);
  if (i < 0) return "fehlt:" + ziel;
  waehleKarte(i);
  return cur;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function bisLinks(wort) {
  for (let n = 0; n < 12; n++) {
    if (paar && paar.links && paar.links.wort === wort) return true;
    if (!paar || !paar.rechts || paar.rechts.sonder !== "andere") return false;
    aktiviere("rechts");
  }
  return paar && paar.links && paar.links.wort === wort;
}

// Selbsttest im Browser (index.html?selftest=1): Aufbau, Ablauf, Zeiten. Ohne Server.
async function runSelftest() {
  const fehler = [];
  const ok = (cond, msg) => { if (!cond) fehler.push(msg); };
  const calls = [];
  const origFetch = window.fetch;
  window.fetch = url => {
    calls.push(String(url));
    return Promise.resolve({ ok: true, json: async () => ({ ok: false, blocked: true }) });
  };
  const rect = id => {
    const r = el(id).getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
  };
  const nachDruck = () => { lastAktiv = 0; };
  try {
    C.knopf = Object.assign({}, C.knopf, { modus: "zwei" });
    goStart("still");
    const links = rect("links");
    const rechts = rect("rechts");
    ok(links[0] + links[2] <= rechts[0] + 2, "links steht links");
    ok(Math.abs(links[1] - rechts[1]) < 4, "gleiche Höhe");
    ok(links[2] > 300 && rechts[2] > 300, "beide breit");
    ok(links[3] > 280 && rechts[3] > 280, "beide hoch");
    ok(document.querySelectorAll("button.karte").length === 2, "genau zwei Kacheln");
    ok(!document.getElementById("zurueck") && !document.getElementById("hilfe") && !document.getElementById("ja") && !document.getElementById("nein"), "keine Ecken-Leiste");
    ok(!!document.getElementById("setup"), "Einstellungstaste da");
    ok(el("satz").hidden, "am Start keine Frage");
    ok(paar.links.wort === "Ich will was sagen", "links ist Ich will was sagen");
    ok(paar.rechts.sonder === "andere", "rechts ist Andere");
    ok(!el("links").classList.contains("an") && !el("rechts").classList.contains("an"), "ohne Scan keine Markierung");
    ok(getComputedStyle(el("links")).animationName === "none", "keine Animation");
    ok(Pfad.tasteVon(C.keys, "ArrowLeft") === "links" && Pfad.tasteVon(C.keys, "ArrowRight") === "rechts", "Pfeil links ist links, rechts ist rechts");
    ok(Pfad.tasteVon(C.keys, "ArrowUp") === "waehlen" && Pfad.tasteVon(C.keys, " ") === "waehlen" && Pfad.tasteVon(C.keys, "Enter") === "waehlen", "Hoch, Leertaste, Enter wählen");

    const plan = Pfad.idlePlan(window.__zurueckVorlage, false);
    ok(plan.sekunden === 20 && plan.hinweisMs === 15000 && plan.zurueckMs === 20000, "Standard 20s");
    ok(Pfad.idlePlan(window.__zurueckVorlage, true).aktiv === false, "am Start kein Timer");

    ok(bisLinks("Bilder"), "Bilder anblättern");
    nachDruck(); aktiviere("links");
    ok(cur === "ordner-bilder", "Bilder offen, ist " + cur);
    ok(paar.links.wort === "Noch leer" && paar.rechts.sonder === "zurueck", "leer und Zurück");
    ok((window.__sprache || []).some(t => t.indexOf("Hier ist noch nichts. Zurück") !== -1), "Ansage Bilder: zwei kurze Wörter");
    aktiviere("links");
    ok((window.__sprache || []).pop() === "Hier ist noch nichts.", "Ordner leer");
    aktiviere("rechts");
    ok(cur === "start", "hoch zum Start");

    goStart("still");
    aktiviere("links");
    ok(cur === "sagen", "Sagen offen");
    ok(paar.links.wort === "Hilferuf" && paar.rechts.sonder === "andere", "Hilferuf oder Andere");
    aktiviere("links");
    ok((window.__sprache || []).pop() === "Der Ruf ist nicht rausgegangen.", "Ruf ohne Netz im Test");
    ok(!el("hinweis").hidden, "Rufbild bleibt");
    ok(window.__ruf === "aus", "Rufzustand aus");
    // erster Druck schließt nur die Ruf-Anzeige
    nachDruck(); eingabe("links");
    ok(el("hinweis").hidden && cur === "sagen", "Druck schließt Ruf-Anzeige");

    // Zurück ist eine normale Kachel, auch bei zwei Einträgen
    const zwei = Pfad.duoPaar([{ wort: "A" }, { wort: "B" }], 0, true);
    ok(zwei.liste.some(k => k.sonder === "zurueck"), "Zurück erreichbar");

    // Gleich zurück: Hinweis, dann Start; ein Druck im Hinweis geht nicht verloren
    C.zurueck.sekunden = 3;
    C.zurueck.hinweis = "ansage";
    C.zurueck.hinweisVorherSekunden = 2;
    window.__hinweis = 0;
    goStart("still");
    ok(bisLinks("Bilder"), "vor Hinweis Bilder finden");
    nachDruck(); aktiviere("links");
    ok(cur === "ordner-bilder", "vor Hinweis bei den Bildern");
    await sleep(1800);
    ok(window.__hinweis === 1, "Hinweis kam, Zähler " + window.__hinweis);
    ok(!el("hinweis").hidden, "Hinweisbild sichtbar");
    nachDruck(); eingabe("rechts");
    ok(el("hinweis").hidden, "Hinweis weg nach Druck");
    ok(cur === "start", "Druck im Hinweis zählt (Zurück), ist " + cur);
    C.zurueck.sekunden = 0;
    clearIdle();

    // Sperrzeit: zweiter schneller Druck leuchtet, ändert nichts
    goStart("still");
    nachDruck();
    window.__verworfen = 0;
    const n0 = window.__eingaben || 0;
    los("rechts");
    los("rechts");
    ok((window.__eingaben || 0) === n0 + 1 && window.__verworfen === 1, "schneller Druck verworfen und sichtbar");
    ok(el("rechts").classList.contains("verworfen"), "Kachel leuchtet");

    // Ein-Knopf-Scan
    C.knopf = Object.assign({}, C.knopf, { modus: "ein", scanMs: 400 });
    C.zurueck.sekunden = 0;
    clearIdle();
    goStart("still");
    ok(fokus === "links" && window.__scan === true, "Ein-Knopf scannt");
    ok(el("links").classList.contains("an"), "links markiert");
    const vor = (window.__sprache || []).length;
    await sleep(700);
    ok(fokus === "rechts", "Markierung wandert, ist " + fokus);
    ok(((window.__sprache || [])[vor] || "").indexOf("Andere") !== -1, "Wort angesagt");
    nachDruck(); eingabe("waehlen");
    ok(paar.links.wort === "Bilder", "wählen nimmt markierte Kachel (Andere), links ist " + paar.links.wort);
    C.knopf.modus = "zwei";
    armIdle();
    ok(window.__scan === false, "Zwei-Knopf scannt nicht");

    // Rückfrage: nur zwei Kacheln, Nein links
    C.zurueck.sekunden = 2;
    C.zurueck.hinweis = "ton";
    goStart("still");
    ok(bisLinks("Steuern"), "Steuern finden");
    nachDruck(); aktiviere("links");
    ok(cur === "steuern", "Steuern offen");
    ok(bisLinks("Ausschalten"), "Ausschalten finden");
    const davor = calls.length;
    nachDruck(); aktiviere("links");
    ok(window.__frage === true && paar.links.sonder === "nein" && paar.rechts.sonder === "ja", "Rückfrage Nein und Ja");
    ok(!el("satz").hidden && el("satz").textContent.indexOf("Wirklich?") === 0, "Fragetext");
    ok(document.querySelectorAll("button.karte").length === 2, "Frage nur zwei Kacheln");
    ok(!calls.some(u => u.indexOf("/api/baustein") !== -1), "Ausschalten noch nicht gesendet");
    await sleep(2800);
    ok(cur === "start" && !window.__frage, "Zeit bricht Ausschalten ab");
    ok(calls.length === davor, "kein Aufruf nach der Zeit");
    ok(!calls.some(u => u.indexOf("/api/") !== -1), "Test hat nichts ausgelöst");

    window.__einrichten = false;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "e", bubbles: true }));
    ok(!window.__einrichten, "E allein bleibt zu");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "E", code: "KeyE", ctrlKey: true, shiftKey: true, bubbles: true }));
    ok(window.__einrichten === true, "Strg+Umschalt+E");

    const ergebnis = fehler.length ? "SELFTEST FAIL " + fehler.join(" | ") : "SELFTEST PASS";
    el("selftest").textContent = ergebnis;
    window.__selftestResult = ergebnis;
    return ergebnis;
  } catch (e) {
    const ergebnis = "SELFTEST FAIL " + (e && e.message ? e.message : e);
    el("selftest").textContent = ergebnis;
    window.__selftestResult = ergebnis;
    return ergebnis;
  } finally {
    window.fetch = origFetch;
    if (C && C.zurueck) C.zurueck.sekunden = 0;
    if (C && C.knopf) C.knopf.modus = "zwei";
    frage = null;
    clearIdle();
    clearSetup();
    try { goStart("still"); } catch (e) {}
  }
}

addEventListener("focus", () => {
  if (tvAn) {
    // mpv ist zu: gleich nachsehen, ob es ein Fehler war (dann die ruhige Meldung)
    tvBeobachten();
    return;
  }
  if (away && phase === "app") goStart("druck");
});

function bildVonPlugin(basis, datei) {
  const name = String(datei || "");
  if (!name) return "img/sagen.svg";
  if (name.indexOf("/") !== -1) return name;
  return basis + name;
}

function pluginEinsetzen(id, daten, basis) {
  if (!C || !C.screens || !/^[a-z0-9_-]{1,40}$/.test(id)) return;
  if (!daten || typeof daten !== "object") return;
  const start = C.screens.start;
  if (!start || !Array.isArray(start.liste)) return;
  const screenId = "plugin-" + id;
  const liste = (Array.isArray(daten.karten) ? daten.karten : []).map(karte => {
    return Object.assign({}, karte, { bild: bildVonPlugin(basis, karte && karte.bild) });
  }).filter(karte => !Pfad.istLeer(karte, C.ziele));
  start.liste = start.liste.filter(karte => {
    const aktion = Pfad.aktionVon(karte);
    return !(aktion && aktion.ziel === screenId);
  });
  delete C.screens[screenId];
  if (!liste.length) return;
  C.screens[screenId] = {
    name: daten.name || id,
    liste: liste,
  };
  start.liste.push({
    wort: daten.name || id,
    sprechen: daten.sprechen || daten.name || id,
    bild: bildVonPlugin(basis, daten.bild),
    aktion: { typ: "untermenue", ziel: screenId },
  });
}

function pluginDatei(name) {
  const lang = I18N.sprache();
  const lade = datei => fetch("plugins/" + name + "/" + datei, { cache: "no-store" }).then(r => (r.ok ? r.json() : null)).catch(() => null);
  if (lang === "de") return lade("plugin.json");
  return lade("plugin." + lang + ".json").then(d => d || lade("plugin.json"));
}

function pluginsHolen() {
  if (C && C.pluginsAn === false) return Promise.resolve();
  return fetch("plugins/index.json", { cache: "no-store" })
    .then(r => r.ok ? r.json() : [])
    .catch(() => [])
    .then(ids => {
      if (!Array.isArray(ids)) return;
      return Promise.all(ids.map(id => {
        const name = String(id || "");
        if (!/^[a-z0-9_-]{1,40}$/.test(name)) return null;
        return pluginDatei(name)
          .then(daten => daten && pluginEinsetzen(name, daten, "plugins/" + name + "/"))
          .catch(() => null);
      }));
    })
    .then(() => fetch("/api/plugins", { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .then(liste => {
        if (!Array.isArray(liste)) return;
        liste.forEach(eintrag => {
          if (!eintrag || !eintrag.id) return;
          pluginEinsetzen(String(eintrag.id), eintrag, "");
        });
      })
      .catch(() => {}));
}

fetch("config.json", { cache: "no-store" })
  .then(r => r.json())
  .then(c => I18N.laden(params.get("lang") || (params.has("selftest") ? "de" : c.language) || "de").then(() => { I18N.statisch(); return c; }))
  .then(c => {
    C = c;
    window.__zurueckVorlage = JSON.parse(JSON.stringify(c.zurueck || {}));
    if (window.__selftest || window.__test) {
      C.einrichtung = Object.assign({}, C.einrichtung, { fertig: true, modus: "duo" });
    }
    anzeigeWert = C.anzeige || "beides";
    window.__bildstil = Pfad.bildStil(C.bildstil); // der Server liefert img/x.svg aus img/<stil>/
    bindSetup();
    return pfadLaden().then(() => pluginsHolen());
  })
  .then(() => {
    if (setupNoetig()) {
      phase = "setup";
      schritt = Pfad.einrichtungStart(C.einrichtung);
      wahlIndex = 0;
      render();
      sprich(setupAnsage());
      armSetup();
    } else {
      phase = "app";
      zeige(C.start, { ansage: true });
      pruefeTest();
    }
    ws();
    if (window.__selftest) {
      window.__shot = shot;
      window.__runSelftest = runSelftest;
    }
    fokusiere();
    erinnerungenStarten();
    window.__ready = true;
  })
  .catch(err => {
    window.__ready = true;
    window.__selftestResult = "SELFTEST FAIL laden " + err;
  });
