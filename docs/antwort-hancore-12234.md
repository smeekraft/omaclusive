<!-- Draft reply for omacom/omarchy-plugin-marketplace#12234. Not posted. Replace the commit hashes with the merge commit after the merge if preferred. -->

Thanks again, @HANCORE-linux. Fixed in smeekraft/omaclusive#10, code in `b96e8a9`, tests in `5d13ff1` (version 0.3.2).

**The browser no longer holds the session secret, and there is no cookie.**

- `sitzung.js` no longer writes `omaclusive_session` and deletes an old one. The server never reads cookies.
- The launcher uses the `0600` file secret to fetch a single-use start code (valid for 60 s) and writes a private `0600` start page. That page redeems the code with `POST /api/start`, and the server deletes it. The response gives the page a separate browser token. The token lives only in page memory and in `sessionStorage` of `http://127.0.0.1:8795`, which is isolated by port. It is never in a URL (the old `#fragment` is gone), in `localStorage` or in a log.
- Every request must use the Host `127.0.0.1:<port>`. API requests must also come from the exact origin `http://127.0.0.1:<port>` (Origin/Referer, port included). `localhost`, other ports and `Sec-Fetch-Site: same-site`/`cross-site` get `403`. A missing or wrong token gets `401`. Tokens are compared in constant time. There is no CORS, and the server binds only to `127.0.0.1`.
- `<img>`, `<video>` and the PDF use per-URL HMAC signatures. A signature does not reveal the token and opens nothing else. The WebSocket sends the token in the subprotocol, and the server echoes only `omaclusive`.

**How to check:**

- `node --experimental-websocket test_sitzung_browser.js` (real Chromium). A page on `127.0.0.1:<port+1>` in the same browser sees an empty `document.cookie` and empty storage. Its `fetch` calls to the API get `401`/`403`, and its WebSocket handshakes get `401`/`403` (never `101`). The app itself has no cookie, an empty `localStorage`, and no token in its URL or history. As a negative control, putting the old `sitzung.js:14` back makes 3 checks fail: the foreign page then reads the token.
- `python3 test_kein_cookie.py` (511 checks). Covers `401`/`403` for every combination of other port, origin, host and Referer, cookies being ignored, no `Set-Cookie` or CORS header, single-use and expiring start codes, signed media, and that the secrets are not in the server log.
- `python3 test_eingabe_kanal.py` covers the WebSocket: `403` for another port, `localhost`, `null` or a foreign host, and `401` without a token, with a wrong token or with only a cookie.

The full suite (23 test files) passes. I also reviewed the whole repo again and fixed a stored XSS in the settings tiles (file names were inserted with `innerHTML`). I added framing, `nosniff` and sandbox headers, a stricter `Content-Length` check, a connection timeout, and generic `500` responses. Report: `docs/security-review-2026-11-02.md`. Could you please re-check?
