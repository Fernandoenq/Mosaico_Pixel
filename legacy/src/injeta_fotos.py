#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injeta imagens no fluxo do mosaico (MOSAIC + subpastas da galeria), sem passar pelo monitor.

Sem argumentos (ou --gui): abre uma janela simples para escolher imagens e pasta de destino.

A funcao abrir_janela_injecao() pode ser chamada a partir da app principal (main) com master=root
para abrir um Toplevel integrado, sem segundo processo Python.

Linha de comandos:
  python injeta_fotos.py <pasta_destino> <imagem1> [imagem2 ...]
  python injeta_fotos.py <pasta_destino> --pasta <pasta_so_raiz>
  python injeta_fotos.py <pasta_destino> --pasta <pasta> --pausa 2
"""
from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from galeria_monitor import EXTENSOES_SUPORTADAS, injetar_ficheiros

_FILE_TYPES = [
    ("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp *.jfif *.tif *.tiff *.heic"),
    ("Todos", "*.*"),
]


def _format_pausa(s: float) -> str:
    if s == int(s):
        return str(int(s))
    return str(s)


def abrir_janela_injecao(
    master: Any | None,
    *,
    nova_imagem_callback: Callable[[str], None] | None = None,
    initial_dest: str = "",
    initial_pausa_s: float = 2.0,
    initial_aplicar_moldura: bool = True,
    before_destroy: Callable[[], None] | None = None,
) -> Any:
    """
    Abre a janela de injecao. Se master for None, cria um Tk isolado (script autonomo).
    Se master for a janela principal, abre um Toplevel filho.
    Retorna o widget raiz da janela (Tk ou Toplevel).
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    paths: list[Path] = []

    if master is None:
        root = tk.Tk()
    else:
        root = tk.Toplevel(master)
        root.transient(master.winfo_toplevel())

    root.title("Injetar fotos")
    root.minsize(440, 420)

    dest_var = tk.StringVar(value=initial_dest.strip())
    pausa_var = tk.StringVar(value=_format_pausa(max(0.0, float(initial_pausa_s))))
    moldura_var = tk.BooleanVar(value=bool(initial_aplicar_moldura))

    main = ttk.Frame(root, padding=12)
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(5, weight=1)

    ttk.Label(main, text="Pasta de destino (ex.: Galeria / pasta monitorada)").grid(
        row=0, column=0, sticky="w"
    )
    row_dest = ttk.Frame(main)
    row_dest.grid(row=1, column=0, sticky="ew", pady=(4, 10))
    row_dest.columnconfigure(0, weight=1)
    ttk.Entry(row_dest, textvariable=dest_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))

    def escolher_destino() -> None:
        d = filedialog.askdirectory(
            title="Pasta onde as fotos serao processadas",
            initialdir=dest_var.get().strip() or None,
        )
        if d:
            dest_var.set(d)

    ttk.Button(row_dest, text="Escolher pasta…", command=escolher_destino).grid(row=0, column=1)

    ttk.Label(main, text="Imagens").grid(row=2, column=0, sticky="w")
    row_img = ttk.Frame(main)
    row_img.grid(row=3, column=0, sticky="ew", pady=(4, 6))
    lbl_count = ttk.Label(row_img, text="Nenhuma imagem selecionada")
    lbl_count.pack(side="left")

    def escolher_imagens() -> None:
        fs = filedialog.askopenfilenames(
            title="Imagens a injetar",
            filetypes=_FILE_TYPES,
        )
        if not fs:
            return
        paths.clear()
        paths.extend(Path(p) for p in fs)
        lbl_count.config(text=f"{len(paths)} ficheiro(s) selecionado(s)")

    def limpar_imagens() -> None:
        paths.clear()
        lbl_count.config(text="Nenhuma imagem selecionada")

    ttk.Button(row_img, text="Escolher imagens…", command=escolher_imagens).pack(side="left", padx=(12, 0))
    ttk.Button(row_img, text="Limpar", command=limpar_imagens).pack(side="left", padx=(8, 0))

    opts = ttk.Frame(main)
    opts.grid(row=4, column=0, sticky="w", pady=(0, 8))
    ttk.Label(opts, text="Pausa entre cada foto (s)").pack(side="left")
    ttk.Entry(opts, textvariable=pausa_var, width=6).pack(side="left", padx=(8, 16))
    ttk.Checkbutton(opts, text="Aplicar moldura", variable=moldura_var).pack(side="left")

    log_frame = ttk.LabelFrame(main, text="Registo", padding=6)
    log_frame.grid(row=5, column=0, sticky="nsew", pady=(0, 10))
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    main.rowconfigure(5, weight=1)

    log = tk.Text(log_frame, height=10, wrap="word", font=("Segoe UI", 9))
    log.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(log_frame, command=log.yview)
    sb.grid(row=0, column=1, sticky="ns")
    log.configure(yscrollcommand=sb.set)

    def log_ui(msg: str) -> None:
        def _append() -> None:
            log.insert("end", msg + "\n")
            log.see("end")

        try:
            root.after(0, _append)
        except tk.TclError:
            pass

    bottom = ttk.Frame(main)
    bottom.grid(row=6, column=0, sticky="ew", pady=(4, 0))
    btn_injetar = ttk.Button(bottom, text="Injetar")

    def fechar() -> None:
        if before_destroy:
            try:
                before_destroy()
            except Exception:
                pass
        try:
            root.destroy()
        except tk.TclError:
            pass

    root.protocol("WM_DELETE_WINDOW", fechar)

    def injetar() -> None:
        dest = dest_var.get().strip()
        if not dest:
            messagebox.showwarning("Injetar", "Escolha a pasta de destino.", parent=root)
            return
        pdest = Path(dest)
        if not pdest.is_dir():
            messagebox.showerror("Injetar", "A pasta de destino nao existe ou nao e valida.", parent=root)
            return
        if not paths:
            messagebox.showwarning("Injetar", "Escolha pelo menos uma imagem.", parent=root)
            return
        try:
            pausa = max(0.0, float(pausa_var.get().replace(",", ".")))
        except ValueError:
            messagebox.showerror(
                "Injetar",
                "Pausa em segundos invalida (use por exemplo 2 ou 0.5).",
                parent=root,
            )
            return

        btn_injetar.config(state="disabled")
        copia = list(paths)

        def work() -> None:
            try:
                ok, falhas = injetar_ficheiros(
                    pdest,
                    copia,
                    aplicar_moldura=moldura_var.get(),
                    intervalo_s=pausa,
                    log_callback=log_ui,
                    nova_imagem_callback=nova_imagem_callback,
                )

                def done() -> None:
                    btn_injetar.config(state="normal")
                    messagebox.showinfo("Injetar", f"Concluido: {ok} ok, {falhas} falha(s).", parent=root)

                root.after(0, done)
            except Exception as exc:

                def err() -> None:
                    btn_injetar.config(state="normal")
                    messagebox.showerror("Injetar", str(exc), parent=root)

                root.after(0, err)

        threading.Thread(target=work, daemon=True).start()

    btn_injetar.config(command=injetar)
    btn_injetar.pack(side="left")
    ttk.Button(bottom, text="Fechar", command=fechar).pack(side="right")

    return root


def run_gui() -> int:
    root = abrir_janela_injecao(None)
    root.mainloop()
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        return run_gui()
    if len(sys.argv) == 2 and sys.argv[1] in ("--gui", "-g"):
        return run_gui()

    p = argparse.ArgumentParser(description="Injetar fotos no mosaico Pic Brand.")
    p.add_argument("galeria", type=Path, help="Pasta de destino da injecao (ex.: Galeria)")
    p.add_argument("ficheiros", nargs="*", type=Path, help="Imagens a injetar")
    p.add_argument("--pasta", type=Path, help="Em vez de listar ficheiros, usa todos na raiz desta pasta")
    p.add_argument("--pausa", type=float, default=2.0, help="Segundos entre cada foto (0 = sem pausa)")
    p.add_argument("--sem-moldura", action="store_true", help="Igual a desligar moldura na app")
    args = p.parse_args()

    paths: list[Path] = []
    if args.pasta:
        if not args.pasta.is_dir():
            print("Erro: --pasta nao e uma pasta.", file=sys.stderr)
            return 2
        paths = sorted(
            x for x in args.pasta.iterdir() if x.is_file() and x.suffix.lower() in EXTENSOES_SUPORTADAS
        )
    else:
        paths = [x for x in args.ficheiros if x.exists()]

    if not paths:
        print("Nenhum ficheiro para injetar.", file=sys.stderr)
        return 1

    if not args.galeria.is_dir():
        print("Erro: pasta de destino nao existe ou nao e uma pasta.", file=sys.stderr)
        return 2

    ok, falhas = injetar_ficheiros(
        args.galeria,
        paths,
        aplicar_moldura=not args.sem_moldura,
        intervalo_s=max(0.0, float(args.pausa)),
        log_callback=print,
        nova_imagem_callback=None,
    )
    print(f"Feito: {ok} ok, {falhas} falha(s).")
    return 0 if falhas == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
