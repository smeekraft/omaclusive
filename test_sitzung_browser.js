"use strict";
// Hängt sich an den von test_sitzung.py gestarteten Chrome. Die Seite kommt
// über die Startdatei (file://), ohne dass das Geheimnis in der Befehlszeile steht.
const http = require("http");

const port = process.env.PORT;
const debugPort = process.env.DEBUG_PORT;

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let body = "";
      res.on("data", c => { body += c; });
      res.on("end", () => { try { resolve(JSON.parse(body)); } catch (e) { reject(e); } });
    }).on("error", reject);
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

function cdp(wsUrl) {
  let id = 0;
  const pending = new Map();
  const ws = new WebSocket(wsUrl);
  const opened = new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", () => reject(new Error("DevTools nicht verbunden")));
  });
  ws.addEventListener("message", ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const job = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) job.reject(new Error(JSON.stringify(msg.error)));
      else job.resolve(msg.result);
    }
  });
  return {
    opened,
    send(method, params) {
      const mine = ++id;
      ws.send(JSON.stringify({ id: mine, method, params: params || {} }));
      return new Promise((resolve, reject) => pending.set(mine, { resolve, reject }));
    },
    close() { try { ws.close(); } catch (e) {} },
  };
}

async function ev(client, expression, awaitPromise) {
  const r = await client.send("Runtime.evaluate", { expression, awaitPromise: !!awaitPromise, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 500));
  return r.result && r.result.value;
}

async function main() {
  let list = null;
  for (let i = 0; i < 50; i++) {
    try { list = await getJson("http://127.0.0.1:" + debugPort + "/json/list"); break; }
    catch (e) { await sleep(150); }
  }
  if (!list) throw new Error("Chrome antwortet nicht");
  const tab = list.find(item => item.webSocketDebuggerUrl && item.type === "page");
  if (!tab) throw new Error("kein Fenster");
  const client = cdp(tab.webSocketDebuggerUrl);
  await client.opened;
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  let stand = null;
  for (let i = 0; i < 80; i++) {
    stand = await ev(client, "JSON.stringify({ready:window.__ready===true,phase:window.__phase,url:location.href,kacheln:document.querySelectorAll('button.karte').length,passwort:!!document.querySelector('input[type=password]')})");
    stand = JSON.parse(stand || "{}");
    if (stand.ready && stand.url.indexOf("127.0.0.1:" + port) !== -1) break;
    await sleep(150);
  }
  if (!stand || !stand.ready) throw new Error("Seite nicht bereit: " + JSON.stringify(stand));
  if (stand.url.indexOf("/api/sitzung") !== -1 || stand.url.indexOf("k=") !== -1) {
    throw new Error("Geheimnis steht noch in der Adresse: " + stand.url);
  }
  if (stand.passwort) throw new Error("es gibt ein Passwortfeld");
  if (stand.phase !== "app" || stand.kacheln < 2) throw new Error("keine zwei Kacheln: " + JSON.stringify(stand));
  const api = JSON.parse(await ev(client, "fetch('/api/pfad',{cache:'no-store'}).then(async r=>JSON.stringify({s:r.status,ok:(await r.json()).ok}))", true));
  if (api.s !== 200 || api.ok !== true) throw new Error("API aus der Seite: " + JSON.stringify(api));
  const aus = JSON.parse(await ev(client, "fetch('/api/baustein',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'system.poweroff',confirm:false})}).then(async r=>JSON.stringify({s:r.status,b:await r.json()}))", true));
  if (aus.s !== 200 || !aus.b || aus.b.bestaetigen !== true || aus.b.ok !== false) {
    throw new Error("Rückfrage aus der Seite: " + JSON.stringify(aus));
  }
  console.log("OBERFLAECHE_OK");
  client.close();
}

main().catch(err => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
