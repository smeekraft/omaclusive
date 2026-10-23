"use strict";
/* Liest das Sitzungsgeheimnis aus dem Fragment (nur dieser Browser) und schickt es
   bei lokalen Aufrufen mit. Andere Benutzer sehen es nicht, und es gibt keine Anmeldung. */
(function () {
  var NAME = "omaclusive-token";
  var token = "";
  var roh = (location.hash || "").replace(/^#/, "");
  if (/^[A-Za-z0-9_-]{20,128}$/.test(roh)) token = roh;
  if (!token) {
    try { token = sessionStorage.getItem(NAME) || ""; } catch (err) { token = ""; }
  }
  if (token) {
    try { sessionStorage.setItem(NAME, token); } catch (err) {}
    document.cookie = "omaclusive_session=" + encodeURIComponent(token) + "; Path=/; SameSite=Strict";
  }
  if (roh) {
    try { history.replaceState(null, "", location.pathname + location.search); } catch (err) {}
  }
  window.__omaclusiveToken = token;

  function zielVon(url) {
    return new URL(url, location.href);
  }

  function braucht(url) {
    try {
      var ziel = zielVon(url);
      if (ziel.origin !== location.origin) return false;
      return ziel.pathname === "/config.json" || ziel.pathname.indexOf("/api/") === 0;
    } catch (err) {
      return false;
    }
  }

  var orig = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    if (!token || !braucht(url)) return orig.call(this, input, init);
    var next = Object.assign({}, init);
    var headers = new Headers(next.headers || (typeof Request !== "undefined" && input instanceof Request ? input.headers : undefined));
    if (!headers.has("X-Omaclusive-Token")) headers.set("X-Omaclusive-Token", token);
    next.headers = headers;
    return orig.call(this, input, next);
  };
})();
