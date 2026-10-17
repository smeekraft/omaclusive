"use strict";
/* Zweisprachigkeit de/en. Schluessel ist der deutsche Originaltext.
   Tabellen: locales/de.json, locales/en.json. Sprache: ?lang=en in der Adresse,
   sonst "language" in config.json, sonst "de". Jeder Code mit locales/xx.json geht. Fehlt die Datei, faellt es auf Englisch zurueck.
   Fehlt ein Eintrag, bleibt der Originaltext stehen. */
(function (g) {
  let sprache = "de";
  let tabelle = {};

  function normal(code) {
    const c = String(code || "").trim().toLowerCase().replace("_", "-").split("-")[0];
    if (!c) return "de";
    return /^[a-z]{2,3}$/.test(c) ? c : "en";
  }

  function T(text) {
    text = String(text);
    if (sprache === "de") return text;
    return Object.prototype.hasOwnProperty.call(tabelle, text) ? tabelle[text] : text;
  }

  function Tf(text) {
    const args = Array.prototype.slice.call(arguments, 1);
    let i = 0;
    return T(text).replace(/\{\}/g, () => (i < args.length ? String(args[i++]) : ""));
  }

  function laden(code) {
    sprache = normal(code);
    g.document && g.document.documentElement && g.document.documentElement.setAttribute("lang", sprache);
    if (sprache === "de") return Promise.resolve();
    const hole = code => fetch("locales/" + code + ".json", { cache: "no-store" }).then(r => (r.ok ? r.json() : null)).catch(() => null);
    return hole(sprache)
      .then(t => t || (sprache = "en", g.document && g.document.documentElement.setAttribute("lang", "en"), hole("en")))
      .then(t => { tabelle = t && typeof t === "object" ? t : {}; });
  }

  function statisch(wurzel) {
    const doc = wurzel || g.document;
    if (!doc || sprache === "de") return;
    const w = doc.createTreeWalker(doc.body || doc, 4);
    const knoten = [];
    while (w.nextNode()) knoten.push(w.currentNode);
    knoten.forEach(k => {
      if (k.parentNode && /^(SCRIPT|STYLE)$/.test(k.parentNode.nodeName)) return;
      const roh = k.nodeValue, t = roh.trim();
      if (!t) return;
      const v = T(t);
      if (v !== t) k.nodeValue = roh.replace(t, v);
    });
    doc.querySelectorAll("[placeholder]").forEach(e => { e.placeholder = T(e.placeholder); });
    doc.title = T(doc.title);
  }

  function sprechLang() {
    return sprache === "de" ? "de-DE" : "en-US";
  }

  g.I18N = { T: T, Tf: Tf, laden: laden, statisch: statisch, normal: normal, sprache: () => sprache, sprechLang: sprechLang };
  g.T = T;
  g.Tf = Tf;
})(typeof window !== "undefined" ? window : globalThis);
