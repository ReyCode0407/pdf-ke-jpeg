"""PIXORA by Rey - aplikasi pengolah PDF dan gambar.

Fitur:
  - Gabung, Pisah, Putar, dan Kompres PDF
  - Gerbang kode akses saat aplikasi dibuka
  - PDF -> Word (.docx) memakai pdf2docx
  - PDF -> Gambar (JPEG, PNG, WebP), pilih halaman, resolusi, kualitas
  - Gambar -> PDF, urutan bisa diatur

Dependensi: customtkinter, pymupdf, pillow, pdf2docx
"""
import os
import sys
import time
import hashlib
import threading
import subprocess
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageTk

from make_icon import make_icon

APP_NAME = "PIXORA"
APP_TAGLINE = "Aplikasi pengolah PDF dan gambar"

# Palet sama dengan versi web: oranye = sisi PDF, teal = sisi gambar
BG = "#080D12"
SURFACE = "#111A22"
INNER = "#0E161D"
FRAME = "#192630"
LINE = "#223039"
FG = "#E8EFF4"
MUTED = "#8DA0AE"
PDF_C = "#FF6B3D"
JPG_C = "#34D9C5"
JPG_HOVER = "#2BC2B0"
JPG_DEEP = "#17917F"
DARK = "#06110F"
DANGER = "#FF8A80"

MAX_DIM = 12000
AMBER = "#F5C451"

# Kode akses: hanya hash yang disimpan di sini. Ini kunci ringan, bukan pengaman kuat.
ACCESS_HASH = "f4ef1dd55b46891e563296947f2c033102f6587ac4b2ea524e96c6dea6ddc2bb"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".pixora_akses")
# Sisi terpanjang minimal sesuai pilihan (Full HD = 1920 px), dan tidak pernah di bawah 150 DPI
RES = {"Full HD": 1920, "2K": 2560, "4K": 3840, "300 DPI": None}
IMG_TYPES = [("Gambar", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"), ("Semua file", "*.*")]
FORMATS = {"JPEG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WebP": ("WEBP", "webp")}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def font(size, weight="normal", mono=False):
    return ctk.CTkFont(family="Consolas" if mono else "Segoe UI", size=size, weight=weight)


def code_hash(text):
    raw = "".join(ch for ch in text.upper() if ch.isascii() and ch.isalnum())
    return hashlib.sha256(("pixora-by-rey:" + raw).encode()).hexdigest()


def unique_path(path):
    base, ext = os.path.splitext(path)
    n, cand = 1, path
    while os.path.exists(cand):
        n += 1
        cand = f"{base}_{n}{ext}"
    return cand


def scale_for(w, h, res):
    long_side = max(w, h)
    target = RES[res]
    s = 300 / 72 if target is None else max(target / long_side, 150 / 72)
    return min(s, MAX_DIM / long_side)


def parse_pages(text, total):
    """'1-3,5' -> [0,1,2,4]; kosong = semua halaman."""
    text = text.strip()
    if not text:
        return list(range(total))
    pages = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a > b:
                a, b = b, a
            pages.update(range(a, b + 1))
        else:
            pages.add(int(part))
    return [p - 1 for p in sorted(pages) if 1 <= p <= total]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PIXORA by Rey")
        self.geometry("1020x780")
        self.minsize(960, 720)
        self.configure(fg_color=BG)

        self._icon_ref = ImageTk.PhotoImage(make_icon(64))
        self.after(250, self._set_icon)  # CustomTkinter menimpa ikon, jadi dipasang ulang

        self.pdfs = []
        self.images = []
        self.busy = False
        self.preview_img = None
        self.out_dir = os.path.join(os.path.expanduser("~"), "Pictures", "PIXORA")

        self.fails = 0
        self.locked_until = 0
        self.pt = {}
        self._gate_or_start()

    def _set_icon(self):
        try:
            self.iconphoto(True, self._icon_ref)
        except Exception:
            pass

    # ------------------------------------------------------------ ui helpers
    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=18, border_width=1, border_color=LINE, **kw)

    def btn(self, parent, text, command, kind="secondary", width=None, height=34):
        if kind == "primary":
            kw = dict(fg_color=JPG_C, hover_color=JPG_HOVER, text_color=DARK, font=font(13, "bold"))
        elif kind == "danger":
            kw = dict(fg_color=FRAME, hover_color=LINE, text_color=DANGER, font=font(13))
        else:
            kw = dict(fg_color=FRAME, hover_color=LINE, text_color=FG, font=font(13))
        extra = {"width": width} if width else {}
        return ctk.CTkButton(parent, text=text, command=command, height=height, corner_radius=10, **kw, **extra)

    def seg(self, parent, values, command=None):
        return ctk.CTkSegmentedButton(
            parent, values=values, command=command, height=34, corner_radius=10,
            fg_color=FRAME, selected_color=JPG_DEEP, selected_hover_color=JPG_DEEP,
            unselected_color=FRAME, unselected_hover_color=LINE, text_color=FG, font=font(13, "bold"))

    def label(self, parent, text, size=13, color=FG, weight="normal", mono=False, **kw):
        return ctk.CTkLabel(parent, text=text, font=font(size, weight, mono), text_color=color, **kw)

    def caption(self, parent, text):
        return self.label(parent, text.upper(), 11, MUTED, mono=True, anchor="w")

    # ------------------------------------------------------------ header
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=28, pady=(22, 6))

        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        logo = ctk.CTkImage(light_image=make_icon(96), dark_image=make_icon(96), size=(56, 56))
        ctk.CTkLabel(left, image=logo, text="").pack(side="left", padx=(0, 14))

        text = ctk.CTkFrame(left, fg_color="transparent")
        text.pack(side="left")
        row = ctk.CTkFrame(text, fg_color="transparent")
        row.pack(anchor="w")
        ctk.CTkLabel(row, text="PIX", font=font(38, "bold"), text_color=PDF_C).pack(side="left")
        ctk.CTkLabel(row, text="ORA", font=font(38, "bold"), text_color=JPG_C).pack(side="left")
        ctk.CTkLabel(row, text="  by Rey", font=font(15, mono=True), text_color=MUTED).pack(side="left", pady=(14, 0))
        self.label(text, APP_TAGLINE, 14, MUTED, anchor="w").pack(anchor="w")

        chip = ctk.CTkFrame(head, fg_color=SURFACE, corner_radius=999, border_width=1, border_color=LINE)
        chip.pack(side="right", pady=(8, 0))
        ctk.CTkLabel(chip, text="●", font=font(11), text_color=JPG_C).pack(side="left", padx=(14, 4), pady=6)
        ctk.CTkLabel(chip, text="DIPROSES DI KOMPUTER · TANPA UNGGAH", font=font(11, mono=True),
                     text_color=MUTED).pack(side="left", padx=(0, 14))
        self.btn(head, "Keluar", self._logout, width=80).pack(side="right", padx=(0, 10), pady=(8, 0))

    TOOLS = {
        "pdf": ("PDF ke Gambar", "Ubah setiap halaman PDF menjadi JPEG, PNG, atau WebP dalam resolusi tinggi."),
        "img": ("Gambar ke PDF", "Gabungkan beberapa gambar menjadi satu PDF. Urutkan sesuai keinginan."),
        "doc": ("PDF ke Word", "Ubah PDF menjadi dokumen Word (.docx) yang bisa diedit."),
        "merge": ("Gabung PDF", "Satukan beberapa file PDF jadi satu dokumen. Atur urutannya."),
        "split": ("Pisah PDF", "Ambil rentang halaman tertentu, atau pecah setiap halaman jadi file sendiri."),
        "rotate": ("Putar PDF", "Putar halaman PDF yang miring atau terbalik, lalu simpan hasilnya."),
        "compress": ("Kompres PDF", "Perkecil ukuran PDF. Gambar di dalamnya dikompres, teks tetap bisa dipilih."),
    }
    WORD_C = "#5AA2FF"
    CARDS = [("pdf", PDF_C, "JPG"), ("img", JPG_C, "PDF"), ("doc", WORD_C, "W"),
             ("merge", PDF_C, "A+B"), ("split", JPG_C, "A|B"), ("rotate", WORD_C, "90°"), ("compress", AMBER, "MB↓")]

    # ------------------------------------------------------------ gerbang kode akses
    def _gate_or_start(self):
        try:
            with open(TOKEN_FILE, encoding="utf-8") as fh:
                ok = fh.read().strip() == ACCESS_HASH
        except OSError:
            ok = False
        if ok:
            self._start_app()
        else:
            self._build_gate()

    def _build_gate(self):
        self.gate = ctk.CTkFrame(self, fg_color=BG)
        self.gate.pack(fill="both", expand=True)
        card = self.card(self.gate)
        card.place(relx=0.5, rely=0.46, anchor="center")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=34, pady=30)
        logo = ctk.CTkImage(light_image=make_icon(96), dark_image=make_icon(96), size=(64, 64))
        ctk.CTkLabel(inner, image=logo, text="").pack(pady=(0, 8))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack()
        ctk.CTkLabel(row, text="PIX", font=font(40, "bold"), text_color=PDF_C).pack(side="left")
        ctk.CTkLabel(row, text="ORA", font=font(40, "bold"), text_color=JPG_C).pack(side="left")
        self.label(inner, "by Rey", 13, MUTED, mono=True).pack(pady=(0, 6))
        self.label(inner, "Masukkan kode akses untuk menggunakan aplikasi.", 13, MUTED).pack(pady=(0, 14))
        self.code_entry = ctk.CTkEntry(inner, width=280, height=42, show="•", placeholder_text="XXXX-XXXX",
                                       fg_color=INNER, border_width=0, text_color=FG, font=font(15, mono=True))
        self.code_entry.pack()
        self.code_entry.bind("<Return>", lambda _e: self._try_code())
        self.remember = ctk.CTkCheckBox(inner, text="Ingat di komputer ini", text_color=FG, font=font(13),
                                        fg_color=JPG_DEEP, hover_color=JPG_DEEP, border_color=LINE)
        self.remember.select()
        self.remember.pack(anchor="w", pady=(12, 12))
        self.btn(inner, "Masuk", self._try_code, "primary", height=44).pack(fill="x")
        self.gate_err = self.label(inner, "", 12, DANGER)
        self.gate_err.pack(pady=(10, 0))
        self.after(100, self.code_entry.focus)

    def _try_code(self):
        if time.time() < self.locked_until:
            self.gate_err.configure(text="Terlalu banyak percobaan. Tunggu sebentar.")
            return
        if code_hash(self.code_entry.get()) == ACCESS_HASH:
            if self.remember.get():
                try:
                    with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
                        fh.write(ACCESS_HASH)
                except OSError:
                    pass
            self.gate.destroy()
            self._start_app()
            return
        self.fails += 1
        self.gate_err.configure(text="Kode salah. Coba lagi.")
        self.code_entry.delete(0, "end")
        if self.fails >= 5:
            self.locked_until = time.time() + 30
            self.fails = 0
            self.gate_err.configure(text="Kode salah 5 kali. Coba lagi dalam 30 detik.")

    def _logout(self):
        try:
            os.remove(TOKEN_FILE)
        except OSError:
            pass
        for w in self.winfo_children():
            w.destroy()
        self.pt = {}
        self._build_gate()

    def _start_app(self):
        self._build_header()
        self._build_tabs()
        self._show_tab("home")

    def _build_tabs(self):
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.btn(self.toolbar, "←  Semua alat", lambda: self._show_tab("home"), width=130).pack(side="left")
        tt = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        tt.pack(side="left", padx=18)
        self.tool_title = self.label(tt, "", 24, FG, "bold", anchor="w")
        self.tool_title.pack(anchor="w")
        self.tool_desc = self.label(tt, "", 13, MUTED, anchor="w")
        self.tool_desc.pack(anchor="w")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        self.tab_home = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        self.tabs = {"home": self.tab_home}
        for key in self.TOOLS:
            self.tabs[key] = ctk.CTkFrame(self.body, fg_color="transparent")
        self.tab_pdf, self.tab_img, self.tab_doc = self.tabs["pdf"], self.tabs["img"], self.tabs["doc"]
        self._build_home(self.tab_home)
        self._build_pdf_tab(self.tab_pdf)
        self._build_img_tab(self.tab_img)
        self._build_doc_tab(self.tab_doc)
        self._build_extra_tools()

    def _build_home(self, tab):
        self.label(tab, "Pilih alat", 24, FG, "bold", anchor="w").pack(anchor="w", pady=(20, 2))
        self.label(tab, "Semua diproses di komputer Anda. File tidak diunggah ke mana pun.", 13, MUTED,
                   anchor="w").pack(anchor="w", pady=(0, 18))
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x")
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="cards")
        for i, (key, color, glyph) in enumerate(self.CARDS):
            col = i % 3
            card = self._tool_card(grid, key, color, glyph)
            card.grid(row=i // 3, column=col, sticky="nsew", pady=(0, 16),
                      padx=(0 if col == 0 else 8, 0 if col == 2 else 8))

    def _tool_card(self, parent, key, color, glyph):
        title, desc = self.TOOLS[key]
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=18, border_width=1, border_color=LINE, cursor="hand2")
        tile = ctk.CTkFrame(card, width=54, height=54, corner_radius=15, fg_color=color)
        tile.pack_propagate(False)
        tile.pack(anchor="w", padx=22, pady=(22, 12))
        g = ctk.CTkLabel(tile, text=glyph, font=font(14, "bold", mono=True), text_color=DARK)
        g.place(relx=0.5, rely=0.5, anchor="center")
        t = self.label(card, title, 18, FG, "bold", anchor="w")
        t.pack(anchor="w", padx=22)
        d = self.label(card, desc, 13, MUTED, anchor="w", justify="left", wraplength=250)
        d.pack(anchor="w", padx=22, pady=(4, 22))
        for w in [card, tile, g, t, d]:
            w.bind("<Button-1>", lambda _e, k=key: self._show_tab(k))
            w.bind("<Enter>", lambda _e, c=card, col=color: c.configure(border_color=col, fg_color=FRAME))
            w.bind("<Leave>", lambda _e, c=card: c.configure(border_color=LINE, fg_color=SURFACE))
        return card

    def _show_tab(self, name):
        for t in self.tabs.values():
            t.pack_forget()
        self.toolbar.pack_forget()
        if name != "home":
            title, desc = self.TOOLS[name]
            self.tool_title.configure(text=title)
            self.tool_desc.configure(text=desc)
            self.toolbar.pack(fill="x", padx=28, pady=(8, 12), before=self.body)
        self.tabs[name].pack(fill="both", expand=True)

    # ------------------------------------------------------------ alat PDF tambahan (pymupdf)
    def _build_extra_tools(self):
        def opt_none(inner):
            return lambda: {}

        def opt_split(inner):
            self.caption(inner, "Cara memisahkan").pack(anchor="w")
            mode = self.seg(inner, ["Ambil rentang", "Tiap halaman"])
            mode.set("Ambil rentang")
            mode.pack(fill="x", pady=(6, 14))
            self.caption(inner, "Halaman (kosong = semua)").pack(anchor="w")
            rng = ctk.CTkEntry(inner, height=36, placeholder_text="contoh: 1-3,5", fg_color=INNER,
                               border_width=0, text_color=FG, font=font(13))
            rng.pack(fill="x", pady=(6, 14))
            return lambda: {"mode": mode.get(), "range": rng.get()}

        def opt_rotate(inner):
            self.caption(inner, "Putar ke kanan").pack(anchor="w")
            deg = self.seg(inner, ["90°", "180°", "270°"])
            deg.set("90°")
            deg.pack(fill="x", pady=(6, 14))
            self.caption(inner, "Halaman (kosong = semua)").pack(anchor="w")
            rng = ctk.CTkEntry(inner, height=36, placeholder_text="contoh: 1-3,5", fg_color=INNER,
                               border_width=0, text_color=FG, font=font(13))
            rng.pack(fill="x", pady=(6, 14))
            return lambda: {"deg": deg.get(), "range": rng.get()}

        def opt_compress(inner):
            self.caption(inner, "Tingkat kompres").pack(anchor="w")
            lv = self.seg(inner, ["Ringan", "Sedang", "Kuat"])
            lv.set("Sedang")
            lv.pack(fill="x", pady=(6, 14))
            return lambda: {"level": lv.get()}

        specs = [
            ("merge", True, True, 2, "Pengaturan gabung", "Gabungkan PDF", PDF_C, opt_none, self._run_merge),
            ("split", False, False, 1, "Pengaturan pisah", "Pisahkan PDF", JPG_C, opt_split, self._run_split),
            ("rotate", False, False, 1, "Pengaturan putar", "Putar PDF", self.WORD_C, opt_rotate, self._run_rotate),
            ("compress", True, False, 1, "Pengaturan kompres", "Kompres PDF", AMBER, opt_compress, self._run_compress),
        ]
        for key, multi, order, min_files, rail_title, btn_text, color, opts, run in specs:
            self._build_simple_tool(self.tabs[key], key, multi, order, min_files, rail_title, btn_text, color, opts, run)

    def _build_simple_tool(self, tab, key, multi, order, min_files, rail_title, btn_text, color, build_opts, run):
        st = {"files": [], "get_opts": None}
        self.pt[key] = st
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=0, minsize=330)
        tab.grid_rowconfigure(0, weight=1)

        left = self.card(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        self.label(top, "File PDF", 17, FG, "bold").pack(side="left")
        self.btn(top, "Hapus semua", lambda: (st["files"].clear(), refresh()), width=104).pack(side="right", padx=(8, 0))
        add_btn = self.btn(top, "+ Pilih file PDF", lambda: add(), width=140)
        add_btn.configure(fg_color=color, hover_color=color, text_color=DARK, font=font(13, "bold"))
        add_btn.pack(side="right")
        hint = "Pilih dua file atau lebih. Urutan di daftar menjadi urutan halaman." if order else (
            "Bisa memilih lebih dari satu file." if multi else "Pilih satu file PDF.")
        self.label(left, hint, 12, MUTED, anchor="w").pack(anchor="w", padx=18)
        listf = ctk.CTkScrollableFrame(left, fg_color=INNER, corner_radius=12)
        listf.pack(fill="both", expand=True, padx=18, pady=(10, 18))

        rail = self.card(tab)
        rail.grid(row=0, column=1, sticky="nsew")
        ctk.CTkFrame(rail, height=4, fg_color=color, corner_radius=0).pack(fill="x")
        inner = ctk.CTkFrame(rail, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=16)
        self.label(inner, rail_title, 18, FG, "bold", anchor="w").pack(anchor="w", pady=(0, 12))
        st["get_opts"] = build_opts(inner)
        self.caption(inner, "Folder tujuan").pack(anchor="w")
        orow = ctk.CTkFrame(inner, fg_color="transparent")
        orow.pack(fill="x", pady=(6, 14))
        out_entry = ctk.CTkEntry(orow, height=36, fg_color=INNER, border_width=0, text_color=FG, font=font(13))
        out_entry.pack(side="left", fill="x", expand=True)
        out_entry.insert(0, os.path.join(os.path.expanduser("~"), "Documents", "PIXORA"))

        def pick_out():
            d = filedialog.askdirectory(title="Pilih folder tujuan")
            if d:
                out_entry.delete(0, "end")
                out_entry.insert(0, d)
        self.btn(orow, "Pilih…", pick_out, width=70, height=36).pack(side="left", padx=(8, 0))

        readout = self.label(inner, "Belum ada file.", 12, FG, mono=True, anchor="w", justify="left",
                             fg_color=FRAME, corner_radius=12, wraplength=260)
        readout.pack(fill="x", ipady=10, pady=(0, 14))
        go = self.btn(inner, btn_text, lambda: start(), "primary", height=46)
        go.configure(fg_color=color, hover_color=color, text_color=DARK, font=font(15, "bold"), corner_radius=14)
        go.pack(fill="x")
        prog = ctk.CTkProgressBar(inner, height=8, progress_color=color, fg_color=FRAME)
        prog.set(0)
        prog.pack(fill="x", pady=(12, 6))
        status = self.label(inner, "Siap.", 12, MUTED, anchor="w", justify="left", wraplength=270)
        status.pack(anchor="w")

        def say(text, value=None, error=False):
            def _do():
                status.configure(text=text, text_color=DANGER if error else MUTED)
                if value is not None:
                    prog.set(value)
            self.after(0, _do)

        def refresh():
            for w in listf.winfo_children():
                w.destroy()
            files = st["files"]
            if not files:
                self.label(listf, "Belum ada file.\nKlik “+ Pilih file PDF”.", 13, MUTED).pack(pady=40)
            for i, p in enumerate(files):
                row = ctk.CTkFrame(listf, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=LINE)
                row.pack(fill="x", pady=4, padx=4)
                self.label(row, f"{i + 1:02d}", 12, color, mono=True).pack(side="left", padx=(12, 8), pady=10)
                self.label(row, os.path.basename(p), 13, FG, anchor="w").pack(side="left", fill="x", expand=True)
                self.btn(row, "✕", lambda i=i: (files.pop(i), refresh()), "danger", width=34, height=30).pack(
                    side="right", padx=(0, 8))
                if order:
                    self.btn(row, "▼", lambda i=i: move(i, 1), width=34, height=30).pack(side="right", padx=2)
                    self.btn(row, "▲", lambda i=i: move(i, -1), width=34, height=30).pack(side="right", padx=2)
            readout.configure(text=f"{len(files)} file dipilih" if files else "Belum ada file.")

        def move(i, d):
            j = i + d
            files = st["files"]
            if 0 <= j < len(files):
                files[i], files[j] = files[j], files[i]
                refresh()

        def add():
            paths = filedialog.askopenfilenames(title="Pilih PDF", filetypes=[("PDF", "*.pdf")])
            if not paths:
                return
            if multi:
                for p in paths:
                    if p not in st["files"]:
                        st["files"].append(p)
            else:
                st["files"] = [paths[0]]
            refresh()

        def start():
            if self.busy:
                return
            if len(st["files"]) < min_files:
                messagebox.showwarning("Belum cukup file", f"Tambahkan minimal {min_files} file PDF.")
                return
            out = out_entry.get().strip()
            if not out:
                messagebox.showwarning("Folder tujuan", "Pilih folder tujuan dulu.")
                return
            self.busy = True
            go.configure(state="disabled", text="⏳  Memproses…")
            opts = st["get_opts"]()
            files = list(st["files"])

            def work():
                try:
                    os.makedirs(out, exist_ok=True)
                    paths = run(files, opts, out, say)
                    self.after(0, lambda: messagebox.showinfo("Selesai", f"{len(paths)} file tersimpan di:\n{out}"))
                except ValueError as e:
                    say(str(e) or "Format halaman tidak valid. Contoh: 1-3,5", 0, True)
                except Exception as e:  # noqa: BLE001
                    say(f"Error: {e}", 0, True)
                finally:
                    self.busy = False
                    self.after(0, lambda: go.configure(state="normal", text=btn_text))
            threading.Thread(target=work, daemon=True).start()

        refresh()

    def _run_merge(self, files, opts, out, say):
        doc = fitz.open()
        for i, f in enumerate(files, start=1):
            say(f"Menggabung file {i} dari {len(files)}…", (i - 1) / len(files))
            with fitz.open(f) as src:
                doc.insert_pdf(src)
        path = unique_path(os.path.join(out, "gabungan.pdf"))
        doc.save(path, garbage=3, deflate=True)
        doc.close()
        say("Selesai ✅  gabungan.pdf tersimpan.", 1.0)
        return [path]

    def _run_split(self, files, opts, out, say):
        f = files[0]
        stem = os.path.splitext(os.path.basename(f))[0]
        paths = []
        with fitz.open(f) as src:
            n = src.page_count
            if opts["mode"] == "Tiap halaman":
                for i in range(n):
                    say(f"Halaman {i + 1} dari {n}…", i / n)
                    d = fitz.open()
                    d.insert_pdf(src, from_page=i, to_page=i)
                    path = unique_path(os.path.join(out, f"{stem}_halaman_{i + 1:03d}.pdf"))
                    d.save(path, garbage=3, deflate=True)
                    d.close()
                    paths.append(path)
            else:
                idx = parse_pages(opts["range"], n)
                if not idx:
                    raise ValueError(f"Tidak ada halaman yang cocok. File ini punya {n} halaman.")
                d = fitz.open()
                for i in idx:
                    d.insert_pdf(src, from_page=i, to_page=i)
                tag = opts["range"].replace(" ", "").replace(",", "_") or "semua"
                path = unique_path(os.path.join(out, f"{stem}_hal_{tag}.pdf"))
                d.save(path, garbage=3, deflate=True)
                d.close()
                paths.append(path)
        say(f"Selesai ✅  {len(paths)} file tersimpan.", 1.0)
        return paths

    def _run_rotate(self, files, opts, out, say):
        f = files[0]
        deg = int(opts["deg"].rstrip("°"))
        stem = os.path.splitext(os.path.basename(f))[0]
        with fitz.open(f) as doc:
            idx = parse_pages(opts["range"], doc.page_count)
            if not idx:
                raise ValueError(f"Tidak ada halaman yang cocok. File ini punya {doc.page_count} halaman.")
            for i in idx:
                page = doc[i]
                page.set_rotation((page.rotation + deg) % 360)
            path = unique_path(os.path.join(out, f"{stem}_diputar.pdf"))
            doc.save(path, garbage=3, deflate=True)
        say("Selesai ✅  PDF yang diputar tersimpan.", 1.0)
        return [path]

    def _run_compress(self, files, opts, out, say):
        dpi, quality = {"Ringan": (150, 85), "Sedang": (110, 70), "Kuat": (80, 55)}[opts["level"]]
        paths, before, after = [], 0, 0
        for i, f in enumerate(files, start=1):
            say(f"Mengompres file {i} dari {len(files)}…", (i - 1) / len(files))
            stem = os.path.splitext(os.path.basename(f))[0]
            path = unique_path(os.path.join(out, f"{stem}_kecil.pdf"))
            with fitz.open(f) as doc:
                if hasattr(doc, "rewrite_images"):
                    try:
                        doc.rewrite_images(dpi_threshold=dpi + 30, dpi_target=dpi, quality=quality)
                    except Exception:  # noqa: BLE001
                        pass
                doc.save(path, garbage=4, deflate=True, clean=True)
            before += os.path.getsize(f)
            after += os.path.getsize(path)
            paths.append(path)
        if after < before:
            note = f"Ukuran turun {round((1 - after / before) * 100)}% ({before // 1024} KB → {after // 1024} KB)."
        else:
            note = "Hasil tidak lebih kecil dari aslinya. File asli sudah efisien."
        say("Selesai ✅  " + note, 1.0)
        return paths

    # ------------------------------------------------------------ tab 1: PDF -> Gambar
    def _build_pdf_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=0, minsize=330)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # file card
        fc = self.card(left)
        fc.grid(row=0, column=0, sticky="ew")
        top = ctk.CTkFrame(fc, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        self.label(top, "File PDF", 17, FG, "bold").pack(side="left")
        self.btn(top, "Hapus semua", self.pdf_clear, width=104).pack(side="right", padx=(8, 0))
        self.btn(top, "+ Tambah PDF", self.pdf_add, "primary", width=124).pack(side="right")
        self.file_box = ctk.CTkTextbox(fc, height=88, fg_color=INNER, corner_radius=12, text_color=FG,
                                       font=font(13), border_width=0)
        self.file_box.pack(fill="x", padx=18, pady=(0, 16))

        # preview card
        pc = self.card(left)
        pc.grid(row=1, column=0, sticky="nsew", pady=(14, 14))
        self.caption(pc, "Pratinjau halaman pertama").pack(anchor="w", padx=18, pady=(14, 0))
        self.preview = ctk.CTkLabel(pc, text="Belum ada file.\nTambahkan PDF untuk melihat pratinjau.",
                                    font=font(13), text_color=MUTED, justify="center")
        self.preview.pack(expand=True, fill="both", padx=18, pady=14)

        # output card
        oc = self.card(left)
        oc.grid(row=2, column=0, sticky="ew")
        self.caption(oc, "Folder tujuan").pack(anchor="w", padx=18, pady=(14, 6))
        orow = ctk.CTkFrame(oc, fg_color="transparent")
        orow.pack(fill="x", padx=18, pady=(0, 16))
        self.out_entry = ctk.CTkEntry(orow, height=36, fg_color=INNER, border_width=0, text_color=FG, font=font(13))
        self.out_entry.pack(side="left", fill="x", expand=True)
        self.out_entry.insert(0, self.out_dir)
        self.btn(orow, "Pilih…", self.choose_out, width=84, height=36).pack(side="left", padx=(8, 0))

        # rail
        rail = self.card(tab)
        rail.grid(row=0, column=1, sticky="nsew")
        bar = ctk.CTkFrame(rail, height=4, fg_color=PDF_C, corner_radius=0)
        bar.pack(fill="x")
        inner = ctk.CTkFrame(rail, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=16)
        self.label(inner, "Pengaturan", 18, FG, "bold", anchor="w").pack(anchor="w", pady=(0, 12))

        self.caption(inner, "Format").pack(anchor="w")
        self.fmt_seg = self.seg(inner, list(FORMATS))
        self.fmt_seg.set("JPEG")
        self.fmt_seg.configure(command=self._fmt_changed)
        self.fmt_seg.pack(fill="x", pady=(6, 14))

        self.caption(inner, "Resolusi").pack(anchor="w")
        self.res_seg = self.seg(inner, list(RES), command=lambda _v: self.update_readout())
        self.res_seg.set("Full HD")
        self.res_seg.pack(fill="x", pady=(6, 14))

        qrow = ctk.CTkFrame(inner, fg_color="transparent")
        qrow.pack(fill="x")
        self.caption(qrow, "Kualitas").pack(side="left")
        self.q_label = self.label(qrow, "95", 12, FG, mono=True)
        self.q_label.pack(side="right")
        self.q_slider = ctk.CTkSlider(inner, from_=40, to=100, number_of_steps=60, button_color=JPG_C,
                                      button_hover_color=JPG_HOVER, progress_color=JPG_C, fg_color=FRAME,
                                      command=lambda v: self.q_label.configure(text=str(int(v))))
        self.q_slider.set(95)
        self.q_slider.pack(fill="x", pady=(6, 14))

        self.caption(inner, "Halaman (kosong = semua)").pack(anchor="w")
        self.pages_entry = ctk.CTkEntry(inner, height=36, placeholder_text="contoh: 1-3,5", fg_color=INNER,
                                        border_width=0, text_color=FG, font=font(13))
        self.pages_entry.pack(fill="x", pady=(6, 14))

        self.readout = self.label(inner, "Belum ada file.", 12, FG, mono=True, anchor="w", justify="left",
                                  fg_color=FRAME, corner_radius=12)
        self.readout.pack(fill="x", ipady=10, pady=(0, 14))

        self.go_btn = self.btn(inner, "Konversi ke JPEG", self.pdf_start, "primary", height=46)
        self.go_btn.configure(font=font(15, "bold"), corner_radius=14)
        self.go_btn.pack(fill="x")
        self.progress = ctk.CTkProgressBar(inner, height=8, progress_color=JPG_C, fg_color=FRAME)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(12, 6))
        self.status = self.label(inner, "Siap.", 12, MUTED, anchor="w", justify="left", wraplength=270)
        self.status.pack(anchor="w")
        self.btn(inner, "📂  Buka folder hasil", self.open_out).pack(fill="x", pady=(10, 0))

        self.pdf_refresh()

    def _fmt_changed(self, value):
        self.go_btn.configure(text=f"Konversi ke {value}")
        self.q_slider.configure(state="disabled" if value == "PNG" else "normal")

    def pdf_add(self):
        for p in filedialog.askopenfilenames(title="Pilih PDF", filetypes=[("PDF", "*.pdf")]):
            if p not in self.pdfs:
                self.pdfs.append(p)
        self.pdf_refresh()

    def pdf_clear(self):
        self.pdfs = []
        self.pdf_refresh()

    def pdf_refresh(self):
        self.file_box.configure(state="normal")
        self.file_box.delete("1.0", "end")
        if self.pdfs:
            self.file_box.insert("end", "\n".join(f"•  {os.path.basename(p)}" for p in self.pdfs))
        else:
            self.file_box.insert("end", "Belum ada file. Klik “+ Tambah PDF”.")
        self.file_box.configure(state="disabled")
        self.refresh_preview()
        self.update_readout()

    def refresh_preview(self):
        if not self.pdfs:
            self.preview.configure(image=None, text="Belum ada file.\nTambahkan PDF untuk melihat pratinjau.")
            self.preview_img = None
            return
        try:
            with fitz.open(self.pdfs[0]) as doc:
                page = doc[0]
                zoom = min(330 / page.rect.height, 330 / page.rect.width) * 1.6
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            h = 300
            w = max(1, int(img.width * h / img.height))
            self.preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self.preview.configure(image=self.preview_img, text="")
        except Exception as e:  # noqa: BLE001
            self.preview.configure(image=None, text=f"Tidak bisa membuka pratinjau.\n{e}")

    def update_readout(self):
        if not self.pdfs:
            self.readout.configure(text="Belum ada file.")
            return
        try:
            with fitz.open(self.pdfs[0]) as doc:
                r = doc[0].rect
                k = scale_for(r.width, r.height, self.res_seg.get())
                self.readout.configure(
                    text=f"{len(self.pdfs)} file dipilih\n≈ {round(r.width * k)} × {round(r.height * k)} px per halaman")
        except Exception:
            self.readout.configure(text=f"{len(self.pdfs)} file dipilih")

    def choose_out(self):
        d = filedialog.askdirectory(title="Pilih folder tujuan")
        if d:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, d)

    def open_out(self):
        d = self.out_entry.get().strip()
        if not os.path.isdir(d):
            messagebox.showinfo("Info", "Folder belum ada. Lakukan konversi dulu.")
            return
        if sys.platform.startswith("win"):
            os.startfile(d)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def _say(self, text, value=None, error=False):
        def _do():
            self.status.configure(text=text, text_color=DANGER if error else MUTED)
            if value is not None:
                self.progress.set(value)
        self.after(0, _do)

    def pdf_start(self):
        if self.busy:
            return
        if not self.pdfs:
            messagebox.showwarning("Belum ada file", "Tambahkan minimal satu file PDF.")
            return
        out = self.out_entry.get().strip()
        if not out:
            messagebox.showwarning("Folder tujuan", "Pilih folder tujuan dulu.")
            return
        self.busy = True
        self.go_btn.configure(state="disabled", text="⏳  Memproses…")
        args = (list(self.pdfs), out, FORMATS[self.fmt_seg.get()], self.res_seg.get(),
                int(self.q_slider.get()), self.pages_entry.get())
        threading.Thread(target=self._pdf_work, args=args, daemon=True).start()

    def _pdf_work(self, files, out, fmt, res, quality, pages_text):
        pil_fmt, ext = fmt
        done = 0
        try:
            plan = []
            for f in files:
                with fitz.open(f) as d:
                    plan.append((f, parse_pages(pages_text, d.page_count)))
            grand = sum(len(p) for _, p in plan) or 1
            for f, pages in plan:
                stem = os.path.splitext(os.path.basename(f))[0]
                dest = os.path.join(out, stem)
                os.makedirs(dest, exist_ok=True)
                with fitz.open(f) as doc:
                    for n, idx in enumerate(pages, start=1):
                        page = doc[idx]
                        zoom = scale_for(page.rect.width, page.rect.height, res)
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        kw = {"optimize": True} if pil_fmt != "WEBP" else {}
                        if pil_fmt != "PNG":
                            kw["quality"] = quality
                        if pil_fmt == "JPEG":
                            kw["subsampling"] = 0  # warna penuh 4:4:4, teks tidak berbayang
                        img.save(os.path.join(dest, f"{stem}_halaman_{n:03d}.{ext}"), pil_fmt, **kw)
                        done += 1
                        self._say(f"Memproses {done} dari {grand}…", done / grand)
            self._say(f"Selesai ✅  {done} gambar tersimpan.", 1.0)
            self.after(0, lambda: messagebox.showinfo("Selesai", f"{done} gambar berhasil dibuat."))
        except ValueError:
            self._say("Format halaman tidak valid. Contoh: 1-3,5", 0, True)
        except Exception as e:  # noqa: BLE001
            self._say(f"Error: {e}", 0, True)
        finally:
            self.busy = False
            self.after(0, lambda: self.go_btn.configure(state="normal", text=f"Konversi ke {self.fmt_seg.get()}"))

    # ------------------------------------------------------------ tab 2: Gambar -> PDF
    def _build_img_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=0, minsize=330)
        tab.grid_rowconfigure(0, weight=1)

        left = self.card(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        self.label(top, "Gambar", 17, FG, "bold").pack(side="left")
        self.btn(top, "Hapus semua", self.img_clear, width=104).pack(side="right", padx=(8, 0))
        self.btn(top, "+ Tambah gambar", self.img_add, "primary", width=140).pack(side="right")
        self.label(left, "Urutan di daftar ini menjadi urutan halaman di PDF.", 12, MUTED, anchor="w").pack(
            anchor="w", padx=18)
        self.img_list = ctk.CTkScrollableFrame(left, fg_color=INNER, corner_radius=12)
        self.img_list.pack(fill="both", expand=True, padx=18, pady=(10, 18))

        rail = self.card(tab)
        rail.grid(row=0, column=1, sticky="nsew")
        ctk.CTkFrame(rail, height=4, fg_color=JPG_C, corner_radius=0).pack(fill="x")
        inner = ctk.CTkFrame(rail, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=16)
        self.label(inner, "Pengaturan PDF", 18, FG, "bold", anchor="w").pack(anchor="w", pady=(0, 12))
        self.caption(inner, "Ukuran halaman").pack(anchor="w")
        self.size_seg = self.seg(inner, ["Sesuai gambar", "A4"])
        self.size_seg.set("Sesuai gambar")
        self.size_seg.pack(fill="x", pady=(6, 14))
        self.img_readout = self.label(inner, "Belum ada gambar.", 12, FG, mono=True, anchor="w", justify="left",
                                      fg_color=FRAME, corner_radius=12)
        self.img_readout.pack(fill="x", ipady=10, pady=(0, 14))
        self.pdf_btn = self.btn(inner, "Buat PDF", self.img_make, "primary", height=46)
        self.pdf_btn.configure(font=font(15, "bold"), corner_radius=14)
        self.pdf_btn.pack(fill="x")
        self.img_progress = ctk.CTkProgressBar(inner, height=8, progress_color=JPG_C, fg_color=FRAME)
        self.img_progress.set(0)
        self.img_progress.pack(fill="x", pady=(12, 6))
        self.img_status = self.label(inner, "Siap.", 12, MUTED, anchor="w", justify="left", wraplength=270)
        self.img_status.pack(anchor="w")
        self.img_rebuild()

    def img_add(self):
        for p in filedialog.askopenfilenames(title="Pilih gambar", filetypes=IMG_TYPES):
            self.images.append(p)
        self.img_rebuild()

    def img_clear(self):
        self.images = []
        self.img_rebuild()

    def img_move(self, i, d):
        j = i + d
        if 0 <= j < len(self.images):
            self.images[i], self.images[j] = self.images[j], self.images[i]
            self.img_rebuild()

    def img_remove(self, i):
        del self.images[i]
        self.img_rebuild()

    def img_rebuild(self):
        for w in self.img_list.winfo_children():
            w.destroy()
        if not self.images:
            self.label(self.img_list, "Belum ada gambar.\nKlik “+ Tambah gambar”.", 13, MUTED).pack(pady=40)
        for i, p in enumerate(self.images):
            row = ctk.CTkFrame(self.img_list, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=LINE)
            row.pack(fill="x", pady=4, padx=4)
            self.label(row, f"{i + 1:02d}", 12, JPG_C, mono=True).pack(side="left", padx=(12, 8), pady=10)
            self.label(row, os.path.basename(p), 13, FG, anchor="w").pack(side="left", fill="x", expand=True)
            self.btn(row, "✕", lambda i=i: self.img_remove(i), "danger", width=34, height=30).pack(side="right", padx=(0, 8))
            self.btn(row, "▼", lambda i=i: self.img_move(i, 1), width=34, height=30).pack(side="right", padx=2)
            self.btn(row, "▲", lambda i=i: self.img_move(i, -1), width=34, height=30).pack(side="right", padx=2)
        n = len(self.images)
        self.img_readout.configure(text=f"{n} gambar akan jadi {n} halaman" if n else "Belum ada gambar.")

    def _img_say(self, text, value=None, error=False):
        def _do():
            self.img_status.configure(text=text, text_color=DANGER if error else MUTED)
            if value is not None:
                self.img_progress.set(value)
        self.after(0, _do)

    def img_make(self):
        if self.busy:
            return
        if not self.images:
            messagebox.showwarning("Belum ada gambar", "Tambahkan minimal satu gambar.")
            return
        out = filedialog.asksaveasfilename(title="Simpan PDF", defaultextension=".pdf",
                                           filetypes=[("PDF", "*.pdf")], initialfile="PIXORA.pdf")
        if not out:
            return
        self.busy = True
        self.pdf_btn.configure(state="disabled", text="⏳  Memproses…")
        threading.Thread(target=self._img_work, args=(list(self.images), self.size_seg.get(), out), daemon=True).start()

    def _img_work(self, paths, size, out):
        try:
            pages = []
            for i, p in enumerate(paths, start=1):
                im = ImageOps.exif_transpose(Image.open(p))
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGBA")
                    bg = Image.new("RGB", im.size, "white")
                    bg.paste(im, mask=im.split()[3])
                    im = bg
                else:
                    im = im.convert("RGB")
                if size == "A4":  # 150 DPI
                    canvas = Image.new("RGB", (1240, 1754), "white")
                    im.thumbnail((1240 - 120, 1754 - 120))
                    canvas.paste(im, ((1240 - im.width) // 2, (1754 - im.height) // 2))
                    im = canvas
                pages.append(im)
                self._img_say(f"Membaca gambar {i} dari {len(paths)}…", i / len(paths) * 0.9)
            self._img_say("Menyimpan PDF…", 0.95)
            pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
            self._img_say(f"Selesai ✅  {len(pages)} halaman tersimpan.", 1.0)
            self.after(0, lambda: messagebox.showinfo("Selesai", f"PDF berhasil dibuat:\n{out}"))
        except Exception as e:  # noqa: BLE001
            self._img_say(f"Error: {e}", 0, True)
        finally:
            self.busy = False
            self.after(0, lambda: self.pdf_btn.configure(state="normal", text="Buat PDF"))

    # ------------------------------------------------------------ tab 3: PDF -> Word
    def _build_doc_tab(self, tab):
        self.docs = []
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=0, minsize=330)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        fc = self.card(left)
        fc.grid(row=0, column=0, sticky="nsew")
        top = ctk.CTkFrame(fc, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        self.label(top, "File PDF", 17, FG, "bold").pack(side="left")
        self.btn(top, "Hapus semua", self.doc_clear, width=104).pack(side="right", padx=(8, 0))
        self.btn(top, "+ Tambah PDF", self.doc_add, "primary", width=124).pack(side="right")
        self.doc_box = ctk.CTkTextbox(fc, fg_color=INNER, corner_radius=12, text_color=FG, font=font(13), border_width=0)
        self.doc_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.label(fc, "Tata letak, tabel, dan gambar dipertahankan semaksimal mungkin.\n"
                       "PDF hasil pindai (berupa gambar) butuh OCR, yang belum tersedia.",
                   12, MUTED, anchor="w", justify="left").pack(anchor="w", padx=18, pady=(0, 14))

        oc = self.card(left)
        oc.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.caption(oc, "Folder tujuan").pack(anchor="w", padx=18, pady=(14, 6))
        orow = ctk.CTkFrame(oc, fg_color="transparent")
        orow.pack(fill="x", padx=18, pady=(0, 16))
        self.doc_out = ctk.CTkEntry(orow, height=36, fg_color=INNER, border_width=0, text_color=FG, font=font(13))
        self.doc_out.pack(side="left", fill="x", expand=True)
        self.doc_out.insert(0, os.path.join(os.path.expanduser("~"), "Documents", "PIXORA"))
        self.btn(orow, "Pilih…", self.doc_choose_out, width=84, height=36).pack(side="left", padx=(8, 0))

        rail = self.card(tab)
        rail.grid(row=0, column=1, sticky="nsew")
        ctk.CTkFrame(rail, height=4, fg_color=PDF_C, corner_radius=0).pack(fill="x")
        inner = ctk.CTkFrame(rail, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=16)
        self.label(inner, "Pengaturan Word", 18, FG, "bold", anchor="w").pack(anchor="w", pady=(0, 12))
        self.caption(inner, "Halaman (kosong = semua)").pack(anchor="w")
        self.doc_pages = ctk.CTkEntry(inner, height=36, placeholder_text="contoh: 1-3,5", fg_color=INNER,
                                      border_width=0, text_color=FG, font=font(13))
        self.doc_pages.pack(fill="x", pady=(6, 14))
        self.doc_readout = self.label(inner, "Belum ada file.", 12, FG, mono=True, anchor="w", justify="left",
                                      fg_color=FRAME, corner_radius=12)
        self.doc_readout.pack(fill="x", ipady=10, pady=(0, 14))
        self.doc_btn = self.btn(inner, "Konversi ke Word", self.doc_start, "primary", height=46)
        self.doc_btn.configure(font=font(15, "bold"), corner_radius=14)
        self.doc_btn.pack(fill="x")
        self.doc_progress = ctk.CTkProgressBar(inner, height=8, progress_color=JPG_C, fg_color=FRAME)
        self.doc_progress.set(0)
        self.doc_progress.pack(fill="x", pady=(12, 6))
        self.doc_status = self.label(inner, "Siap.", 12, MUTED, anchor="w", justify="left", wraplength=270)
        self.doc_status.pack(anchor="w")
        self.btn(inner, "📂  Buka folder hasil", self.doc_open).pack(fill="x", pady=(10, 0))
        self.doc_refresh()

    def doc_add(self):
        for p in filedialog.askopenfilenames(title="Pilih PDF", filetypes=[("PDF", "*.pdf")]):
            if p not in self.docs:
                self.docs.append(p)
        self.doc_refresh()

    def doc_clear(self):
        self.docs = []
        self.doc_refresh()

    def doc_refresh(self):
        self.doc_box.configure(state="normal")
        self.doc_box.delete("1.0", "end")
        if self.docs:
            self.doc_box.insert("end", "\n".join(f"•  {os.path.basename(p)}" for p in self.docs))
        else:
            self.doc_box.insert("end", "Belum ada file. Klik “+ Tambah PDF”.")
        self.doc_box.configure(state="disabled")
        self.doc_readout.configure(text=f"{len(self.docs)} file akan jadi .docx" if self.docs else "Belum ada file.")

    def doc_choose_out(self):
        d = filedialog.askdirectory(title="Pilih folder tujuan")
        if d:
            self.doc_out.delete(0, "end")
            self.doc_out.insert(0, d)

    def doc_open(self):
        d = self.doc_out.get().strip()
        if not os.path.isdir(d):
            messagebox.showinfo("Info", "Folder belum ada. Lakukan konversi dulu.")
            return
        if sys.platform.startswith("win"):
            os.startfile(d)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def _doc_say(self, text, value=None, error=False):
        def _do():
            self.doc_status.configure(text=text, text_color=DANGER if error else MUTED)
            if value is not None:
                self.doc_progress.set(value)
        self.after(0, _do)

    def doc_start(self):
        if self.busy:
            return
        if not self.docs:
            messagebox.showwarning("Belum ada file", "Tambahkan minimal satu file PDF.")
            return
        out = self.doc_out.get().strip()
        if not out:
            messagebox.showwarning("Folder tujuan", "Pilih folder tujuan dulu.")
            return
        self.busy = True
        self.doc_btn.configure(state="disabled", text="⏳  Memproses…")
        threading.Thread(target=self._doc_work, args=(list(self.docs), out, self.doc_pages.get()), daemon=True).start()

    def _doc_work(self, files, out, pages_text):
        done, skipped = 0, []
        try:
            try:
                from pdf2docx import Converter
            except ImportError:
                self._doc_say("Modul pdf2docx belum terpasang. Jalankan: pip install pdf2docx", 0, True)
                return
            os.makedirs(out, exist_ok=True)
            for i, f in enumerate(files, start=1):
                self._doc_say(f"File {i} dari {len(files)}: {os.path.basename(f)}…", (i - 1) / len(files))
                with fitz.open(f) as d:
                    total = d.page_count
                    has_text = any(d[n].get_text().strip() for n in range(min(total, 5)))
                    pages = parse_pages(pages_text, total)
                if not has_text:
                    skipped.append(os.path.basename(f))
                    continue
                dest = os.path.join(out, os.path.splitext(os.path.basename(f))[0] + ".docx")
                cv = Converter(f)
                try:
                    cv.convert(dest, pages=pages if pages_text.strip() else None)
                finally:
                    cv.close()
                done += 1
            note = f" Dilewati karena tanpa teks: {', '.join(skipped)}." if skipped else ""
            self._doc_say(f"Selesai ✅  {done} file tersimpan.{note}", 1.0)
            if done:
                self.after(0, lambda: messagebox.showinfo("Selesai", f"{done} file Word berhasil dibuat."))
        except ValueError:
            self._doc_say("Format halaman tidak valid. Contoh: 1-3,5", 0, True)
        except Exception as e:  # noqa: BLE001
            self._doc_say(f"Error: {e}", 0, True)
        finally:
            self.busy = False
            self.after(0, lambda: self.doc_btn.configure(state="normal", text="Konversi ke Word"))


if __name__ == "__main__":
    App().mainloop()
