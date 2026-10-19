-- Omaclusive Fernsehen: die Knöpfe in mpv. Wird nur von fernsehen.py geladen (--script=...).
-- Omaclusive TV: the buttons inside mpv. Only loaded by fernsehen.py (--script=...).
--
-- Zwei Knöpfe: links = Zurück zum Start, rechts = Pause / Weiter, beide 3 s halten = Zurück.
-- Ein Knopf:   kurz = Pause / Weiter, 3 s halten = Zurück.
-- Esc ist immer Zurück. Zu schnelle Drücke (Sperrzeit wie in Omaclusive) zählen nicht.
-- Nichts blinkt, nichts wird eingeblendet. Kommt in der Wartezeit kein Bild, endet mpv
-- mit Code 3; Omaclusive sagt dann ruhig "Geht gerade nicht" und geht zum Start.

local mp = require "mp"
local options = require "mp.options"

local o = { links = "LEFT/MBTN_LEFT", rechts = "RIGHT/MBTN_RIGHT", ein = "nein",
            halten = 3000, entprell = 300, warten = 30 }
options.read_options(o, "omaclusive_tv")

local ein = o.ein == "ja"
local unten = {}          -- "links"/"rechts" -> { seit = Zeit, verbraucht = bool, verworfen = bool }
local letzter = nil       -- Zeit des letzten gezählten Drucks
local halte_timer = nil
local angekommen = false
local warte_timer = nil
local puffer_timer = nil

local function jetzt() return mp.get_time() * 1000 end

local function zurueck() mp.commandv("quit", "0") end

local function pause_wechseln()
  mp.set_property_bool("pause", not mp.get_property_bool("pause", false))
end

local function anzahl()
  local n = 0
  for _ in pairs(unten) do n = n + 1 end
  return n
end

local function halte_stopp()
  if halte_timer then halte_timer:kill(); halte_timer = nil end
end

local function halte_start()
  halte_stopp()
  halte_timer = mp.add_timeout(o.halten / 1000, function()
    halte_timer = nil
    zurueck()
  end)
end

-- mpv kennt immer nur eine gedrückte Taste: drückt man die zweite, meldet mpv die erste
-- sofort als losgelassen. Darum wartet ein Loslassen kurz (WARTE_MS). Kommt in der Zeit der
-- andere Knopf, sind es "beide": 3 s halten = Zurück, früher loslassen = nichts.
local WARTE_MS = 150
local wartet = nil        -- { knopf = ..., timer = ... }: ein Loslassen, das kurz wartet
local beide = false

local function ausfuehren(knopf)
  if ein or knopf == "rechts" then pause_wechseln() else zurueck() end
end

local function beide_an(knopf, t)
  for _, x in pairs(unten) do x.verbraucht = true end
  unten[knopf] = unten[knopf] or { seit = t, verbraucht = true, verworfen = false }
  beide = true
  halte_start()                        -- beide halten = Zurück
end

local function druck(knopf)
  if unten[knopf] then return end      -- gehalten, die Taste wiederholt sich
  local t = jetzt()
  if wartet and wartet.knopf ~= knopf then
    wartet.timer:kill(); wartet = nil  -- der andere Knopf kam dazu: das sind beide
    beide_an(knopf, t)
    return
  end
  local e = { seit = t, verbraucht = false, verworfen = false }
  if letzter and t - letzter < o.entprell then e.verworfen = true else letzter = t end
  unten[knopf] = e
  if ein then
    halte_start()                      -- ein Knopf: 3 s halten = Zurück
  elseif anzahl() >= 2 then
    beide_an(knopf, t)
  end
end

local function los(knopf)
  local e = unten[knopf]
  if not e then return end
  unten[knopf] = nil
  if beide then
    halte_stopp()                      -- vor 3 s losgelassen: nichts passiert
    unten = {}                         -- mpv meldet den ersten Knopf nicht noch einmal
    beide = false
    return
  end
  if ein then halte_stopp() end
  if e.verbraucht or e.verworfen then return end
  if ein then ausfuehren(knopf); return end
  if wartet then wartet.timer:kill() end
  local w = { knopf = knopf }
  w.timer = mp.add_timeout(WARTE_MS / 1000, function()
    if wartet ~= w then return end
    wartet = nil
    ausfuehren(knopf)
  end)
  wartet = w
end

local function binde(tasten, knopf)
  local i = 0
  for taste in string.gmatch(tasten or "", "[^/]+") do
    i = i + 1
    mp.add_forced_key_binding(taste, "omaclusive-" .. knopf .. "-" .. i, function(ev)
      if ev.event == "down" then druck(knopf)
      elseif ev.event == "up" then los(knopf)
      elseif ev.event == "press" then druck(knopf); los(knopf) end
    end, { complex = true })
  end
end

binde(o.links, "links")
binde(o.rechts, "rechts")
mp.add_forced_key_binding("ESC", "omaclusive-esc", zurueck)

-- Kommt kein Bild: ruhig aufgeben (Code 3), nie endlos schwarz warten.
local function aufgeben() mp.commandv("quit", "3") end

warte_timer = mp.add_timeout(o.warten, function()
  if not angekommen then aufgeben() end
end)

mp.register_event("playback-restart", function()
  angekommen = true
  if warte_timer then warte_timer:kill(); warte_timer = nil end
end)

-- Hängt der Stream später zu lange (Puffer leer), auch ruhig aufgeben.
mp.observe_property("paused-for-cache", "bool", function(_, haengt)
  if haengt then
    if not puffer_timer then puffer_timer = mp.add_timeout(o.warten, aufgeben) end
  elseif puffer_timer then
    puffer_timer:kill(); puffer_timer = nil
  end
end)

mp.register_event("end-file", function(ev)
  if ev.reason == "error" then mp.commandv("quit", "2") end
end)
