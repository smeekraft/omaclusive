#!/bin/bash
# Sagt dem lokalen Omaclusive auf Port 8795, einen Film zu beenden. Startet nichts.
curl -s http://127.0.0.1:8795/api/back >/dev/null 2>&1 || true
