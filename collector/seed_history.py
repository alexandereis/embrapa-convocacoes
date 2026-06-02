#!/usr/bin/env python3
"""Semeia (uma vez) a curva historica da linha do tempo.

Importa a serie historica COMPLETA que a fonte publica ja consolida em
data/stats/cumulative_stats.json (convocados por semana ISO + contratados por
mes) e o general_stats.json (extras: tempo medio aceite, etc.). Expande os
agregados em eventos datados, que o transform.py re-agrega em semanas/meses e
velocidade. Os totais sao depois reconciliados com os numeros OFICIAIS no
transform (escala), entao o formato/ritmo vem daqui e o total final e exato.

Necessario apenas UMA vez; depois o coletor acumula sozinho (timeline.py).

Uso (na pasta do projeto):
    python collector/seed_history.py
"""
import json
import os
import urllib.request
from datetime import date, timedelta

BASE = "https://raw.githubusercontent.com/arjonilla87/embrapa-site/main/data/stats"
CUM = f"{BASE}/cumulative_stats.json"
STATS = f"{BASE}/general_stats.json"
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                   "site", "data", "timeline_seed.json")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "embrapa-collector"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig")


def _week_monday(label):
    # "2026-W04" -> date da segunda-feira daquela semana ISO
    y, w = label.upper().split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def _month_first(label):
    # aceita "2026-01" ou "10/25" -> primeiro dia do mes
    label = label.strip()
    if "/" in label:
        m, y = label.split("/")
        return date(2000 + int(y), int(m), 1)
    y, m = label.split("-")
    return date(int(y), int(m), 1)


def _spread(start, count, span):
    # distribui `count` eventos pelos dias UTEIS de [start, start+span)
    if count <= 0:
        return []
    days = [start + timedelta(days=i) for i in range(span)]
    wd = [d for d in days if d.weekday() < 5] or days
    return [wd[i % len(wd)] for i in range(count)]


def main():
    cum = json.loads(_get(CUM))
    conv = []
    for w in cum.get("weekly", {}).get("convocado", []):
        try:
            mon = _week_monday(w["label"])
        except Exception:  # noqa: BLE001
            continue
        for d in _spread(mon, int(w.get("value", 0)), 7):
            conv.append({"date": d.isoformat(), "cargo": ""})

    contr = []
    for m in cum.get("monthly_contratados", {}).get("contratados", []):
        try:
            first = _month_first(m["label"])
        except Exception:  # noqa: BLE001
            continue
        for d in _spread(first, int(m.get("value", 0)), 28):
            contr.append({"date": d.isoformat(), "cargo": ""})

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
