#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ponto de entrada principal do sistema.
Inicia o monitoramento da galeria e dispara a geração de mosaicos quando
novas imagens chegarem na pasta de entrada.
"""

from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from galeria_monitor import monitorar_e_gerar
from live_mosaic_panel import LiveMosaicPanel
from simple_frontend import SimpleMosaicFrontend


class GaleriaMonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mosaico Pic Brand")
        self.root.geometry("720x980")
        self.root.minsize(680, 860)
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

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.largura_painel_var = tk.IntVar(value=max(640, screen_w // 2))
        self.altura_painel_var = tk.IntVar(value=max(360, screen_h // 2))
        self.fundo_painel_var = tk.StringVar(value=self._fundo_padrao())

        self.live_panel = None
        self.web_frontend = SimpleMosaicFrontend()
        self._ultima_assinatura_painel = None
        self._ultimo_evento_imagem_ts = 0.0
        self._stagger_em_execucao = False
        self._idle_para_stagger_s = 3.5

        self._configurar_estilo()
        self._build_ui()
        self._registrar_bindings()
        self._atualizar_resumo()
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
        container.rowconfigure(2, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(container, text="Mosaico Pic Brand", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text="Inicie o monitoramento e acompanhe o mosaico ao vivo com configuracao rapida.",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        card_esquerdo = ttk.Frame(container, padding=14, style="Card.TFrame")
        card_esquerdo.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        card_esquerdo.columnconfigure(0, weight=1)

        card_direito = ttk.Frame(container, padding=14, style="Card.TFrame")
        card_direito.grid(row=3, column=0, sticky="nsew")
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

        ttk.Label(card_esquerdo, text="Configuracao do painel ao vivo", style="Section.TLabel").grid(row=7, column=0, sticky="w")

        fundo_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        fundo_row.grid(row=8, column=0, sticky="ew", pady=(6, 10))
        fundo_row.columnconfigure(1, weight=1)
        ttk.Label(fundo_row, text="Fundo").grid(row=0, column=0, sticky="w")
        ttk.Entry(fundo_row, textvariable=self.fundo_painel_var, style="App.TEntry").grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(fundo_row, text="Selecionar", style="Secondary.TButton", command=self._selecionar_fundo).grid(row=0, column=2)

        tamanho_row = ttk.Frame(card_esquerdo, style="Card.TFrame")
        tamanho_row.grid(row=9, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(tamanho_row, text="Largura").grid(row=0, column=0, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.largura_painel_var, width=8, style="App.TEntry").grid(row=0, column=1, padx=(6, 12))
        ttk.Label(tamanho_row, text="Altura").grid(row=0, column=2, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.altura_painel_var, width=8, style="App.TEntry").grid(row=0, column=3, padx=(6, 12))
        ttk.Label(tamanho_row, text="Celula").grid(row=0, column=4, sticky="w")
        ttk.Entry(tamanho_row, textvariable=self.celula_var, width=8, style="App.TEntry").grid(row=0, column=5, padx=(6, 0))

        ttk.Button(card_esquerdo, text="Usar metade da tela", style="Secondary.TButton", command=self._usar_metade_tela).grid(row=10, column=0, sticky="w")

        botoes = ttk.Frame(card_esquerdo, style="Card.TFrame")
        botoes.grid(row=11, column=0, sticky="ew", pady=(12, 0))
        self.btn_iniciar = ttk.Button(
            botoes, text="Iniciar monitoramento", style="Primary.TButton", command=self._iniciar_monitoramento
        )
        self.btn_iniciar.pack(side="left")
        self.btn_parar = ttk.Button(
            botoes, text="Parar monitoramento", style="Secondary.TButton", command=self._parar_monitoramento, state="disabled"
        )
        self.btn_parar.pack(side="left", padx=8)
        self.btn_limpar = ttk.Button(
            botoes, text="Limpar mosaico", style="Secondary.TButton", command=self._limpar_mosaico
        )
        self.btn_limpar.pack(side="left")

        ttk.Label(card_direito, text="Resumo da sessao", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card_direito, textvariable=self.summary_var, justify="left", style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 12)
        )

        ttk.Label(card_direito, text="Status", style="Section.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(container, textvariable=self.status_var, style="Status.TLabel").grid(row=4, column=0, sticky="w", pady=(12, 6))
        ttk.Label(container, textvariable=self.log_var, style="Log.TLabel", anchor="w").grid(
            row=5, column=0, sticky="ew"
        )

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
            self.fundo_painel_var,
        ]
        for var in variaveis:
            var.trace_add("write", self._atualizar_resumo_callback)

    def _atualizar_resumo_callback(self, *_):
        self._atualizar_resumo()

    def _atualizar_resumo(self):
        largura = max(320, int(self.largura_painel_var.get() or 320))
        altura = max(240, int(self.altura_painel_var.get() or 240))
        celula = max(40, int(self.celula_var.get() or 40))
        colunas = max(1, largura // celula)
        linhas = max(1, altura // celula)
        total = colunas * linhas
        painel = "Ativo" if self.painel_ao_vivo_var.get() else "Desativado"
        reload_auto = "Ativo" if self.reload_automatico_var.get() else "Desativado"
        modo = "Rapido" if self.modo_rapido_var.get() else "Completo"
        moldura = "Nao" if self.sem_moldura_var.get() else "Sim"
        resumo = (
            f"- Modo: {modo}\n"
            f"- Aplicar moldura: {moldura}\n"
            f"- Painel ao vivo: {painel}\n"
            f"- Reload automatico: {reload_auto}\n"
            f"- Tamanho do painel: {largura}x{altura}\n"
            f"- Grade estimada: {colunas} x {linhas} ({total} fotos)\n"
            f"- Fundo selecionado: {'Sim' if self.fundo_painel_var.get().strip() else 'Nao'}"
        )
        self.summary_var.set(resumo)

    def _assinatura_painel(self):
        return (
            bool(self.painel_ao_vivo_var.get()),
            int(self.largura_painel_var.get()),
            int(self.altura_painel_var.get()),
            int(self.celula_var.get()),
            self.fundo_painel_var.get().strip(),
        )

    def _painel_ativo(self):
        return (
            self.stop_event is not None
            and not self.stop_event.is_set()
            and self.worker_thread is not None
            and self.worker_thread.is_alive()
        )

    def _recriar_painel_ao_vivo(self):
        if self.live_panel is not None:
            try:
                self.live_panel.window.destroy()
            except Exception:
                pass
        self.live_panel = LiveMosaicPanel(
            master=self.root,
            largura=self.largura_painel_var.get(),
            altura=self.altura_painel_var.get(),
            fundo_path=self.fundo_painel_var.get().strip() or None,
            celula_px=self.celula_var.get(),
        )
        self._ultima_assinatura_painel = self._assinatura_painel()

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

            # Se ficar um tempo sem novas imagens, dispara montagem final em stagger.
            if (
                self._painel_ativo()
                and self.live_panel is not None
                and self.painel_ao_vivo_var.get()
                and not self._stagger_em_execucao
                and self._ultimo_evento_imagem_ts > 0
            ):
                if time.time() - self._ultimo_evento_imagem_ts >= self._idle_para_stagger_s:
                    try:
                        self.live_panel.play_staggered_flow()
                        self._stagger_em_execucao = True
                        self.log_var.set("Staggered flow: mosaico final montado em cascata.")
                    except Exception as exc:
                        self.log_var.set(f"Falha no staggered flow: {exc}")
        finally:
            self.root.after(800, self._auto_reload_tick)

    def _selecionar_pasta(self):
        pasta_escolhida = filedialog.askdirectory(
            title="Selecione a pasta que sera monitorada",
            initialdir=self.pasta_var.get(),
        )
        if pasta_escolhida:
            self.pasta_var.set(pasta_escolhida)

    def _fundo_padrao(self) -> str:
        candidatos = ["fundobaixosemtexto.png", "fundoaltosemtexto.png", "fundobaixo.png", "fundoalto.png", "fundo.jpg"]
        for nome in candidatos:
            p = Path.cwd() / nome
            if p.exists():
                return str(p.resolve())
        return ""

    def _selecionar_fundo(self):
        fundo = filedialog.askopenfilename(
            title="Selecione o fundo da tela de mosaico",
            initialdir=str(Path.cwd()),
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.webp"), ("Todos", "*.*")],
        )
        if fundo:
            self.fundo_painel_var.set(fundo)

    def _usar_metade_tela(self):
        self.largura_painel_var.set(max(640, self.root.winfo_screenwidth() // 2))
        self.altura_painel_var.set(max(360, self.root.winfo_screenheight() // 2))

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
                elif msg_type == "nova_imagem" and self.live_panel is not None:
                    self.live_panel.add_image(message)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_logs)

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
        self.btn_iniciar.config(state="disabled")
        self.btn_parar.config(state="normal")
        self.status_var.set("Status: Iniciando...")

        aplicar_moldura = not self.sem_moldura_var.get()
        modo_rapido = self.modo_rapido_var.get()
        try:
            self.web_frontend.start(background_path=self.fundo_painel_var.get().strip() or None)
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
            },
            daemon=True,
        )
        self.worker_thread.start()

    def _queue_new_image(self, image_path: str):
        self._ultimo_evento_imagem_ts = time.time()
        self._stagger_em_execucao = False
        self.log_queue.put(("nova_imagem", image_path))

    def _parar_monitoramento(self):
        if self.stop_event:
            self.stop_event.set()
        try:
            self.web_frontend.stop()
        except Exception:
            pass
        self.btn_iniciar.config(state="normal")
        self.btn_parar.config(state="disabled")
        self.status_var.set("Status: Parando...")

    def _limpar_mosaico(self):
        total_arquivos_removidos = 0
        pasta_mosaic = Path.cwd() / "MOSAIC"
        extensoes_imagem = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}

        if pasta_mosaic.exists() and pasta_mosaic.is_dir():
            for caminho in pasta_mosaic.iterdir():
                if caminho.is_file() and caminho.suffix.lower() in extensoes_imagem:
                    try:
                        caminho.unlink()
                        total_arquivos_removidos += 1
                    except Exception:
                        # Se um arquivo estiver em uso, ignora e segue os demais.
                        pass

        try:
            if self.live_panel is not None:
                self.live_panel.clear_tiles()
            self.log_var.set(
                f"Mosaico limpo. {total_arquivos_removidos} arquivo(s) removido(s) da pasta MOSAIC."
            )
            self.status_var.set("Status: Mosaico e pasta MOSAIC limpos")
        except Exception as exc:
            self.log_var.set(f"Falha ao limpar mosaico: {exc}")

    def _on_close(self):
        if self.stop_event:
            self.stop_event.set()
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
