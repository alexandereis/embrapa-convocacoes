#!/usr/bin/env python3
"""Limpeza UNICA do historico ja gravado em site/data/timeline_state.json.

A guarda nova (timeline.py) impede que leituras de GERACAO ANTIGA da fonte
virem eventos -- mas nao desfaz os que ja foram gravados. Este script apaga os
que sobraram: 81 pares de ida-e-volta e 34 encadeamentos partidos, que o painel
mostrava como a mesma pessoa mudando de situacao varias vezes ao dia.

O que ele considera artefato: uma EXCURSAO -- a convocacao anda para tras
(_e_suspeita) e volta ao status anterior em ate JANELA_H horas. Todos os
eventos da excursao caem. Os 81 retornos observados fecharam em no maximo 11h;
uma reconvocacao de verdade leva dias, entao 24h separa com folga um do outro.

Depois de limpar, reencadeia os eventos (o `de` de cada um passa a ser o `para`
do anterior) e RECONSTROI as series de convocacoes/contratacoes a partir do
diario limpo -- elas contavam a mesma pessoa de novo a cada piscada da fonte
(27 contratacoes apareciam em 07/08 E em 08/08).

Limitacao conhecida: os eventos antigos foram gravados sem a colocacao, entao
para eles o agrupamento e por opcao+nome. Nas poucas pessoas com DUAS chamadas
na mesma opcao (uma pela cota, outra pela ampla) as duas trilhas ficam juntas;
nesses casos o script nao aplica o ajuste de cauda, para nao inventar. Eventos
novos ja carregam `col` e sao agrupados pela vaga exata.

Uso:  python collector/limpar_historico.py [--check]
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import timeline  # noqa: E402

JANELA_H = 24     # ida-e-volta que fecha nesse prazo e artefato, nao noticia


def _horas(ts_a, ts_b):
    fmt = "%Y-%m-%d %H:%M"
    try:
        return (datetime.strptime(ts_b, fmt)
                - datetime.strptime(ts_a, fmt)).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return float("inf")


def _fim_da_excursao(evs, i, atual):
    """De onde retomar se evs[i] for ida de uma excursao; None se for real."""
    e = evs[i]
    j = i + 1
    while j < len(evs) and _horas(e.get("ts", ""), evs[j].get("ts", "")) <= JANELA_H:
        if evs[j].get("para", "") == atual:
            return j + 1        # retorno explicito: caem a ida E a volta
        j += 1
    prox = evs[i + 1] if i + 1 < len(evs) else None
    if prox is not None and not prox.get("novo") and prox.get("de", "") == atual:
        # Retorno SILENCIOSO: o proximo evento foi gravado saindo do status de
        # antes da excursao, entao a fonte ja tinha voltado -- o evento de volta
        # e que nao ficou (o _dedup_changes o descartou por repetir o anterior).
        return i + 1
    return None


def limpar_trilha(eventos, atual_real=None):
    """Devolve (eventos REAIS da trilha, status final), sem as excursoes da fonte.

    `atual_real` e o status que a fonte diz HOJE, quando da para saber. Serve
    para as excursoes cujo retorno nunca foi gravado: o _dedup_changes engolia o
    evento de volta quando ele repetia (pessoa, dia, de, para) de um anterior, e
    sobrava so a ida -- uma regressao pendurada, sem par. Se o historico limpo
    nao termina onde a fonte esta, desfazemos a cauda ate bater.
    """
    evs = [e for e in sorted(eventos, key=lambda c: c.get("ts", ""))
           if e.get("para")]                    # eventos sem status sao lixo
    atual = evs[0].get("de", "") if evs else ""
    hist = [atual] if atual else []
    trilha, i = [], 0                           # (evento, atual_antes, hist_antes)
    while i < len(evs):
        e = evs[i]
        destino = e.get("para", "")
        # So o PRIMEIRO evento pode ser "novo". Um segundo "novo" e a convocacao
        # que sumiu da fonte e voltou (leitura de geracao antiga) -- nao e outra
        # chamada: era isso que inflava a serie de convocacoes.
        novo = bool(e.get("novo")) and not trilha
        if not novo and timeline._e_suspeita(atual, destino, hist):
            salto = _fim_da_excursao(evs, i, atual)
            if salto is not None:
                i = salto              # a excursao inteira some
                continue
        trilha.append((dict(e, novo=novo, de="" if novo else atual), atual, list(hist)))
        if destino not in hist:
            hist.append(destino)
        atual = destino
        i += 1

    # INVARIANTE: o diario nao pode contradizer o status que a fonte da HOJE --
    # se o historico limpo termina noutro lugar, ele esta errado por construcao,
    # entao a cauda cai ate bater (calar e melhor que mentir).
    while atual_real and trilha and atual != atual_real:
        e, atual_antes, hist_antes = trilha[-1]
        if e.get("novo"):
            break
        trilha.pop()
        atual, hist = atual_antes, hist_antes

    # sobra de reencadeamento: evento que virou "de == para" nao mudou nada.
    return [e for e, _a, _h in trilha
            if e.get("novo") or e.get("de") != e.get("para")], atual


def _grupo(c):
    """Identidade da trilha. Eventos novos trazem a colocacao (vaga exata); os
    antigos foram gravados sem ela e caem no agrupamento por opcao+nome."""
    return (timeline._norm(c.get("opcao", "")), timeline._norm(c.get("col", "")),
            timeline._norm(c.get("nome", "")))


def main():
    check = "--check" in sys.argv
    state = timeline._read(timeline.STATE_PATH, None)
    if not state:
        print("ERRO: timeline_state.json nao encontrado.")
        sys.exit(1)

    people = dict(state.get("people", {}))
    changed_at = dict(state.get("changed_at", {}))
    changes = state.get("changes", [])
    ev = state.get("events", {}) or {}

    # status atual por grupo -- so quando o grupo aponta para UMA vaga so.
    por_grupo, ambiguos = {}, set()
    for k, s in people.items():
        partes = k.split("|")
        g = (partes[0], "", partes[-1])      # opcao, (sem colocacao), nome
        if g in por_grupo and por_grupo[g] != s:
            ambiguos.add(g)
        por_grupo.setdefault(g, s)

    trilhas = {}
    for c in changes:
        trilhas.setdefault(_grupo(c), []).append(c)

    limpos = []
    for g, evs in trilhas.items():
        alvo = None if g in ambiguos else por_grupo.get(g)
        mantidos, _final = limpar_trilha(evs, alvo)
        limpos.extend(mantidos)

    limpos = timeline._dedup_changes(limpos)
    datas = [c.get("date", "") for c in limpos if c.get("date")]
    corte = min(datas) if datas else ""

    # --- series: preserva o que e anterior ao diario e reconstroi o resto -----
    def reconstruir(antigos, novos):
        return sorted([e for e in antigos if e.get("date", "") < corte] + novos,
                      key=lambda e: e.get("date", ""))

    conv = [{"date": c["date"], "cargo": c.get("cargo", "")}
            for c in limpos if c.get("novo")]
    contr, vistos = [], set()
    for c in sorted(limpos, key=lambda c: c.get("ts", "")):
        g = _grupo(c)
        if timeline._e_contratado(c.get("para")) and g not in vistos:
            vistos.add(g)
            contr.append({"date": c["date"], "cargo": c.get("cargo", "")})
    novo_conv = reconstruir(ev.get("convocacoes", []), conv)
    novo_contr = reconstruir(ev.get("contratacoes", []), contr)

    print("=== ANTES -> DEPOIS ===")
    print(f"  convocacoes no estado : {len(people):5}")
    print(f"  eventos no diario     : {len(changes):5} -> {len(limpos):5}"
          f"   ({len(changes) - len(limpos)} artefatos removidos)")
    print(f"  serie convocacoes     : {len(ev.get('convocacoes', [])):5} -> {len(novo_conv):5}")
    print(f"  serie contratacoes    : {len(ev.get('contratacoes', [])):5} -> {len(novo_contr):5}")
    if ambiguos:
        print(f"  trilhas ambiguas (2 chamadas na mesma opcao, sem colocacao no"
              f" evento antigo): {len(ambiguos)} -- cauda nao ajustada")

    if check:
        print("\n--check: nada gravado.")
        return

    timeline._write(timeline.STATE_PATH, {
        "people": people,
        "events": {"convocacoes": novo_conv, "contratacoes": novo_contr},
        "changes": limpos,
        "changed_at": {k: v for k, v in changed_at.items() if k in people},
        "last_change": state.get("last_change"),
        # historia por vaga recomecada do status atual: o diario antigo nao tem
        # a colocacao, entao nao da para reatribuir status por vaga sem chutar.
        # A guarda nao depende disso -- ela tambem barra regressao pela escada.
        "hist": {k: [s] for k, s in people.items() if s},
        "pendentes": {},
        "lote": {},
        "convocados": sorted(people),
        "contratados": sorted(k for k, s in people.items()
                              if timeline._e_contratado(s)),
    })
    print("\ntimeline_state.json regravado. Rode collect.py para refazer o data.json.")


if __name__ == "__main__":
    main()
