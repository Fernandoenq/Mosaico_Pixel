#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes de upload S3 no monitoramento de imagens."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import galeria_monitor  # noqa: E402


class S3UploadMonitorTests(unittest.TestCase):
    def test_processar_imagem_uploads_saidas_para_s3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mosaic_upload_test_") as tmp:
            tmp_path = Path(tmp)
            entrada = tmp_path / "entrada"
            pasta_com = entrada / "com_moldura"
            pasta_sem = entrada / "sem_moldura"
            pasta_orig = entrada / "originais"
            mosaic_dir = tmp_path / "MOSAIC"
            for folder in (entrada, pasta_com, pasta_sem, pasta_orig, mosaic_dir):
                folder.mkdir(parents=True, exist_ok=True)

            imagem = tmp_path / "fonte.jpg"
            Image.new("RGB", (150, 200), color="red").save(imagem)

            uploaded = []

            class FakeS3Client:
                def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
                    uploaded.append({
                        "Filename": Filename,
                        "Bucket": Bucket,
                        "Key": Key,
                        "ExtraArgs": ExtraArgs,
                    })

            with patch.object(galeria_monitor, "PASTA_MOSAIC", mosaic_dir):
                with patch.dict(os.environ, {
                    "AWS_ACCESS_KEY_ID": "fake-access",
                    "AWS_SECRET_ACCESS_KEY": "fake-secret",
                    "AWS_REGION": "us-east-1",
                    "S3_BUCKET": "fake-bucket",
                }, clear=False):
                    with patch("galeria_monitor.boto3.client", return_value=FakeS3Client()) as mocked_client:
                        destino_mosaic = galeria_monitor.processar_imagem(
                            imagem,
                            pasta_com,
                            pasta_sem,
                            pasta_orig,
                            aplicar_moldura=True,
                            indice_img=1,
                            log_callback=lambda msg: None,
                        )

            self.assertEqual(destino_mosaic, mosaic_dir / "img1.jpg")
            self.assertEqual(len(uploaded), 3)
            self.assertEqual(mocked_client.call_count, 3)

            uploaded_filenames = {item["Filename"] for item in uploaded}
            self.assertIn(str(pasta_sem / "img1.jpg"), uploaded_filenames)
            self.assertIn(str(pasta_com / "img1.jpg"), uploaded_filenames)
            self.assertIn(str(mosaic_dir / "img1.jpg"), uploaded_filenames)


if __name__ == "__main__":
    unittest.main()
