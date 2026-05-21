#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ponto de entrada principal do sistema.
Inicia o monitoramento da galeria e dispara a geração de mosaicos quando
novas imagens chegarem na pasta de entrada.
"""

from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from galeria_monitor import EXTENSOES_SUPORTADAS, injetar_ficheiros, monitorar_e_gerar
from live_mosaic_panel import LiveMosaicPanel
from simple_frontend import SimpleMosaicFrontend

_PROJECT_DIR = Path(__file__).resolve().parent


class GaleriaMonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mosaico Pic Brand")
        self.root.geometry("740x1040")
        self.root.minsize(680, 900)
        self.root.resizable(True, True)

        self.log_queue = queue.Queue()
        self.stop_event = None
        self.worker_thread = None

        self.pasta_var = tk.StringVar(value=str((Path.cwd() / "Galeria").resolve()))
        self.status_var = tk.StringVar(value="Status: Parado")
        self.log_var = tk.StringVar(value="Sistema pronto para iniciar.")
        self.summary_var = tk.StringVar(value="")
        self.sem_moldura_var = tk.BooleanVar(value=False)
        self.modo_rapido_var = tk.BooleanVar(value=True)
        self.painel_ao_vivo_var = tk.BooleanVar(value=True)
        self.reload_automatico_var = tk.BooleanVar(value=True)
        self.celula_var = tk.IntVar(value=90)
        # Espaço entre cada foto no painel ao vivo (ms) — evita travar a UI com rajadas.
        self.intervalo_mosaico_ms_var = tk.IntVar(value=360)
        self.animacao_var = tk.StringVar(value="Mosaic Fly-In")
        self.intensidade_animacao_var = tk.StringVar(value="Medio")
        # Navegador / gravacao: pastilha maior = menos celulas (~100-150 em Full HD com ~120 px).
        self.navegador_pastilha_px_var = tk.IntVar(value=56)
        self.navegador_grade_tela_cheia_var = tk.BooleanVar(value=True)
        # Desligado por defeito: composicao foto a foto; liga para grelha cheia no video.
        self.navegador_duplicar_grade_var = tk.BooleanVar(value=False)
        # Pausa entre fotos na injecao manual (painel / sensacao de ir largando).
        self.injecao_intervalo_ms_var = tk.IntVar(value=2000)
        # Vazio = usa a pasta monitorada; senao injeta nessa pasta (ex.: copiar para Galeria).
        self.injecao_pasta_destino_var = tk.StringVar(value="")
        # Moldura apenas na injecao manual (painel abaixo); o monitor usa sem_moldura_var a esquerda.
        self.injecao_aplicar_moldura_var = tk.BooleanVar(value=not self.sem_moldura_var.get())
        self._injecao_paths: list[Path] = []
        self._injecao_log_text: tk.Text | None = None
        self._injecao_lbl_count: ttk.Label | None = None
        self._injecao_btn_injetar: ttk.Button | None = None
        self._injecao_btn_automatica: ttk.Button | None = None
        self._injecao_auto_thread: threading.Thread | None = None
        self._injecao_auto_stop = threading.Event()
        # Monitor: pausa entre processar cada ficheiro novo na pasta; copia aleatoria evita bloqueio.
        self.pausa_entre_fotos_monitor_var = tk.IntVar(value=2)
        self.renomear_entrada_aleatoria_var = tk.BooleanVar(value=True)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.largura_painel_var = tk.IntVar(value=max(640, screen_w // 2))
        self.altura_painel_var = tk.IntVar(value=max(360, screen_h // 2))
        self.backdrop_var = tk.StringVar(
            value=self._arte_padrao(
                "fundo.jpg",
                "fundo_evento_1024x825.png",
                "backdrop.png",
                "fundobaixosemtexto.png",
                "fundobaixo.png",
            )
        )
        self.overlay_var = tk.StringVar(
            value=self._arte_padrao("logo.png", "overlay.png")
        )

        self.live_panel = None
        self.web_frontend = SimpleMosaicFrontend()
        self._ultima_assinatura_painel = None
        self._ultimo_backdrop_painel = None
        self._ultimo_overlay_painel = None
        self._ultimo_evento_imagem_ts = 0.0
        self._stagger_em_execucao = False
        self._idle_para_stagger_s = 3.5

        self._mosaic_pending = queue.Queue()
        self._mosaic_feeder_active = False
        self._mosaic_feed_after_id = None
        self._resumo_web_after_id = None

        self._configurar_estilo()
        self._build_ui()
        self._registrar_bindings()
        self._atualizar_resumo()
        self._sincronizar_frontend_web()
        self._iniciar_servidor_web(silent=True)
        self._poll_logs()
        self._auto_reload_tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configurar_estilo(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Root.TFrame", background="#0d0d0f")
        style.configure("Card.TFrame", background="#16181d", relief="flat")
        style.configure("Title.TLabel", background="#0d0d0f", foreground="#d9c9ff", font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabel", background="#16181d", foreground="#b99cff", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", background="#16181d", foreground="#a79ac8", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#0d0d0f", foreground="#efe9ff", font=("Segoe UI", 11, "bold"))
        style.configure("Log.TLabel", background="#1d1a28", foreground="#e2dcf8", padding=(10, 8))
        style.configure("App.TCheckbutton", background="#16181d", foreground="#d2d8e6", font=("Segoe UI", 10))
        style.map("App.TCheckbutton", background=[("active", "#16181d")], foreground=[("active", "#ffffff")])
        style.configure("App.TEntry", fieldbackground="#12151b", foreground="#f5f6fb", bordercolor="#2f3750", lightcolor="#2f3750", darkcolor="#2f3750")

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#7c3aed",
            foreground="#ffffff",
            borderwidth=0,
            padding=(14, 8),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#6d28d9"), ("pressed", "#5b21b6"), ("disabled", "#4a3f63")],
            foreground=[("disabled", "#cad2e4")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#2a2438",
            foreground="#efe9ff",
            borderwidth=0,
            padding=(12, 8),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#3a2f4d"), ("pressed", "#251f33"), ("disabled", "#1b1f27")],
            foreground=[("disabled", "#7f8aa3")],
        )

    def _build_ui(self):
        self.root.configure(bg="#0d0d0f")

        container = ttk.Frame(self.root, padding=18, style="Root.TFrame")
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(container, text="Mosaico Pic Brand", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text="Inicie o monitoramento e acompanhe o mosaico ao vivo com configuracao rapida.",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        action_bar = ttk.Frame(container, padding=(0, 2, 0, 8), style="Root.TFrame")
        action_bar.grid(row=2, column=0, sticky="ew")
        self.btn_iniciar = ttk.Button(
            action_bar, text="Iniciar monitoramento", style="Primary.TButton", command=self._iniciar_monitoramento
        )
        self.btn_iniciar.pack(side="left")
        self.btn_parar = ttk.Button(
            action_bar, text="Parar monitoramento", style="Secondary.TButton", command=self._parar_monitoramento, state="disabled"
        )
        self.btn_parar.pack(side="left", padx=8)
        self.btn_limpar = ttk.Button(
            action_bar, text="Limpar mosaico", style="Secondary.TButton", command=self._limpar_mosaico
        )
        self.btn_limpar.pack(side="left")

        scroll_outer = ttk.Frame(container, style="Root.TFrame")
        scroll_outer.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        scroll_outer.columnconfigure(0, weight=1)
        scroll_outer.rowconfigure(0, weight=1)

        self._main_scroll_canvas = tk.Canvas(
            scroll_outer,
            highlightthickness=0,
            borderwidth=0,
            bg="#0d0d0f",
        )
        self._main_scroll_vsb = ttk.Scrollbar(scroll_outer, orient="vertical", command=self._main_scroll_canvas.yview)
        self._main_scroll_canvas.configure(yscrollcommand=self._main_scroll_vsb.set)
        self._main_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self._main_scroll_vsb.grid(row=0, column=1, sticky="ns")

        scroll_inner = ttk.Frame(self._main_scroll_canvas, style="Root.TFrame")
        scroll_inner.columnconfigure(0, weight=1)
        self._main_scroll_window = self._main_scroll_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")

        def _on_scroll_inner_configure(_event=None):
            self._main_scroll_canvas.configure(scrollregion=self._main_scroll_canvas.bbox("all"))

        def _on_scroll_canvas_configure(event):
            self._main_scroll_canvas.itemconfig(self._main_scroll_window, width=event.width)

        scroll_inner.bind("<Configure>", _on_scroll_inner_configure)
        self._main_scroll_canvas.bind("<Configure>", _on_scroll_canvas_configure)

        def _scroll_wheel(event):
            delta = getattr(event, "delta", 0) or 0
            if delta:
                self._main_scroll_canvas.yview_scroll(int(-1 * (delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                self._main_scroll_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self._main_scroll_canvas.yview_scroll(1, "units")

        def _bind_wheel_rec(widget):
            widget.bind("<MouseWheel>", _scroll_wheel)
            if sys.platform.startswith("linux"):
                widget.bind("<Button-4>", _scroll_wheel)
                widget.bind("<Button-5>", _scroll_wheel)
            for ch in widget.winfo_children():
                _bind_wheel_rec(ch)

        self._main_scroll_canvas.bind("<MouseWheel>", _scroll_wheel)
        if sys.platform.startswith("linux"):
            self._main_scroll_canvas.bind("<Button-4>", _scroll_wheel)
            self._main_scroll_canvas.bind("<Button-5>", _scroll_wheel)

        card_esquerdo = ttk.Frame(scroll_inner, padding=14, style="Card.TFrame")
        card_esquerdo.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card_esquerdo.columnconfigure(0, weight=1)

        card_direito = ttk.Frame(scroll_inner, padding=14, style="Card.TFrame")
        card_direito.grid(row=1, column=0, sticky="ew")
        card_direito.columnconfigure(0, weight=1)

        ttk.Label(card_esquerdo, text="Pasta monitorada", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        pasta_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        pasta_row.grid(row=1, column=0, sticky="ew", pady=(6, 12))
        pasta_row.columnconfigure(0, weight=1)
        self.entry_pasta = ttk.Entry(pasta_row, textvariable=self.pasta_var, style="App.TEntry")
        self.entry_pasta.grid(row=0, column=0, sticky="ew")
        ttk.Button(pasta_row, text="Selecionar pasta", style="Secondary.TButton", command=self._selecionar_pasta).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(card_esquerdo, text="Opcoes de processamento", style="Section.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(
            card_esquerdo,
            text="Nao aplicar molduras (processar fotos sem moldura)",
            variable=self.sem_moldura_var,
            style="App.TCheckbutton",
        ).grid(row=3, column=0, sticky="w", pady=(6, 6))
        ttk.Checkbutton(
            card_esquerdo,
            text="Modo rapido (gera apenas mosaico 1680x1176)",
            variable=self.modo_rapido_var,
            style="App.TCheckbutton",
        ).grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Checkbutton(
            card_esquerdo,
            text="Mostrar tela de mosaico ao vivo",
            variable=self.painel_ao_vivo_var,
            style="App.TCheckbutton",
        ).grid(row=5, column=0, sticky="w", pady=(0, 12))
        ttk.Checkbutton(
            card_esquerdo,
            text="Reload automatico do painel ao vivo",
            variable=self.reload_automatico_var,
            style="App.TCheckbutton",
        ).grid(row=6, column=0, sticky="w", pady=(0, 12))

        mon_extra = ttk.Frame(card_esquerdo, style="Card.TFrame")
        mon_extra.grid(row=7, column=0, sticky="ew", pady=(0, 10))
        mon_r1 = ttk.Frame(mon_extra, style="Card.TFrame")
        mon_r1.pack(fill="x")
        ttk.Label(mon_r1, text="Pausa apos cada foto nova na pasta (s)").pack(side="left")
        ttk.Entry(mon_r1, textvariable=self.pausa_entre_fotos_monitor_var, width=4, style="App.TEntry").pack(
            side="left", padx=(8, 0)
        )
        ttk.Checkbutton(
            mon_extra,
            text="Copiar para nome aleatorio antes de processar (evita bloquear com o mesmo nome de ficheiro)",
            variable=self.renomear_entrada_aleatoria_var,
            style="App.TCheckbutton",
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(card_esquerdo, text="Configuracao do painel ao vivo", style="Section.TLabel").grid(row=8, column=0, sticky="w")

        backdrop_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        backdrop_row.grid(row=9, column=0, sticky="ew", pady=(6, 6))
        backdrop_row.columnconfigure(1, weight=1)
        ttk.Label(backdrop_row, text="Fundo (atrás do mosaico)").grid(row=0, column=0, sticky="w")
        ttk.Entry(backdrop_row, textvariable=self.backdrop_var, style="App.TEntry").grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(backdrop_row, text="…", style="Secondary.TButton", command=self._selecionar_backdrop).grid(
            row=0, column=2
        )

        overlay_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        overlay_row.grid(row=10, column=0, sticky="ew", pady=(0, 10))
        overlay_row.columnconfigure(1, weight=1)
        ttk.Label(overlay_row, text="Overlay (logo por cima)").grid(row=0, column=0, sticky="w")
        ttk.Entry(overlay_row, textvariable=self.overlay_var, style="App.TEntry").grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(overlay_row, text="…", style="Secondary.TButton", command=self._selecionar_overlay).grid(row=0, column=2)

        tamanho_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        tamanho_row.grid(row=11, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(tamanho_row, text="Largura").grid(row=0, column=0, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.largura_painel_var, width=8, style="App.TEntry").grid(row=0, column=1, padx=(6, 12))
        ttk.Label(tamanho_row, text="Altura").grid(row=0, column=2, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.altura_painel_var, width=8, style="App.TEntry").grid(row=0, column=3, padx=(6, 12))
        ttk.Label(tamanho_row, text="Celula").grid(row=0, column=4, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.celula_var, width=8, style="App.TEntry").grid(row=0, column=5, padx=(6, 0))

        timing_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        timing_row.grid(row=12, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(timing_row, text="Intervalo entre fotos no painel (ms)").grid(row=0, column=0, sticky="w")
        ttk.Entry(timing_row, textvariable=self.intervalo_mosaico_ms_var, width=8, style="App.TEntry").grid(
            row=0, column=1, padx=(8, 0), sticky="w"
        )
        ttk.Label(
            timing_row,
            text="Maior = mais suave; menor = mais rapido.",
            style="Hint.TLabel",
        ).grid(row=0, column=2, padx=(12, 0), sticky="w")

        anim_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        anim_row.grid(row=13, column=0, sticky="ew", pady=(0, 10))
        anim_row.columnconfigure(1, weight=1)
        ttk.Label(anim_row, text="Animacao").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            anim_row,
            textvariable=self.animacao_var,
            values=(
                "Mosaic Fly-In",
                "Soft Zoom Fade-In",
                "Hero Spotlight Pulse",
                "Staggered Grid Cascade",
                "Pure Fade Mosaic",
            ),
            state="readonly",
            width=26,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 10))
        ttk.Label(anim_row, text="Intensidade").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            anim_row,
            textvariable=self.intensidade_animacao_var,
            values=("Suave", "Medio", "Forte"),
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Button(card_esquerdo, text="Usar metade da tela", style="Secondary.TButton", command=self._usar_metade_tela).grid(
            row=14, column=0, sticky="w", pady=(0, 4)
        )

        ttk.Label(card_direito, text="Resumo da sessao", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card_direito, textvariable=self.summary_var, justify="left", style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 12)
        )

        ttk.Label(card_direito, text="Mosaico no navegador (gravacao / cliente)", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        nav_row = ttk.Frame(card_direito, style="Card.TFrame")
        nav_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(nav_row, text="Pastilha (px)").grid(row=0, column=0, sticky="w")
        ttk.Entry(nav_row, textvariable=self.navegador_pastilha_px_var, width=5, style="App.TEntry").grid(
            row=0, column=1, padx=(8, 12), sticky="w"
        )
        ttk.Label(
            nav_row,
            text="40-80 px; grelha fixa 20 colunas no telao (menor = mais fotos).",
            style="Hint.TLabel",
        ).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(
            card_direito,
            text="Grelha em tela cheia (preenche o navegador)",
            variable=self.navegador_grade_tela_cheia_var,
            style="App.TCheckbutton",
        ).grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            card_direito,
            text="Duplicar fotos para preencher toda a grelha (só no fim / exportar video)",
            variable=self.navegador_duplicar_grade_var,
            style="App.TCheckbutton",
        ).grid(row=5, column=0, sticky="w", pady=(2, 0))

        ttk.Label(card_direito, text="Injetar fotos (manual)", style="Section.TLabel").grid(
            row=6, column=0, sticky="w", pady=(12, 0)
        )
        inj_dest_row = ttk.Frame(card_direito, style="Card.TFrame")
        inj_dest_row.grid(row=7, column=0, sticky="ew", pady=(4, 0))
        inj_dest_row.columnconfigure(1, weight=1)
        ttk.Label(inj_dest_row, text="Pasta destino").grid(row=0, column=0, sticky="w")
        ttk.Entry(inj_dest_row, textvariable=self.injecao_pasta_destino_var, style="App.TEntry").grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(
            inj_dest_row, text="Escolher pasta…", style="Secondary.TButton", command=self._selecionar_injecao_destino
        ).grid(row=0, column=2)
        inj_imgs = ttk.Frame(card_direito, style="Card.TFrame")
        inj_imgs.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self._injecao_lbl_count = ttk.Label(inj_imgs, text="Nenhuma imagem na fila")
        self._injecao_lbl_count.pack(side="left")
        ttk.Button(
            inj_imgs, text="Escolher imagens…", style="Secondary.TButton", command=self._injecao_escolher_imagens
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            inj_imgs, text="Carregar pasta (raiz)", style="Secondary.TButton", command=self._injecao_carregar_pasta_raiz
        ).pack(side="left", padx=(8, 0))
        ttk.Button(inj_imgs, text="Limpar fila", style="Secondary.TButton", command=self._injecao_limpar_fila).pack(
            side="left", padx=(8, 0)
        )
        inj_opts = ttk.Frame(card_direito, style="Card.TFrame")
        inj_opts.grid(row=9, column=0, sticky="w", pady=(8, 0))
        ttk.Label(inj_opts, text="Pausa entre cada injecao (ms; vazio = 2000)").pack(side="left")
        ttk.Entry(inj_opts, textvariable=self.injecao_intervalo_ms_var, width=6, style="App.TEntry").pack(
            side="left", padx=(8, 12)
        )
        ttk.Checkbutton(
            inj_opts,
            text="Aplicar moldura nesta injecao",
            variable=self.injecao_aplicar_moldura_var,
            style="App.TCheckbutton",
        ).pack(side="left")
        inj_log_fr = ttk.LabelFrame(card_direito, text="Registo da injecao", padding=6)
        inj_log_fr.grid(row=10, column=0, sticky="nsew", pady=(8, 6))
        inj_log_fr.columnconfigure(0, weight=1)
        inj_log_fr.rowconfigure(0, weight=1)
        card_direito.rowconfigure(10, weight=1)
        self._injecao_log_text = tk.Text(
            inj_log_fr,
            height=8,
            wrap="word",
            font=("Segoe UI", 9),
            bg="#1a1c22",
            fg="#e8e4f5",
            insertbackground="#e8e4f5",
            relief="flat",
            highlightthickness=0,
        )
        self._injecao_log_text.grid(row=0, column=0, sticky="nsew")
        inj_log_sb = ttk.Scrollbar(inj_log_fr, command=self._injecao_log_text.yview)
        inj_log_sb.grid(row=0, column=1, sticky="ns")
        self._injecao_log_text.configure(yscrollcommand=inj_log_sb.set)
        inj_btn_row = ttk.Frame(card_direito, style="Card.TFrame")
        inj_btn_row.grid(row=11, column=0, sticky="w", pady=(4, 0))
        self._injecao_btn_injetar = ttk.Button(
            inj_btn_row, text="Injetar fila agora", style="Secondary.TButton", command=self._injecao_executar
        )
        self._injecao_btn_injetar.pack(side="left")
        self._injecao_btn_automatica = ttk.Button(
            inj_btn_row,
            text="Injecao automatica (devagar)",
            style="Secondary.TButton",
            command=self._injecao_toggle_automatica,
        )
        self._injecao_btn_automatica.pack(side="left", padx=(10, 0))
        ttk.Label(
            card_direito,
            text="Destino vazio = pasta monitorada (esquerda). "
            "Injecao automatica: um clique abre a pasta (se a fila estiver vazia) e injeta todas as fotos, "
            "uma a uma com pausa; durante a corrida o mesmo botao passa a Parar. "
            "O navegador segue as animacoes; mantenha o front aberto apos Iniciar.",
            style="Hint.TLabel",
            wraplength=380,
        ).grid(row=12, column=0, sticky="w", pady=(6, 0))

        ttk.Label(card_direito, text="Status", style="Section.TLabel").grid(row=13, column=0, sticky="w", pady=(10, 0))
        ttk.Label(container, textvariable=self.status_var, style="Status.TLabel").grid(row=4, column=0, sticky="w", pady=(12, 6))
        ttk.Label(container, textvariable=self.log_var, style="Log.TLabel", anchor="w").grid(
            row=5, column=0, sticky="ew"
        )

        _bind_wheel_rec(scroll_inner)

    def _registrar_bindings(self):
        variaveis = [
            self.pasta_var,
            self.sem_moldura_var,
            self.modo_rapido_var,
            self.painel_ao_vivo_var,
            self.reload_automatico_var,
            self.largura_painel_var,
            self.altura_painel_var,
            self.celula_var,
            self.intervalo_mosaico_ms_var,
            self.animacao_var,
            self.intensidade_animacao_var,
            self.backdrop_var,
            self.overlay_var,
            self.navegador_pastilha_px_var,
            self.navegador_grade_tela_cheia_var,
            self.navegador_duplicar_grade_var,
            self.injecao_intervalo_ms_var,
            self.injecao_pasta_destino_var,
            self.injecao_aplicar_moldura_var,
            self.pausa_entre_fotos_monitor_var,
            self.renomear_entrada_aleatoria_var,
        ]
        for var in variaveis:
            var.trace_add("write", self._atualizar_resumo_callback)

    def _atualizar_resumo_callback(self, *_):
        if self._resumo_web_after_id is not None:
            try:
                self.root.after_cancel(self._resumo_web_after_id)
            except tk.TclError:
                pass
        self._resumo_web_after_id = self.root.after(120, self._debounced_resumo_e_web)

    def _debounced_resumo_e_web(self) -> None:
        self._resumo_web_after_id = None
        self._atualizar_resumo()
        self._sincronizar_frontend_web()

    def _sincronizar_frontend_web(self):
        try:
            self.web_frontend.update_settings(
                animation_mode=self._animation_mode_key(self.animacao_var.get()),
                animation_intensity=self.intensidade_animacao_var.get().strip().lower(),
                tile_interval_ms=int(self.intervalo_mosaico_ms_var.get() or 360),
                tile_size_px=max(40, min(80, int(self.navegador_pastilha_px_var.get() or 56))),
                mosaic_fullscreen=bool(self.navegador_grade_tela_cheia_var.get()),
                duplicate_fill=bool(self.navegador_duplicar_grade_var.get()),
            )
            self.web_frontend.set_backdrop_path(self._backdrop_path_efetivo())
            self.web_frontend.set_overlay_path(self._overlay_path_efetivo())
            self._sync_backdrop_painel_ao_vivo()
            self._sync_overlay_painel_ao_vivo()
        except Exception:
            pass

    def _iniciar_servidor_web(self, silent: bool = False) -> None:
        """Sobe o HTTP do telao cedo para o refresh do browser nao ficar preto."""
        try:
            self._sincronizar_frontend_web()
            self.web_frontend.start(
                backdrop_path=self._backdrop_path_efetivo(),
                overlay_path=self._overlay_path_efetivo(),
                open_browser=not silent,
            )
        except Exception:
            pass

    def _sync_backdrop_painel_ao_vivo(self) -> None:
        if self.live_panel is None:
            return
        try:
            if not self.live_panel.window.winfo_exists():
                return
        except tk.TclError:
            return
        path = self._backdrop_path_efetivo()
        if path == getattr(self, "_ultimo_backdrop_painel", None):
            return
        self._ultimo_backdrop_painel = path
        try:
            self.live_panel._apply_backdrop(path, reset_tiles=False)
        except Exception:
            pass

    def _sync_overlay_painel_ao_vivo(self) -> None:
        if self.live_panel is None:
            return
        try:
            if not self.live_panel.window.winfo_exists():
                return
        except tk.TclError:
            return
        path = self._overlay_path_efetivo()
        if path == getattr(self, "_ultimo_overlay_painel", None):
            return
        self._ultimo_overlay_painel = path
        try:
            self.live_panel._apply_overlay(path, reset_tiles=False)
        except Exception:
            pass

    def _atualizar_resumo(self):
        largura = max(320, int(self.largura_painel_var.get() or 320))
        altura = max(240, int(self.altura_painel_var.get() or 240))
        celula = max(40, int(self.celula_var.get() or 40))
        intervalo_ms = max(80, min(8000, int(self.intervalo_mosaico_ms_var.get() or 360)))
        colunas = max(1, largura // celula)
        linhas = max(1, altura // celula)
        total = colunas * linhas
        painel = "Ativo" if self.painel_ao_vivo_var.get() else "Desativado"
        reload_auto = "Ativo" if self.reload_automatico_var.get() else "Desativado"
        modo = "Rapido" if self.modo_rapido_var.get() else "Completo"
        moldura = "Nao" if self.sem_moldura_var.get() else "Sim"
        animacao = self.animacao_var.get().strip() or "Soft Zoom Fade-In"
        intensidade = self.intensidade_animacao_var.get().strip() or "Medio"
        try:
            nav_tile = max(40, min(80, int(self.navegador_pastilha_px_var.get() or 56)))
        except (tk.TclError, ValueError):
            nav_tile = 56
        nav_full = "Sim" if self.navegador_grade_tela_cheia_var.get() else "Nao"
        nav_dup = "Sim" if self.navegador_duplicar_grade_var.get() else "Nao"
        try:
            pausa_mon = max(0, min(120, int(self.pausa_entre_fotos_monitor_var.get() or 0)))
        except (tk.TclError, ValueError):
            pausa_mon = 2
        nome_ale = "Sim" if self.renomear_entrada_aleatoria_var.get() else "Nao"
        try:
            inj_ms = max(0, min(60_000, int(self.injecao_intervalo_ms_var.get() or 0)))
        except (tk.TclError, ValueError):
            inj_ms = 2000
        inj_dest = self.injecao_pasta_destino_var.get().strip()
        inj_dest_txt = inj_dest if inj_dest else "(pasta monitorada)"
        inj_mold = "Sim" if self.injecao_aplicar_moldura_var.get() else "Nao"
        resumo = (
            f"- Modo: {modo}\n"
            f"- Aplicar moldura: {moldura}\n"
            f"- Painel ao vivo: {painel}\n"
            f"- Reload automatico: {reload_auto}\n"
            f"- Monitor: pausa {pausa_mon} s entre fotos na pasta, copia aleatoria {nome_ale}\n"
            f"- Injecao manual: destino {inj_dest_txt}, pausa {inj_ms} ms, moldura {inj_mold}\n"
            f"- Tamanho do painel: {largura}x{altura}\n"
            f"- Grade estimada: {colunas} x {linhas} ({total} fotos)\n"
            f"- Intervalo entre fotos no painel: {intervalo_ms} ms\n"
            f"- Animacao: {animacao} ({intensidade})\n"
            f"- Navegador: telao 768x960, pastilha {nav_tile} px, tela cheia {nav_full}, duplicar grelha {nav_dup}\n"
            f"- Fundo (telao): {self._backdrop_resumo()} | Overlay (logo): {self._overlay_resumo()}"
        )
        self.summary_var.set(resumo)

    def _assinatura_painel(self):
        return (
            bool(self.painel_ao_vivo_var.get()),
            int(self.largura_painel_var.get()),
            int(self.altura_painel_var.get()),
            int(self.celula_var.get()),
            self.animacao_var.get().strip(),
            self.intensidade_animacao_var.get().strip(),
            self.backdrop_var.get().strip(),
            self.overlay_var.get().strip(),
        )

    @staticmethod
    def _animation_mode_key(label: str) -> str:
        mapa = {
            "Mosaic Fly-In": "mosaic_fly_in",
            "Soft Zoom Fade-In": "soft_zoom_fade",
            "Hero Spotlight Pulse": "hero_spotlight_pulse",
            "Staggered Grid Cascade": "staggered_grid_cascade",
            "Pure Fade Mosaic": "pure_fade_mosaic",
        }
        return mapa.get((label or "").strip(), "mosaic_fly_in")

    def _painel_ativo(self):
        return (
            self.stop_event is not None
            and not self.stop_event.is_set()
            and self.worker_thread is not None
            and self.worker_thread.is_alive()
        )

    def _recriar_painel_ao_vivo(self):
        self._mosaic_cancel_feeder()
        if self.live_panel is not None:
            try:
                self.live_panel.window.destroy()
            except Exception:
                pass
            self.live_panel = None
        self._ultimo_backdrop_painel = None
        self._ultimo_overlay_painel = None
        self.live_panel = LiveMosaicPanel(
            master=self.root,
            largura=self.largura_painel_var.get(),
            altura=self.altura_painel_var.get(),
            backdrop_path=self._backdrop_path_efetivo(),
            overlay_path=self._overlay_path_efetivo(),
            celula_px=self.celula_var.get(),
            animation_mode=self._animation_mode_key(self.animacao_var.get()),
            animation_intensity=self.intensidade_animacao_var.get().strip().lower(),
        )
        self._ultima_assinatura_painel = self._assinatura_painel()
        try:
            self.root.after(0, self._mosaic_try_start_feeder)
        except tk.TclError:
            pass

    def _auto_reload_tick(self):
        try:
            assinatura_atual = self._assinatura_painel()
            if self._painel_ativo() and self.reload_automatico_var.get():
                if self.painel_ao_vivo_var.get():
                    precisa_recriar = assinatura_atual != self._ultima_assinatura_painel
                    if self.live_panel is not None:
                        try:
                            _ = self.live_panel.window.winfo_exists()
                        except Exception:
                            precisa_recriar = True
                    else:
                        precisa_recriar = True
                    if precisa_recriar:
                        self._recriar_painel_ao_vivo()
                        self.log_var.set("Painel ao vivo recarregado automaticamente.")
                elif self.live_panel is not None:
                    try:
                        self.live_panel.window.destroy()
                    except Exception:
                        pass
                    self.live_panel = None
                    self._ultima_assinatura_painel = assinatura_atual
        finally:
            self.root.after(800, self._auto_reload_tick)

    def _selecionar_pasta(self):
        pasta_escolhida = filedialog.askdirectory(
            title="Selecione a pasta que sera monitorada",
            initialdir=self.pasta_var.get(),
        )
        if pasta_escolhida:
            self.pasta_var.set(pasta_escolhida)

    def _arte_padrao(self, *nomes: str) -> str:
        for nome in nomes:
            p = _PROJECT_DIR / nome
            if p.exists():
                return str(p.resolve())
        return ""

    def _backdrop_path_efetivo(self) -> str | None:
        raw = self.backdrop_var.get().strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_file():
            return None
        return str(p.resolve())

    def _backdrop_resumo(self) -> str:
        raw = self.backdrop_var.get().strip()
        if not raw:
            return "Nao (preto)"
        if self._backdrop_path_efetivo():
            return "Sim"
        return "Caminho invalido"

    def _overlay_path_efetivo(self) -> str | None:
        """Logo por cima do mosaico; ignora mascaras de video (fundo*.png)."""
        raw = self.overlay_var.get().strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_file():
            return None
        if p.stem.lower().startswith("fundo"):
            return None
        return str(p.resolve())

    def _overlay_resumo(self) -> str:
        raw = self.overlay_var.get().strip()
        if not raw:
            return "Nao"
        if self._overlay_path_efetivo():
            return "Sim"
        if Path(raw).is_file() and Path(raw).stem.lower().startswith("fundo"):
            return "Ignorado (mascara de video — use overlay.png ou o logo Pic Brand)"
        return "Caminho invalido"

    def _selecionar_backdrop(self):
        caminho = filedialog.askopenfilename(
            title="Fundo do telao (atrás das fotos do mosaico)",
            initialdir=str(_PROJECT_DIR),
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.webp"), ("Todos", "*.*")],
        )
        if caminho:
            self.backdrop_var.set(caminho)

    def _selecionar_overlay(self):
        caminho = filedialog.askopenfilename(
            title="Overlay do evento (logo por cima das fotos)",
            initialdir=str(_PROJECT_DIR),
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.webp"), ("Todos", "*.*")],
        )
        if caminho:
            self.overlay_var.set(caminho)

    def _usar_metade_tela(self):
        self.largura_painel_var.set(max(640, self.root.winfo_screenwidth() // 2))
        self.altura_painel_var.set(max(360, self.root.winfo_screenheight() // 2))

    def _selecionar_injecao_destino(self):
        d = filedialog.askdirectory(
            title="Pasta onde as fotos serao injetadas (processadas para MOSAIC)",
            initialdir=self.injecao_pasta_destino_var.get().strip() or self.pasta_var.get(),
        )
        if d:
            self.injecao_pasta_destino_var.set(d)

    def _injecao_set_botoes_state(self, state: str, *, estado_botao_automatica: str | None = None) -> None:
        """estado_botao_automatica: se definido, o botao automatica usa este estado (ex.: normal durante a corrida)."""
        if self._injecao_btn_injetar is not None:
            try:
                self._injecao_btn_injetar.config(state=state)
            except tk.TclError:
                pass
        if self._injecao_btn_automatica is not None:
            try:
                self._injecao_btn_automatica.config(
                    state=state if estado_botao_automatica is None else estado_botao_automatica
                )
            except tk.TclError:
                pass

    def _injecao_append_log(self, msg: str) -> None:
        def append() -> None:
            w = self._injecao_log_text
            if w is not None:
                try:
                    if w.winfo_exists():
                        w.insert("end", msg + "\n")
                        w.see("end")
                except tk.TclError:
                    pass

        try:
            self.root.after(0, append)
        except tk.TclError:
            pass

    def _injecao_atualizar_contagem(self) -> None:
        if self._injecao_lbl_count is None:
            return
        n = len(self._injecao_paths)
        self._injecao_lbl_count.config(
            text=f"{n} ficheiro(s) na fila" if n else "Nenhuma imagem na fila"
        )

    def _injecao_escolher_imagens(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Imagens para a fila de injecao",
            filetypes=[
                ("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp *.jfif *.tif *.tiff *.heic"),
                ("Todos", "*.*"),
            ],
        )
        if not paths:
            return
        self._injecao_paths = [Path(p) for p in paths]
        self._injecao_atualizar_contagem()
        self._injecao_append_log(f"Fila: {len(self._injecao_paths)} ficheiro(s) selecionado(s).")

    def _injecao_carregar_pasta_raiz(self) -> None:
        d = filedialog.askdirectory(title="Pasta com imagens (apenas ficheiros na raiz)")
        if not d:
            return
        p = Path(d)
        self._injecao_paths = sorted(
            x for x in p.iterdir() if x.is_file() and x.suffix.lower() in EXTENSOES_SUPORTADAS
        )
        self._injecao_atualizar_contagem()
        if not self._injecao_paths:
            messagebox.showinfo("Injecao", "Nenhuma imagem suportada na raiz dessa pasta.")
            self._injecao_append_log("Carregar pasta: nenhuma imagem na raiz.")
        else:
            self._injecao_append_log(f"Fila: {len(self._injecao_paths)} ficheiro(s) da pasta {p.name}.")

    def _injecao_limpar_fila(self) -> None:
        self._injecao_paths.clear()
        self._injecao_atualizar_contagem()
        self._injecao_append_log("Fila limpa.")

    def _injecao_toggle_automatica(self) -> None:
        """Um clique: inicia sequencia cadenciada (e abre pasta se fila vazia). Durante a corrida: Parar."""
        t = self._injecao_auto_thread
        if t is not None and t.is_alive():
            self._injecao_auto_stop.set()
            self._injecao_append_log("Pedido de paragem enviado…")
            return

        if not self._injecao_paths:
            d = filedialog.askdirectory(
                title="Pasta com as fotos a injetar (ficheiros na raiz — um clique, sequencia automatica)",
                initialdir=self.pasta_var.get(),
            )
            if not d:
                return
            p = Path(d)
            self._injecao_paths = sorted(
                x for x in p.iterdir() if x.is_file() and x.suffix.lower() in EXTENSOES_SUPORTADAS
            )
            self._injecao_atualizar_contagem()
            if not self._injecao_paths:
                messagebox.showinfo("Injecao", "Nenhuma imagem suportada na raiz dessa pasta.")
                self._injecao_append_log("Injecao automatica: pasta sem imagens.")
                return
            self._injecao_append_log(
                f"Injecao automatica: {len(self._injecao_paths)} ficheiro(s) de {p.name}."
            )

        raw_dest = self.injecao_pasta_destino_var.get().strip()
        pasta = Path(raw_dest) if raw_dest else Path(self.pasta_var.get().strip())
        if not pasta.is_dir():
            messagebox.showerror(
                "Injecao",
                "Pasta de destino invalida.\n"
                "Use 'Escolher pasta' ou deixe o campo vazio para usar a pasta monitorada.",
            )
            return

        aplicar = bool(self.injecao_aplicar_moldura_var.get())
        try:
            pausa_ms = max(0, min(60_000, int(self.injecao_intervalo_ms_var.get() or 0)))
        except (tk.TclError, ValueError):
            pausa_ms = 0
        intervalo_s = max(pausa_ms / 1000.0, 2.6)
        paths = list(self._injecao_paths)
        n = len(paths)

        self._injecao_auto_stop.clear()

        def log_ui(msg: str) -> None:
            self._injecao_append_log(msg)
            try:
                self.root.after(0, lambda m=msg: self.log_var.set(m))
            except tk.TclError:
                pass

        def restaurar_ui() -> None:
            self._injecao_auto_thread = None
            self._injecao_set_botoes_state("normal")
            if self._injecao_btn_automatica is not None:
                try:
                    self._injecao_btn_automatica.config(text="Injecao automatica (devagar)")
                except tk.TclError:
                    pass

        self._injecao_set_botoes_state("disabled", estado_botao_automatica="normal")
        if self._injecao_btn_automatica is not None:
            try:
                self._injecao_btn_automatica.config(text="Parar injecao automatica")
            except tk.TclError:
                pass

        def work() -> None:
            try:
                ok_t, fail_t = 0, 0
                for p in paths:
                    if self._injecao_auto_stop.is_set():
                        break
                    o, f = injetar_ficheiros(
                        pasta,
                        [p],
                        aplicar_moldura=aplicar,
                        intervalo_s=0.0,
                        log_callback=log_ui,
                        nova_imagem_callback=self._queue_new_image,
                    )
                    ok_t += o
                    fail_t += f
                    if self._injecao_auto_stop.is_set():
                        break
                    if intervalo_s > 0:
                        time.sleep(intervalo_s)
                if self._injecao_auto_stop.is_set() and ok_t + fail_t < len(paths):
                    log_ui(f"Injecao automatica interrompida: {ok_t} ok, {fail_t} falha(s).")
                else:
                    log_ui(f"Injecao automatica concluida: {ok_t} ok, {fail_t} falha(s).")
            except Exception as exc:
                log_ui(f"Injecao automatica abortada: {exc}")
            finally:
                try:
                    self.root.after(0, restaurar_ui)
                except tk.TclError:
                    pass

        self._injecao_auto_thread = threading.Thread(target=work, daemon=True)
        self._injecao_auto_thread.start()
        self._injecao_append_log(f"Injecao automatica a correr: {n} ficheiro(s), pausa ~{intervalo_s:.1f} s entre cada.")
        self.log_var.set(f"Injecao automatica: {n} ficheiro(s)...")

    def _injecao_executar(self) -> None:
        if not self._injecao_paths:
            messagebox.showwarning("Injecao", "Adicione imagens a fila antes de injetar.")
            return
        raw_dest = self.injecao_pasta_destino_var.get().strip()
        pasta = Path(raw_dest) if raw_dest else Path(self.pasta_var.get().strip())
        if not pasta.is_dir():
            messagebox.showerror(
                "Injecao",
                "Pasta de destino invalida.\n"
                "Use 'Escolher pasta' ou deixe o campo vazio para usar a pasta monitorada.",
            )
            return
        aplicar = bool(self.injecao_aplicar_moldura_var.get())
        try:
            raw = str(self.injecao_intervalo_ms_var.get()).strip()
            pausa_ms = int(raw) if raw else 2000
            pausa_ms = max(0, min(60_000, pausa_ms))
        except (tk.TclError, ValueError):
            pausa_ms = 2000
        intervalo_s = pausa_ms / 1000.0
        paths = list(self._injecao_paths)
        n = len(paths)

        self._injecao_set_botoes_state("disabled")

        def log_ui(msg: str) -> None:
            self._injecao_append_log(msg)
            try:
                self.root.after(0, lambda m=msg: self.log_var.set(m))
            except tk.TclError:
                pass

        def work() -> None:
            try:
                ok_t, fail_t = 0, 0
                for p in paths:
                    o, f = injetar_ficheiros(
                        pasta,
                        [p],
                        aplicar_moldura=aplicar,
                        intervalo_s=0.0,
                        log_callback=log_ui,
                        nova_imagem_callback=self._queue_new_image,
                    )
                    ok_t += o
                    fail_t += f
                    if intervalo_s > 0 and (ok_t + fail_t) < len(paths):
                        time.sleep(intervalo_s)
                log_ui(f"Injecao concluida: {ok_t} foto(s), {fail_t} ignorada(s) ou com erro.")
            except Exception as exc:
                log_ui(f"Injecao abortada: {exc}")
            finally:

                def enable_btn() -> None:
                    self._injecao_set_botoes_state("normal")

                try:
                    self.root.after(0, enable_btn)
                except tk.TclError:
                    pass

        threading.Thread(target=work, daemon=True).start()
        self._injecao_append_log(
            f"A injetar {n} ficheiro(s), um de cada vez"
            + (f", pausa {intervalo_s:.1f} s entre cada." if intervalo_s > 0 else " (sem pausa).")
        )
        self.log_var.set(f"Injetando {n} ficheiro(s)...")

    def _queue_log(self, message: str):
        self.log_queue.put(("log", message))

    def _queue_status(self, message: str):
        self.log_queue.put(("status", message))

    def _poll_logs(self):
        try:
            while True:
                msg_type, message = self.log_queue.get_nowait()
                if msg_type == "log":
                    self.log_var.set(message)
                elif msg_type == "status":
                    self.status_var.set(f"Status: {message}")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_logs)

    def _mosaic_cancel_feeder(self):
        if self._mosaic_feed_after_id is not None:
            try:
                self.root.after_cancel(self._mosaic_feed_after_id)
            except tk.TclError:
                pass
            self._mosaic_feed_after_id = None
        self._mosaic_feeder_active = False

    def _mosaic_drain_pending(self):
        while True:
            try:
                self._mosaic_pending.get_nowait()
            except queue.Empty:
                break

    def _mosaic_try_start_feeder(self):
        if self._mosaic_feeder_active:
            return
        if self.live_panel is None:
            return
        if self._mosaic_pending.empty():
            return
        self._mosaic_feeder_active = True
        self._mosaic_feed_step()

    def _mosaic_feed_step(self):
        self._mosaic_feed_after_id = None
        panel = self.live_panel
        if panel is None:
            self._mosaic_drain_pending()
            self._mosaic_feeder_active = False
            return
        try:
            path = self._mosaic_pending.get_nowait()
        except queue.Empty:
            self._mosaic_feeder_active = False
            return
        try:
            panel.add_image(path)
        except Exception as exc:
            self.log_var.set(f"Falha ao adicionar no painel: {exc}")
        try:
            interval = max(80, min(8000, int(self.intervalo_mosaico_ms_var.get() or 360)))
        except (tk.TclError, ValueError):
            interval = 360
        if self._mosaic_pending.empty():
            self._mosaic_feeder_active = False
            return
        try:
            self._mosaic_feed_after_id = self.root.after(interval, self._mosaic_feed_step)
        except tk.TclError:
            self._mosaic_feeder_active = False

    def _iniciar_monitoramento(self):
        pasta = Path(self.pasta_var.get().strip())
        if not str(pasta):
            self.log_var.set("Selecione uma pasta valida antes de iniciar.")
            return
        if not pasta.exists():
            messagebox.showerror("Pasta invalida", "A pasta selecionada nao existe.")
            return
        if not pasta.is_dir():
            messagebox.showerror("Pasta invalida", "O caminho selecionado nao e uma pasta.")
            return
        if self.largura_painel_var.get() < 320 or self.altura_painel_var.get() < 240:
            messagebox.showwarning("Painel pequeno", "Use no minimo 320x240 para boa visualizacao.")
            return
        if self.celula_var.get() < 40:
            messagebox.showwarning("Celula invalida", "O tamanho minimo da celula e 40.")
            return

        self.stop_event = threading.Event()
        self._mosaic_cancel_feeder()
        self._mosaic_drain_pending()
        self._sincronizar_frontend_web()
        self.btn_iniciar.config(state="disabled")
        self.btn_parar.config(state="normal")
        self.status_var.set("Status: Iniciando...")

        aplicar_moldura = not self.sem_moldura_var.get()
        modo_rapido = self.modo_rapido_var.get()
        try:
            pausa_mon_s = float(max(0, min(120, int(self.pausa_entre_fotos_monitor_var.get() or 0))))
        except (tk.TclError, ValueError):
            pausa_mon_s = 2.0
        renomear_ale = bool(self.renomear_entrada_aleatoria_var.get())
        try:
            self._iniciar_servidor_web(silent=False)
        except Exception as exc:
            self.log_var.set(f"Falha ao iniciar front web: {exc}")
        if self.painel_ao_vivo_var.get():
            self._recriar_painel_ao_vivo()
        else:
            self.live_panel = None
            self._ultima_assinatura_painel = self._assinatura_painel()

        self.worker_thread = threading.Thread(
            target=monitorar_e_gerar,
            kwargs={
                "pasta_entrada": pasta,
                "aplicar_moldura": aplicar_moldura,
                "modo_rapido": modo_rapido,
                "stop_event": self.stop_event,
                "log_callback": self._queue_log,
                "status_callback": self._queue_status,
                "nova_imagem_callback": self._queue_new_image,
                "pausa_entre_fotos_s": pausa_mon_s,
                "renomear_entrada_aleatorio": renomear_ale,
            },
            daemon=True,
        )
        self.worker_thread.start()

    def _schedule_web_mosaic_notify(self, image_path: str, attempt: int = 0) -> None:
        """Avisa o telao web quando o JPEG em MOSAIC/ ja esta gravado (evita tile cinza/amarelo)."""
        path = Path(image_path)
        ready = False
        try:
            if path.is_file():
                st = path.stat()
                ready = st.st_size >= 512
        except OSError:
            ready = False
        if ready or attempt >= 10:
            try:
                self.web_frontend.notify_mosaic_changed()
            except Exception:
                pass
            return
        try:
            self.root.after(80, lambda: self._schedule_web_mosaic_notify(image_path, attempt + 1))
        except tk.TclError:
            pass

    def _queue_new_image(self, image_path: str):
        """Sempre na thread principal: painel ao vivo (se ativo) + sinal ao navegador."""

        def apply() -> None:
            if self.painel_ao_vivo_var.get():
                self._mosaic_pending.put(image_path)
                self._mosaic_try_start_feeder()
            self._schedule_web_mosaic_notify(image_path)

        try:
            self.root.after(0, apply)
        except tk.TclError:
            pass

    def _parar_monitoramento(self):
        if self.stop_event:
            self.stop_event.set()
        self._mosaic_cancel_feeder()
        self._mosaic_drain_pending()
        try:
            self.web_frontend.stop()
        except Exception:
            pass
        self.btn_iniciar.config(state="normal")
        self.btn_parar.config(state="disabled")
        self.status_var.set("Status: Parando...")

    def _limpar_mosaico(self):
        total_arquivos_removidos = 0
        falhas = 0
        pasta_mosaic = _PROJECT_DIR / "MOSAIC"
        pasta_mosaic.mkdir(parents=True, exist_ok=True)

        for caminho in list(pasta_mosaic.iterdir()):
            if not caminho.is_file():
                continue
            try:
                caminho.unlink()
                total_arquivos_removidos += 1
            except Exception:
                falhas += 1

        try:
            self.web_frontend.reset_mosaic_catalog()
            self.web_frontend.notify_mosaic_changed()
        except Exception:
            pass

        try:
            if self.live_panel is not None:
                self.live_panel.clear_tiles()
            msg = f"Mosaico limpo. {total_arquivos_removidos} arquivo(s) removido(s) da pasta MOSAIC."
            if falhas:
                msg += f" ({falhas} nao removido(s).)"
            self.log_var.set(msg)
            self.status_var.set("Status: Mosaico e pasta MOSAIC limpos")
        except Exception as exc:
            self.log_var.set(f"Falha ao limpar mosaico: {exc}")

    def _on_close(self):
        if self.stop_event:
            self.stop_event.set()
        if self._resumo_web_after_id is not None:
            try:
                self.root.after_cancel(self._resumo_web_after_id)
            except tk.TclError:
                pass
            self._resumo_web_after_id = None
        self._injecao_auto_stop.set()
        t = self._injecao_auto_thread
        if t is not None and t.is_alive():
            try:
                t.join(timeout=4.0)
            except Exception:
                pass
        self._mosaic_cancel_feeder()
        self._mosaic_drain_pending()
        try:
            self.web_frontend.stop()
        except Exception:
            pass
        if self.live_panel is not None:
            try:
                self.live_panel.window.destroy()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = GaleriaMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
