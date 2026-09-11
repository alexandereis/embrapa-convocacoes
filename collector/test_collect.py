#!/usr/bin/env python3
"""Testes do orquestrador collect.py -- `python collector/test_collect.py`."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect  # noqa: E402
import timeline  # noqa: E402


class TestCheckNaoGrava(unittest.TestCase):
    """`--check` promete "so valida, nao grava" -- e precisa cumprir.

    A linha do tempo grava o estado DENTRO da coleta, entao um --check rodado na
    maquina de alguem avancava o timeline_state.json de verdade. Se esse estado
    fosse commitado junto de outra mudanca, producao herdava um estado que
    ninguem gerou de proposito.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._paths = (timeline.STATE_PATH, timeline.SEED_PATH)
        timeline.STATE_PATH = os.path.join(self.tmp.name, "state.json")
        timeline.SEED_PATH = os.path.join(self.tmp.name, "seed.json")

    def tearDown(self):
        timeline.STATE_PATH, timeline.SEED_PATH = self._paths
        self.tmp.cleanup()

    def _pessoas(self, *nomes):
        return [{"nome": n, "status": "Convocado", "opcao": "40001690",
                 "colocacao": f"{i + 1}o AC", "unidade": "", "lotacao": "",
                 "cargo": "Pesquisador"} for i, n in enumerate(nomes)]

    def test_somente_leitura_nao_cria_o_estado(self):
        timeline.update_and_build(self._pessoas("ANA", "BIA"),
                                  somente_leitura=True)
        self.assertFalse(os.path.exists(timeline.STATE_PATH),
                         "--check nao pode gravar o estado da timeline")

    def _estado_bruto(self):
        with open(timeline.STATE_PATH, encoding="utf-8") as f:
            return f.read()

    def test_somente_leitura_nao_avanca_o_estado_existente(self):
        timeline.update_and_build(self._pessoas("ANA"))
        antes = self._estado_bruto()
        timeline.update_and_build(self._pessoas("ANA", "BIA"),
                                  somente_leitura=True)
        self.assertEqual(self._estado_bruto(), antes)

    def test_modo_normal_continua_gravando(self):
        timeline.update_and_build(self._pessoas("ANA"))
        self.assertTrue(os.path.exists(timeline.STATE_PATH))

    def test_somente_leitura_ainda_devolve_os_dados(self):
        _conv, _contr, _extras, pessoas = timeline.update_and_build(
            self._pessoas("ANA", "BIA"), somente_leitura=True)
        self.assertEqual(len(pessoas), 2)


class TestAvisoVisivel(unittest.TestCase):
    """Coleta descartada tem que APARECER, nao so existir no log.

    O painel ficou dias congelado sem ninguem notar porque todo run terminava
    verde. No Actions, um `::warning::` aparece na interface do run e no resumo
    da lista -- e a diferenca entre "descobri hoje" e "descobri em uma semana".
    """

    def setUp(self):
        self._antes = os.environ.get("GITHUB_ACTIONS")
        os.environ.pop("GITHUB_ACTIONS", None)

    def tearDown(self):
        os.environ.pop("GITHUB_ACTIONS", None)
        if self._antes is not None:
            os.environ["GITHUB_ACTIONS"] = self._antes

    def _saida(self, msg):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collect._aviso(msg)
        return buf.getvalue()

    def test_no_actions_sai_como_warning(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        self.assertTrue(self._saida("fonte velha").startswith("::warning::"))

    def test_fora_do_actions_e_texto_normal(self):
        saida = self._saida("fonte velha")
        self.assertNotIn("::warning::", saida)
        self.assertIn("fonte velha", saida)

    def test_a_mensagem_sempre_aparece(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        self.assertIn("fonte velha", self._saida("fonte velha"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
