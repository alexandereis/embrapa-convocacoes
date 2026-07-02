"""Recalcula TODAS as metricas do dashboard a partir dos dados brutos.

Independente da fonte: recebe um RawData e devolve o data.json final.
Aqui mora a inteligencia do coletor -- nada vem "pronto" da fonte, exceto
os poucos campos que exigem historico diario fino (complementados via extras).
"""
from collections import defaultdict, OrderedDict
from datetime import date, datetime, timedelta, timezone
import geo
import timeline

_BR = timezone(timedelta(hours=-3))   # Brasilia (UTC-3) — "hoje" igual ao diario



def _iso_week(dstr):
    y, w, _ = datetime.strptime(dstr, "%Y-%m-%d").isocalendar()
    return f"{y}-W{w:02d}"


def _month(dstr):
    return dstr[:7]


def _business_days(d0, d1):
    n, cur = 0, d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _cota(colocacao):
    """Extrai a cota da colocacao (ex.: '10ª AC', 'REC 2º PCD')."""
    s = (colocacao or "").upper()
    if "PPP" in s:
        return "PPP"
    if "PCD" in s or "PNE" in s:
        return "PCD"
    if "AC" in s:
        return "AC"
    return "Outros"


def _scale_series(series, target):
    """Escala os valores de uma serie {label,value} para que a soma seja
    exatamente `target`, preservando o formato (proporcao entre os periodos).

    Usado para reconciliar a curva historica (que vem de uma fonte datada
    INCOMPLETA) com os totais OFICIAIS exatos: a distribuicao mensal/semanal e
    uma estimativa do ritmo; o total final bate com o numero real.
    """
    s = sum(x["value"] for x in series)
    if s <= 0 or not target:
        return series
    f = target / s
    out, acc, running = [], 0.0, 0
    for x in series:
        acc += x["value"] * f
        v = round(acc) - running
        running += v
        out.append({**x, "value": v})
    drift = target - sum(x["value"] for x in out)
    if out and drift:
        out[-1]["value"] += drift
    return out


def _moving_avg(values, window):
    out = []
    for i in range(len(values)):
        seg = values[max(0, i - window + 1):i + 1]
        out.append(round(sum(seg) / len(seg), 1))
    return out


def build(raw):
    pessoas = raw.pessoas
    opcoes = raw.opcoes

    # ---------- status ----------
    por_status = defaultdict(int)
    for p in pessoas:
        por_status[p["status"]] += 1
    por_status = dict(por_status)

    # ---------- por cargo (a partir do resumo por opcao) ----------
    cg = defaultdict(lambda: {"total": 0, "em_contratacao": 0, "contratados": 0,
                              "convocados": 0, "desistencias": 0})
    for o in opcoes:
        c = cg[o["cargo"]]
        c["total"] += o["vagas"]
        c["em_contratacao"] += o["em_contratacao"] + o["aguardando"]
        c["contratados"] += o["contratados"]
        c["convocados"] += o["convocados"]
        c["desistencias"] += o["desistencias"]
    por_cargo = []
    for cargo, v in cg.items():
        total = v["total"] or 1
        por_cargo.append({
            "cargo": cargo, "total": v["total"], "em_contratacao": v["em_contratacao"],
            "contratados": v["contratados"],
            # % efetivamente contratado (fato consolidado)
            "pct_contratado": round(v["contratados"] / total * 100, 2),
            # % preenchido = contratados + em andamento (mesma leitura do controle de referencia)
            "pct_preenchido": round((v["contratados"] + v["em_contratacao"]) / total * 100, 2),
            "vagas_abertas": max(0, v["total"] - v["contratados"] - v["em_contratacao"]),
        })
    rank = {"Pesquisador": 0, "Analista": 1, "Tecnico": 2, "Assistente": 3}
    por_cargo.sort(key=lambda x: rank.get(x["cargo"], 9))

    # ---------- desistencias por cargo ----------
    desist = [{"cargo": "Todos",
               "desistencias": sum(c["desistencias"] for c in cg.values()),
               "convocacoes": sum(c["convocados"] for c in cg.values()), "pct": 0}]
    for cargo, v in cg.items():
        conv = v["convocados"] or 1
        desist.append({"cargo": cargo, "desistencias": v["desistencias"],
                       "convocacoes": v["convocados"],
                       "pct": round(v["desistencias"] / conv * 100, 2)})
    for d in desist:
        conv = d["convocacoes"] or 1
        d["pct"] = round(d["desistencias"] / conv * 100, 2)
    desist.sort(key=lambda x: (x["cargo"] != "Todos", rank.get(x["cargo"], 9)))

    # ---------- distribuicao de opcoes por nº de candidatos/convocados ----------
    buckets = OrderedDict([("1-5", 0), ("6-10", 0), ("11-15", 0), ("16-20", 0), (">20", 0)])
    for o in opcoes:
        n = o["convocados"]
        key = "1-5" if n <= 5 else "6-10" if n <= 10 else "11-15" if n <= 15 else "16-20" if n <= 20 else ">20"
        buckets[key] += 1
    options_distribution = {"buckets": [{"range": k, "count": v} for k, v in buckets.items()]}

    # ---------- series temporais (recomputadas das datas) ----------
    conv_dates = sorted(c["date"] for c in raw.convocacoes if c.get("date"))
    weekly = defaultdict(int)
    for ds in conv_dates:
        weekly[_iso_week(ds)] += 1
    weekly_series = [{"label": k, "value": weekly[k]} for k in sorted(weekly)]

    contr_dates = sorted(c["date"] for c in raw.contratacoes if c.get("date"))
    monthly = defaultdict(int)
    for ds in contr_dates:
        monthly[_month(ds)] += 1
    monthly_contr = []
    for k in sorted(monthly):
        y, m = k.split("-")
        monthly_contr.append({"label": f"{m}/{y[2:]}", "value": monthly[k]})

    # velocidade diaria (ultimos 15 dias, ate HOJE) — a partir do DIARIO (datas
    # reais do backfill + coletas). A serie de eventos nao recebe o backfill,
    # entao usariamos dados furados; o diario tem o ritmo real dia a dia.
    ex = raw.extras or {}
    novos_por_dia = ex.get("novos_por_dia") or {}
    if novos_por_dia:
        hoje_d = datetime.now(_BR).date()
        # calcula sobre 25 dias (15 exibidos + folga para a media movel de 10)
        dias = [(hoje_d - timedelta(days=i)).isoformat() for i in range(24, -1, -1)]
        vals = [novos_por_dia.get(d, 0) for d in dias]
        mm5 = _moving_avg(vals, 5)
        mm10 = _moving_avg(vals, 10)
        velocity = [{"date": dias[i], "convocados": vals[i], "mm5": mm5[i], "mm10": mm10[i]}
                    for i in range(len(dias))][-15:]
    elif conv_dates:
        # fallback (sem diario): comportamento antigo pela serie de eventos.
        daily = defaultdict(int)
        for ds in conv_dates:
            daily[ds] += 1
        d0 = datetime.strptime(conv_dates[0], "%Y-%m-%d").date()
        d1 = datetime.strptime(conv_dates[-1], "%Y-%m-%d").date()
        all_days, cur = [], d0
        while cur <= d1:
            all_days.append(cur.isoformat())
            cur += timedelta(days=1)
        vals = [daily.get(d, 0) for d in all_days]
        mm5 = _moving_avg(vals, 5)
        mm10 = _moving_avg(vals, 10)
        velocity = [{"date": all_days[i], "convocados": vals[i], "mm5": mm5[i], "mm10": mm10[i]}
                    for i in range(len(all_days))][-15:]
    else:
        velocity = []

    # ---------- unidades ----------
    pu = defaultdict(lambda: {"total": 0, "contratados": 0})
    for p in pessoas:
        u = p["unidade"] or "Nao informada"
        pu[u]["total"] += 1
        if p["status"] == "Contratado":
            pu[u]["contratados"] += 1
    por_unidade = sorted(({"unidade": k, **v} for k, v in pu.items()),
                         key=lambda x: -x["total"])

    # ---------- aceites pendentes ----------
    aceites = [{"nome": p["nome"], "opcao": p["opcao"], "unidade": p["unidade"],
                "lotacao": p["lotacao"]}
               for p in pessoas if p["status"] in ("Aceitou", "Convocado")]

    # ---------- distribuicao por cota ----------
    pc = defaultdict(lambda: {"total": 0, "contratados": 0})
    for p in pessoas:
        c = _cota(p["colocacao"])
        pc[c]["total"] += 1
        if p["status"] == "Contratado":
            pc[c]["contratados"] += 1
    ordem_cota = {"AC": 0, "PPP": 1, "PCD": 2, "Outros": 3}
    por_cota = sorted(({"cota": k, **v} for k, v in pc.items()),
                      key=lambda x: ordem_cota.get(x["cota"], 9))

    # ---------- general ----------
    total_vagas = sum(c["total"] for c in por_cargo)
    total_convocados = sum(c["convocados"] for c in cg.values()) or len(pessoas)
    total_contratados = sum(v for k, v in por_status.items()
                            if "contratado" in k.lower())
    total_aceitou = por_status.get("Aceitou", 0)
    total_desist = sum(c["desistencias"] for c in cg.values())

    # Reconcilia as series temporais com os totais OFICIAIS: a fonte datada
    # (seed) e incompleta, entao escalamos a distribuicao para somar o total
    # real. O formato (ritmo por periodo) e estimativa; o total final e exato.
    weekly_series = _scale_series(weekly_series, total_convocados)
    monthly_contr = _scale_series(monthly_contr, total_contratados)
    _alldates = conv_dates + contr_dates
    biz = (_business_days(datetime.strptime(min(_alldates), "%Y-%m-%d").date(),
                          datetime.now(_BR).date()) if _alldates else 0)
    media_mm10 = velocity[-1]["mm10"] if velocity else 0
    hoje = datetime.now(_BR).date().isoformat()

    changed_at = ex.get("changed_at") or {}
    # "Convocados hoje": novas convocacoes (novo=True) datadas de hoje, pelo
    # MESMO diario que alimenta a velocidade -> KPI e grafico batem.
    convocados_hoje = novos_por_dia.get(hoje, 0)
    if not novos_por_dia:
        convocados_hoje = sum(1 for c in (ex.get("changes") or [])
                              if c.get("date") == hoje and c.get("novo"))
    # Media/dia (10d) = media movel de 10 dias do proprio grafico de velocidade
    # (que ja vem do diario). Assim o numero do KPI bate exatamente com o grafico.
    media_diaria = round(media_mm10, 1)
    general = {
        "last_update": raw.last_update or datetime.now().strftime("%d/%m/%Y - %H:%M:%S"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_ts": int(datetime.now().timestamp()),
        "business_days_elapsed": biz,
        "total_convocados": total_convocados,
        "total_aceitou": total_aceitou,
        "total_contratados": total_contratados,
        "pct_desistencias": round(total_desist / (total_convocados or 1) * 100, 1),
        "convocados_hoje": convocados_hoje,
        "media_diaria_mm10": media_diaria,
        "avg_days_convocado_to_aceitou": ex.get("avg_days_convocado_to_aceitou", None),
        "vagas_edital": total_vagas,
        "fonte_ultima_mudanca": ex.get("fonte_ultima_mudanca"),
    }

    return {
        "general": general,
        "por_cargo": por_cargo,
        "desistencias": desist,
        "por_status": por_status,
        "por_unidade": por_unidade,
        "options_distribution": options_distribution,
        "cumulative": {
            "weekly": {"convocado": weekly_series},
            "monthly_contratados": {"contratados": monthly_contr},
        },
        "velocity": velocity,
        "opcoes": opcoes,
        "por_cota": por_cota,
        "por_estado": geo.por_estado(pessoas)[0],
        "mudancas": ex.get("changes", []),
        "pessoas": [{"col": p["colocacao"], "nome": p["nome"], "opcao": p["opcao"],
                     "cargo": p.get("cargo", ""), "cota": _cota(p["colocacao"]),
                     "status": p["status"], "unidade": p["unidade"] or "Nao informada",
                     "lotacao": p["lotacao"],
                     "alterado_em": changed_at.get(
                         timeline.norm_key(p["opcao"], p["colocacao"], p["nome"]), "")}
                    for p in pessoas],
        "aceites_pendentes": aceites,
        "remaining_days": [{"cargo": "ALL",
                            "vagas_restantes": sum(c["vagas_abertas"] for c in por_cargo)}],
    }
