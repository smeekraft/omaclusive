#!/usr/bin/env python3
"""Baut die Kartenbilder (img/*.svg) als reine Rechtecke auf 24x24: weiss auf dunkelblau."""
import math, sys, os
N = 24
NAVY, WHITE, YEL, RED = "#0c2340", "#ffffff", "#ffe14a", "#9a3412"

class C:
    def __init__(s, n=24):
        s.n = n; s.g = [[0]*n for _ in range(n)]
    def px(s, x, y, v=1):
        if 0 <= x < s.n and 0 <= y < s.n: s.g[y][x] = v
    def R(s, x, y, w, h, v=1):
        for j in range(y, y+h):
            for i in range(x, x+w): s.px(i, j, v)
    def fill(s, f, v=1):
        for y in range(s.n):
            for x in range(s.n):
                if f(x+.5, y+.5): s.px(x, y, v)
    def disc(s, cx, cy, r, v=1): s.fill(lambda x,y:(x-cx)**2+(y-cy)**2 <= r*r, v)
    def ring(s, cx, cy, r, t=2, v=1):
        s.fill(lambda x,y:(r-t)**2 <= (x-cx)**2+(y-cy)**2 <= r*r, v)
    def poly(s, pts, v=1):
        def inside(x, y):
            c = False; n = len(pts)
            for i in range(n):
                x1,y1 = pts[i]; x2,y2 = pts[(i+1)%n]
                if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: c = not c
            return c
        s.fill(inside, v)
    def line(s, x0, y0, x1, y1, t=2, v=1):
        h = t/2.0
        def f(x, y):
            dx, dy = x1-x0, y1-y0; L = dx*dx+dy*dy
            u = 0 if L == 0 else max(0, min(1, ((x-x0)*dx+(y-y0)*dy)/L))
            return (x-(x0+u*dx))**2+(y-(y0+u*dy))**2 <= h*h+0.01
        s.fill(f, v)
    def arc(s, cx, cy, r, a0, a1, t=2, v=1):
        def f(x, y):
            d = math.hypot(x-cx, y-cy)
            if not (r-t <= d <= r): return False
            a = math.degrees(math.atan2(-(y-cy), x-cx)) % 360
            return (a - a0) % 360 <= (a1 - a0) % 360
        s.fill(f, v)
    def slash(s, t=2):  # Durchstreichen: dunkle Kante, dann weisse Linie
        s.line(3, 3, 21, 21, t+1.6, 0); s.line(3, 3, 21, 21, t, 1)
    def svg(s, bg, fg, form=None):
        k = 24.0 / s.n
        def f(v): return ('%g' % (v*k))
        out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" shape-rendering="crispEdges"%s>' % (' data-form="%s"' % form if form else ''),
               '<rect width="24" height="24" fill="%s"/>' % bg]
        # Laufweiten je Zeile, dann senkrecht verschmelzen
        runs = {}
        for y in range(s.n):
            x = 0
            while x < s.n:
                if s.g[y][x]:
                    x0 = x
                    while x < s.n and s.g[y][x]: x += 1
                    runs.setdefault((x0, x-x0), []).append(y)
                else: x += 1
        rects = []
        for (x0, w), ys in runs.items():
            ys.sort(); a = ys[0]; p = a
            for y in ys[1:]+[None]:
                if y is not None and y == p+1: p = y; continue
                rects.append((a, x0, w, p-a+1))
                if y is not None: a = p = y
        for a, x0, w, h in sorted(rects):
            out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (f(x0), f(a), f(w), f(h), fg))
        out.append('</svg>')
        return "".join(out)

def speaker(c, x=1):
    c.R(x, 9, 3, 6); c.poly([(x+3,9),(x+9,4),(x+9,20),(x+3,15)])
def bell(c, x=0):
    c.poly([(x+12,2),(x+14,3),(x+16,7),(x+17,13),(x+20,17),(x+20,18),(x+4,18),(x+4,17),(x+7,13),(x+8,7),(x+10,3)])
    c.R(x+10, 19, 4, 2)
def person(c, cx=12, top=3):
    c.disc(cx, top+4, 4); c.poly([(cx-8,22),(cx-7,15),(cx-4,13),(cx+4,13),(cx+7,15),(cx+8,22)])
def note(c):
    c.R(8, 4, 12, 3); c.R(8, 4, 3, 13); c.R(17, 4, 3, 11)
    c.disc(7, 17, 3.2); c.disc(16, 15, 3.2)
def wifi(c):
    for r in (10, 7, 4): c.arc(12, 19, r+1, 45, 135, 2)
    c.R(11, 18, 2, 2)
def tri(c, x0, y0, x1, y1, x2, y2): c.poly([(x0,y0),(x1,y1),(x2,y2)])

def sagen48(c):
    # Kopf im Seitenprofil (48er-Raster, Koordinaten im 24er-Bild halbiert), offener Mund, drei Striche
    c.poly([(8,15),(13,8),(21,5),(29,6),(34,10),(35,17),(39,25),(35,27),(36,29),(33,29),(33,39),(35,40),(34,42),(30,44),(31,48),(10,48),(12,36),(8,26)])
    c.poly([(31,29),(41,28),(38,34),(41,36),(31,39)], 0)
    c.line(41, 25, 46, 21, 2); c.line(42, 31, 47.5, 31, 2); c.line(41, 37, 46, 41, 2)

I = {}
P = {}
def icon(name, bg=NAVY, fg=WHITE, form=None, n=24, ziel=None):
    def d(fn):
        c = C(n); fn(c); (P if ziel == "plugin" else I)[name] = (c, bg, fg, form); return fn
    return d

@icon("sagen", n=48)
def _(c):
    sagen48(c)
@icon("ja", YEL, NAVY, "haken")
def _(c): c.line(4, 12.5, 9, 18, 3.4); c.line(8.5, 18, 20, 5.5, 3.4)
@icon("nein", NAVY, YEL, "kreuz")
def _(c): c.line(5, 5, 19, 19, 3.4); c.line(19, 5, 5, 19, 3.4)
@icon("zurueck", NAVY, YEL, "pfeil")
def _(c): c.line(4, 12, 20, 12, 3.4); c.line(4.5, 12, 11, 5.5, 3.4); c.line(4.5, 12, 11, 18.5, 3.4)
@icon("hilfe", RED, WHITE, "glocke")
def _(c): bell(c); c.line(3,4,6,7,1.4); c.line(21,4,18,7,1.4)
@icon("ruf-aus")
def _(c): bell(c); c.slash()
@icon("ruf-gesehen")
def _(c):
    bell(c); c.R(14, 13, 10, 10, 0); c.line(15.5, 18.5, 18.2, 21.2, 2.2); c.line(18, 21.2, 23, 14.5, 2.2)
@icon("ruf-test")
def _(c):
    bell(c, -3); c.arc(13, 10, 6, 310, 50, 2.2); c.arc(13, 10, 10, 310, 50, 2.2)
@icon("aus")
def _(c): c.ring(12, 13, 9, 3); c.R(8, 2, 8, 9, 0); c.R(10.5 and 10, 2, 4, 11)
@icon("neu")
def _(c):
    c.arc(12, 12, 9, 40, 320, 3); tri(c, 16, 1, 22, 6, 14, 8)
    # Pfeilspitze am oberen Ende
@icon("sperren")
def _(c): c.ring(12, 9, 6, 3); c.R(6, 9, 3, 2); c.R(15, 9, 3, 2); c.R(4, 11, 16, 11); c.R(11, 14, 2, 4, 0)
@icon("sonne")
def _(c):
    c.disc(12, 12, 5)
    for a in range(0, 360, 45):
        r = math.radians(a); c.line(12+7.5*math.cos(r), 12+7.5*math.sin(r), 12+10.5*math.cos(r), 12+10.5*math.sin(r), 2)
@icon("mond")
def _(c): c.disc(11, 12, 9); c.disc(16, 8, 7.5, 0)
@icon("spaeter")
def _(c): c.ring(12, 12, 10, 2.6); c.R(11, 5, 2, 8); c.R(11, 11, 6, 2)
@icon("suche")
def _(c): c.ring(10, 10, 7.5, 3); c.line(15.5, 15.5, 21, 21, 3.6)
@icon("sehen")
def _(c):
    c.poly([(1,12),(6,6),(12,4),(18,6),(23,12),(18,18),(12,20),(6,18)]); c.disc(12, 12, 5, 0); c.disc(12, 12, 2.8)
@icon("schreiben")
def _(c):
    c.poly([(16,2),(22,8),(9,21),(3,21),(3,15)]); c.line(14, 4.5, 19.5, 10, 1.2, 0); c.R(1, 22, 14, 1)
@icon("system")
def _(c):
    for a in range(0, 360, 45):
        r = math.radians(a); c.line(12, 12, 12+9.6*math.cos(r), 12+9.6*math.sin(r), 4)
    c.disc(12, 12, 7.6); c.disc(12, 12, 3.4, 0)
@icon("wlan")
def _(c): wifi(c)
@icon("wlan-aus")
def _(c): wifi(c); c.slash()
@icon("bluetooth")
def _(c):
    c.line(12, 2, 12, 22, 3); c.line(12, 2, 18, 7.5, 2.6); c.line(18, 7.5, 6, 17, 2.6); c.line(6, 7, 18, 16.5, 2.6); c.line(18, 16.5, 12, 22, 2.6)
@icon("bluetooth-aus")
def _(c):
    c.line(12, 2, 12, 22, 3); c.line(12, 2, 18, 7.5, 2.6); c.line(18, 7.5, 6, 17, 2.6); c.line(6, 7, 18, 16.5, 2.6); c.line(18, 16.5, 12, 22, 2.6); c.slash()
@icon("internet")
def _(c):
    c.ring(12, 12, 10.5, 2); c.R(2, 11, 20, 2); c.R(11, 2, 2, 20)
    c.fill(lambda x,y: 0.78 <= (((x-12)/5.5)**2+((y-12)/10.5)**2) <= 1.0, 1)
    c.R(4, 6, 16, 2); c.R(4, 16, 16, 2)
@icon("mail")
def _(c): c.R(2, 5, 20, 15); c.line(3, 6.5, 12, 13.5, 2, 0); c.line(21, 6.5, 12, 13.5, 2, 0)
@icon("anruf")
def _(c):
    c.poly([(3,4),(8,3),(10,9),(8,11),(10,15),(13,17),(15,15),(21,16),(20,21),(15,21),(8,17),(4,11)])
    c.arc(13, 11, 6, 300, 60, 2); c.arc(13, 11, 10, 300, 60, 2)
@icon("messenger")
def _(c):
    c.R(2, 3, 20, 14); tri(c, 5, 16.5, 5, 22, 11, 16.5)
    for x in (6, 11, 16): c.R(x, 9, 2, 2, 0)
@icon("nachrichten")
def _(c):
    c.R(2, 3, 20, 18); c.R(4, 5, 7, 6, 0); c.R(13, 5, 7, 2, 0); c.R(13, 9, 7, 2, 0)
    for y in (13, 16, 19): c.R(4, y, 16, 1, 0)
@icon("text")
def _(c):
    c.R(4, 2, 16, 20); c.R(7, 6, 10, 2, 0); c.R(11, 6, 2, 12, 0)
@icon("diktat")
def _(c):
    c.R(8, 2, 8, 12); c.R(10, 4, 4, 1, 0); c.arc(12, 11, 8, 190, 350, 2); c.R(11, 19, 2, 3); c.R(7, 21, 10, 2)
    c.arc(12, 11, 8, 190, 350, 2)
@icon("fernsehen")
def _(c):
    c.R(2, 6, 20, 15); c.R(4, 8, 13, 11, 0); c.R(18, 10, 2, 2, 0); c.R(18, 14, 2, 2, 0)
    c.line(12, 6, 7, 1.5, 1.8); c.line(12, 6, 17, 1.5, 1.8)
@icon("fotos")
def _(c):
    c.R(2, 4, 20, 16); c.R(4, 6, 16, 12, 0); c.disc(8, 10, 2); c.poly([(4,18),(9,12),(12,15),(15,11),(20,17),(20,18)])
@icon("musik")
def _(c): note(c)
@icon("medien")
def _(c): c.ring(12, 12, 10.5, 2.6); tri(c, 9.5, 7, 9.5, 17, 17.5, 12)
@icon("pause")
def _(c): c.R(5, 4, 5, 16); c.R(14, 4, 5, 16)
@icon("ton")
def _(c):
    speaker(c, 0)
    for r in (5.5, 9.5): c.arc(9, 12, r+3, 322, 38, 2.4)
@icon("lauter")
def _(c): speaker(c, 0); c.R(14, 11, 9, 2); c.R(17.5 and 17, 7, 2, 10)
@icon("leiser")
def _(c): speaker(c, 0); c.R(14, 11, 9, 2)
@icon("stumm")
def _(c): speaker(c, 0); c.line(15, 8.5, 22, 15.5, 2.4); c.line(22, 8.5, 15, 15.5, 2.4)
@icon("dateien")
def _(c): c.poly([(2,5),(9,5),(11,8),(22,8),(22,21),(2,21)])
@icon("funk")
def _(c):
    c.disc(12, 10, 2.6); c.line(12, 12, 12, 22, 2.4); c.R(8, 21, 8, 2)
    for r in (6, 10): c.arc(12, 10, r, 120, 240, 2.2); c.arc(12, 10, r, 300, 60, 2.2)
@icon("geraet")
def _(c): c.R(3, 4, 18, 12); c.R(5, 6, 14, 8, 0); c.R(1, 17, 22, 3)
@icon("einfach")
def _(c): c.disc(12, 12, 7.5)
@icon("zwei")
def _(c): c.disc(6, 12, 4.8); c.disc(18, 12, 4.8)
@icon("mehr")
def _(c): c.R(10, 3, 4, 18); c.R(3, 10, 18, 4)
@icon("andere")
def _(c):
    for x in (4, 11, 18): c.R(x - 0, 10, 4, 4)
@icon("anpassen")
def _(c):
    for y, x in ((5, 15), (11, 7), (17, 13)): c.R(2, y, 20, 2); c.R(x - 2, y - 2, 5, 6); c.R(x-1, y-1, 3, 4, 0) if False else None
@icon("helfen")
def _(c):
    c.disc(8, 6, 3.6); c.disc(16, 6, 3.6); c.poly([(4.4,7.5),(19.6,7.5),(12,15)])
    c.poly([(1,17),(6,15),(11,18),(17,18),(23,15),(23,17),(16,22),(7,22),(1,20)])

@icon("durst", ziel="plugin")
def _(c):
    c.poly([(4,2),(20,2),(17,22),(7,22)]); c.poly([(6.2,4),(17.8,4),(16.8,11),(7.2,11)], 0)
@icon("hunger", ziel="plugin")
def _(c):
    c.ring(12, 12, 6.5, 2); c.disc(12, 12, 2.2)
    for x in (0, 2, 4): c.R(x, 2, 1, 7)
    c.R(0, 8, 5, 2); c.R(1, 10, 3, 12)
    c.R(21, 2, 2, 20)
@icon("toilette", ziel="plugin")
def _(c):
    c.R(6, 2, 12, 4); c.R(4, 7, 16, 2); c.poly([(3,10),(21,10),(19,15),(15,17),(15,22),(9,22),(9,17),(5,15)])
@icon("schmerz", RED, WHITE, ziel="plugin")
def _(c): c.poly([(14,1),(5,13),(11,13),(9,23),(19,10),(13,10)])
@icon("pause", ziel="plugin")
def _(c): c.R(5, 4, 5, 16); c.R(14, 4, 5, 16)
@icon("kalt", ziel="plugin")
def _(c):
    for a in (90, 150, 210):
        r = math.radians(a); c.line(12+10.5*math.cos(r), 12-10.5*math.sin(r), 12-10.5*math.cos(r), 12+10.5*math.sin(r), 2.2)
    for a in range(0, 360, 60):
        r = math.radians(a+90)
        for d in (-45, 45):
            q = math.radians(a+90+180+d); bx, by = 12+7.5*math.cos(r), 12-7.5*math.sin(r)
            c.line(bx, by, bx+3.2*math.cos(q), by-3.2*math.sin(q), 1.8)
@icon("warm", ziel="plugin")
def _(c):
    c.poly([(12,1),(16,7),(19,12),(19,17),(16,22),(8,22),(5,17),(5,12),(8,8),(9,12),(10,6)]); c.disc(12, 18, 3.2, 0)
@icon("haus", ziel="plugin")
def _(c): c.poly([(12,2),(23,11),(1,11)]); c.R(4, 11, 16, 11); c.R(10, 15, 4, 7, 0)
@icon("grund", ziel="plugin")
def _(c): c.disc(8, 8, 4.8); c.disc(16, 8, 4.8); c.poly([(3.5,10),(20.5,10),(12,21.5)])
def person_n(c, n):
    c.disc(12, 6, 4); c.poly([(4,18),(5,12),(8,10.5),(16,10.5),(19,12),(20,18)])
    w = n*3 + (n-1)*2; x = 12 - w//2
    for i in range(n): c.R(x + i*5, 20, 3, 3)
@icon("kontakt-1")
def _(c): person_n(c, 1)
@icon("kontakt-2")
def _(c): person_n(c, 2)
@icon("kontakt-3", RED, WHITE)
def _(c): person_n(c, 3)

# Ziffernpunkte unter den Kontakten
for n in (1, 2, 3):
    pass

def schreiben(ziel, plugin=None):
    for d, ordner in ((I, ziel), (P, plugin)):
      if not ordner: continue
      for name, (c, bg, fg, form) in d.items():
        ziel = ordner
        open(os.path.join(ziel, name + ".svg"), "w", encoding="utf-8").write(c.svg(bg, fg, form))

if __name__ == "__main__":
    schreiben(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
