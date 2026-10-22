"use strict";
const { execFileSync } = require("child_process");

function token(port, home, root) {
  const env = Object.assign({}, process.env, { PORT: String(port) });
  if (home) env.HOME = home;
  return execFileSync("python3", ["-c", "import os, sitzung; print(sitzung.lesen(int(os.environ['PORT']), os.environ.get('HOME') or None), end='')"], {
    cwd: root,
    env,
    encoding: "utf8",
  }).trim();
}

module.exports = { token };
