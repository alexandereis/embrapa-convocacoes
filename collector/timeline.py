"""Linha do tempo PROPRIA do coletor (sem datas vindas do oficial).

  - SEED (uma vez): curva historica importada dos dados publicos existentes ->
    site/data/timeline_seed.json (versionado). Tambem traz 'extras'.
  - DIFF DE CONJUNTO (a cada coleta): guardamos {pessoa: status} em
    site/data/timeline_state.json. QUALQUER mudanca de status (entrou na tabela
    ou mudou de situacao) vira um evento com DATA E HORA. Tambem guardamos, por
    pessoa, o instante da ultima alteracao (para a coluna "Alterado em").

Na 1a coleta nao geramos nada (baseline) -> sem pico falso.
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
_KEEP_DAYS = 90        # quantos dias de diario manter no estado
_RETURN_DAYS = 30      # quantos dias de diario expor para o site


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


def _cutoff(days):
    return (datetime.now(_BR).date() - timedelta(days=days)).isoformat()


def update_and_build(pessoas):
    now = datetime.now(_BR)
    day = now.date().isoformat()
    ts = now.strftime("%Y-%m-%d %H:%M")

    seed = _read(SEED_PATH, {}) or {}
    seed_conv = list(seed.get("convocacoes", []))
    seed_contr = list(seed.get("contratacoes", []))
    extras = dict(seed.get("extras", {}) or {})

    state = _read(STATE_PATH, {}) or {}
    last_people = state.get("people", {}) if isinstance(state, dict) else {}
    ev = state.get("events", {}) if isinstance(state, dict) else {}
    fwd_conv = list(ev.get("convocacoes", []))
    fwd_contr = list(ev.get("contratacoes", []))
    changes = list(state.get("changes", []))
    changed_at = dict(state.get("changed_at", {}))
    # migra entradas do schema antigo (tipo/date) para o novo (para/de/ts)
    for c in changes:
        if "para" not in c:
            c["para"] = c.get("tipo", "")
            c.setdefault("de", "")
            c.setdefault("ts", c.get("date", ""))
            c.setdefault("novo", c.get("tipo") == "Convocado")
    last_change = state.get("last_change")

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
            mudou = is_new or (prev != status)
            # eventos para os GRAFICOS (convocacao quando entra; contratacao
            # quando vira Contratado)
            if is_new:
                fwd_conv.append(_event(day, cargo))
            if prev != _CONTRATADO and status == _CONTRATADO:
                fwd_contr.append(_event(day, cargo))
            # diario: QUALQUER mudanca de status, com data+hora e a transicao
            if mudou:
                changes.append({"ts": ts, "date": day, "nome": p.get("nome", ""),
                                "opcao": p.get("opcao", ""), "cargo": cargo,
                                "unidade": p.get("unidade", ""),
                                "de": prev or "", "para": status, "novo": is_new})
                changed_at[k] = ts
        if current != last_people:
            last_change = day

    cut = _cutoff(_KEEP_DAYS)
    changes = [c for c in changes if c.get("date", "") >= cut]

    new_state = {"people": current,
                 "events": {"convocacoes": fwd_conv, "contratacoes": fwd_contr},
                 "changes": changes, "changed_at": changed_at,
                 "last_change": last_change}
    try:
        _write(STATE_PATH, new_state)
    except Exception:
        pass

    rcut = _cutoff(_RETURN_DAYS)
    recent = [c for c in changes if c.get("date", "") >= rcut]
    recent.sort(key=lambda c: c.get("ts", ""), reverse=True)
    extras["changes"] = recent[:80]   # Visao Geral: 80 mudancas mais recentes
    extras["changed_at"] = changed_at
    extras["fonte_ultima_mudanca"] = last_change
    return seed_conv + fwd_conv, seed_contr + fwd_contr, extras
