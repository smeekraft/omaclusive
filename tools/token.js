"use strict";
const { execFileSync } = require("child_process");

function python(code, port, home, root, extra) {
  const env = Object.assign({}, process.env, { PORT: String(port) }, extra || {});
  if (home) env.HOME = home;
  return execFileSync("python3", ["-c", code], { cwd: root, env, encoding: "utf8" }).trim();
}

/* Datei-Geheimnis (0600) für Anfragen von Node aus, wie die Werkzeuge dieses Kontos. Nie für den Browser. */
function token(port, home, root) {
  return python("import os, sitzung; print(sitzung.lesen(int(os.environ['PORT']), os.environ.get('HOME') or None), end='')", port, home, root);
}

/* Echter Startweg für den Browser: Einmal-Code holen, private Startdatei schreiben, file://-Adresse zurück.
   Die Startdatei löst den Code per POST /api/start ein und landet auf http://127.0.0.1:<port>/<seite>. */
function startUrl(port, home, root, seite) {
  return python("import os, sitzung; print(sitzung.boot_url(int(os.environ['PORT']), os.environ.get('SEITE') or '', os.environ.get('HOME') or None), end='')",
    port, home, root, { SEITE: seite || "" });
}

module.exports = { token, startUrl };
