#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitora uma pasta de entrada, cria versões com/sem moldura e
alimenta a pasta MOSAIC para gerar os vídeos de mosaico automaticamente.
"""

import time
import threading
import shutil
from pathlib import Path
from PIL import Image, ImageOps

from criar_video_album import gerar_todos_os_videos


PASTA_MOSAIC = Path("MOSAIC")

EXTENSOES_SUPORTADAS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}
INTERVALO_MONITORAMENTO = 2
MOLDURA_PIXELS = 20
COR_MOLDURA = (255, 255, 255)


def garantir_pastas(
    pasta_entrada: Path,
    pasta_com_moldura: Path,
    pasta_sem_moldura: Path,
    pasta_originais: Path,
):
    for pasta in (pasta_entrada, pasta_com_moldura, pasta_sem_moldura, pasta_originais, PASTA_MOSAIC):
        pasta.mkdir(parents=True, exist_ok=True)


def gerar_nome_unico(pasta_destino: Path, nome_base: str) -> Path:
    destino = pasta_destino / nome_base
    if not destino.exists():
        return destino

    stem = Path(nome_base).stem
    suffix = Path(nome_base).suffix
    contador = 1
    while True:
        candidato = pasta_destino / f"{stem}_{contador}{suffix}"
        if not candidato.exists():
            return candidato
        contador += 1


def _proximo_indice_img(*pastas: Path) -> int:
    """Retorna o próximo índice disponível no padrão imgN."""
    maior = 0
    for pasta in pastas:
        if not pasta.exists():
            continue
        for caminho in pasta.iterdir():
            if not caminho.is_file():
                continue
            stem = caminho.stem.lower()
            if stem.startswith("img") and stem[3:].isdigit():
                maior = max(maior, int(stem[3:]))
    return maior + 1


def _resolver_estrutura_galeria(pasta_entrada: Path) -> tuple[Path, Path, Path, Path]:
    """
    Resolve a estrutura padrão da galeria:
    - <monitorada>/com_moldura
    - <monitorada>/sem_moldura
    - <monitorada>/originais
    """
    pasta_entrada_real = pasta_entrada
    pasta_com_moldura = pasta_entrada_real / "com_moldura"
    pasta_sem_moldura = pasta_entrada_real / "sem_moldura"
    pasta_originais = pasta_entrada_real / "originais"
    return pasta_entrada_real, pasta_com_moldura, pasta_sem_moldura, pasta_originais


def processar_imagem(
    caminho_imagem: Path,
    pasta_com_moldura: Path,
    pasta_sem_moldura: Path,
    pasta_originais: Path,
    aplicar_moldura: bool,
    indice_img: int,
    log_callback=None,
):
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    with Image.open(caminho_imagem) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")

        extensao = caminho_imagem.suffix.lower() or ".jpg"
        nome_img = f"img{indice_img}{extensao}"

        destino_sem_moldura = pasta_sem_moldura / nome_img
        img.save(destino_sem_moldura)

        destino_com_moldura = None
        if aplicar_moldura:
            imagem_com_moldura = ImageOps.expand(img, border=MOLDURA_PIXELS, fill=COR_MOLDURA)
            destino_com_moldura = pasta_com_moldura / nome_img
            imagem_com_moldura.save(destino_com_moldura)

        destino_mosaic = PASTA_MOSAIC / nome_img
        img.save(destino_mosaic)

    destino_original = pasta_originais / nome_img
    try:
        shutil.move(str(caminho_imagem), str(destino_original))
    except Exception:
        destino_original = caminho_imagem

    log(f"✅ Processada: {caminho_imagem.name}")
    log(f"   • Sem moldura: {destino_sem_moldura}")
    if destino_com_moldura:
        log(f"   • Com moldura: {destino_com_moldura}")
    else:
        log("   • Com moldura: desativado")
    log(f"   • Original organizada em: {destino_original}")
    log(f"   • Enviada ao mosaico: {destino_mosaic}")
    return destino_mosaic


def listar_novas_imagens(pasta_entrada: Path, processadas: set[str]) -> list[Path]:
    imagens = []
    for caminho in sorted(pasta_entrada.iterdir()):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
            continue

        assinatura = f"{caminho.resolve()}::{caminho.stat().st_mtime_ns}"
        if assinatura not in processadas:
            imagens.append(caminho)

    return imagens


def monitorar_e_gerar(
    pasta_entrada: str | Path = "Galeria/entrada",
    aplicar_moldura: bool = True,
    modo_rapido: bool = True,
    stop_event: threading.Event | None = None,
    log_callback=None,
    status_callback=None,
    nova_imagem_callback=None,
):
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def update_status(msg: str):
        if status_callback:
            status_callback(msg)
        else:
            print(f"STATUS: {msg}")

    stop_signal = stop_event or threading.Event()
    gerar_evento = threading.Event()
    geracao_em_andamento = threading.Event()

    pasta_entrada_path = Path(pasta_entrada)
    pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais = _resolver_estrutura_galeria(pasta_entrada_path)

    garantir_pastas(pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais)
    processadas = set()
    proximo_indice = _proximo_indice_img(pasta_com_moldura, pasta_sem_moldura, pasta_originais, PASTA_MOSAIC)

    update_status("Monitorando")
    log("=" * 72)
    log("MONITORAMENTO ATIVO")
    log("=" * 72)
    log(f"📥 Pasta de entrada: {pasta_entrada_path.resolve()}")
    log(f"🗂️  Pasta base da galeria: {pasta_entrada_path.parent.resolve()}")
    log(f"🖼️  Saída sem moldura: {pasta_sem_moldura.resolve()}")
    log(f"🖼️  Saída com moldura: {pasta_com_moldura.resolve()}")
    log(f"🧾 Originais processadas: {pasta_originais.resolve()}")
    log(f"🎬 Pasta MOSAIC (fonte do vídeo): {PASTA_MOSAIC.resolve()}")
    log(f"🧩 Aplicar moldura: {'Sim' if aplicar_moldura else 'Nao'}")
    log(f"⚡ Modo rapido: {'Sim' if modo_rapido else 'Nao'}")
    log("\nAguardando novas imagens... (Ctrl+C para parar)\n")

    def worker_geracao():
        while not stop_signal.is_set():
            houve_sinal = gerar_evento.wait(timeout=0.5)
            if not houve_sinal:
                continue

            gerar_evento.clear()
            geracao_em_andamento.set()
            update_status("Gerando mosaico")
            log("\n🎞️ Geração de mosaico iniciada em paralelo...")
            try:
                nomes_videos = ["Mosaico_Pixel_1680x1176.mp4"] if modo_rapido else None
                gerar_todos_os_videos(nomes_videos=nomes_videos)
                log("✅ Mosaicos atualizados com sucesso.\n")
            except Exception as exc:
                log(f"❌ Falha ao gerar mosaicos: {exc}\n")
            finally:
                geracao_em_andamento.clear()
                if not stop_signal.is_set():
                    update_status("Monitorando")

    thread_geracao = threading.Thread(target=worker_geracao, daemon=True)
    thread_geracao.start()

    try:
        while not stop_signal.is_set():
            novas = listar_novas_imagens(pasta_entrada_path, processadas)
            houve_processamento = False

            for caminho in novas:
                try:
                    assinatura = f"{caminho.resolve()}::{caminho.stat().st_mtime_ns}"
                    destino_mosaic = processar_imagem(
                        caminho,
                        pasta_com_moldura,
                        pasta_sem_moldura,
                        pasta_originais,
                        aplicar_moldura=aplicar_moldura,
                        indice_img=proximo_indice,
                        log_callback=log,
                    )
                    proximo_indice += 1
                    if nova_imagem_callback:
                        nova_imagem_callback(str(destino_mosaic))
                    processadas.add(assinatura)
                    houve_processamento = True
                except Exception as exc:
                    log(f"❌ Erro ao processar {caminho.name}: {exc}")

            if houve_processamento:
                # Sinaliza geração sem bloquear o loop de monitoramento.
                # Se já estiver gerando, roda novamente ao término.
                if geracao_em_andamento.is_set():
                    log("🕒 Novas imagens chegaram durante a geração. Reagendando atualização.")
                gerar_evento.set()

            time.sleep(INTERVALO_MONITORAMENTO)
    finally:
        stop_signal.set()
        gerar_evento.set()
        thread_geracao.join(timeout=2)

    update_status("Parado")
    log("⏹️ Monitoramento encerrado.")


if __name__ == "__main__":
    try:
        monitorar_e_gerar()
    except KeyboardInterrupt:
        print("\n⏹️ Monitoramento encerrado.")
