"""
Prepara os cenários do evento a partir das artes entregues pelo cliente.

Cada arte é um PNG/JPG de tela cheia. A foto entra POR BAIXO da logo vazada:
cada losango do halftone é recortado no formato dele e vira uma janela; o fundo,
a malha entre um losango e outro e os textos ficam opacos por cima do mosaico.
É o desenho da marca que o cliente veio buscar — já se tentou abrir tudo o que
cai dentro do contorno para não sobrar quadro vazio, e a malha virou uma chapa
de fotos sem logo nenhum.

Para cada arte o script produz:

  * o overlay (PNG com alfa) — os losangos viram janela transparente, o resto
    continua opaco e é desenhado por cima do mosaico;
  * a grade: nas artes em halftone, a própria malha de losangos; nas de logo
    chapado, a grade quase quadrada que melhor cobre o logo com ~250 células;
  * a lista de células do logo e a pintura de cada uma: as do vermelho saem
    tingidas, as do branco saem claras.

Roda uma vez, quando o cliente manda arte nova:

    python tools/preparar_cenarios.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "fundos"
DESTINO = RAIZ / "backend" / "storage" / "cenarios"

# Quantas células de foto o cliente quer ver dentro do logo.
ALVO_CELULAS = 250
# Quanto a célula pode fugir do quadrado antes de a foto começar a distorcer.
PROPORCAO_MIN, PROPORCAO_MAX = 0.88, 1.14
# Fração do ladrilho que precisa estar sobre o logo para a célula valer.
COBERTURA_MINIMA = 0.5
# Fração da célula da malha que a janela do losango precisa ocupar para a célula
# receber foto. O losango cheio fica perto de 0,85; o vizinho que só pega a ponta
# de um losango ao lado não passa de 0,3.
COBERTURA_LOSANGO = 0.45


def separar_regioes(img_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    (vermelho, branco chapado, claro cru) do logo.

    Nem todo branco da arte é logo. Também são brancos os TEXTOS e as tarjas que
    algumas artes trazem coladas na borda de cima e de baixo. Se qualquer um dos
    dois entrasse, "HSBC Brazil Decade" e as tarjas virariam célula de foto.

    O que separa é a forma: a chapa do logo é grande NOS DOIS eixos. Letra falha
    na área; tarja é larguíssima e baixa, e falha na altura.

    O claro cru sai junto porque nas artes de miolo picotado não existe chapa
    nenhuma para achar aqui — quem separa losango de texto lá é `losangos_claros`,
    pelo tamanho.
    """
    b, g, r = (img_bgr[:, :, i].astype(np.int16) for i in range(3))
    vermelho = (r > 110) & (g < 90) & (b < 90)
    claro_mask = ((r > 170) & (g > 170) & (b > 170))
    claro = claro_mask.astype(np.uint8)

    altura, largura = claro.shape
    quantidade, rotulos, stats, _ = cv2.connectedComponentsWithStats(claro, 8)
    branco = np.zeros_like(claro, dtype=bool)
    for i in range(1, quantidade):
        area = stats[i, cv2.CC_STAT_AREA]
        larg = stats[i, cv2.CC_STAT_WIDTH]
        alt = stats[i, cv2.CC_STAT_HEIGHT]
        if area > largura * altura * 0.02 and larg > largura * 0.05 and alt > altura * 0.05:
            branco |= rotulos == i
    return vermelho, branco, claro_mask


def melhor_grade(logo: np.ndarray, caixa: tuple[int, int, int, int]) -> tuple[int, int]:
    """(rows, cols) que chega mais perto de ALVO_CELULAS mantendo a célula quadrada."""
    x0, y0, gw, gh = caixa
    candidatos = []
    for rows in range(8, 22):
        for cols in range(14, 40):
            tw, th = gw / cols, gh / rows
            if not (PROPORCAO_MIN <= tw / th <= PROPORCAO_MAX):
                continue
            dentro = sum(
                1
                for r in range(rows)
                for c in range(cols)
                if logo[int(y0 + r * th):int(y0 + (r + 1) * th),
                        int(x0 + c * tw):int(x0 + (c + 1) * tw)].mean() >= COBERTURA_MINIMA
            )
            candidatos.append((abs(dentro - ALVO_CELULAS), rows, cols, dentro))
    if not candidatos:
        raise ValueError("Nenhuma grade quadrada cabe nesta arte.")
    _, rows, cols, dentro = min(candidatos)
    print(f"      grade {rows}x{cols} -> {dentro} células no logo")
    return rows, cols


def _centroides(mascara: np.ndarray, area_minima: int = 40) -> np.ndarray:
    quantidade, _, stats, centros = cv2.connectedComponentsWithStats(mascara.astype(np.uint8), 8)
    return np.array([
        centros[i] for i in range(1, quantidade)
        if stats[i, cv2.CC_STAT_AREA] >= area_minima
    ])


def _area_tipica(mascara: np.ndarray, area_minima: int = 40) -> float:
    quantidade, _, stats, _ = cv2.connectedComponentsWithStats(mascara.astype(np.uint8), 8)
    areas = [
        stats[i, cv2.CC_STAT_AREA] for i in range(1, quantidade)
        if stats[i, cv2.CC_STAT_AREA] >= area_minima
    ]
    return float(np.median(areas)) if areas else 0.0


def losangos_claros(claro: np.ndarray, area_referencia: float, casco: np.ndarray) -> np.ndarray:
    """
    Os losangos CLAROS da malha, quando o miolo do logo também vem picotado.

    Nas artes em que o miolo é branco chapado, `separar_regioes` acha a chapa e
    o assunto morre ali. Nestas aqui não existe chapa nenhuma: o branco também é
    uma malha de centenas de losangos do mesmo tamanho dos vermelhos. Nenhum
    deles passa no filtro de bloco grande, `branco` sai vazio, e o miolo do logo
    ficava sem janela — foto atrás de tinta opaca.

    Dois filtros, e os dois são necessários. A ÁREA descarta a tarja da borda,
    grande demais, e o respingo de antisserrilhado, pequeno demais. Mas letra
    graúda tem o tamanho de um losango: só pelo tamanho, o "B" de "Brazil" e o
    "C" de "HSBC" viravam janela e apareciam com foto dentro. O que resolve é o
    LUGAR — losango mora dentro do contorno da malha vermelha, texto mora fora.
    """
    if area_referencia <= 0 or casco is None:
        return np.zeros(claro.shape, dtype=bool)
    quantidade, rotulos, stats, centros = cv2.connectedComponentsWithStats(claro.astype(np.uint8), 8)
    escolhidos = np.zeros(claro.shape, dtype=bool)
    for i in range(1, quantidade):
        area = stats[i, cv2.CC_STAT_AREA]
        if not (0.3 * area_referencia <= area <= 3.0 * area_referencia):
            continue
        if cv2.pointPolygonTest(casco, (float(centros[i][0]), float(centros[i][1])), False) < 0:
            continue
        escolhidos |= rotulos == i
    return escolhidos


def grade_do_halftone(vermelho: np.ndarray, branco: np.ndarray, claro: np.ndarray) -> dict | None:
    """
    Grade casada com a MALHA de losangos, para artes em halftone.

    Aqui o logo não é uma chapa: são centenas de losangos soltos numa malha em
    quincôncio — cada linha deslocada meio passo em relação à de cima. Procurar
    "a grade de ~250 quadrados" numa arte dessas daria células atravessando
    losangos pela metade. A malha já é a grade; o trabalho é descobrir o passo.

    Devolve None quando a arte não é halftone (poucos losangos soltos).
    """
    centros = _centroides(vermelho)
    if len(centros) < 50:
        return None

    # Miolo claro: a chapa (artes antigas) OU a malha de losangos brancos
    # (artes novas). As duas viram janela e recebem foto em cor original.
    casco = cv2.convexHull(centros.astype(np.float32).reshape(-1, 1, 2))
    claros = branco | losangos_claros(claro, _area_tipica(vermelho), casco)
    centros_c = _centroides(claros)

    # Agrupa por linha para medir os dois passos separadamente.
    ordenados = centros[np.argsort(centros[:, 1])]
    linhas: list[list] = [[ordenados[0]]]
    for ponto in ordenados[1:]:
        if ponto[1] - linhas[-1][-1][1] > 12:
            linhas.append([ponto])
        else:
            linhas[-1].append(ponto)
    linhas = [np.array(l) for l in linhas if len(l) >= 2]
    if len(linhas) < 3:
        return None

    passo_y = float(np.median(np.diff([l[:, 1].mean() for l in linhas])))
    passos_x = [np.median(np.diff(np.sort(l[:, 0]))) for l in linhas if len(l) > 3]
    # Em quincôncio o vão DENTRO da linha é o dobro do passo real da malha: a
    # linha de baixo cai justamente no meio. Usar o vão cheio como largura de
    # célula perderia metade dos losangos.
    passo_x = float(np.median(passos_x)) / 2.0

    x_min, y_min = float(centros[:, 0].min()), float(centros[:, 1].min())
    x0, y0 = x_min - passo_x / 2, y_min - passo_y / 2
    cols = int(round((centros[:, 0].max() - x_min) / passo_x)) + 1
    rows = int(round((centros[:, 1].max() - y_min) / passo_y)) + 1

    celulas: list[str] = []
    pintura: dict[str, str] = {}
    for cx, cy in centros:
        c = int(round((cx - x_min) / passo_x))
        r = int(round((cy - y_min) / passo_y))
        chave = f"{r}_{c}"
        if chave not in pintura:
            celulas.append(chave)
            pintura[chave] = "red"

    if len(centros_c):
        for cx, cy in centros_c:
            c = int(round((cx - x_min) / passo_x))
            r = int(round((cy - y_min) / passo_y))
            chave = f"{r}_{c}"
            if chave not in celulas:
                celulas.append(chave)

    # Losango que o centróide não viu: quem manda agora é a ÁREA da janela.
    #
    # Contar um centróide por componente perde os losangos que se encostam. O
    # antisserrilhado cola quatro, cinco vizinhos num borrão só, o borrão devolve
    # um centróide, e os outros ficam sem célula — foto nenhuma pousa neles pelo
    # evento inteiro. Na arte preta isso era metade da malha.
    #
    # Uma célula da malha é um losango: se a janela ocupa boa parte dela, ali
    # cabe foto, tenha o borrão dado centróide ou não. Os dois critérios se
    # somam, não se substituem — o centróide ainda é quem pega o losango
    # miúdo da ponta do degradê, pequeno demais para preencher a célula.
    objetos = vermelho | claros
    for r in range(rows):
        ya, yb = int(round(y0 + r * passo_y)), int(round(y0 + (r + 1) * passo_y))
        if yb <= 0 or ya >= objetos.shape[0]:
            continue
        for c in range(cols):
            chave = f"{r}_{c}"
            if chave in celulas:
                continue
            xa, xb = int(round(x0 + c * passo_x)), int(round(x0 + (c + 1) * passo_x))
            recorte = objetos[max(0, ya):yb, max(0, xa):xb]
            if recorte.size == 0 or recorte.mean() < COBERTURA_LOSANGO:
                continue
            celulas.append(chave)
            # Quem manda na cor é a tinta que ocupa a maior parte da janela.
            if vermelho[max(0, ya):yb, max(0, xa):xb].mean() > \
                    claros[max(0, ya):yb, max(0, xa):xb].mean():
                pintura[chave] = "red"

    # A chapa branca do logo (quando existe) também recebe foto: cada célula da
    # MESMA malha cujo centro cai dentro dela.
    #
    # E só. Já se tentou abrir TODA célula dentro do contorno do logo, para não
    # sobrar quadro vazio — e o preço foi a marca: com tudo aberto o losango
    # deixa de existir, a malha vira uma chapa de fotos e o cliente perde o
    # desenho que veio buscar. A foto fica ATRÁS da logo vazada; o respiro entre
    # um losango e outro é a própria arte, não um buraco a tapar.
    for r in range(rows):
        for c in range(cols):
            chave = f"{r}_{c}"
            if chave in pintura:
                continue
            cy, cx = int(y0 + (r + 0.5) * passo_y), int(x0 + (c + 0.5) * passo_x)
            if 0 <= cy < branco.shape[0] and 0 <= cx < branco.shape[1] and branco[cy, cx]:
                if chave not in celulas:
                    celulas.append(chave)

    print(f"      malha {rows}x{cols} passo {passo_x:.1f}x{passo_y:.1f}px -> {len(celulas)} células "
          f"({len(pintura)} losangos vermelhos, {len(celulas) - len(pintura)} claras)")
    return {
        "rows": rows,
        "cols": cols,
        "gridOffsetX": int(round(x0)),
        "gridOffsetY": int(round(y0)),
        "gridWidth": int(round(cols * passo_x)),
        "gridHeight": int(round(rows * passo_y)),
        "customMaskCells": celulas,
        "cellFilters": pintura,
        "objetos": vermelho | claros,
    }


def identificador(nome: str) -> str:
    """Nome de arquivo do cliente vira um id estável e sem surpresa."""
    base = re.sub(r"\.(png|jpe?g)$", "", nome, flags=re.I)
    base = re.sub(r"[^0-9a-zA-Z]+", "_", base).strip("_").lower()
    return base


def preparar(caminho: Path) -> dict:
    img = cv2.imread(str(caminho))
    if img is None:
        raise ValueError(f"Arte ilegível: {caminho}")
    altura, largura = img.shape[:2]
    print(f"   {caminho.name}  {largura}x{altura}")

    vermelho, branco, claro_mask = separar_regioes(img)
    # `branco`, a chapa filtrada — não `claro_mask`. Todo pixel claro da arte
    # inclui os TEXTOS, e com eles dentro do logo a caixa da grade esticava até
    # a borda da tela e as letras viravam janela de foto.
    logo = vermelho | branco

    ys, xs = np.where(logo)
    if not len(xs):
        raise ValueError(f"Não achei o logo em {caminho.name}")

    x0, y0 = int(xs.min()), int(ys.min())
    gw, gh = int(xs.max() - x0 + 1), int(ys.max() - y0 + 1)

    # Arte em halftone: a malha de losangos JÁ é a grade. Procurar quadrados de
    # ~250 numa arte dessas partiria losangos ao meio.
    malha = grade_do_halftone(vermelho, branco, claro_mask)
    if malha is not None:
        rows, cols = malha["rows"], malha["cols"]
        x0, y0 = malha["gridOffsetX"], malha["gridOffsetY"]
        gw, gh = malha["gridWidth"], malha["gridHeight"]
        celulas, pintura = malha["customMaskCells"], malha["cellFilters"]

        # Vazado: só os objetos do logo viram janela — cada losango recortado no
        # seu próprio formato. O fundo, a malha entre os losangos e os TEXTOS
        # continuam opacos por cima do mosaico. Aqui entram os objetos que a
        # malha já separou, NÃO `claro_mask`, que é todo pixel claro da arte:
        # com o cru, as letras viravam janela e as fotos apareciam dentro delas.
        alfa = np.where(malha["objetos"], 0, 255).astype(np.uint8)
        DESTINO.mkdir(parents=True, exist_ok=True)
        nome = f"{identificador(caminho.name)}.png"
        cv2.imwrite(str(DESTINO / nome), np.dstack([img, alfa]))
        return {
            "id": identificador(caminho.name),
            "rotulo": f"{caminho.stem.strip()} · {largura}x{altura}",
            "arquivo": nome,
            "screenWidth": largura,
            "screenHeight": altura,
            "rows": rows,
            "cols": cols,
            "gridOffsetX": x0,
            "gridOffsetY": y0,
            "gridWidth": gw,
            "gridHeight": gh,
            "customMaskCells": celulas,
            "cellFilters": pintura,
            "celulasNoLogo": len(celulas),
            "celulasVermelhas": len(pintura),
            "celulasClaras": len(celulas) - len(pintura),
        }

    logo_grade = logo.copy()
    is_camada_1 = "camada 1" in caminho.name.lower()
    vermelho_original = vermelho.copy() if is_camada_1 else None
    
    if is_camada_1:
        # Camada 1: Logo tem losangos pequenos que não dão 50% de cobertura.
        # Usa convex hull para fechar o shape e achar a grade.
        contornos, _ = cv2.findContours(vermelho.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contornos:
            hull = cv2.convexHull(np.vstack(contornos))
            lg_uint8 = logo_grade.astype(np.uint8)
            cv2.drawContours(lg_uint8, [hull], -1, 1, -1)
            logo_grade = lg_uint8 > 0

    rows, cols = melhor_grade(logo_grade, (x0, y0, gw, gh))
    tw, th = gw / cols, gh / rows

    celulas: list[str] = []
    pintura: dict[str, str] = {}
    for r in range(rows):
        ya, yb = int(y0 + r * th), int(y0 + (r + 1) * th)
        for c in range(cols):
            xa, xb = int(x0 + c * tw), int(x0 + (c + 1) * tw)
            if logo_grade[ya:yb, xa:xb].mean() < COBERTURA_MINIMA:
                continue
            chave = f"{r}_{c}"
            celulas.append(chave)
            # Quem manda na cor é a região que ocupa a MAIOR parte da célula.
            # Usa o vermelho original para contar
            if vermelho[ya:yb, xa:xb].mean() > 0.05:
                pintura[chave] = "red"

    # Overlay: o logo vira janela; fundo e textos continuam opacos por cima do
    # mosaico. Borda afiada para garantir que a cor das células fique forte até o limite.
    alfa = np.where(logo, 0, 255).astype(np.uint8)
    if is_camada_1:
        # Usa os diamantes originais (vermelho_original) para abrir os recortes exatos.
        # Mas no meio onde queremos as claras, não temos diamantes na imagem original.
        # Então no meio, se não abrirmos nada, ficará preto.
        # Espera, a imagem original tem um grid? 
        # Sim, o usuário quer que os buracos fiquem vazados exatamente no formato do logo.
        # Vamos manter o alfa apenas nos losangos vermelhos originais, e criar losangos artificiais no meio?
        # Ou simplesmente usar o vermelho original para a máscara inteira? 
        # "tirar o fundo igual fez com a camada 0": A Camada 0 tinha as janelas prontas.
        alfa = np.where(vermelho_original, 0, 255).astype(np.uint8)
        
    overlay = np.dstack([img, alfa])

    DESTINO.mkdir(parents=True, exist_ok=True)
    nome = f"{identificador(caminho.name)}.png"
    cv2.imwrite(str(DESTINO / nome), overlay)

    return {
        "id": identificador(caminho.name),
        "rotulo": f"{caminho.stem.strip()} · {largura}x{altura}",
        "arquivo": nome,
        "screenWidth": largura,
        "screenHeight": altura,
        "rows": rows,
        "cols": cols,
        "gridOffsetX": x0,
        "gridOffsetY": y0,
        "gridWidth": gw,
        "gridHeight": gh,
        "customMaskCells": celulas,
        "cellFilters": pintura,
        "celulasNoLogo": len(celulas),
        "celulasVermelhas": len(pintura),
        "celulasClaras": len(celulas) - len(pintura),
    }


def main():
    if not ORIGEM.exists():
        raise SystemExit(f"Pasta das artes não encontrada: {ORIGEM}")

    cenarios = []
    for caminho in sorted(ORIGEM.iterdir()):
        if caminho.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        cenarios.append(preparar(caminho))

    manifesto = DESTINO / "cenarios.json"

    # Cenário cuja arte saiu de `fundos/` continua no painel enquanto o overlay
    # dele estiver no disco.
    #
    # A pasta é área de trabalho: o cliente manda arte nova, alguém limpa o que
    # não usa mais. Regerar do zero fazia esse faxina apagar do painel cenários
    # que ainda rodavam — sem aviso, e sem como refazer, porque o original já
    # tinha ido embora.
    if manifesto.exists():
        try:
            anteriores = json.loads(manifesto.read_text(encoding="utf-8")).get("cenarios", [])
        except (OSError, json.JSONDecodeError):
            anteriores = []
        gerados = {c["id"] for c in cenarios}
        for antigo in anteriores:
            if antigo.get("id") in gerados:
                continue
            if not (DESTINO / antigo.get("arquivo", "")).exists():
                continue
            cenarios.append(antigo)
            print(f"   {antigo['id']:<26} preservado (arte fora de fundos/)")

    manifesto.write_text(json.dumps({"cenarios": cenarios}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(cenarios)} cenário(s) em {manifesto}")
    for c in cenarios:
        print(f"   {c['id']:<26} {c['rows']}x{c['cols']} | {c['celulasNoLogo']} células "
              f"({c['celulasVermelhas']} vermelhas, {c['celulasClaras']} claras)")


if __name__ == "__main__":
    main()
