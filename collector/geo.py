# -*- coding: utf-8 -*-
"""De-para cidade (lotacao) -> UF e agregacao por estado para o mapa.

Mapeia pela CIDADE porque a mesma unidade Embrapa tem postos em estados
diferentes. Cidades nao mapeadas caem em 'ND' (e sao listadas para inclusao).
"""
import unicodedata

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia",
    "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}


def _norm(s):
    s = (s or "").split("/")[0]  # "Pelotas/RS" -> "Pelotas"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = "".join(c if c.isalnum() else " " for c in s.lower())
    return " ".join(s.split())


# chaves JA normalizadas (minusculas, sem acento)
CITY_UF = {
    "brasilia": "DF", "planaltina": "DF", "gama": "DF",
    "maceio": "AL", "rio largo": "AL",
    "barbalha": "CE", "fortaleza": "CE", "sobral": "CE",
    "campina grande": "PB",
    "campinas": "SP", "sao carlos": "SP", "jaguariuna": "SP", "pindorama": "SP",
    "irece": "BA", "luis eduardo magalhaes": "BA", "cruz das almas": "BA",
    "sinop": "MT",
    "seropedica": "RJ", "rio de janeiro": "RJ",
    "santo antonio de goias": "GO", "santo antonio de gioas": "GO", "goiania": "GO",
    "palmas": "TO",
    "colombo": "PR", "londrina": "PR", "ponta grossa": "PR",
    "campo grande": "MS", "dourados": "MS", "corumba": "MS",
    "coronel pacheco": "MG", "caronel pacheco": "MG", "juiz de fora": "MG",
    "nova porteirinha": "MG", "sete lagoas": "MG", "uberaba": "MG",
    "balsas": "MA", "sao luis": "MA", "sao luiz": "MA",
    "recife": "PE", "petrolina": "PE",
    "concordia": "SC",
    "passo fundo": "RS", "bento goncalves": "RS", "pelotas": "RS", "bage": "RS",
    "manaus": "AM",
    "rio branco": "AC",
    "macapa": "AP",
    "ouro preto d oeste": "RO", "ouro preto do oeste": "RO",
    "porto velho": "RO", "vilhena": "RO",
    "boa vista": "RR",
    "parnaiba": "PI", "teresina": "PI",
    "aracaju": "SE", "nossa senhora da gloria": "SE",
    "belem": "PA",
}


def uf_of(cidade):
    return CITY_UF.get(_norm(cidade))


def por_estado(pessoas):
    """Devolve (lista_por_uf, info). lista: [{uf, estado, total, contratados}]."""
    agg = {}
    nd = 0
    nao_mapeadas = {}
    for p in pessoas:
        cid = p.get("lotacao", "")
        uf = uf_of(cid)
        if not uf:
            if (cid or "").strip() not in ("", "-"):
                nao_mapeadas[cid] = nao_mapeadas.get(cid, 0) + 1
            nd += 1
            continue
        a = agg.setdefault(uf, {"uf": uf, "estado": UF_NOME[uf],
                                "total": 0, "contratados": 0})
        a["total"] += 1
        if p.get("status") == "Contratado":
            a["contratados"] += 1
    lista = sorted(agg.values(), key=lambda x: -x["total"])
    info = {"sem_estado": nd, "nao_mapeadas": nao_mapeadas}
    return lista, info
