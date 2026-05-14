#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitora uma pasta de entrada, cria versões com/sem moldura e
alimenta a pasta MOSAIC para gerar os vídeos de mosaico automaticamente.

Imagens com lado maior que MAX_LADO_PIXELS_MOSAICO sao reduzidas antes de gravar
em MOSAIC/com_moldura/sem_moldura; a copia em originais mantem o ficheiro integral.
"""

import time
import threading
import shutil
import secrets
from pathlib import Path
from PIL import Image, ImageOps

from criar_video_album import gerar_todos_os_videos


PASTA_MOSAIC = Path("MOSAIC")

EXTENSOES_SUPORTADAS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".png",
    ".bmp",
    ".webp",
    ".jfif",
    ".tif",
    ".tiff",
    ".heic",
}
INTERVALO_MONITORAMENTO = 0.7
# Apos a ultima foto processada, espera este silencio antes de gerar video (evita N geracoes em rajada).
DEBOUNCE_GERACAO_VIDEO_S = 3.5
MOLDURA_PIXELS = 20
COR_MOLDURA = (255, 255, 255)

# Maior lado em pixels ao gravar variantes no disco (MOSAIC, com/sem moldura). 0 = sem limite.
# Originais continuam com copia integral do ficheiro de entrada. Reduz I/O, browser e geracao de video.
MAX_LADO_PIXELS_MOSAICO = 1920

# Subpastas geradas/usadas pelo proprio sistema — nao devem ser monitoradas.
SUBPASTAS_INTERNAS = {"com_moldura", "sem_moldura", "originais"}

# Numero de varreduras seguidas em que o arquivo precisa aparecer estavel
# (mesmo tamanho e mesma mtime) para ser considerado pronto. Garantia contra
# capturas grandes via tether (Canon EOS Utility, Lightroom etc) que ainda
# estao terminando de escrever no disco.
ESTAVEL_VARREDURAS_NECESSARIAS = 2


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


def _redimensionar_se_muito_grande(img: Image.Image, max_lado: int) -> Image.Image:
    if max_lado <= 0:
        return img
    w, h = img.size
    m = max(w, h)
    if m <= max_lado:
        return img
    ratio = max_lado / m
    nw = max(1, int(round(w * ratio)))
    nh = max(1, int(round(h * ratio)))
    return img.resize((nw, nh), Image.Resampling.BICUBIC)


def _kwargs_save(extensao: str) -> dict:
    e = extensao.lower()
    if e in (".jpg", ".jpeg", ".jpe", ".jfif"):
        return {"quality": 90, "optimize": True}
    if e == ".webp":
        return {"quality": 88, "method": 4}
    return {}


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

        img = _redimensionar_se_muito_grande(img, MAX_LADO_PIXELS_MOSAICO)

        extensao = caminho_imagem.suffix.lower() or ".jpg"
        nome_img = f"img{indice_img}{extensao}"

        skw = _kwargs_save(extensao)

        destino_sem_moldura = pasta_sem_moldura / nome_img
        img.save(destino_sem_moldura, **skw)

        destino_com_moldura = None
        if aplicar_moldura:
            imagem_com_moldura = ImageOps.expand(img, border=MOLDURA_PIXELS, fill=COR_MOLDURA)
            destino_com_moldura = pasta_com_moldura / nome_img
            imagem_com_moldura.save(destino_com_moldura, **skw)

        destino_mosaic = PASTA_MOSAIC / nome_img
        img.save(destino_mosaic, **skw)

    destino_original = pasta_originais / nome_img
    try:
        shutil.copy2(str(caminho_imagem), str(destino_original))
    except Exception:
        destino_original = None

    log(f"✅ Processada: {caminho_imagem.name}")
    log(f"   • Sem moldura: {destino_sem_moldura}")
    if destino_com_moldura:
        log(f"   • Com moldura: {destino_com_moldura}")
    else:
        log("   • Com moldura: desativado")
    log("   • Original mantida na pasta monitorada")
    if destino_original is not None:
        log(f"   • Copia em originais: {destino_original}")
    log(f"   • Enviada ao mosaico: {destino_mosaic}")
    return destino_mosaic


def injetar_ficheiros(
    pasta_entrada: str | Path,
    ficheiros: list[str | Path],
    aplicar_moldura: bool = True,
    intervalo_s: float = 0.0,
    log_callback=None,
    nova_imagem_callback=None,
) -> tuple[int, int]:
    """
    Processa ficheiros como se tivessem entrado na pasta monitorada (MOSAIC + com/sem moldura + originais).
    intervalo_s > 0: garante pelo menos esse intervalo (em segundos) entre o fim de uma injecao
        bem-sucedida e o inicio da seguinte.
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    pasta_entrada_path = Path(pasta_entrada)
    pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais = _resolver_estrutura_galeria(
        pasta_entrada_path
    )
    garantir_pastas(pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais)
    proximo_indice = _proximo_indice_img(pasta_com_moldura, pasta_sem_moldura, pasta_originais, PASTA_MOSAIC)
    ok = 0
    falhas = 0
    ultima_ok_mon = 0.0
    for caminho in ficheiros:
        if intervalo_s > 0 and ultima_ok_mon > 0.0:
            falta = intervalo_s - (time.monotonic() - ultima_ok_mon)
            if falta > 0:
                time.sleep(falta)
        p = Path(caminho)
        if not p.is_file() or p.suffix.lower() not in EXTENSOES_SUPORTADAS:
            log(f"Ignorado (nao suportado ou nao e ficheiro): {p}")
            falhas += 1
            continue
        try:
            destino_mosaic = processar_imagem(
                p,
                pasta_com_moldura,
                pasta_sem_moldura,
                pasta_originais,
                aplicar_moldura=aplicar_moldura,
                indice_img=proximo_indice,
                log_callback=log_callback,
            )
            proximo_indice += 1
            ok += 1
            ultima_ok_mon = time.monotonic()
            if nova_imagem_callback:
                nova_imagem_callback(str(destino_mosaic))
        except Exception as exc:
            log(f"Erro ao injetar {p.name}: {exc}")
            falhas += 1
    log(f"Injecao: {ok} ok, {falhas} falha(s).")
    return ok, falhas


def listar_novas_imagens(
    pasta_entrada: Path,
    processadas: set[str],
    pendentes: dict[str, tuple[int, int, int]] | None = None,
) -> list[Path]:
    """
    Lista arquivos prontos para processar. Um arquivo so e considerado
    "pronto" quando aparece com o mesmo tamanho e mesma mtime em
    ESTAVEL_VARREDURAS_NECESSARIAS varreduras consecutivas.

    Isso evita pegar arquivos ainda sendo escritos por outras ferramentas
    (Canon EOS Utility, drivers de tether, sync de bucket, etc).
    """
    pendentes = pendentes if pendentes is not None else {}
    imagens: list[Path] = []
    vistos_agora: set[str] = set()

    for caminho in sorted(pasta_entrada.iterdir()):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
            continue

        try:
            stat_atual = caminho.stat()
        except (FileNotFoundError, PermissionError):
            continue

        try:
            chave = str(caminho.resolve())
        except Exception:
            chave = str(caminho)
        vistos_agora.add(chave)

        assinatura = f"{chave}::{stat_atual.st_mtime_ns}"
        if assinatura in processadas:
            continue

        anterior = pendentes.get(chave)
        if (
            anterior is not None
            and anterior[0] == stat_atual.st_size
            and anterior[1] == stat_atual.st_mtime_ns
        ):
            estaveis = anterior[2] + 1
        else:
            estaveis = 1

        if estaveis >= ESTAVEL_VARREDURAS_NECESSARIAS:
            imagens.append(caminho)
            pendentes.pop(chave, None)
        else:
            pendentes[chave] = (stat_atual.st_size, stat_atual.st_mtime_ns, estaveis)

    # Remove entradas pendentes para arquivos que sumiram (renomeio/movido).
    for chave in list(pendentes.keys()):
        if chave not in vistos_agora:
            pendentes.pop(chave, None)

    return imagens


def monitorar_e_gerar(
    pasta_entrada: str | Path = "Galeria/entrada",
    aplicar_moldura: bool = True,
    modo_rapido: bool = True,
    stop_event: threading.Event | None = None,
    log_callback=None,
    status_callback=None,
    nova_imagem_callback=None,
    pausa_entre_fotos_s: float = 2.0,
    renomear_entrada_aleatorio: bool = True,
    debounce_geracao_video_s: float = DEBOUNCE_GERACAO_VIDEO_S,
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
    debounce_geracao_video_s = max(0.5, float(debounce_geracao_video_s))
    pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais = _resolver_estrutura_galeria(
        pasta_entrada_path
    )

    garantir_pastas(pasta_entrada_path, pasta_com_moldura, pasta_sem_moldura, pasta_originais)
    processadas: set[str] = set()
    pendentes: dict[str, tuple[int, int, int]] = {}
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
    log(f"⏱️ Pausa minima entre fotos (apos cada processamento com sucesso): {pausa_entre_fotos_s:.1f} s")
    log(f"🔤 Copia com nome aleatorio antes de processar: {'Sim' if renomear_entrada_aleatorio else 'Nao'} (evita bloquear com o mesmo nome de ficheiro)")
    log(f"⏱️ Debounce geracao de video: {debounce_geracao_video_s:.1f} s apos a ultima foto (menos carga na CPU)")
    log("\nAguardando novas imagens... (Ctrl+C para parar)\n")

    def worker_geracao():
        while not stop_signal.is_set():
            houve_sinal = gerar_evento.wait(timeout=0.5)
            if not houve_sinal:
                continue

            gerar_evento.clear()
            geracao_em_andamento.set()
            update_status("Gerando mosaico")
            log("\n🎞️ Geracao de video a iniciar (modo sequencial, menos carga na CPU)...")
            try:
                nomes_videos = ["Mosaico_Pixel_1680x1176.mp4"] if modo_rapido else None
                # Sequencial = menos picos de CPU; debounce no loop principal ja reduz chamadas.
                gerar_todos_os_videos(nomes_videos=nomes_videos, paralelo=False)
                log("✅ Mosaicos atualizados com sucesso.\n")
            except Exception as exc:
                log(f"❌ Falha ao gerar mosaicos: {exc}\n")
            finally:
                geracao_em_andamento.clear()
                if not stop_signal.is_set():
                    update_status("Monitorando")

    thread_geracao = threading.Thread(target=worker_geracao, daemon=True)
    thread_geracao.start()

    ultima_atividade_processamento = 0.0
    ultima_injecao_mon = 0.0
    try:
        while not stop_signal.is_set():
            novas = listar_novas_imagens(pasta_entrada_path, processadas, pendentes)
            houve_processamento = False

            for caminho in novas:
                if pausa_entre_fotos_s > 0 and not stop_signal.is_set() and ultima_injecao_mon > 0.0:
                    falta = pausa_entre_fotos_s - (time.monotonic() - ultima_injecao_mon)
                    if falta > 0:
                        time.sleep(falta)
                temp_copy: Path | None = None
                sucesso_neste = False
                try:
                    assinatura = f"{caminho.resolve()}::{caminho.stat().st_mtime_ns}"
                    process_path = caminho
                    if renomear_entrada_aleatorio:
                        suf = caminho.suffix.lower() or ".jpg"
                        temp_copy = pasta_entrada_path / f"_in_{secrets.token_hex(8)}{suf}"
                        try:
                            shutil.copy2(caminho, temp_copy)
                            process_path = temp_copy
                            log(
                                f"Copia temporaria com nome aleatorio ({temp_copy.name}) — "
                                "o ficheiro original na pasta fica intacto e evita bloqueio com o mesmo nome."
                            )
                        except OSError as exc:
                            log(f"Aviso: nao foi possivel copiar para nome aleatorio ({exc}); a processar o original.")
                            temp_copy = None
                            process_path = caminho

                    destino_mosaic = processar_imagem(
                        process_path,
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
                    sucesso_neste = True
                    ultima_injecao_mon = time.monotonic()
                except Exception as exc:
                    log(f"❌ Erro ao processar {caminho.name}: {exc}")
                finally:
                    if temp_copy is not None:
                        try:
                            if temp_copy.exists():
                                temp_copy.unlink()
                        except OSError:
                            pass

            if houve_processamento:
                if geracao_em_andamento.is_set():
                    log(
                        "🕒 Novas imagens durante a geracao de video — "
                        "a atualizacao ficara para depois da pausa (debounce)."
                    )
                ultima_atividade_processamento = time.monotonic()

            if (
                ultima_atividade_processamento > 0.0
                and not geracao_em_andamento.is_set()
                and (time.monotonic() - ultima_atividade_processamento) >= debounce_geracao_video_s
            ):
                log(
                    f"⏱️ Sem novas fotos ha {debounce_geracao_video_s:.0f} s — "
                    "a agendar geracao de video (um lote)."
                )
                gerar_evento.set()
                ultima_atividade_processamento = 0.0

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
