"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const Pfad = require("./pfad.js");

const root = __dirname;
const configDatei = fs.existsSync(path.join(root, "config.json")) ? "config.json" : "config.example.json";
const config = JSON.parse(fs.readFileSync(path.join(root, configDatei), "utf8"));

function woerter(id) {
  return Pfad.karten(config.screens[id]).map(card => card.wort);
}

function ziel(card) {
  const aktion = Pfad.aktionVon(card);
  return aktion && aktion.ziel;
}

assert.strictEqual(Pfad.sekundenWert(undefined), 20);
assert.strictEqual(Pfad.sekundenWert(20), 20);
assert.strictEqual(Pfad.sekundenWert(0), 0);
assert.strictEqual(Pfad.sekundenWert("aus"), 0);
assert.strictEqual(Pfad.sekundenWert("off"), 0);
assert.strictEqual(Pfad.sekundenWert(false), 0);
assert.strictEqual(Pfad.sekundenWert(90), 60);
assert.strictEqual(Pfad.sekundenWert(-4), 0);
assert.strictEqual(Pfad.sekundenWert(20.4), 20);

const standard = Pfad.idlePlan(config.zurueck, false);
assert.strictEqual(standard.sekunden, 20);
assert.strictEqual(standard.hinweis, "ansage");
assert.strictEqual(standard.hinweisMs, 15000);
assert.strictEqual(standard.zurueckMs, 20000);
assert.strictEqual(standard.aktiv, true);
assert.strictEqual(Pfad.langerDruckMs(undefined), 0);
assert.strictEqual(Pfad.langerDruckMs(800), 800);
assert.strictEqual(Pfad.langerDruckMs(9000), 5000);
assert.strictEqual(Pfad.loslassen(4000, 0), "klick");
assert.strictEqual(Pfad.scanMs(undefined), 3000);
assert.strictEqual(Pfad.scanMs(1500), 1500);
assert.strictEqual(Pfad.scanMs(50), 400);
assert.strictEqual(Pfad.knopfModus("ein"), "ein");
assert.strictEqual(Pfad.knopfModus("zwei"), "zwei");
assert.strictEqual(Pfad.hinweisArt(undefined), "ansage");
assert.strictEqual(Pfad.hinweisArt("ton"), "ton");
assert.deepStrictEqual(config.keys, { links: ["ArrowLeft"], rechts: ["ArrowRight"], waehlen: ["ArrowUp", " ", "Enter"] });
assert.strictEqual(Pfad.tasteVon(config.keys, "ArrowLeft"), "links");
assert.strictEqual(Pfad.tasteVon(config.keys, "ArrowRight"), "rechts");
assert.strictEqual(Pfad.tasteVon(config.keys, "ArrowUp"), "waehlen");
assert.strictEqual(Pfad.tasteVon(config.keys, " "), "waehlen");
assert.strictEqual(Pfad.tasteVon(config.keys, "Space"), "waehlen");
assert.strictEqual(Pfad.tasteVon(config.keys, "Enter"), "waehlen");
assert.strictEqual(Pfad.tasteVon(config.keys, "a"), "");
assert.strictEqual(Pfad.tasteVon(undefined, "ArrowLeft"), "links");
// Maus: Links = Knopf 1, Rechts = Knopf 2, Kachel direkt, Zusatztasten zählen nicht
assert.strictEqual(Pfad.mausWahl(0, "", false), "links");
assert.strictEqual(Pfad.mausWahl(2, "", false), "rechts");
assert.strictEqual(Pfad.mausWahl(0, "rechts", false), "rechts");
assert.strictEqual(Pfad.mausWahl(2, "links", false), "rechts");
assert.strictEqual(Pfad.mausWahl(0, "", true), "waehlen");
assert.strictEqual(Pfad.mausWahl(2, "", true), "waehlen");
assert.strictEqual(Pfad.mausWahl(0, "rechts", true), "rechts");
assert.strictEqual(Pfad.mausWahl(1, "", false), "");
assert.strictEqual(Pfad.mausWahl(3, "links", false), "");
assert.strictEqual(Pfad.mausWahl(4, "", false), "");
assert.strictEqual(Pfad.entprellMs(undefined), 300);
assert.strictEqual(Pfad.entprellMs(10), 100);
assert.strictEqual(Pfad.entprellMs(900), 900);
assert.strictEqual(Pfad.halteMs(undefined), 3000);
assert.strictEqual(config.debounceMs, 300);
assert.strictEqual(config.hoeren, false);
assert.strictEqual(config.knopf.modus, "zwei");
assert.strictEqual(config.knopf.scanMs, 3000);
assert.strictEqual(config.stimmeTempo, 1.15);
assert.ok(JSON.stringify(config.screens.steuern.liste).includes("bt.list"), "Bluetooth im Steuern-Menü");
assert.ok(!("langerDruckMs" in config.zurueck) && !("beideKnopfe" in config.zurueck), "keine alten Haltezeiten");
assert.ok(!config.feste.hilfe, "keine Hilfe-Ecke");
assert.ok(!JSON.stringify(config).includes("\"hilfe\":"), "keine Hilfetexte mehr");
assert.strictEqual(config.zurueck.hinweis, "ansage");
assert.strictEqual(config.anzeige, "beides");
assert.strictEqual(config.stimme, "piper");

assert.strictEqual(Pfad.idlePlan({ sekunden: "aus" }, false).aktiv, false);
assert.strictEqual(Pfad.idlePlan(config.zurueck, true).aktiv, false);
const kurz = Pfad.idlePlan({ sekunden: 2, hinweis: "ansage" }, false);
assert.strictEqual(kurz.aktiv, true);
assert.strictEqual(kurz.hinweisMs, null);
assert.strictEqual(kurz.zurueckMs, 2000);
const knapp = Pfad.idlePlan({ sekunden: 4, hinweisVorherSekunden: 9 }, false);
assert.strictEqual(knapp.hinweisVorherSekunden, 3);
assert.strictEqual(knapp.hinweisMs, 1000);
assert.strictEqual(Pfad.wahr(false), false);
assert.strictEqual(Pfad.wahr("ja"), true);
assert.strictEqual(Pfad.loslassen(1999, 2000), "klick");
assert.strictEqual(Pfad.loslassen(2000, 2000), "start");

assert.deepStrictEqual(woerter("start"), [
  "Ich will was sagen",
  "Bilder",
  "Filme",
  "Fernsehen",
  "Radio",
  "Aufgaben",
  "Steuern",
]);
assert.deepStrictEqual(woerter("sagen"), ["Hilferuf", "Klingel", "Kontakt Eins", "Kontakt Zwei", "Kontakt Drei"]);
assert.deepStrictEqual(woerter("steuern"), ["Lautstärke", "WLAN", "Bluetooth", "Ausschalten"]);
assert.deepStrictEqual(woerter("lautstaerke"), ["Lauter", "Leiser", "Stumm"]);
assert.ok(!config.screens.internet && !config.screens.system && !config.screens.helligkeit, "alte Bereiche sind raus");

const startZiele = Pfad.karten(config.screens.start).map(ziel);
assert.deepStrictEqual(startZiele, ["sagen", "bilder", "filme", undefined, undefined, undefined, "steuern"]);
assert.deepStrictEqual(Pfad.karten(config.screens.start).map(c => Pfad.aktionVon(c).typ), ["untermenue", "ordner", "ordner", "fernsehen", "radio", "aufgaben", "untermenue"]);
assert.deepStrictEqual(Pfad.pruefeBaum(config.screens, "start"), []);
assert.strictEqual(Pfad.istLeer({ aktion: { typ: "ziel", name: "browser" } }, config.ziele), true);
assert.strictEqual(Pfad.istLeer({ aktion: { typ: "ziel", name: "browser" } }, { browser: "https://beispiel.invalid" }), false);
assert.strictEqual(Pfad.istLeer({ wort: "Da", aktion: { typ: "sprechen", text: "Da." } }, {}), false);
assert.strictEqual(Pfad.istLeer({ aktion: { typ: "link", url: "  " } }, {}), true);
assert.deepStrictEqual(Pfad.karten({
  liste: [
    { wort: "Browser", aktion: { typ: "ziel", name: "browser" } },
    { wort: "Da", aktion: { typ: "sprechen", text: "Da." } },
  ],
}, config.ziele).map(card => card.wort), ["Da"]);

const aus = Pfad.karten(config.screens.steuern).find(card => card.wort === "Ausschalten");
assert.strictEqual(Pfad.brauchtRueckfrage(aus), true);
assert.strictEqual(Pfad.brauchtRueckfrage(Object.assign({ _ja: true }, aus)), false);
assert.strictEqual(aus.abbruch, "Der Rechner bleibt an.");

const hilferufKarte = Pfad.karten(config.screens.sagen)[0];
assert.strictEqual(Pfad.aktionVon(hilferufKarte).typ, "hilferuf");
assert.strictEqual(config.hilferuf.server, "https://ntfy.sh");
assert.strictEqual(config.hilferuf.testTage, 30);
const kanalOk = wert => wert === "" || /^[a-f0-9]{32}$/.test(String(wert));
assert.ok(kanalOk(config.hilferuf.kanal) && kanalOk(config.hilferuf.antwort), "Kanäle leer oder Zufall");
if (config.hilferuf.kanal || config.hilferuf.antwort) {
  assert.notStrictEqual(config.hilferuf.kanal, config.hilferuf.antwort);
}
Object.keys(config.ziele).forEach(name => assert.strictEqual(config.ziele[name], "", name));

assert.deepStrictEqual(Pfad.FESTE, ["zurueck", "nein", "ja"]);
assert.strictEqual(Pfad.naechster(["links", "rechts"], "links"), "rechts");
assert.strictEqual(Pfad.naechster(["links", "rechts"], "rechts"), "links");
assert.strictEqual(Pfad.zustand("Steuern", "Lautstärke"), "Steuern. Lautstärke.");

const startPaar = Pfad.duoPaar(Pfad.karten(config.screens.start), 0, false);
assert.strictEqual(startPaar.links.wort, "Ich will was sagen");
assert.strictEqual(startPaar.rechts.sonder, "andere");
assert.strictEqual(startPaar.blaettern, true);
assert.strictEqual(startPaar.liste.length, 7);
const sagenPaar = Pfad.duoPaar(Pfad.karten(config.screens.sagen), 0, true);
assert.strictEqual(sagenPaar.links.wort, "Hilferuf");
assert.strictEqual(sagenPaar.rechts.sonder, "andere");
assert.strictEqual(sagenPaar.blaettern, true);
const steuernPaar = Pfad.duoPaar(Pfad.karten(config.screens.steuern), 0, true);
assert.strictEqual(steuernPaar.links.wort, "Lautstärke");
assert.strictEqual(steuernPaar.rechts.sonder, "andere");
assert.strictEqual(steuernPaar.liste[4].sonder, "zurueck");
const letzte = Pfad.duoPaar(Pfad.karten(config.screens.steuern), 4, true);
assert.strictEqual(letzte.links.sonder, "zurueck");
const zweiMit = Pfad.duoPaar([{ wort: "A", aktion: { typ: "sprechen", text: "A" } }, { wort: "B", aktion: { typ: "sprechen", text: "B" } }], 0, true);
assert.ok(zweiMit.liste.some(k => k.sonder === "zurueck"), "Zurück ist auch bei zwei Einträgen erreichbar");
const eine = Pfad.duoPaar([{ wort: "Noch leer", aktion: { typ: "sprechen", text: "Hier ist noch nichts." } }], 0, true);
assert.strictEqual(eine.links.wort, "Noch leer");
assert.strictEqual(eine.rechts.sonder, "zurueck");
const fragePaar = Pfad.fragePaar();
assert.strictEqual(fragePaar.links.sonder, "nein");
assert.strictEqual(fragePaar.rechts.sonder, "ja");
assert.strictEqual(fragePaar.frage, true);
// Einrichtung: bedienung (Stimme | Knöpfe) -> knopf -> modus (b | a | c). Nie still fertig.
const stimmeWahl = Pfad.einrichtungWahl("bedienung", "stimme");
assert.strictEqual(stimmeWahl.fertig, false);
assert.strictEqual(stimmeWahl.schritt, "modus");
assert.strictEqual(stimmeWahl.hoeren, true);
assert.strictEqual(stimmeWahl.knopf, "zwei");
assert.strictEqual(Pfad.einrichtungStart({ fertig: false }), "sprache");
assert.strictEqual(Pfad.einrichtungStart({ fertig: false, sprache: true }), "bedienung");
assert.strictEqual(Pfad.einrichtungWahl("sprache", "en").sprache, "en");
assert.strictEqual(Pfad.einrichtungWahl("sprache", "de").schritt, "bedienung");
const knoepfeWahl = Pfad.einrichtungWahl("bedienung", "knoepfe");
assert.strictEqual(knoepfeWahl.schritt, "knopf");
assert.strictEqual(knoepfeWahl.hoeren, false);
assert.strictEqual(Pfad.einrichtungWahl("knopf", "ein").knopf, "ein");
assert.strictEqual(Pfad.einrichtungWahl("knopf", "ein").schritt, "modus");
assert.strictEqual(Pfad.einrichtungWahl("knopf", "zwei").knopf, "zwei");
["a", "b", "c"].forEach(m => {
  const e = Pfad.einrichtungWahl("modus", m);
  assert.strictEqual(e.fertig, false, "nach dem Modus kommt noch die Autostart-Frage");
  assert.strictEqual(e.schritt, "autostart");
  assert.strictEqual(e.modus, m);
  assert.notStrictEqual(e.autostart, true, "kein stiller Autostart");
});
// Letzte Frage: nur ein ausdrückliches Ja schaltet ein
assert.deepStrictEqual(Pfad.einrichtungWahl("autostart", "ja"), { fertig: true, autostart: true });
assert.deepStrictEqual(Pfad.einrichtungWahl("autostart", "nein"), { fertig: true, autostart: false });
assert.strictEqual(Pfad.einrichtungWahl("autostart", undefined).autostart, false, "ohne Antwort = Nein");
assert.strictEqual(Pfad.einrichtungWahl("autostart", "x").autostart, false);
// Diashow: 10 s pro Bild, einstellbar 3 bis 120 s
assert.strictEqual(Pfad.bildMs(undefined), 10000);
assert.strictEqual(Pfad.bildMs(""), 10000);
assert.strictEqual(Pfad.bildMs("x"), 10000);
assert.strictEqual(Pfad.bildMs(1), 3000);
assert.strictEqual(Pfad.bildMs(25), 25000);
assert.strictEqual(Pfad.bildMs(999), 120000);
assert.strictEqual(JSON.parse(fs.readFileSync(path.join(root, "config.example.json"), "utf8")).bildSekunden, 10);
// Listenseite mit je zwei Karten und "Weiter blättern"
const filme = ["a", "b", "c", "d", "e"].map(n => ({ wort: n, aktion: { typ: "film", name: n + ".mp4" } }));
const s0 = Pfad.seitenPaar(filme, 0);
assert.strictEqual(s0.links.wort, "a"); assert.strictEqual(s0.rechts.wort, "b");
assert.strictEqual(s0.fussB.sonder, "blaettern"); assert.strictEqual(s0.fussZ.sonder, "zurueck");
assert.strictEqual(s0.seiten, 3); assert.strictEqual(s0.mehr, true);
assert.strictEqual(Pfad.naechsteSeite(s0), 2);
const s2 = Pfad.seitenPaar(filme, 2);
assert.strictEqual(s2.links.wort, "c"); assert.strictEqual(s2.rechts.wort, "d");
const s4 = Pfad.seitenPaar(filme, 4);
assert.strictEqual(s4.links.wort, "e"); assert.strictEqual(s4.rechts.sonder, "zurueck", "leerer Platz zeigt Zurück");
assert.strictEqual(Pfad.naechsteSeite(s4), 0, "nach der letzten Seite wieder die erste");
assert.strictEqual(Pfad.seitenPaar([], 0).seiten, 1);
assert.strictEqual(Pfad.tasteVon(undefined, "ArrowDown"), "blaettern");
assert.strictEqual(Pfad.istLeer({ aktion: { typ: "film", name: "" } }, {}), true);
// Wahl-Wartezeit der Kachel: Standard 3 s, 0 = sofort, höchstens 10 s
assert.strictEqual(Pfad.waehlMs(undefined), 3000);
assert.strictEqual(Pfad.waehlMs(""), 3000);
assert.strictEqual(Pfad.waehlMs("x"), 3000);
assert.strictEqual(Pfad.waehlMs(0), 0);
assert.strictEqual(Pfad.waehlMs(1.5), 1500);
assert.strictEqual(Pfad.waehlMs(99), 10000);
assert.strictEqual(Pfad.waehlMs(-2), 0);
["config.example.json", "config.example.en.json"].forEach(n => {
  assert.strictEqual(JSON.parse(fs.readFileSync(path.join(root, n), "utf8")).waehlSekunden, 3, n + ": Wahl-Wartezeit 3 s");
});
assert.strictEqual(Pfad.einrichtungWahl("modus", "x").fertig, false, "unbekannte Wahl beendet nichts");
assert.strictEqual(Pfad.einrichtungWahl("irgendwas", "x").fertig, false);
assert.deepStrictEqual(Pfad.MODI, ["b", "a", "c"], "Standard b zuerst");
const einStd = Pfad.einrichtungStandard();
assert.strictEqual(einStd.modus, "b");
assert.strictEqual(einStd.knopf, "zwei");
assert.strictEqual(einStd.autostart, false);
assert.strictEqual(Pfad.einrichtungNoetig(undefined), true);
assert.strictEqual(Pfad.einrichtungNoetig({ fertig: false }), true);
assert.strictEqual(Pfad.einrichtungNoetig({ fertig: true }), true, "alte Einrichtung fragt neu");
assert.strictEqual(Pfad.einrichtungNoetig({ fertig: true, stand: 1 }), true);
assert.strictEqual(Pfad.einrichtungNoetig({ fertig: true, stand: Pfad.EINRICHTUNG_STAND }), false);
// ausgeblendete Karten (Editor) zählen nicht
assert.strictEqual(Pfad.karten({ liste: [{ wort: "A", aktion: { typ: "hilferuf" } }, { wort: "B", aus: true, aktion: { typ: "hilferuf" } }] }).length, 1);
assert.strictEqual(Pfad.einrichtungWarteMs, undefined, "erste Einrichtung hat kein Zeitlimit");
assert.strictEqual(Pfad.passend("individuell", ["Zwei Wege", "Individuell"]), "Individuell");
assert.strictEqual(Pfad.passend("Zwei Wege oder Individuell", ["Zwei Wege", "Individuell"]), "");
assert.strictEqual(Pfad.passend("Gleich automatisch", ["Zwei Wege", "Individuell"]), "");
assert.strictEqual(Pfad.passend("ja oder nein", ["Ja", "Nein"]), "");
assert.strictEqual(Pfad.passend("nein", ["Ja", "Nein"]), "Nein");
const andereSvg = fs.readFileSync(path.join(root, "img/pixel/andere.svg"), "utf8");
assert.ok(!andereSvg.includes("L176"), "Andere ist kein Pfeil");
assert.ok(andereSvg.includes("<rect"), "Andere zeigt Flächen");
assert.ok(config.einrichtung);
assert.strictEqual(config.einrichtung.fertig, false, "frische Config startet in der Einrichtung");
assert.strictEqual(config.einrichtung.stand, undefined);
assert.strictEqual(config.modus, "b", "Standardmodus b");
["config.example.json", "config.example.en.json"].forEach(n => {
  const c = JSON.parse(fs.readFileSync(path.join(root, n), "utf8"));
  assert.notStrictEqual(c.einrichtung && c.einrichtung.fertig, true, n + " darf nicht fertig sein");
  assert.ok(!(c.einrichtung && c.einrichtung.stand), n + " ohne Stand");
});
assert.ok(config.autostart !== true);
assert.strictEqual(Pfad.darfTiefer(2), true);
assert.strictEqual(Pfad.darfTiefer(3), false);

const zuTief = {
  start: { liste: [{ wort: "A", aktion: { typ: "untermenue", ziel: "a" } }] },
  a: { liste: [{ wort: "B", aktion: { typ: "untermenue", ziel: "b" } }] },
  b: { liste: [{ wort: "C", aktion: { typ: "untermenue", ziel: "c" } }] },
  c: { liste: [{ wort: "D" }] },
};
assert.ok(Pfad.pruefeBaum(zuTief, "start").length > 0);

const pluginIndex = JSON.parse(fs.readFileSync(path.join(root, "plugins/index.json"), "utf8"));
assert.deepStrictEqual(pluginIndex, ["grundbeduerfnisse"]);
const plugin = JSON.parse(fs.readFileSync(path.join(root, "plugins/grundbeduerfnisse/plugin.json"), "utf8"));
assert.strictEqual(plugin.karten.length, 7);
assert.ok(plugin.karten.every(karte => karte.aktion && karte.aktion.typ === "sprechen" && karte.aktion.text));
assert.ok(!JSON.stringify(plugin).includes("/home/"));
const lizenz = fs.readFileSync(path.join(root, "LICENSE"), "utf8");
assert.ok(lizenz.startsWith("GNU GENERAL PUBLIC LICENSE"));
assert.ok(lizenz.includes("Version 3, 29 June 2007"));

["app.js", "pfad.js", configDatei, "README.md", "bausteine.py", "server.py", "index.html", "startlib.sh", "AUSWAHL-LISTE.md", "ohr.py", "hilferuf.py", "setup.html", "praxis.py", "install.sh", "start-talker.sh", "start-talker-fenster.sh", "zurueck.sh", "LICENSE", "CREDITS.md", "plugins/index.json", "plugins/grundbeduerfnisse/plugin.json"].forEach(name => {
  const text = fs.readFileSync(path.join(root, name), "utf8");
  assert.ok(!text.includes("/home/"), name + " enthält einen festen Privatpfad");
});
const roh = fs.readFileSync(path.join(root, configDatei), "utf8");
assert.ok(!/youtube|joyn|chipmunk/i.test(roh));

console.log("PFAD_OK idle=20 hinweis=15 beide=aus tiefe<=3");

// Bildsatz: glatt ist Standard, alte Pfade bleiben gültig
assert.strictEqual(Pfad.bildStil(undefined), "glatt");
assert.strictEqual(Pfad.bildStil("Pixel"), "pixel");
assert.strictEqual(Pfad.bildStil("quatsch"), "glatt");
assert.strictEqual(Pfad.bildPfad("img/ja.svg"), "img/glatt/ja.svg");
assert.strictEqual(Pfad.bildPfad("img/ja.svg", "pixel"), "img/pixel/ja.svg");
assert.strictEqual(Pfad.bildPfad("img/pixel/ja.svg", "glatt"), "img/pixel/ja.svg");
assert.strictEqual(Pfad.bildPfad("plugins/grundbeduerfnisse/durst.svg", "pixel"), "plugins/grundbeduerfnisse/pixel/durst.svg");
assert.strictEqual(Pfad.bildPfad("/api/plugin-bild?id=a&datei=b.svg", "pixel"), "/api/plugin-bild?id=a&datei=b.svg");
assert.strictEqual(Pfad.bildPfad("https://x/y.svg", "pixel"), "https://x/y.svg");
console.log("BILDSTIL_JS_OK");
