"use strict";
/* Browser-Token für die lokale Omaclusive-API.

   Das Token kommt einmal beim Start über /api/start (POST mit Einmal-Code aus einer
   privaten Startdatei) und liegt danach nur in sessionStorage dieser Herkunft
   (http://127.0.0.1:<port>, also auch dieses Ports) und im Speicher der Seite.
   Nie in einem Cookie (Cookies trennen keine Ports, RFC 6265 §8.5), nie in localStorage,
   nie in einer Adresse und nie im Log.

   - fetch() zu /api/* und /config.json bekommt den Kopf X-Omaclusive-Token.
   - Bilder, Filme und das PDF laden über Adressen mit Signatur (HMAC über genau diese
     Adresse). Die Signatur verrät das Token nicht und gilt für nichts anderes.
   - WebSocket: Token im Unterprotokoll, nicht in der Adresse. */
(function () {
  var NAME = "omaclusive-sitzung";
  var token = "";
  try { token = sessionStorage.getItem(NAME) || ""; } catch (err) { token = ""; }
  if (!/^[A-Za-z0-9_-]{20,128}$/.test(token)) token = "";
  // Altes Cookie früherer Versionen entfernen (es trug das Geheimnis für alle Ports).
  try { document.cookie = "omaclusive_session=; Max-Age=0; Path=/; SameSite=Strict"; } catch (err) {}

  // --- SHA-256 und HMAC, synchron (für img.src und video.src) ---
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  function utf8(text) {
    return Array.prototype.slice.call(new TextEncoder().encode(text));
  }
  function sha256(bytes) {
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var m = bytes.slice();
    var bits = bytes.length * 8;
    m.push(0x80);
    while (m.length % 64 !== 56) m.push(0);
    for (var s = 7; s >= 0; s--) m.push(s >= 4 ? 0 : (bits >>> (s * 8)) & 0xff);
    var w = new Array(64);
    for (var i = 0; i < m.length; i += 64) {
      for (var t = 0; t < 16; t++) {
        w[t] = (m[i + 4 * t] << 24) | (m[i + 4 * t + 1] << 16) | (m[i + 4 * t + 2] << 8) | m[i + 4 * t + 3];
      }
      for (t = 16; t < 64; t++) {
        var x = w[t - 15], y = w[t - 2];
        var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        var s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
      for (t = 0; t < 64; t++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (k + S1 + ch + K[t] + w[t]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) | 0;
        k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
      h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + k) | 0;
    }
    var out = [];
    for (i = 0; i < 8; i++) out.push((h[i] >>> 24) & 0xff, (h[i] >>> 16) & 0xff, (h[i] >>> 8) & 0xff, h[i] & 0xff);
    return out;
  }
  function hmacHex(schluessel, text) {
    var key = utf8(schluessel);
    if (key.length > 64) key = sha256(key);
    while (key.length < 64) key.push(0);
    var innen = key.map(function (v) { return v ^ 0x36; });
    var aussen = key.map(function (v) { return v ^ 0x5c; });
    var mac = sha256(aussen.concat(sha256(innen.concat(utf8(text)))));
    return mac.map(function (v) { return (v < 16 ? "0" : "") + v.toString(16); }).join("");
  }

  var SIGNIERBAR = ["/api/datei", "/api/plugin-bild", "/api/medium", "/api/blatt"];

  function eigen(url) {
    try {
      var ziel = new URL(url, location.href);
      return ziel.origin === location.origin ? ziel : null;
    } catch (err) {
      return null;
    }
  }

  function braucht(url) {
    var ziel = eigen(url);
    return !!ziel && (ziel.pathname === "/config.json" || ziel.pathname.indexOf("/api/") === 0);
  }

  /* Medien-Adresse mit Signatur, sonst unverändert (z. B. img/x.svg). */
  function src(url) {
    var text = String(url == null ? "" : url);
    var ziel = eigen(text);
    if (!token || !ziel || SIGNIERBAR.indexOf(ziel.pathname) === -1) return text;
    var suche = ziel.search.replace(/([?&])sig=[0-9a-f]*$/, "").replace(/[?&]$/, "");
    var basis = ziel.pathname + suche;
    var sig = hmacHex(token, "medien\n" + basis);
    return basis + (suche ? "&" : "?") + "sig=" + sig;
  }

  function websocket(pfad) {
    var protokolle = ["omaclusive"];
    if (token) protokolle.push("omaclusive-token." + token);
    return new WebSocket("ws://" + location.host + pfad, protokolle);
  }

  var orig = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    if (!token || !braucht(url)) return orig.call(this, input, init);
    var next = Object.assign({}, init);
    var headers = new Headers(next.headers || (typeof Request !== "undefined" && input instanceof Request ? input.headers : undefined));
    if (!headers.has("X-Omaclusive-Token")) headers.set("X-Omaclusive-Token", token);
    next.headers = headers;
    next.credentials = "omit";
    return orig.call(this, input, next);
  };

  Object.defineProperty(window, "Sitzung", {
    value: Object.freeze({
      angemeldet: !!token,
      src: src,
      websocket: websocket,
      _hmac: hmacHex,
    }),
    writable: false,
    configurable: false,
  });
})();
