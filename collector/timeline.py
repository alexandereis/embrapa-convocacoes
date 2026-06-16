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
_REMOVIDO = "Removido"   # status sintetico: pessoa saiu da tabela oficial
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
    """Uma linha por chave. Quando a fonte traz a MESMA pessoa em linhas com
    status conflitantes (ex.: remanejamento), resolve de forma deterministica:
      1) se houver status TERMINAL (Desistente/Desclassificado/Nao se
         manifestou -> rank 0), ele PREVALECE: nesta fonte a linha ativa que
         sobra costuma ser a obsoleta, e o terminal e o estado real atual;
      2) senao, mantem o status mais avancado (_rank).
    Independe da ordem das linhas -> sem flip-flop entre coletas."""
    by_key = {}
    for p in pessoas:
        by_key.setdefault(_key(p), []).append(p)
    out = []
    for rows in by_key.values():
        if len(rows) == 1:
            out.append(rows[0])
            continue
        terminais = [r for r in rows if _rank(r.get("status", "")) == 0]
        if terminais:
            out.append(terminais[0])
        else:
            out.append(max(rows, key=lambda r: _rank(r.get("status", ""))))
    return out


def dedupe_pessoas(pessoas):
    """Publico: colapsa linhas duplicadas (mesma pessoa no MESMO slot
    opcao+colocacao, ex.: 2 lotacoes) num registro so. Usado pelo extrator para
    a contagem nao inflar; mantem o status real (terminal prevalece)."""
    return _dedupe(pessoas)


def _dedup_changes(changes):
    """Remove eventos duplicados (mesma pessoa + mesma transicao + mesmo dia),
    mantendo o MAIS ANTIGO. Evita repeticoes quando uma re-coleta redetecta
    transicoes ja registradas (ex.: baseline que regrediu)."""
    seen, out = set(), []
    for c in sorted(changes, key=lambda c: c.get("ts", "")):   # mais antigo 1o
        k = (c.get("opcao", ""), c.get("nome", ""), c.get("date", ""),
             c.get("de", ""), c.get("para", ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


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
    cargo_por_op = {}
    for p in pessoas:
        current[_key(p)] = p.get("status", "")
        cargo_por_op.setdefault(p.get("opcao", ""), p.get("cargo", ""))

    if not first_run:
        # ENTROU / MUDOU: percorre quem esta na fonte agora.
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
        # SAIU: estava no baseline e sumiu da fonte agora -> registra a exclusao.
        # A chave e "opcao|colocacao|nome" normalizado; extraimos os dados dela.
        for k, prev in last_people.items():
            if k in current or prev == _REMOVIDO:
                continue
            partes = k.split("|")
            op = partes[0] if partes else ""
            nome = partes[2] if len(partes) > 2 else ""
            changes.append({"ts": ts, "date": day, "nome": nome,
                            "opcao": op, "cargo": cargo_por_op.get(op, ""),
                            "unidade": "", "de": prev or "", "para": _REMOVIDO,
                            "novo": False})
            changed_at[k] = ts
        if current != last_people:
            last_change = day

    # alterado_em so interessa a quem esta na lista atual (limita o crescimento).
    changed_at = {k: v for k, v in changed_at.items() if k in current}

    cut = _cutoff(_KEEP_DAYS)
    changes = [c for c in changes if c.get("date", "") >= cut]
    changes = _dedup_changes(changes)   # remove re-deteccoes repetidas

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
