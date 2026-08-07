#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes de download S3 no monitoramento de imagens."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import galeria_monitor  # noqa: E402


class S3DownloadMonitorTests(unittest.TestCase):
    def test_baixar_novas_imagens_s3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mosaic_download_test_") as tmp:
            tmp_path = Path(tmp)
            entrada = tmp_path / "entrada"
            entrada.mkdir(parents=True, exist_ok=True)
            
            downloads = []

            class FakeS3Client:
                def list_objects_v2(self, Bucket, MaxKeys=None):
                    return {
                        "Contents": [
                            {"Key": "foto1.jpg"},
                            {"Key": "texto.txt"}, # Deve ser ignorado
                            {"Key": "foto2.png"}
                        ]
                    }
                    
                def download_file(self, Bucket, Key, Filename):
                    downloads.append(Key)
                    # Cria um arquivo fake para simular o download
                    Path(Filename).write_text("fake image")

            with patch.dict(os.environ, {
                "AWS_ACCESS_KEY_ID": "fake-access",
                "AWS_SECRET_ACCESS_KEY": "fake-secret",
                "AWS_REGION": "us-east-1",
                "S3_BUCKET": "fake-bucket",
            }, clear=False):
                with patch("galeria_monitor.boto3.client", return_value=FakeS3Client()):
                    # Garantir que as processadas estao vazias no teste
                    galeria_monitor.PROCESSADAS_S3.clear()
                    
                    galeria_monitor.baixar_novas_imagens_s3(
                        entrada,
                        log_callback=lambda msg: None,
                    )
                    
            self.assertEqual(len(downloads), 2)
            self.assertIn("foto1.jpg", downloads)
            self.assertIn("foto2.png", downloads)
            
            # Testa se gravou os arquivos fakes localmente
            self.assertTrue((entrada / "foto1.jpg").exists())
            self.assertTrue((entrada / "foto2.png").exists())
            self.assertFalse((entrada / "texto.txt").exists())

            # Se rodar de novo, não deve baixar nada pois estão no set PROCESSADAS_S3
            downloads.clear()
            with patch.dict(os.environ, {
                "AWS_ACCESS_KEY_ID": "fake-access",
                "AWS_SECRET_ACCESS_KEY": "fake-secret",
                "AWS_REGION": "us-east-1",
                "S3_BUCKET": "fake-bucket",
            }, clear=False):
                with patch("galeria_monitor.boto3.client", return_value=FakeS3Client()):
                    galeria_monitor.baixar_novas_imagens_s3(
                        entrada,
                        log_callback=lambda msg: None,
                    )
            
            self.assertEqual(len(downloads), 0)

if __name__ == "__main__":
    unittest.main()
