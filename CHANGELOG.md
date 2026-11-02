# Changelog

## 0.3.2 (2026-11-02)

Security release for omacom/omarchy-plugin-marketplace#12234 (session secret in a host-wide cookie). Full report: `docs/security-review-2026-11-02.md`.

- **No secret in a cookie, URL or log.** `sitzung.js` no longer writes `omaclusive_session` (cookies are not isolated by port,
  RFC 6265 §8.5) and removes an old one. The server ignores cookies. The start page no longer carries the secret in the URL fragment.
- **One-time start.** The launcher fetches a single-use start code (60 s) with the file secret and writes a private `0600` start page
  that redeems it by `POST /api/start`. The server answers with a separate browser token that only lives in page memory and in
  `sessionStorage` of `http://127.0.0.1:8795` (isolated by port). The start page is deleted when the code is redeemed.
- **Exact origin with port.** Host must be `127.0.0.1:<port>` for every request (DNS rebinding), Origin/Referer `http://127.0.0.1:<port>`;
  `localhost`, other ports, `same-site` and `cross-site` are refused. `401` without or with a wrong token, `403` for a foreign origin/host/port.
- **Media without cookie:** pictures, films and the PDF use per-URL HMAC signatures. WebSocket: token in the subprotocol.
- **Hardening from the review:** setup tiles no longer built with `innerHTML` (XSS via file names), `X-Frame-Options`/`frame-ancestors`,
  `nosniff`, `no-referrer`, CSP `sandbox` for served pictures, strict `Content-Length`, 30 s connection timeout, generic `500` without details,
  voice download errors without paths, quoted autostart `Exec`, installer copies `pflege.py`/`pflege.html`.
- Tests: new `test_kein_cookie.py` and `test_sitzung_browser.js`; browser tests use the real start path; `test_bild.js` starts its own server.

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
