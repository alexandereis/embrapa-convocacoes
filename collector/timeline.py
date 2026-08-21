"""Linha do tempo PROPRIA do coletor (sem datas vindas do oficial).

  - SEED (uma vez): curva historica -> site/data/timeline_seed.json.
  - DIFF DE CONJUNTO (a cada coleta): guardamos {pessoa: status} em
    site/data/timeline_state.json. QUALQUER mudanca de status vira um evento com
    DATA E HORA. Tambem guardamos, por pessoa, o instante da ultima alteracao.

A chave e OPCAO|COLOCACAO|NOME, NORMALIZADA (sem acento, maiusculas): uma
convocacao e uma VAGA NA FILA, nao uma pessoa. A mesma pessoa pode ser chamada
duas vezes na mesma opcao -- primeiro pela cota, depois pela ampla concorrencia,
em datas diferentes. Confirmado no historico: a linha "23o AC" de RODRIGO
MARTINS CANUTO ROCHA (opcao 40000127) nasceu em 19/06/2026, meses depois da
"1o PCD" dele. Sao duas chamadas, e as duas contam. O que _dedupe() colapsa e
so a MESMA vaga repetida em duas lotacoes.

CONFIANCA NA FONTE. O painel oficial (Looker) as vezes devolve uma GERACAO
ANTIGA do conjunto, servida de cache. Aconteceu de verdade: em 2026-08-08 07:05
UTC a coleta recebeu um snapshot IDENTICO ao de 2026-08-07 20:31 (1119 linhas)
depois de ja ter coletado a geracao nova (1123 linhas) -- 4 pessoas
"desconvocadas" e 29 "descontratadas" que voltaram horas depois. Como toda
diferenca virava evento datado, o painel enchia de mudancas contraditorias da
mesma pessoa. Por isso NAO acreditamos de primeira quando a fonte anda para
tras (_e_suspeita): em lote, a coleta inteira e descartada; isolada, espera
confirmacao. Ha escape em ambos os casos para correcao legitima nao travar o
painel.

Na 1a coleta nao geramos nada (baseline). Defensivo: falha aqui NAO derruba a
coleta -- exceto FonteDesatualizada, que PRECISA abortar a coleta inteira.
"""
import hashlib
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
_RETURN_DAYS = 7       # quantos dias de diario expor para o site (painel enxuto)

# --- limiares da guarda contra geracao antiga da fonte --------------------
# 2+ pessoas voltando ao status anterior NA MESMA coleta nao e coincidencia:
# e a fonte inteira desatualizada. Foi o caso ARIANE+CLEILTON (18-19/08), que
# oscilaram juntas mais de vinte vezes.
_LIMIAR_LOTE = 2
# Regressao isolada: quantas coletas seguidas precisam concordar para virar fato.
_CONFIRMACOES = 2
# Escape: se a fonte insistir no MESMO lote tantas coletas seguidas, e correcao
# real (nao cache) e passamos a aceitar -- senao o painel congelaria para sempre.
_CONFIRMACOES_LOTE = 3


class FonteDesatualizada(Exception):
    """A fonte devolveu uma geracao ANTIGA do conjunto (cache velho).

    Quem chama deve DESCARTAR a coleta inteira: nao regravar data.json nem
    avancar o estado. A proxima coleta reavalia.
    """


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def norm_nome(nome):
    """Nome normalizado -- identifica a PESSOA entre opcoes diferentes."""
    return _norm(nome)


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


def _e_contratado(status):
    # por palavra-chave -> inclui "Contratado subjudice" (contratacao especial,
    # sob decisao judicial, mas contratacao).
    return "contratado" in (status or "").lower()


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


# Baldes do resumo por opcao. Por PALAVRA-CHAVE, nao por igualdade: a fonte usa
# variantes ("Aceitou subjudice", "Contratado subjudice", "Reconvocado") e, com
# comparacao exata, essa gente sumia de TODAS as contagens -- a vaga aparecia
# como "em aberto" mesmo com o processo andando.
def balde_status(status):
    """Em que balde do resumo por opcao esse status cai. None = desconhecido:
    melhor o coletor avisar do que somar no lugar errado."""
    s = (status or "").lower()
    if "contratado" in s:
        return "contratados"
    if "aceitou" in s:
        return "em_contratacao"
    if "convocado" in s or "reconvocad" in s:
        return "aguardando"
    if "desisten" in s or "desclassific" in s or "manifest" in s:
        return "desistencias"
    return None


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return None


def media_aceite(changes, minimo=3):
    """Media de dias entre a convocacao e o aceite, com base nas convocacoes que
    acompanhamos do inicio ao fim. Devolve None quando a amostra e pequena
    demais -- ai o painel mantem a media historica que veio do seed, em vez de
    publicar ruido."""
    convocado, dias = {}, []
    for c in sorted(changes, key=lambda c: c.get("ts", "")):
        k = (c.get("opcao", ""), c.get("col", ""), c.get("nome", ""))
        para = (c.get("para", "") or "").lower()
        t = _ts(c.get("ts", ""))
        if t is None:
            continue
        if "convocado" in para or "reconvocad" in para:
            convocado.setdefault(k, t)
        elif "aceitou" in para and k in convocado:
            dias.append((t - convocado.pop(k)).total_seconds() / 86400)
    if len(dias) < minimo:
        return None
    return round(sum(dias) / len(dias), 1)


def _e_suspeita(prev, novo, historico):
    """True quando a mudanca tem cara de leitura de GERACAO ANTIGA da fonte.

    Uma leitura velha so consegue mostrar o PASSADO da pessoa. Entao e suspeita
    quando anda para tras -- e so isso:
      - volta a um status que ela JA teve;
      - desce a escada Convocado -> Aceitou -> Contratado;
      - sai de um status terminal sem ser por reconvocacao.
    NAO e suspeita ENTRAR num terminal (desistir/ser desclassificado depois de
    aceitar e comum e definitivo), nem qualquer avanco: esses aparecem na hora.
    """
    if not prev or novo == prev:
        return False
    if novo in (historico or ()):
        return True
    if _rank(novo) == 0:                      # entrar em terminal: legitimo
        return False
    if _rank(prev) == 0:                      # sair de terminal: so reconvocacao
        return "reconvocad" not in (novo or "").lower()
    return _rank(novo) < _rank(prev)


def _prioridade(p):
    """Ordena as linhas da MESMA vaga (opcao+colocacao+nome) -- menor = fica.

    1) status TERMINAL (Desistente/Desclassificado/Nao se manifestou) prevalece:
       nesta fonte a linha ativa que sobra costuma ser a obsoleta;
    2) senao, o status mais avancado;
    3) prefere a linha com lotacao conhecida (alimenta mapa e ranking de unidades);
    4) desempate lexicografico -> independe da ordem em que a fonte devolveu.
    """
    status = p.get("status", "")
    return (0 if _rank(status) == 0 else 1,
            -_rank(status),
            0 if (p.get("unidade") or "").strip() else 1,
            _norm(p.get("unidade")), _norm(p.get("lotacao")))


def _dedupe(pessoas):
    """Uma linha por VAGA (opcao+colocacao+nome). A fonte as vezes lista a mesma
    vaga em duas lotacoes (remanejamento) -- ai e uma convocacao so, e contar
    duas inflava convocados, desistencias e o mapa. NAO mexe em colocacoes
    diferentes: chamada pela cota e chamada pela ampla concorrencia sao duas
    convocacoes de verdade, ainda que da mesma pessoa na mesma opcao."""
    by_key = {}
    for p in pessoas:
        by_key.setdefault(_key(p), []).append(p)
    return [rows[0] if len(rows) == 1 else min(rows, key=_prioridade)
            for rows in by_key.values()]


def dedupe_pessoas(pessoas):
    """Publico: colapsa as linhas duplicadas da mesma vaga num registro so.
    O extrator chama ANTES de publicar, para a contagem nao inflar."""
    return _dedupe(pessoas)


def _dedup_changes(changes):
    """Remove eventos duplicados (mesma VAGA + mesma transicao + mesmo dia),
    mantendo o MAIS ANTIGO. Evita repeticoes quando uma re-coleta redetecta
    transicoes ja registradas (ex.: baseline que regrediu). A colocacao entra na
    chave: sem ela, duas chamadas da mesma pessoa na mesma opcao (uma pela cota,
    outra pela ampla) desapareciam uma na outra."""
    seen, out = set(), []
    for c in sorted(changes, key=lambda c: c.get("ts", "")):   # mais antigo 1o
        k = (c.get("opcao", ""), c.get("col", ""), c.get("nome", ""),
             c.get("date", ""), c.get("de", ""), c.get("para", ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def _cutoff(days):
    return (datetime.now(_BR).date() - timedelta(days=days)).isoformat()


def _assinatura_lote(suspeitas, sumiram, current):
    """Identidade do lote suspeito, para reconhecer o MESMO lote insistindo."""
    corpo = "|".join(sorted("{}={}".format(k, current.get(k, "")) for k in suspeitas)
                     + sorted("-" + k for k in sumiram))
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


def update_and_build(pessoas):
    """Devolve (convocacoes, contratacoes, extras, pessoas).

    `pessoas` volta com TODAS as linhas da fonte -- o total do painel espelha o
    oficial -- e com o status CONFIAVEL: se a fonte regrediu alguem e ainda nao
    confirmou, publicamos o status anterior. Levanta FonteDesatualizada quando
    a coleta inteira parece uma geracao antiga; o chamador descarta a coleta.

    O HISTORICO, porem, e ancorado na VAGA (opcao|colocacao|nome), nao na linha:
    a mesma vaga as vezes aparece em duas linhas (a EMBRAPA ofereceu em duas
    cidades e manteve as duas). Ancorar na linha seria pior -- a lotacao muda
    quando a pessoa escolhe a localidade, e cada escolha viraria uma
    "convocacao nova" fantasma.
    """
    now = datetime.now(_BR)
    day = now.date().isoformat()
    ts = now.strftime("%Y-%m-%d %H:%M")

    # `todas` = o que vai para o site (espelha a fonte 1:1). `pessoas` = uma
    # linha por VAGA, de forma deterministica, para o diff de estado.
    todas = list(pessoas)
    pessoas = _dedupe(todas)

    seed = _read(SEED_PATH, {}) or {}
    seed_conv = list(seed.get("convocacoes", []))
    seed_contr = list(seed.get("contratacoes", []))
    extras = dict(seed.get("extras", {}) or {})

    state = _read(STATE_PATH, {}) or {}
    if not isinstance(state, dict):
        state = {}
    last_people = dict(state.get("people", {}))
    ev = state.get("events", {}) if isinstance(state.get("events"), dict) else {}
    fwd_conv = list(ev.get("convocacoes", []))
    fwd_contr = list(ev.get("contratacoes", []))
    changes = list(state.get("changes", []))
    changed_at = dict(state.get("changed_at", {}))
    last_change = state.get("last_change")
    # historico de status ja vistos por pessoa: e o que revela uma leitura de
    # geracao antiga (voltar a um status que a pessoa JA teve).
    hist = {k: list(v) for k, v in (state.get("hist") or {}).items()}
    pendentes = {k: dict(v) for k, v in (state.get("pendentes") or {}).items()}
    lote = dict(state.get("lote") or {})
    # Quem JA entrou em cada serie. Sem isso, uma pessoa que some da fonte e
    # volta (o que uma leitura de geracao antiga provoca) era contada de novo e
    # inflava o ritmo da linha do tempo.
    convocados_ja = set(state.get("convocados") or [])
    contratados_ja = set(state.get("contratados") or [])

    segurados = {}          # vagas cujo status regrediu e ainda nao confirmou
    first_run = not last_people
    # Estado antigo (sem 'hist'/'contratados'): semeia com o que ja sabemos, para
    # a guarda comecar a valer imediatamente e as contratacoes nao repetirem.
    for k, s in last_people.items():
        hist.setdefault(k, [s])
        convocados_ja.add(k)
        if _e_contratado(s):
            contratados_ja.add(k)

    current = {}
    for p in pessoas:
        current[_key(p)] = p.get("status", "")

    if not first_run:
        # ---- guarda: a fonte voltou no tempo? --------------------------------
        suspeitas = [k for k, s in current.items()
                     if k in last_people
                     and _e_suspeita(last_people[k], s, hist.get(k, []))]
        # quem some tambem denuncia geracao antiga: ela ainda nao tinha essa pessoa.
        sumiram = [k for k in last_people if k not in current]
        lote_confirmado = False
        if len(suspeitas) + len(sumiram) >= _LIMIAR_LOTE:
            assinatura = _assinatura_lote(suspeitas, sumiram, current)
            n = lote.get("n", 0) + 1 if lote.get("assinatura") == assinatura else 1
            if n < _CONFIRMACOES_LOTE:
                # Grava SO o contador: o resto do estado fica intacto.
                state["lote"] = {"assinatura": assinatura, "n": n}
                try:
                    _write(STATE_PATH, state)
                except Exception:  # noqa: BLE001
                    pass
                raise FonteDesatualizada(
                    "{} pessoa(s) voltaram a um status anterior e {} sumiram "
                    "(leitura {}/{} do mesmo lote)".format(
                        len(suspeitas), len(sumiram), n, _CONFIRMACOES_LOTE))
            # Mesmo lote insistindo tantas vezes: e correcao real da fonte, nao
            # cache. Ja esta verificado -- nao precisa confirmar pessoa a pessoa.
            lote_confirmado = True
        lote = {}

        # ---- ENTROU / MUDOU: percorre quem esta na fonte agora ---------------
        for i, p in enumerate(pessoas):
            k = _key(p)
            status = p.get("status", "")
            cargo = p.get("cargo", "")
            prev = last_people.get(k)
            is_new = prev is None
            mudou = is_new or (prev != status)

            if mudou and not lote_confirmado \
                    and _e_suspeita(prev, status, hist.get(k, [])):
                # Regressao isolada: so vira fato depois de _CONFIRMACOES coletas
                # seguidas dizendo o mesmo. Ate la publicamos o status anterior.
                pend = pendentes.get(k)
                n = pend["n"] + 1 if pend and pend.get("status") == status else 1
                if n < _CONFIRMACOES:
                    pendentes[k] = {"status": status, "n": n}
                    current[k] = prev
                    segurados[k] = prev
                    continue
            pendentes.pop(k, None)

            if is_new and k not in convocados_ja:
                convocados_ja.add(k)
                fwd_conv.append(_event(day, cargo))
            if _e_contratado(status) and k not in contratados_ja:
                contratados_ja.add(k)
                fwd_contr.append(_event(day, cargo))
            if mudou:
                changes.append({"ts": ts, "date": day, "nome": p.get("nome", ""),
                                "opcao": p.get("opcao", ""),
                                "col": p.get("colocacao", ""), "cargo": cargo,
                                "unidade": p.get("unidade", ""),
                                "de": prev or "", "para": status, "novo": is_new})
                changed_at[k] = ts
                hist.setdefault(k, []).append(prev or "")
                if status not in hist[k]:
                    hist[k].append(status)
        # SAIU: quem estava no baseline e sumiu da fonte simplesmente DEIXA de
        # existir na nossa base (nao entra em people=current). Sem evento e sem
        # estatistica -> "como se nao houvesse informacao dele". Apenas some.
        if current != last_people:
            last_change = day
    else:
        for k, s in current.items():
            hist[k] = [s]
            convocados_ja.add(k)
            if _e_contratado(s):
                contratados_ja.add(k)

    # changed_at vai para o site: so quem esta na lista atual (payload enxuto).
    changed_at = {k: v for k, v in changed_at.items() if k in current}
    pendentes = {k: v for k, v in pendentes.items() if k in current}
    # hist/convocados/contratados NAO sao podados por `current`: se a pessoa
    # sumir por uma coleta e voltar, precisamos lembrar que ela ja passou por
    # aqui -- senao ela vira "nova" de novo e a guarda perde a memoria dela.
    hist = {k: sorted(set(v) - {""}) for k, v in hist.items()}

    cut = _cutoff(_KEEP_DAYS)
    changes = [c for c in changes if c.get("date", "") >= cut]
    changes = _dedup_changes(changes)   # remove re-deteccoes repetidas

    new_state = {"people": current,
                 "events": {"convocacoes": fwd_conv, "contratacoes": fwd_contr},
                 "changes": changes, "changed_at": changed_at,
                 "last_change": last_change, "hist": hist,
                 "pendentes": pendentes, "lote": lote,
                 "convocados": sorted(convocados_ja),
                 "contratados": sorted(contratados_ja)}
    try:
        _write(STATE_PATH, new_state)
    except Exception:  # noqa: BLE001
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
        if _e_contratado(c.get("para")):
            contr_dia[dt] = contr_dia.get(dt, 0) + 1
    extras["novos_por_dia"] = novos_dia
    extras["contratados_por_dia"] = contr_dia
    # Aceite medio: sai do diario. So sobrescreve o valor historico do seed
    # quando ja temos amostra propria suficiente.
    media = media_aceite(changes)
    if media is not None:
        extras["avg_days_convocado_to_aceitou"] = media

    # Status segurado vale para TODAS as linhas daquela vaga -- senao o painel
    # mostraria a mesma vaga com duas situacoes. Copia: nao mexemos nos dicts
    # que o chamador nos passou.
    if segurados:
        todas = [dict(p, status=segurados[_key(p)]) if _key(p) in segurados else p
                 for p in todas]
    return seed_conv + fwd_conv, seed_contr + fwd_contr, extras, todas
