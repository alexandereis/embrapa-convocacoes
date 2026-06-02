"""Linha do tempo PROPRIA do coletor (sem datas vindas do oficial).

Estrategia robusta (sem efeito-cascata):
  - SEED (uma vez): curva historica importada dos dados publicos existentes ->
    site/data/timeline_seed.json (versionado). Tambem traz 'extras' (ex.: tempo
    medio convocacao->aceite) que o oficial nao expoe.
  - DIFF DE CONJUNTO (a cada coleta): guardamos o conjunto de pessoas e status
    em site/data/timeline_state.json. So quem e novo ou mudou de status gera um
    evento datado de HOJE. Na 1a coleta nao geramos nada (curva = seed) -> sem
    pico falso em "hoje".

Defensivo: falha aqui NAO derruba a coleta.
"""
import json
import os
from datetime import datetime, timedelta, timezone

_SITE_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site", "data")
SEED_PATH = os.path.join(_SITE_DATA, "timeline_seed.json")
STATE_PATH = os.path.join(_SITE_DATA, "timeline_state.json")

_BR = timezone(timedelta(hours=-3))   # Brasilia = UTC-3 (sem horario de verao)
_CONTRATADO = "Contratado"


def hoje_br():
    return datetime.now(_BR).date().isoformat()


def _event(day, cargo):
    return {"date": day, "cargo": cargo or ""}


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _key(p):
    return "{}|{}|{}".format(p.get("opcao", ""), p.get("colocacao", ""),
                             p.get("nome", ""))


def update_and_build(pessoas):
    day = hoje_br()

    seed = _read(SEED_PATH, {}) or {}
    seed_conv = list(seed.get("convocacoes", []))
    seed_contr = list(seed.get("contratacoes", []))
    extras = seed.get("extras", {}) or {}

    state = _read(STATE_PATH, {}) or {}
    last_people = state.get("people", {}) if isinstance(state, dict) else {}
    ev = state.get("events", {}) if isinstance(state, dict) else {}
    fwd_conv = list(ev.get("convocacoes", []))
    fwd_contr = list(ev.get("contratacoes", []))

    first_run = not last_people
    current = {}
    for p in pessoas:
        current[_key(p)] = p.get("status", "")

    if not first_run:
        for p in pessoas:
            k = _key(p)
            status = p.get("status", "")
            cargo = p.get("cargo", "")
            prev = last_people.get(k)
            is_new = prev is None
            became = (prev != _CONTRATADO and status == _CONTRATADO)
            if is_new:
                fwd_conv.append(_event(day, cargo))
            if became or (is_new and status == _CONTRATADO):
                fwd_contr.append(_event(day, cargo))

    new_events = {"convocacoes": fwd_conv, "contratacoes": fwd_contr}
    try:
        _write(STATE_PATH, {"people": current, "events": new_events})
    except Exception:
        pass

    return seed_conv + fwd_conv, seed_contr + fwd_contr, extras
