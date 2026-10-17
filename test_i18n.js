"use strict";
// Prueft sprache.js: Deutsch bleibt unveraendert, Englisch kommt aus locales/en.json.
const fs = require("fs");
const path = require("path");
global.fetch = file => Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(path.join(__dirname, file), "utf8"))) });
require("./sprache.js");
const fail = m => { console.error("I18N_JS_FAIL " + m); process.exit(1); };
(async () => {
  await I18N.laden("de");
  if (T("Ich rufe.") !== "Ich rufe.") fail("de");
  await I18N.laden("en");
  if (T("Ich rufe.") !== "I am calling.") fail("en");
  if (Tf("{} oder {}.", "A", "B") !== "A or B.") fail("Tf");
  if (T("gibt es nicht") !== "gibt es nicht") fail("Fallback Original");
  await I18N.laden("fr");
  if (I18N.sprache() !== "en") fail("Unbekannt -> en");
  if (I18N.sprechLang() !== "en-US") fail("sprechLang");
  console.log("I18N_JS_OK");
})();
