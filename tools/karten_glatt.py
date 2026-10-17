#!/usr/bin/env python3
"""Baut den glatten Bildsatz: SVG mit Pfaden, Kreisen und Linien, 24x24, weiss auf dunkelblau.
Aufruf: karten_glatt.py <img/glatt> [<plugins/xyz/glatt>]"""
import os, sys
NAVY, WHITE, YEL, RED = "#0c2340", "#ffffff", "#ffe14a", "#9a3412"
W = 2.2  # einheitliche Strichstaerke
I, P = {}, {}

def icon(name, bg=NAVY, fg=WHITE, form=None, plugin=False):
    def d(fn):
        (P if plugin else I)[name] = (fn, bg, fg, form); return fn
    return d

def S(*items, w=W, col=None):
    """Konturen: Pfad-Strings (d=...) oder fertige Elemente."""
    out = []
    for it in items:
        out.append(it if it.startswith("<") else '<path d="%s"/>' % it)
    return '<g fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round" stroke-linejoin="round">%s</g>' % (col or "FG", w, "".join(out))
def F(*items, col=None):
    out = [it if it.startswith("<") else '<path d="%s"/>' % it for it in items]
    return '<g fill="%s" stroke="none">%s</g>' % (col or "FG", "".join(out))
def circ(cx, cy, r): return '<circle cx="%g" cy="%g" r="%g"/>' % (cx, cy, r)
def rect(x, y, w, h, r=0): return '<rect x="%g" y="%g" width="%g" height="%g" rx="%g"/>' % (x, y, w, h, r)
def line(x0, y0, x1, y1): return '<path d="M%g %gL%g %g"/>' % (x0, y0, x1, y1)
def BG(): return "BG"
def slash(): return S("M4 4L20 20", w=W + 3.4, col="BG") + S("M4 4L20 20")

BELL = "M12 3.2C8.6 3.2 6.8 6 6.8 9.4C6.8 13.8 5.4 15.6 4.2 17.2H19.8C18.6 15.6 17.2 13.8 17.2 9.4C17.2 6 15.4 3.2 12 3.2Z"
SPK = "M3 9.5H6.5L12 5V19L6.5 14.5H3Z"
def waves(c=None):
    return S("M15 9.3C16.4 10.7 16.4 13.3 15 14.7", "M17.8 6.8C20.6 9.8 20.6 14.2 17.8 17.2")
WIFI = S("M2.8 9.2C8 4.6 16 4.6 21.2 9.2", "M6 12.8C9.4 10 14.6 10 18 12.8", "M9.2 16.2C11 14.8 13 14.8 14.8 16.2") + F(circ(12, 19.2, 1.6))
BT = "M6.5 7.5L17 16.5L12 21V3L17 7.5L6.5 16.5"

@icon("sagen")
def _(): return F("M3 22L4.2 17.2C2.2 15.2 1.4 12.6 1.4 9.8C1.4 5 5 1.8 9.4 1.8C13.4 1.8 16.2 4.4 16.3 8L16.4 9.4L18.2 11.5C18.7 12.1 18.4 12.6 17.7 12.7L16.5 12.9L17 13.8L14.8 14.9L16.9 15.9L16.4 17.4L15.9 18.2C15.6 18.8 14.9 19.3 13.8 19.5L12.6 19.9V22Z") + S("M19.4 10.2L22.6 8.4", "M19.8 13.6H23", "M19.4 17L22.6 18.8", w=1.8)

@icon("ja", YEL, NAVY, "haken")
def _(): return S("M5 12.8L10 17.8L19.5 6.5", w=3)
@icon("nein", NAVY, YEL, "kreuz")
def _(): return S("M6 6L18 18", "M18 6L6 18", w=3)
@icon("zurueck", NAVY, YEL, "pfeil")
def _(): return S("M20 12H5", "M11.5 5.5L5 12L11.5 18.5", w=3)
@icon("hilfe", RED, WHITE, "glocke")
def _(): return F(BELL, rect(9.8, 18.6, 4.4, 2.2, 1.1)) + S("M3 4.4L5.4 6.4", "M21 4.4L18.6 6.4", w=1.8)
@icon("ruf-aus")
def _(): return F(BELL, rect(9.8, 18.6, 4.4, 2.2, 1.1)) + slash()
@icon("ruf-gesehen")
def _(): return F(BELL, rect(8, 18.6, 4.4, 2.2, 1.1)) + F(circ(17.5, 17.5, 6.2), col="BG") + F(circ(17.5, 17.5, 4.8)) + S("M15 17.6L16.9 19.4L20 15.6", w=1.8, col="BG")
@icon("ruf-test")
def _(): return F("M10 5.2C7.2 5.2 5.8 7.6 5.8 10.4C5.8 14 4.6 15.4 3.6 16.6H16.4C15.4 15.4 14.2 14 14.2 10.4C14.2 7.6 12.8 5.2 10 5.2Z", rect(7.9, 17.8, 4.2, 2, 1)) + S("M17 6.4C18.6 8 18.6 10.8 17 12.4", "M19.8 3.6C22.8 6.8 22.8 11.8 19.8 15", w=1.9)
@icon("aus")
def _(): return S("M7.2 6.2A8.2 8.2 0 1 0 16.8 6.2", "M12 3V11.5")
@icon("neu")
def _(): return S("M19.5 12A7.5 7.5 0 1 1 16.9 6.3", "M17.5 2.5V7H13")
@icon("sperren")
def _(): return S(rect(5, 10.5, 14, 10.5, 2.2), "M8.2 10.5V8A3.8 3.8 0 0 1 15.8 8V10.5") + F(circ(12, 15.2, 1.6))
@icon("sonne")
def _(): return S(circ(12, 12, 4.6), *[line(12 + 8 * c, 12 + 8 * s, 12 + 10.6 * c, 12 + 10.6 * s) for c, s in ((1,0),(0.7071,0.7071),(0,1),(-0.7071,0.7071),(-1,0),(-0.7071,-0.7071),(0,-1),(0.7071,-0.7071))])
@icon("mond")
def _(): return F("M19.5 14.7A8.6 8.6 0 0 1 9.3 4.5A8.6 8.6 0 1 0 19.5 14.7Z")
@icon("spaeter")
def _(): return S(circ(12, 12, 9), "M12 6.5V12L15.8 14.2")
@icon("suche")
def _(): return S(circ(10, 10, 6.6), "M15 15L20.8 20.8", w=2.8)
@icon("sehen")
def _(): return S("M1.8 12C4.5 7.4 8 5.4 12 5.4C16 5.4 19.5 7.4 22.2 12C19.5 16.6 16 18.6 12 18.6C8 18.6 4.5 16.6 1.8 12Z") + F(circ(12, 12, 3.4))
@icon("schreiben")
def _(): return S("M16.5 3.5L20.5 7.5L8.5 19.5L3.5 20.5L4.5 15.5Z", "M14 6L18 10", "M13 20.8H20.5")
@icon("system")
def _(): return S("M12 2.8V5.2", "M12 18.8V21.2", "M2.8 12H5.2", "M18.8 12H21.2", "M5.5 5.5L7.2 7.2", "M16.8 16.8L18.5 18.5", "M5.5 18.5L7.2 16.8", "M16.8 7.2L18.5 5.5", w=2.6) + S(circ(12, 12, 5.6)) 
@icon("wlan")
def _(): return WIFI
@icon("wlan-aus")
def _(): return WIFI + slash()
@icon("bluetooth")
def _(): return S(BT)
@icon("bluetooth-aus")
def _(): return S(BT) + slash()
@icon("internet")
def _(): return S(circ(12, 12, 9.4), "M2.6 12H21.4", "M12 2.6C8 7 8 17 12 21.4", "M12 2.6C16 7 16 17 12 21.4")
@icon("mail")
def _(): return S(rect(2.8, 5, 18.4, 14, 2), "M3.4 6.6L12 13L20.6 6.6")
@icon("anruf")
def _(): return S("M5 3.6H9L10.8 8.2L8.6 9.8C9.8 12.4 11.6 14.2 14.2 15.4L15.8 13.2L20.4 15V19C20.4 20 19.6 20.8 18.6 20.8C10.8 20.4 3.6 13.2 3.2 5.4C3.2 4.4 4 3.6 5 3.6Z")
@icon("messenger")
def _(): return S("M4.5 4H19.5A1.8 1.8 0 0 1 21.3 5.8V14.6A1.8 1.8 0 0 1 19.5 16.4H10L5.5 20.4V16.4H4.5A1.8 1.8 0 0 1 2.7 14.6V5.8A1.8 1.8 0 0 1 4.5 4Z") + F(circ(7.6, 10.2, 1.4), circ(12, 10.2, 1.4), circ(16.4, 10.2, 1.4))
@icon("nachrichten")
def _(): return S(rect(3, 3.5, 18, 17, 2)) + F(rect(6, 6.5, 6, 5, 0.6)) + S("M14.5 7.5H18", "M14.5 10.5H18", "M6 14.5H18", "M6 17.5H18", w=1.6)
@icon("text")
def _(): return S("M6 2.8H14L19 7.8V20A1.2 1.2 0 0 1 17.8 21.2H6.2A1.2 1.2 0 0 1 5 20V4A1.2 1.2 0 0 1 6.2 2.8Z", "M14 2.8V7.8H19") + S("M8.4 12.2H15.6", "M12 12.2V18", w=2)
@icon("diktat")
def _(): return F(rect(8.6, 2.6, 6.8, 11.6, 3.4)) + S("M5.4 11.4C5.4 15 8 17.4 12 17.4C16 17.4 18.6 15 18.6 11.4", "M12 17.4V21.2", "M8.6 21.2H15.4")
@icon("fernsehen")
def _(): return S(rect(2.8, 7.4, 18.4, 13, 2.2), "M8.2 2.8L12 7.4L15.8 2.8") + F(circ(17.8, 12, 1.1), circ(17.8, 15.6, 1.1))
@icon("fotos")
def _(): return S(rect(2.8, 4.4, 18.4, 15.2, 2), "M3.6 17L9 11.4L13 15.4L15.6 12.8L20.4 17.4") + F(circ(8, 8.6, 1.9))
@icon("musik")
def _(): return F(circ(7, 17.8, 3.4), circ(17, 15.8, 3.4)) + S("M10.4 17.8V5.2L20.4 3.2V15.8", "M10.4 8L20.4 6", w=2)
@icon("medien")
def _(): return S(circ(12, 12, 9.4)) + F("M9.8 7.8L16.8 12L9.8 16.2Z")
@icon("pause")
def _(): return F(rect(5.4, 4.2, 4.8, 15.6, 1.4), rect(13.8, 4.2, 4.8, 15.6, 1.4))
@icon("ton")
def _(): return F(SPK) + waves()
@icon("lauter")
def _(): return F(SPK) + S("M14.6 12H21.4", "M18 8.6V15.4")
@icon("leiser")
def _(): return F(SPK) + S("M14.6 12H21.4")
@icon("stumm")
def _(): return F(SPK) + S("M15 9L21 15", "M21 9L15 15")
@icon("dateien")
def _(): return S("M3 6.4A1.6 1.6 0 0 1 4.6 4.8H9.4L11.6 7.4H19.4A1.6 1.6 0 0 1 21 9V18.2A1.6 1.6 0 0 1 19.4 19.8H4.6A1.6 1.6 0 0 1 3 18.2Z")
@icon("funk")
def _(): return F(circ(12, 9.6, 2)) + S("M12 11.6V21", "M8.6 21H15.4", "M7.4 5.6C5.4 7.8 5.4 11.4 7.4 13.6", "M16.6 5.6C18.6 7.8 18.6 11.4 16.6 13.6", "M4.6 3.2C1.4 6.8 1.4 12.4 4.6 16", "M19.4 3.2C22.6 6.8 22.6 12.4 19.4 16", w=1.9)
@icon("geraet")
def _(): return S(rect(3.4, 4, 17.2, 11.6, 1.8), "M1.8 19.6H22.2")
@icon("einfach")
def _(): return F(circ(12, 12, 7.6))
@icon("zwei")
def _(): return F(circ(6.4, 12, 4.4), circ(17.6, 12, 4.4))
@icon("mehr")
def _(): return S("M12 4V20", "M4 12H20", w=3)
@icon("andere")
def _(): return F(circ(4.6, 12, 2.6), circ(12, 12, 2.6), circ(19.4, 12, 2.6))
@icon("anpassen")
def _(): return S("M3 6H21", "M3 12H21", "M3 18H21") + F(circ(8, 6, 3), circ(16, 12, 3), circ(10, 18, 3)) + S(circ(8, 6, 3), circ(16, 12, 3), circ(10, 18, 3), w=1.6, col="BG")
@icon("helfen")
def _(): return F("M12 17.2C6.2 12.6 4.4 10.4 4.4 7.6A3.9 3.9 0 0 1 12 6.2A3.9 3.9 0 0 1 19.6 7.6C19.6 10.4 17.8 12.6 12 17.2Z") + S("M2.6 15.4L6.4 15.2L10.4 18.4H15.4L21.4 15.4", "M5 21H14.4L21.4 16.6")
def person(n, col=None):
    out = F(circ(12, 6.2, 3.8)) + F("M4.6 16.4C4.6 12.6 7.6 11 12 11C16.4 11 19.4 12.6 19.4 16.4Z")
    xs = {1: [12], 2: [9.4, 14.6], 3: [7, 12, 17]}[n]
    return out + F(*[circ(x, 20, 1.6) for x in xs])
@icon("kontakt-1")
def _(): return person(1)
@icon("kontakt-2")
def _(): return person(2)
@icon("kontakt-3", RED, WHITE)
def _(): return person(3)

# Plugin-Bilder
@icon("durst", plugin=True)
def _(): return F("M5.6 3.6H18.4L16.6 20.2A1.4 1.4 0 0 1 15.2 21.4H8.8A1.4 1.4 0 0 1 7.4 20.2Z") + F("M6.9 9.6H17.1L16.3 16.4C14.4 17.4 12.6 15.6 10.6 16.2C9.4 16.5 8.4 16.6 7.7 16.4Z", col="BG")
@icon("hunger", plugin=True)
def _(): return S("M7 3V10.5", "M4.2 3V9A2.8 2.8 0 0 0 9.8 9V3", "M7 12V21", "M17.4 21V3C15 4.6 13.8 8 13.8 11.4C13.8 12.8 14.4 13.4 17.4 13.4")
@icon("toilette", plugin=True)
def _(): return S(rect(6.4, 2.6, 11.2, 5.6, 1.4), "M3.6 11H20.4C20.4 15.6 17.6 17.4 15.4 17.6V21H8.6V17.6C6.4 17.4 3.6 15.6 3.6 11Z", "M5 8.6H19")
@icon("schmerz", RED, WHITE, plugin=True)
def _(): return F("M14.4 1.8L5 13H10.8L8.8 22.2L19 10H13Z")
@icon("pause", plugin=True)
def _(): return F(rect(5.4, 4.2, 4.8, 15.6, 1.4), rect(13.8, 4.2, 4.8, 15.6, 1.4))
@icon("kalt", plugin=True)
def _():
    arms = ["M12 2.6V21.4", "M3.9 7.3L20.1 16.7", "M3.9 16.7L20.1 7.3"]
    tips = ["M9.6 4.6L12 6.8L14.4 4.6", "M9.6 19.4L12 17.2L14.4 19.4"]
    return S(*arms, *tips, w=2)
@icon("warm", plugin=True)
def _(): return F("M12 1.8C13.2 5.6 19 8.8 19 15A7 7 0 0 1 5 15C5 11.8 6.6 10 8.2 8.2C8.4 10 9.2 11 10.2 11.4C10.2 7.6 10.6 4.4 12 1.8Z") + F("M12 21C9.8 21 8.6 19.4 8.6 17.6C8.6 15.8 10.2 14.8 12 12.6C13.8 14.8 15.4 15.8 15.4 17.6C15.4 19.4 14.2 21 12 21Z", col="BG")
@icon("haus", plugin=True)
def _(): return S("M2.8 11.4L12 3L21.2 11.4", "M5.4 9.4V20.4H18.6V9.4") + F(rect(10, 14, 4, 6.4, 0.8))
@icon("grund", plugin=True)
def _(): return F("M12 20.6C5.4 15.4 3.2 12.8 3.2 9.2A4.6 4.6 0 0 1 12 7.2A4.6 4.6 0 0 1 20.8 9.2C20.8 12.8 18.6 15.4 12 20.6Z")

def schreiben(ziel, plugin=None):
    for d, ordner in ((I, ziel), (P, plugin)):
        if not ordner: continue
        os.makedirs(ordner, exist_ok=True)
        for name, (fn, bg, fg, form) in d.items():
            body = fn()
            body = body.replace('"FG"', '"%s"' % fg).replace('"BG"', '"%s"' % bg)
            open(os.path.join(ordner, name + ".svg"), "w", encoding="utf-8").write(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%s><rect width="24" height="24" fill="%s"/>%s</svg>\n'
                % (' data-form="%s"' % form if form else '', bg, body))

if __name__ == "__main__":
    schreiben(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
