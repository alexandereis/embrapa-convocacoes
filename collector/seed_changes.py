#!/usr/bin/env python3
"""Backfill (uma vez) do diario de mudancas com DATA E HORA reais.

Importa o historico publico de diffs (mantido pela comunidade) e grava em
site/data/timeline_state.json:
  - changes   : eventos recentes (ts, de, para, novo, ...);
  - changed_at: por pessoa, o instante da ULTIMA alteracao (coluna "Alterado em").

SALVAGUARDA ANTI-FANTASMA: so importa eventos de pessoas que EXISTEM na fonte
oficial AGORA (intersecao por chave normalizada com site/data/data.json). Assim
nenhum registro do historico do concorrente que nao esteja no oficial entra no
painel (foi o que gerou o "fantasma" antes).

A chave da pessoa e NORMALIZADA (sem acento, maiusculas) para casar com a fonte
oficial, que vem sem acento. O baseline 'people' e ZERADO de proposito: a
proxima coleta re-cria o baseline limpo (sem sobrescrever as horas do backfill).

ORDEM DE USO (na pasta do projeto), necessario apenas UMA vez:
    python collector/collect.py        # gera data.json oficial + baseline limpo
    python collector/seed_changes.py   # injeta as datas reais (so quem e oficial)
    python collector/collect.py        # regenera data.json com as datas
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
_BASE = os.path.dirname(os.path.dirname(__file__))
DATA = os.path.join(_BASE, "site", "data", "data.json")
STATE = os.path.join(_BASE, "site", "data", "timeline_state.json")
KEEP_DAYS = 90


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "embrapa-collector"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")


def _parse_dt(s):
    return datetime.strptime(s.strip(), "%d/%m/%Y - %H:%M:%S")


def _chaves_oficiais():
    """Chaves normalizadas das pessoas que existem HOJE na fonte oficial."""
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    keys = set()
    for p in data.get("pessoas", []):
        keys.add(norm_key(p.get("opcao", ""), p.get("nome", "")))
    return keys


def main():
    if not os.path.exists(DATA):
        print("ERRO: site/data/data.json nao existe. Rode collect.py primeiro.")
        sys.exit(1)

    oficiais = _chaves_oficiais()
    print(f"pessoas na fonte oficial: {len(oficiais)}")

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
    descartados = 0

    for dt, r in eventos:
        key = norm_key(r.get("OPÇÃO", ""), r.get("NOME", ""))
        # SALVAGUARDA: ignora quem nao esta na fonte oficial (anti-fantasma).
        if key not in oficiais:
            descartados += 1
            continue
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
    print(f"  eventos no historico:                 {len(eventos)}")
    print(f"  descartados (fora da fonte oficial):  {descartados}")
    print(f"  changes (ultimos {KEEP_DAYS}d):              {len(changes)}")
    print(f"  pessoas com 'alterado em':            {len(changed_at)}")


if __name__ == "__main__":
    main()
