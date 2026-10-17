"use strict";
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.Pfad = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const FESTE = ["zurueck", "nein", "ja"];
  const T = text => (typeof globalThis !== "undefined" && typeof globalThis.T === "function" ? globalThis.T(text) : text);
  const MAX_TIEFE = 3;
  const KRITISCH = {
    "system.poweroff": true,
    "system.reboot": true,
    "screen.lock": true,
    "wlan.off": true,
    "bt.off": true,
  };

  // Bildsatz: "glatt" (Standard) oder "pixel". Alte Pfade "img/x.svg" gelten weiter.
  function bildStil(v) {
    const t = String(v === undefined || v === null ? "" : v).trim().toLowerCase();
    return t === "pixel" || t === "pixelart" || t === "pixelstil" ? "pixel" : "glatt";
  }

  function bildPfad(pfad, stil) {
    const p = String(pfad || "");
    const s = bildStil(stil);
    let m = /^(img)\/([A-Za-z0-9_.-]+\.svg)$/.exec(p);
    if (!m) m = /^(plugins\/[a-z0-9_-]{1,40})\/([A-Za-z0-9_.-]+\.svg)$/.exec(p);
    return m ? m[1] + "/" + s + "/" + m[2] : p;
  }

  function sekundenWert(v) {
    if (v === "aus" || v === "off" || v === false || v === null || v === 0 || v === "0") return 0;
    if (v === undefined || v === "") return 20;
    const n = Number(v);
    if (!Number.isFinite(n)) return 20;
    return Math.max(0, Math.min(60, Math.round(n)));
  }

  function wahr(v) {
    return v === true || v === "ja" || v === "an" || v === "true" || v === 1 || v === "1";
  }

  function langerDruckMs(v) {
    if (v === undefined || v === null || v === "" || v === false || v === "aus" || v === "off") return 0;
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return Math.min(5000, Math.round(n));
  }

  function hinweisArt(v) {
    return v === "ton" ? "ton" : "ansage";
  }

  function scanMs(v) {
    if (v === undefined || v === null || v === "") return 3000;
    const n = Number(v);
    if (!Number.isFinite(n)) return 3000;
    return Math.max(400, Math.min(10000, Math.round(n)));
  }

  // Sperrzeit gegen doppelte Drücke. Standard 300 ms, erlaubt 100 bis 2000.
  function entprellMs(v) {
    if (v === undefined || v === null || v === "") return 300;
    const n = Number(v);
    if (!Number.isFinite(n)) return 300;
    return Math.max(100, Math.min(2000, Math.round(n)));
  }

  // So lange muss die Einstellungstaste gehalten werden. Standard 3000 ms.
  function halteMs(v) {
    if (v === undefined || v === null || v === "") return 3000;
    const n = Number(v);
    if (!Number.isFinite(n)) return 3000;
    return Math.max(1000, Math.min(10000, Math.round(n)));
  }

  // So lange bleibt die gewählte Kachel vergrößert stehen, bevor die Eingabe ausgeführt wird.
  // Config "waehlSekunden". Standard 3 s, 0 = sofort, höchstens 10 s.
  function waehlMs(v) {
    if (v === undefined || v === null || v === "") return 3000;
    const n = Number(v);
    if (!Number.isFinite(n)) return 3000;
    return Math.max(0, Math.min(10, n)) * 1000;
  }

  // Zeit pro Bild der Diashow. Config "bildSekunden". Standard 10 s, 3 bis 120 s.
  function bildMs(v) {
    if (v === undefined || v === null || v === "") return 10000;
    const n = Number(v);
    if (!Number.isFinite(n)) return 10000;
    return Math.max(3, Math.min(120, n)) * 1000;
  }

  // Einheitliche Tastenbelegung. Pfeil links = linke Kachel, Pfeil rechts = rechte Kachel,
  // Pfeil hoch, Leertaste und Enter = wählen (nur im Ein-Knopf-Scan wichtig).
  const TASTEN_STANDARD = {
    links: ["ArrowLeft"],
    rechts: ["ArrowRight"],
    waehlen: ["ArrowUp", " ", "Enter"],
    blaettern: ["ArrowDown"], // nur auf Listenseiten mit "Weiter blättern"
  };

  function gleicheTaste(liste, key) {
    const leer = k => k === " " || k === "Space" || k === "Spacebar";
    return (liste || []).some(eintrag => eintrag === key || (leer(eintrag) && leer(key)));
  }

  function tastenListe(keys, name) {
    if (keys && Array.isArray(keys[name]) && keys[name].length) return keys[name];
    return TASTEN_STANDARD[name].slice();
  }

  // Liefert "links", "rechts", "waehlen" oder "".
  function tasteVon(keys, key) {
    if (gleicheTaste(tastenListe(keys, "links"), key)) return "links";
    if (gleicheTaste(tastenListe(keys, "rechts"), key)) return "rechts";
    if (gleicheTaste(tastenListe(keys, "waehlen"), key)) return "waehlen";
    if (gleicheTaste(tastenListe(keys, "blaettern"), key)) return "blaettern";
    return "";
  }

  // Maus: Linksklick = Knopf 1 (linke Kachel), Rechtsklick = Knopf 2 (rechte Kachel).
  // Ein Klick direkt auf eine Kachel wählt diese Kachel. Andere Maustasten zählen nicht.
  function mausWahl(taste, kachel, einKnopf) {
    if (taste !== 0 && taste !== 2) return "";
    if (kachel && taste === 0) return kachel;
    if (einKnopf) return "waehlen";
    return taste === 0 ? "links" : "rechts";
  }

  function knopfModus(v) {
    if (v === "ein" || v === "einknopf" || v === 1 || v === "1") return "ein";
    return "zwei";
  }

  function idlePlan(zurueck, zuHause) {
    const z = zurueck || {};
    const sek = sekundenWert(z.sekunden);
    const plan = {
      sekunden: sek,
      hinweis: hinweisArt(z.hinweis),
      langerDruckMs: langerDruckMs(z.langerDruckMs),
      beideKnopfe: wahr(z.beideKnopfe),
      aktiv: false,
      hinweisMs: null,
      zurueckMs: null,
      hinweisVorherSekunden: 0,
    };
    if (sek === 0 || zuHause) return plan;
    plan.aktiv = true;
    plan.zurueckMs = sek * 1000;
    if (sek < 3) return plan;
    let vor = Number(z.hinweisVorherSekunden);
    if (!Number.isFinite(vor)) vor = 5;
    vor = Math.round(vor);
    if (vor < 1) vor = 1;
    if (vor >= sek) vor = sek - 1;
    plan.hinweisVorherSekunden = vor;
    plan.hinweisMs = (sek - vor) * 1000;
    return plan;
  }

  function istLeer(card, ziele) {
    const aktion = aktionVon(card);
    if (!aktion || !aktion.typ) return true;
    if (aktion.typ === "link") return !String(aktion.url || "").trim();
    if (aktion.typ === "datei") return !String(aktion.pfad || "").trim();
    if (aktion.typ === "sprechen") return !String(aktion.text || card.wort || card.label || "").trim();
    if (aktion.typ === "untermenue") return !String(aktion.ziel || "").trim();
    if (aktion.typ === "dynamisch" || aktion.typ === "ordner") return !String(aktion.quelle || aktion.ziel || "").trim();
    if (aktion.typ === "film") return !String(aktion.name || "").trim();
    if (aktion.typ === "ziel") return !String((ziele || {})[aktion.name] || "").trim();
    return false;
  }

  function karten(screen, ziele) {
    if (!screen) return [];
    let liste;
    if (Array.isArray(screen.liste)) liste = screen.liste.filter(Boolean);
    else {
      liste = [];
      if (screen.left) liste.push(screen.left);
      if (screen.right) liste.push(screen.right);
    }
    return liste.filter(card => !(card && card.aus === true) && !istLeer(card, ziele));
  }

  function aktionVon(card) {
    if (!card) return null;
    if (card.aktion && card.aktion.typ) return card.aktion;
    if (card.next) return { typ: "untermenue", ziel: card.next };
    if (card.action && card.action.type === "url") return { typ: "link", url: card.action.url };
    if (card.action && card.action.type === "file") return { typ: "datei", pfad: card.action.path };
    return null;
  }

  function wortVon(card) {
    if (!card) return "";
    return String(card.sprechen || card.wort || card.label || "");
  }

  function brauchtRueckfrage(card) {
    if (!card || card._ja) return false;
    if (card.bestaetigen || card.confirm) return true;
    const aktion = aktionVon(card);
    return !!(aktion && KRITISCH[aktion.name]);
  }

  function naechster(reihe, id) {
    if (!reihe || !reihe.length) return null;
    const i = reihe.indexOf(id);
    if (i < 0) return reihe[0];
    return reihe[(i + 1) % reihe.length];
  }

  function zustand(ebene, karte) {
    const e = String(ebene || "").replace(/\s+/g, " ").trim();
    const k = String(karte || "").replace(/\s+/g, " ").trim();
    if (e && k) return e + ". " + k + ".";
    const eins = e || k;
    return eins ? eins + "." : "";
  }

  function darfTiefer(tiefe) {
    return tiefe < MAX_TIEFE;
  }

  function pruefeBaum(screens, startId) {
    const fehler = [];
    const gesehen = new Set();
    const warteschlange = [{ id: startId, tiefe: 1, pfad: [startId] }];
    while (warteschlange.length) {
      const knoten = warteschlange.shift();
      const id = knoten.id;
      const tiefe = knoten.tiefe;
      const pfad = knoten.pfad;
      if (pfad.slice(0, -1).indexOf(id) !== -1) {
        fehler.push("Kreis: " + pfad.join(" > "));
        continue;
      }
      if (tiefe > MAX_TIEFE) {
        fehler.push("Zu tief: " + pfad.join(" > "));
        continue;
      }
      const screen = screens[id];
      if (!screen) {
        fehler.push("Fehlt: " + id);
        continue;
      }
      const schluessel = id + "@" + tiefe;
      if (gesehen.has(schluessel)) continue;
      gesehen.add(schluessel);
      karten(screen).forEach(card => {
        const aktion = aktionVon(card);
        if (!aktion) return;
        const name = card.wort || card.label || id;
        if (aktion.typ === "untermenue") {
          if (!darfTiefer(tiefe)) fehler.push("Ebene " + tiefe + " öffnet noch ein Menü: " + name);
          warteschlange.push({ id: aktion.ziel, tiefe: tiefe + 1, pfad: pfad.concat(aktion.ziel) });
        }
        if (aktion.typ === "dynamisch" && !darfTiefer(tiefe)) {
          fehler.push("Ebene " + tiefe + " öffnet noch eine Liste: " + name);
        }
      });
    }
    return fehler;
  }

  function loslassen(dauerMs, grenzeMs) {
    if (!grenzeMs || grenzeMs <= 0) return "klick";
    return dauerMs >= grenzeMs ? "start" : "klick";
  }

  function sonderKarte(sonder, feste, standardWort, standardBild) {
    const extra = (feste && feste[sonder]) || {};
    const wort = extra.wort || T(standardWort);
    return {
      sonder: sonder,
      wort: wort,
      sprechen: wort,
      bild: extra.bild || standardBild,
    };
  }

  function duoPaar(kartenListe, index, mitZurueck, feste) {
    const andere = { sonder: "andere", wort: T("Andere"), sprechen: T("Andere"), bild: "img/andere.svg" };
    const zurueck = sonderKarte("zurueck", feste, "Zurück", "img/zurueck.svg");
    const list = (kartenListe || []).filter(Boolean).slice();
    if (mitZurueck && list.length >= 1 && !list.some(k => k && k.sonder === "zurueck")) list.push(zurueck);
    const n = list.length;
    if (n === 0) return { links: zurueck, rechts: zurueck, index: 0, blaettern: false, liste: list };
    if (n === 1) {
      const nur = list[0];
      const rechts = nur.sonder === "zurueck" ? nur : zurueck;
      return { links: nur, rechts: rechts, index: 0, blaettern: false, liste: list };
    }
    if (n === 2) return { links: list[0], rechts: list[1], index: 0, blaettern: false, liste: list };
    const i = ((index % n) + n) % n;
    return { links: list[i], rechts: andere, index: i, blaettern: true, liste: list };
  }

  // Listenseite: zwei Karten gleichzeitig (Seite 0 = Karte 0 und 1, Seite 1 = Karte 2 und 3 ...).
  // Dazu zwei kleine Fußkacheln: "Weiter blättern" und "Zurück". Gibt die Seite zurück, die zum Start passt.
  function seitenPaar(kartenListe, start, feste) {
    const list = (kartenListe || []).filter(Boolean);
    const n = list.length;
    const seiten = Math.max(1, Math.ceil(n / 2));
    const seite = Math.max(0, Math.min(seiten - 1, Math.floor((Number(start) || 0) / 2)));
    return {
      links: list[seite * 2] || null,
      rechts: list[seite * 2 + 1] || sonderKarte("zurueck", feste, "Zurück", "img/zurueck.svg"),
      fussB: sonderKarte("blaettern", feste, "Weiter blättern", "img/blaettern.svg"),
      fussZ: sonderKarte("zurueck", feste, "Zurück", "img/zurueck.svg"),
      seite: seite,
      seiten: seiten,
      index: seite * 2,
      blaettern: false,
      liste: list,
      seitig: true,
      mehr: seiten > 1,
    };
  }

  function naechsteSeite(paarWert) {
    if (!paarWert || !paarWert.seitig) return 0;
    return ((paarWert.seite + 1) % paarWert.seiten) * 2;
  }

  function fragePaar(feste) {
    return {
      links: sonderKarte("nein", feste, "Nein", "img/nein.svg"),
      rechts: sonderKarte("ja", feste, "Ja", "img/ja.svg"),
      index: 0,
      blaettern: false,
      frage: true,
      liste: [],
    };
  }

  // Einrichtung: Version der Abfrage. Ältere Einrichtungen ("fertig" ohne "stand") fragen neu.
  const EINRICHTUNG_STAND = 2;
  const MODI = ["b", "a", "c"]; // Reihenfolge in der Abfrage: einfach zuerst (Standard)

  // Allererster Schritt: Sprache (Deutsch | English). Danach nie wieder von allein; später unter Einstellungen.
  function einrichtungStart(e) {
    return e && e.sprache === true ? "bedienung" : "sprache";
  }

  function einrichtungNoetig(e) {
    return !(e && e.fertig === true && Number(e.stand) >= EINRICHTUNG_STAND);
  }

  // Der einfache Standard. Er gilt nie von allein, nur nach einer ausdrücklichen Wahl.
  function einrichtungStandard() {
    return { fertig: true, modus: "b", knopf: "zwei", bedienung: "knoepfe", hoeren: false, autostart: false };
  }

  // Jede Frage hat höchstens zwei Kacheln (die Wahl und "Andere").
  // Schritte: sprache (Deutsch | English) -> bedienung (Stimme | Knöpfe, Maus, Tasten) -> knopf (Zwei | Ein) -> modus (b | a | c) -> autostart (Nein | Ja).
  function einrichtungWahl(schritt, wert) {
    if (schritt === "sprache") return { fertig: false, schritt: "bedienung", sprache: wert === "en" ? "en" : "de" };
    if (schritt === "bedienung" && wert === "stimme") return { fertig: false, schritt: "modus", bedienung: "stimme", knopf: "zwei", hoeren: true };
    if (schritt === "bedienung") return { fertig: false, schritt: "knopf", bedienung: "knoepfe", hoeren: false };
    if (schritt === "knopf") return { fertig: false, schritt: "modus", knopf: wert === "ein" ? "ein" : "zwei" };
    if (schritt === "modus" && MODI.indexOf(wert) !== -1) return { fertig: false, schritt: "autostart", modus: wert };
    // Letzte Frage: nur ein ausdrückliches "ja" schaltet den Autostart ein.
    if (schritt === "autostart") return { fertig: true, autostart: wert === "ja" };
    return { fertig: false, schritt: "bedienung" };
  }

  function passend(text, woerter) {
    const teile = function (wert) {
      return String(wert || "").toLowerCase().split(/[^0-9a-zäöüß]+/).filter(Boolean);
    };
    const satz = " " + teile(text).join(" ") + " ";
    const hits = [];
    (woerter || []).forEach(function (wort) {
      const nadelTeile = teile(wort);
      if (!nadelTeile.length) return;
      const nadel = " " + nadelTeile.join(" ") + " ";
      if (satz.indexOf(nadel) === -1) return;
      if (hits.indexOf(wort) === -1) hits.push(wort);
    });
    return hits.length === 1 ? hits[0] : "";
  }

  return {
    FESTE: FESTE,
    MAX_TIEFE: MAX_TIEFE,
    bildStil: bildStil,
    bildPfad: bildPfad,
    sekundenWert: sekundenWert,
    wahr: wahr,
    langerDruckMs: langerDruckMs,
    hinweisArt: hinweisArt,
    scanMs: scanMs,
    entprellMs: entprellMs,
    halteMs: halteMs,
    waehlMs: waehlMs,
    TASTEN_STANDARD: TASTEN_STANDARD,
    gleicheTaste: gleicheTaste,
    tastenListe: tastenListe,
    tasteVon: tasteVon,
    mausWahl: mausWahl,
    knopfModus: knopfModus,
    idlePlan: idlePlan,
    istLeer: istLeer,
    karten: karten,
    aktionVon: aktionVon,
    wortVon: wortVon,
    brauchtRueckfrage: brauchtRueckfrage,
    naechster: naechster,
    zustand: zustand,
    darfTiefer: darfTiefer,
    pruefeBaum: pruefeBaum,
    loslassen: loslassen,
    duoPaar: duoPaar,
    fragePaar: fragePaar,
    seitenPaar: seitenPaar,
    naechsteSeite: naechsteSeite,
    bildMs: bildMs,
    einrichtungWahl: einrichtungWahl,
    einrichtungStandard: einrichtungStandard,
    einrichtungNoetig: einrichtungNoetig,
    einrichtungStart: einrichtungStart,
    EINRICHTUNG_STAND: EINRICHTUNG_STAND,
    MODI: MODI,
    passend: passend,
  };
});
