"""
Limpeza geral entre um evento e outro.

O que some: fotos. O que fica: a configuração e os arquivos da marca — overlay,
imagem-base, fallbacks e vídeos já exportados. Zerar o visual junto obrigaria a
refazer todo o encaixe da grade antes do próximo evento, que é justamente o
trabalho que não dá para repetir com o cliente esperando.

Nada aqui é reversível. Quem chama tem que ter certeza.
"""

import os
import shutil
from pathlib import Path


def _apagar_conteudo(pasta: Path) -> tuple[int, int]:
    """Esvazia a pasta mantendo ela mesma. Devolve (arquivos, bytes)."""
    if not pasta.exists():
        return 0, 0

    arquivos = bytes_ = 0
    for item in list(pasta.iterdir()):
        if item.is_dir():
            conteudo = [f for f in item.rglob("*") if f.is_file()]
            tamanho = sum(f.stat().st_size for f in conteudo)
            quantidade = len(conteudo)
        else:
            tamanho = item.stat().st_size
            quantidade = 1
        try:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
        except OSError:
            # Arquivo em uso (o telão pode estar servindo um ladrilho agora).
            # Não é motivo para abortar o resto da limpeza.
            continue
        arquivos += quantidade
        bytes_ += tamanho
    return arquivos, bytes_


def limpar_disco(storage_dir: Path, galeria_dir: Path | None, incluir_galeria: bool) -> dict:
    """Esvazia hot folder, ladrilhos, galeria e o registro de chaves do S3."""
    relatorio: dict[str, dict] = {}

    for nome, pasta in (("hot_folder", storage_dir / "hot_folder"), ("tiles", storage_dir / "tiles")):
        arquivos, bytes_ = _apagar_conteudo(pasta)
        relatorio[nome] = {"arquivos": arquivos, "mb": round(bytes_ / 1e6, 1)}

    if incluir_galeria and galeria_dir is not None:
        arquivos, bytes_ = _apagar_conteudo(galeria_dir)
        relatorio["galeria"] = {"arquivos": arquivos, "mb": round(bytes_ / 1e6, 1)}

    return relatorio


def esvaziar_bucket() -> dict:
    """
    Apaga TODOS os objetos do bucket configurado no .env.

    Em lotes de 1000 porque é o teto de `delete_objects`, e relendo a listagem
    a cada volta: o bucket pode receber foto nova durante a limpeza.
    """
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return {"ok": False, "detalhe": "S3_BUCKET não configurado no .env"}

    import boto3

    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION"),
    )

    apagados = 0
    falhas: list[str] = []
    while True:
        pagina = s3.list_objects_v2(Bucket=bucket, MaxKeys=1000)
        chaves = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
        if not chaves:
            break
        resposta = s3.delete_objects(Bucket=bucket, Delete={"Objects": chaves, "Quiet": True})
        erros = resposta.get("Errors") or []
        falhas.extend(e.get("Key", "?") for e in erros)
        apagados += len(chaves) - len(erros)
        if erros and len(erros) == len(chaves):
            # Nenhuma chave saiu nesta volta: insistir só giraria para sempre.
            break

    restantes = s3.list_objects_v2(Bucket=bucket).get("KeyCount", 0)
    return {"ok": not falhas, "apagados": apagados, "restantes": restantes, "falhas": falhas[:5]}
