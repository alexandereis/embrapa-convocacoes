#!/usr/bin/env python3
"""Semeia (uma vez) a curva historica da linha do tempo.

Importa os eventos datados de convocacao/contratacao da serie publica ja
existente e grava em site/data/timeline_seed.json (versionado no repo). Isso
preserva a curva dez->jun. A partir dai, o coletor acumula a timeline sozinho
(ver timeline.py), entao o seed e necessario apenas UMA vez.

Uso (na pasta do projeto):
    python collector/seed_history.py
"""
import csv
import io
import json
import os
import urllib.request

BASE = "https://raw.githubusercontent.com/arjonilla87/embrapa-site/main/data/stats"
CONV = f"{BASE}/convocados_semanal_detalhes.csv"
CONTR = f"{BASE}/contratados_mensal_detalhes.csv"
STATS = f"{BASE}/general_stats.json"
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                   "site", "data", "timeline_seed.json")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "embrapa-collector"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig")


def _events(url):
    rows = list(csv.reader(io.StringIO(_get(url))))
    if not rows:
        return []
    header = rows[0]
    out = []
    for r in rows[1:]:
        rec = dict(zip(header, r))
        d = (rec.get("DATE") or "").strip()
        if d:
            out.append({"date": d[:10], "cargo": (rec.get("CARGO") or "").strip()})
    return out


def main():
    conv = _events(CONV)
    contr = _events(CONTR)
    # extras: metricas que o oficial nao expoe (ex.: tempo medio
    # convocacao->aceite, dias uteis decorridos). Semeadas uma vez como base.
    extras = {}
    try:
        extras = json.loads(_get(STATS))
    except Exception as e:  # noqa: BLE001
        print(f"  (aviso: general_stats.json indisponivel: {e})")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"convocacoes": conv, "contratacoes": contr, "extras": extras},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"seed gravado: {OUT}")
    print(f"  convocacoes historicas: {len(conv)}")
    print(f"  contratacoes historicas: {len(contr)}")
    print(f"  extras: {list(extras.keys()) if extras else '(vazio)'}")


if __name__ == "__main__":
    main()
