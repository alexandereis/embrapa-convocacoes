#!/usr/bin/env python3
"""Testes do adaptador looker_studio -- `python collector/test_looker.py`.

Cobrem a licao aprendida em 11/09/2026: a fonte trata o `rowsCount` como parte
da CHAVE DE CACHE. Pedir um valor diferente do registrado no painel devolve uma
GERACAO ANTIGA do conjunto (na ocasiao, 1157 linhas em vez de 1169), e o painel
congelou por dias sem nenhum erro aparecer em lugar nenhum.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import timeline  # noqa: E402
from config import LOOKER_ROWS_REGISTRADO  # noqa: E402
from extractors import looker_studio as lk  # noqa: E402


def _payload_registrado_do_worker():
    """Le a query REGISTRADA do painel, tal como o worker a envia.

    O worker e a referencia viva: ele recebe a geracao nova da fonte. Se o
    coletor divergir dele, e o coletor que esta errado.
    """
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "worker", "embrapa-watcher.js")
    with open(caminho, encoding="utf-8") as f:
        js = f.read()
    return json.loads(re.search(r"const PAYLOAD = (\{.*?\});\n", js, re.S).group(1))


def _rows_count(payload):
    return payload["dataRequest"][0]["datasetSpec"]["paginateInfo"]["rowsCount"]


def _start_row(payload):
    return payload["dataRequest"][0]["datasetSpec"]["paginateInfo"]["startRow"]


def _resposta(n_linhas, total):
    """Monta uma resposta da fonte com n_linhas linhas e totalCount=total."""
    colunas = []
    for _s, chave, _q in lk.TABLE_FIELDS:
        colunas.append({"stringColumn": {
            "values": [f"{chave}{i}" for i in range(n_linhas)]}})
    return {"dataResponse": [{"dataSubset": [{"dataset": {"tableDataset": {
        "totalCount": total, "size": n_linhas, "column": colunas}}}]}]}


class BaseFonteFalsa(unittest.TestCase):
    """Troca a fonte por uma falsa e isola o estado da timeline num temporario.

    Sem o isolamento, o teste leria o timeline_state.json de producao e a guarda
    de geracao antiga dispararia por causa dos dados ficticios.
    """

    def setUp(self):
        self._post_real = lk._post
        self._paths = (timeline.STATE_PATH, timeline.SEED_PATH)
        self._tmp = tempfile.TemporaryDirectory()
        timeline.STATE_PATH = os.path.join(self._tmp.name, "state.json")
        timeline.SEED_PATH = os.path.join(self._tmp.name, "seed.json")
        self.extractor = lk.LookerStudioExtractor()

    def tearDown(self):
        lk._post = self._post_real
        timeline.STATE_PATH, timeline.SEED_PATH = self._paths
        self._tmp.cleanup()

    def fetch_com(self, paginas):
        """Roda o fetch contra as paginas dadas e devolve (fonte, raw)."""
        fonte = FonteFalsa(paginas)
        lk._post = fonte
        with contextlib.redirect_stdout(io.StringIO()):
            raw = self.extractor.fetch()
        return fonte, raw


class FonteFalsa:
    """Substitui o _post: registra o que foi pedido e devolve o que mandarmos."""

    def __init__(self, paginas):
        self.paginas = list(paginas)
        self.pedidos = []

    def __call__(self, _endpoint, payload, **_kw):
        self.pedidos.append(payload)
        resp = self.paginas[min(len(self.pedidos) - 1, len(self.paginas) - 1)]
        return ")]}'\n" + json.dumps(resp)


class TestQueryRegistrada(unittest.TestCase):
    """O payload do coletor tem que ser IDENTICO ao registrado no painel."""

    def test_payload_igual_ao_do_worker(self):
        esperado = _payload_registrado_do_worker()
        obtido = lk._build_payload(1, LOOKER_ROWS_REGISTRADO)
        self.assertEqual(obtido, esperado,
                         "o payload do coletor divergiu da query registrada do "
                         "painel -- a fonte vai servir uma geracao antiga")

    def test_rows_count_registrado_e_o_do_worker(self):
        self.assertEqual(LOOKER_ROWS_REGISTRADO,
                         _rows_count(_payload_registrado_do_worker()))


class TestPaginacaoNaoAlteraORowsCount(BaseFonteFalsa):
    """O bug: a ultima pagina era "clampada" (min(page, total-start+1)).

    Isso mudava o rowsCount -- e um rowsCount diferente do registrado cai numa
    entrada de cache velha da fonte. Todo pedido tem que usar o MESMO valor.
    """

    def test_uma_pagina_so_usa_o_rows_count_registrado(self):
        fonte, _ = self.fetch_com([_resposta(1169, 1169)])
        self.assertEqual([_rows_count(p) for p in fonte.pedidos],
                         [LOOKER_ROWS_REGISTRADO])

    def test_ultima_pagina_nao_e_clampada(self):
        """Dataset maior que uma pagina: a 2a leitura mantem o rowsCount."""
        fonte, _ = self.fetch_com([
            _resposta(LOOKER_ROWS_REGISTRADO, LOOKER_ROWS_REGISTRADO + 40),
            _resposta(40, LOOKER_ROWS_REGISTRADO + 40),
        ])
        self.assertTrue(len(fonte.pedidos) >= 2, "deveria ter paginado")
        for p in fonte.pedidos:
            self.assertEqual(_rows_count(p), LOOKER_ROWS_REGISTRADO)
        self.assertEqual(_start_row(fonte.pedidos[1]), LOOKER_ROWS_REGISTRADO + 1)


class TestGuardaDeLeituraIncompleta(BaseFonteFalsa):
    """Ler menos linhas do que a fonte declara = leitura truncada.

    Publicar isso apaga gente do painel em silencio. A coleta tem que ser
    descartada, como ja acontece com a geracao antiga.
    """

    def test_leitura_truncada_marca_fonte_desatualizada(self):
        _, raw = self.fetch_com([_resposta(900, 1169), _resposta(0, 1169)])
        self.assertTrue(raw.fonte_desatualizada,
                        "leitura truncada deveria descartar a coleta")
        self.assertIn("900", raw.fonte_desatualizada)
        self.assertIn("1169", raw.fonte_desatualizada)

    def test_leitura_completa_nao_marca_nada(self):
        _, raw = self.fetch_com([_resposta(1169, 1169)])
        self.assertEqual(raw.fonte_desatualizada, "")
        self.assertEqual(len(raw.pessoas), 1169)


if __name__ == "__main__":
    unittest.main(verbosity=2)
