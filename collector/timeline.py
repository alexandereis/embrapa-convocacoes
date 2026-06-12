"""Linha do tempo PROPRIA do coletor (sem datas vindas do oficial).

  - SEED (uma vez): curva historica -> site/data/timeline_seed.json.
  - DIFF DE CONJUNTO (a cada coleta): guardamos {pessoa: status} em
    site/data/timeline_state.json. QUALQUER mudanca de status vira um evento com
    DATA E HORA. Tambem guardamos, por pessoa, o instante da ultima alteracao.

A chave da pessoa e NORMALIZADA (sem acento, maiusculas) para casar entre
fontes diferentes (a oficial vem sem acento; o backfill, com).

Na 1a coleta nao geramos nada (baseline). Defensivo: falha aqui NAO derruba a coleta.
"""
import json
import os
import unicodedata
from datetime import datetime, timedelta, timezone

_SITE_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site", "data")
SEED_PATH = os.path.join(_SITE_DATA, "timeline_seed.json")
STATE_PATH = os.path.join(_SITE_DATA, "timeline_state.json")

_BR = timezone(timedelta(hours=-3))   # Brasilia = UTC-3 (sem horario de verao)
_CONTRATADO = "Contratado"
_KEEP_DAYS = 90        # quantos dias de diario manter no estado
_RETURN_DAYS = 30      # quantos dias de diario expor para o site


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def norm_key(opcao, colocacao, nome):
    return "{}|{}|{}".format(_norm(opcao), _norm(colocacao), _norm(nome))


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
    return norm_key(p.get("opcao", ""), p.get("colocacao", ""), p.get("nome", ""))


# Ordem de "avanco" do status (maior = mais definitivo). Desempata quando a
# fonte traz a MESMA pessoa (mesma chave) em duas linhas com status diferentes
# (ex.: remanejamento -> Reconvocado numa unidade e Desistente noutra). Sem
# isso, a ordem das linhas faz o status "alternar" entre coletas e gera eventos
# fantasmas datados de hoje.
def _rank(status):
    """Rank de 'avanco' do status (maior = mais definitivo). Por palavra-chave
    para tolerar variantes ('Aceitou sub judice', 'Convocado subjudice', ...)."""
    s = (status or "").lower()
    if "contratado" in s:
        return 6
    if "aceitou" in s:               # inclui 'Aceitou sub judice'
        return 5
    if "reconvocad" in s:
        return 4
    if "convocado" in s:             # inclui 'Convocado subjudice'
        return 3
    if "desisten" in s or "desclassific" in s or "manifest" in s:
        return 0
    return 1


def _dedupe(pessoas):
    """Uma linha por chave; em conflito mantem o status mais avancado.
    Deterministico: independe da ordem das linhas da fonte."""
    best = {}
    for p in pessoas:
        k = _key(p)
        atual = best.get(k)
        if atual is None or _rank(p.get("status", "")) > _rank(atual.get("status", "")):
            best[k] = p
    return list(best.values())


def _cutoff(days):
    return (datetime.now(_BR).date() - timedelta(days=days)).isoformat()


def update_and_build(pessoas):
    now = datetime.now(_BR)
    day = now.date().isoformat()
    ts = now.strftime("%Y-%m-%d %H:%M")

    # Colapsa linhas duplicadas (mesma pessoa em 2 lotacoes) ANTES de tudo, de
    # forma deterministica -> sem flip-flop fantasma entre coletas.
    pessoas = _dedupe(pessoas)

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
            if is_new:
                fwd_conv.append(_event(day, cargo))
            if prev != _CONTRATADO and status == _CONTRATADO:
                fwd_contr.append(_event(day, cargo))
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
    extras["changes"] = recent[:80]
    extras["changed_at"] = changed_at
    extras["fonte_ultima_mudanca"] = last_change

    # Contagens diarias REAIS (datas verdadeiras do diario, SEM o cap de 80):
    # novas convocacoes e contratacoes por dia. Alimentam o grafico de
    # velocidade e a media/dia no transform -> grafico e media batem entre si.
    novos_dia, contr_dia = {}, {}
    for c in changes:
        dt = c.get("date", "")
        if not dt:
            continue
        if c.get("novo"):
            novos_dia[dt] = novos_dia.get(dt, 0) + 1
        if c.get("para") == _CONTRATADO:
            contr_dia[dt] = contr_dia.get(dt, 0) + 1
    extras["novos_por_dia"] = novos_dia
    extras["contratados_por_dia"] = contr_dia
    return seed_conv + fwd_conv, seed_contr + fwd_contr, extras
