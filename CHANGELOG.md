# Changelog

## 0.3.1 (2026-10-30)

Security release for the Omarchy plugin review (omacom/omarchy-plugin-marketplace#12234). Full report: `docs/sicherheit-2026-10-30.md`.

- **Input channel needs the session secret.** The app no longer connects to an unauthenticated `ws://localhost:8765`.
  Button bridges now use `ws://127.0.0.1:8795/api/eingabe` on Omaclusive's own server. The handshake checks the same
  session secret, Host and Origin as the HTTP API, also on every reconnect. Off by default: `"eingabe": {"websocket": true}` turns it on.
- **Launcher checks the server.** The browser only opens when the server on port 8795 proves it knows the new session secret
  (HMAC answer on `/api/bereit?probe=…`). A port taken by another account stops the start.
- **Nothing private is served.** `server.log` moved to the private session folder (`0600`). The server no longer serves hidden files,
  `*.log`, `*.bak`, `*.tmp`, `*.teil`, folder listings, or links that point out of its folder.
- **File modes.** The install folder is `0700`, `config.json` and `config.json.bak` are `0600` (also set at server start),
  `pflege.json` is written atomically with `0600`.
- **Picture styles** no longer follow links out of the picture folder.
- Tests: new `test_eingabe_kanal.py`, new browser scenarios in `test_eingabe.js`. `test_modi.py` no longer fails on a second run.
