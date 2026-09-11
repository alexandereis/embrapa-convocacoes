#!/usr/bin/env python3
"""Testes do orquestrador collect.py -- `python collector/test_collect.py`."""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect  # noqa: E402


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
