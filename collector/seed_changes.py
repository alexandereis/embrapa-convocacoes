#!/usr/bin/env python3
"""Backfill (uma vez) do diario de mudancas com DATA E HORA reais.

Importa o historico completo de diffs ja mantido pela fonte publica
(data/complete_diff_history.json), reconstrói as transicoes de status
cronologicamente e grava no site/data/timeline_state.json:
  - changes   : ultimos N dias de eventos (ts, de, para, novo, ...);
  - changed_at: por pessoa, o instante da ULTIMA alteracao (coluna "Alterado em").

A chave da pessoa e NORMALIZADA (sem acento) para casar com a fonte oficial,
que vem sem acento. O baseline 'people' e ZERADO de proposito: a proxima coleta
re-cria o baseline limpo (sem sobrescrever as horas reais do backfill).

A partir daqui o coletor (timeline.py) continua sozinho, so com os NOVOS.
Necessario apenas UMA vez.

Uso (na pasta do projeto):
    python collector/seed_changes.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from timeline import norm_key  # noqa: E402

SRC = ("https://raw.githubusercontent.com/arjonilla87/embrapa-site/"
       "main/data/complete_diff_history.json")
STATE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "site", "data", "timeline_state.json")
KEEP_DAYS = 90


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "embrapa-collector"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")


def _parse_dt(s):
    return datetime.strptime(s.strip(), "%d/%m/%Y - %H:%M:%S")


def main():
    hist = json.loads(_get(SRC))
    eventos = []
    for r in hist:
        try:
            eventos.append((_parse_dt(r.get("DATA / HORA", "")), r))
        except Exception:  # noqa: BLE001
            continue
    eventos.sort(key=lambda x: x[0])

    running = {}
    changes = []
    changed_at = {}
    corte = datetime.now() - timedelta(days=KEEP_DAYS)

    for dt, r in eventos:
        key = norm_key(r.get("OPÇÃO", ""), r.get("COLOCAÇÃO", ""), r.get("NOME", ""))
        status = (r.get("STATUS") or "").strip()
        novo = (r.get("EVENTO") or "").strip().upper() == "NOVO"
        prev = running.get(key)
        de = "" if (novo or prev is None) else prev
        ts = dt.strftime("%Y-%m-%d %H:%M")
        if dt >= corte:
            changes.append({"ts": ts, "date": dt.strftime("%Y-%m-%d"),
                            "nome": (r.get("NOME") or "").strip(),
                            "opcao": (r.get("OPÇÃO") or "").strip(),
                            "cargo": (r.get("CARGO") or "").strip(),
                            "unidade": (r.get("UNIDADE") or "").strip(),
                            "de": de, "para": status, "novo": novo})
        changed_at[key] = ts
        running[key] = status

    state = {}
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:  # noqa: BLE001
            state = {}
    state["people"] = {}   # zera: proxima coleta re-cria baseline limpo
    state.setdefault("events", {"convocacoes": [], "contratacoes": []})
    state["changes"] = changes
    state["changed_at"] = changed_at
    if eventos:
        state["last_change"] = eventos[-1][0].strftime("%Y-%m-%d")

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))

    print(f"backfill gravado: {STATE}")
    print(f"  eventos no historico: {len(eventos)}")
    print(f"  changes (ultimos {KEEP_DAYS}d): {len(changes)}")
    print(f"  pessoas com 'alterado em': {len(changed_at)}")


if __name__ == "__main__":
    main()
