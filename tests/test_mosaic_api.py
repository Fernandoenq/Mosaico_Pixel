#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da API delta do mosaico web (sem browser)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simple_frontend import SimpleMosaicFrontend  # noqa: E402


class MosaicDeltaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="mosaic_test_")
        self.mosaic_dir = Path(self._tmp) / "MOSAIC"
        self.mosaic_dir.mkdir(parents=True)
        self.front = SimpleMosaicFrontend()
        self.front.mosaic_dir = self.mosaic_dir
        self.front.reset_mosaic_catalog()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, name: str) -> Path:
        p = self.mosaic_dir / name
        p.write_bytes(b"\xff\xd8\xff\xd9")
        return p

    def test_unchanged_when_same_generation(self) -> None:
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        gen = self.front._mosaic_generation
        d = self.front.build_mosaic_delta(gen)
        self.assertTrue(d.get("unchanged"))
        self.assertEqual(d.get("added"), [])
        self.assertFalse(d.get("full_sync"))

    def test_incremental_add_without_full_sync(self) -> None:
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        g1 = self.front._mosaic_generation
        self._touch("img2.jpg")
        self.front.notify_mosaic_changed()
        d = self.front.build_mosaic_delta(g1)
        self.assertFalse(d.get("full_sync"))
        self.assertFalse(d.get("unchanged"))
        added_ids = {x["id"] for x in d.get("added", [])}
        self.assertIn("img2.jpg", added_ids)

    def test_snapshot_fallback_avoids_full_sync(self) -> None:
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        g1 = self.front._mosaic_generation
        self._touch("img2.jpg")
        self.front.notify_mosaic_changed()
        snap = self.front._snapshot_ids_at_or_before(g1)
        self.assertIsNotNone(snap)
        self.assertIn("img1.jpg", snap)
        d = self.front.build_mosaic_delta(g1)
        self.assertFalse(d.get("full_sync"))

    def test_reset_catalog_clears_generation(self) -> None:
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        self.assertGreater(self.front._mosaic_generation, 0)
        self.front.reset_mosaic_catalog()
        self.assertEqual(self.front._mosaic_generation, 0)
        d = self.front.build_mosaic_delta(0)
        self.assertFalse(d.get("unchanged"))

    def test_duplicate_fill_first_load_full_sync(self) -> None:
        self.front.duplicate_fill = True
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        d = self.front.build_mosaic_delta(0)
        self.assertTrue(d.get("full_sync"))
        self.assertTrue(d.get("images"))

    def test_duplicate_fill_incremental_after_first(self) -> None:
        self.front.duplicate_fill = True
        self._touch("img1.jpg")
        self.front.notify_mosaic_changed()
        g1 = self.front._mosaic_generation
        self._touch("img2.jpg")
        self.front.notify_mosaic_changed()
        d = self.front.build_mosaic_delta(g1)
        self.assertFalse(d.get("full_sync"))
        self.assertEqual(len(d.get("added", [])), 1)


class MosaicHardeningSimulation(unittest.TestCase):
    """Simula taxas de falha de regras de sync (logica pura)."""

    def test_fingerprint_dedup_rate(self) -> None:
        runs = 1000
        skipped = 0
        last_fp = ""
        for i in range(runs):
            urls = [f"/mosaic/img{j % 20}.jpg?v=1" for j in range(i % 25, (i % 25) + 20)]
            fp = "|".join(sorted(u.split("?")[0].split("/")[-1] for u in urls))
            if fp == last_fp:
                skipped += 1
            last_fp = fp
        skip_rate = skipped / runs * 100
        self.assertGreater(skip_rate, 30.0)

    def test_full_rebuild_only_when_empty(self) -> None:
        cases = [(0, 0, True), (100, 100, False), (50, 120, False), (0, 50, True)]
        for had, disp, expect_rebuild in cases:
            had_tiles = had > 0
            full_rebuild = not had_tiles
            self.assertEqual(full_rebuild, expect_rebuild)


def run_suite() -> dict:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(MosaicDeltaTests))
    suite.addTests(loader.loadTestsFromTestCase(MosaicHardeningSimulation))
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    return {
        "tests_run": total,
        "failures": failures,
        "success_rate_pct": round((total - failures) / max(1, total) * 100, 2),
    }


if __name__ == "__main__":
    stats = run_suite()
    print("RESUMO:", stats)
    raise SystemExit(0 if stats["failures"] == 0 else 1)
