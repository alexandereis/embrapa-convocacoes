#!/usr/bin/env python3
"""Backfill (uma vez) do diario de mudancas com DATA E HORA reais.

Importa o historico completo de diffs ja mantido pela fonte publica
(data/complete_diff_history.json), reconstrói as transicoes de status
cronologicamente e grava no site/data/timeline_state.json:
  - changes   : ultimos N dias de eventos (ts, de, para, novo, ...);
  - changed_at: por pessoa, o instante da ULTIMA alteracao (coluna "Alterado em").

A partir daqui o coletor (timeline.py) continua sozinho, so com os NOVOS.
Necessario apenas UMA vez.

Uso (na pasta do projeto):
    python collector/seed_changes.py
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta

SRC = ("https://raw.githubusercontent.com/arjonilla87/embrapa-site/"
       "main/data/complete_diff_history.json")
STATE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "site", "data", "timeline_state.json")
KEEP_DAYS = 90  # quantos dias de detalhe manter em 'changes' (igual timeline.py)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "embrapa-collector"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")


def _parse_dt(s):
    # "11/06/2026 - 13:44:35"
    return datetime.strptime(s.strip(), "%d/%m/%Y - %H:%M:%S")


def main():
    hist = json.loads(_get(SRC))
    # ordena do mais antigo para o mais novo (o arquivo vem do mais novo p/ velho)
    eventos = []
    for r in hist:
        try:
            dt = _parse_dt(r.get("DATA / HORA", ""))
        except Exception:  # noqa: BLE001
            continue
        eventos.append((dt, r))
    eventos.sort(key=lambda x: x[0])

    running = {}      # key -> ultimo status conhecido (p/ reconstruir o "de")
    changes = []
    changed_at = {}
    corte = datetime.now() - timedelta(days=KEEP_DAYS)

    for dt, r in eventos:
        opcao = (r.get("OPÇÃO") or "").strip()
        col = (r.get("COLOCAÇÃO") or "").strip()
        nome = (r.get("NOME") or "").strip()
        key = f"{opcao}|{col}|{nome}"
        status = (r.get("STATUS") or "").strip()
        evento = (r.get("EVENTO") or "").strip().upper()
        novo = (evento == "NOVO")
        prev = running.get(key)
        de = "" if (novo or prev is None) else prev
        ts = dt.strftime("%Y-%m-%d %H:%M")
        date = dt.strftime("%Y-%m-%d")
        if dt >= corte:   # mantem detalhe so dos ultimos KEEP_DAYS dias
            changes.append({"ts": ts, "date": date, "nome": nome, "opcao": opcao,
                            "cargo": (r.get("CARGO") or "").strip(),
                            "unidade": (r.get("UNIDADE") or "").strip(),
                            "de": de, "para": status, "novo": novo})
        changed_at[key] = ts   # sempre o mais recente (todos os periodos)
        running[key] = status

    # mescla no estado atual (preserva o baseline 'people' e os 'events')
    state = {}
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:  # noqa: BLE001
            state = {}
    state.setdefault("people", {})
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
