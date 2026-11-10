"""PIXORA by Rey - aplikasi pengolah PDF dan gambar.

Fitur:
  - PDF -> Gambar (JPEG, PNG, WebP), pilih halaman, resolusi, kualitas
  - Gambar -> PDF, urutan bisa diatur

Dependensi: customtkinter, pymupdf, pillow
"""
import os
import sys
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
# Sisi terpanjang minimal sesuai pilihan (Full HD = 1920 px), dan tidak pernah di bawah 150 DPI
RES = {"Full HD": 1920, "2K": 2560, "4K": 3840, "300 DPI": None}
IMG_TYPES = [("Gambar", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"), ("Semua file", "*.*")]
FORMATS = {"JPEG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WebP": ("WEBP", "webp")}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def font(size, weight="normal", mono=False):
    return ctk.CTkFont(family="Consolas" if mono else "Segoe UI", size=size, weight=weight)


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

        self._build_header()
        self._build_tabs()
        self._show_tab("PDF → Gambar")

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

    def _build_tabs(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=28, pady=(10, 10))
        self.tab_seg = ctk.CTkSegmentedButton(
            bar, values=["PDF → Gambar", "Gambar → PDF"], command=self._show_tab, height=38, corner_radius=12,
            fg_color=SURFACE, selected_color=JPG_DEEP, selected_hover_color=JPG_DEEP,
            unselected_color=SURFACE, unselected_hover_color=FRAME, text_color=FG, font=font(14, "bold"))
        self.tab_seg.pack(side="left")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        self.tab_pdf = ctk.CTkFrame(self.body, fg_color="transparent")
        self.tab_img = ctk.CTkFrame(self.body, fg_color="transparent")
        self._build_pdf_tab(self.tab_pdf)
        self._build_img_tab(self.tab_img)

    def _show_tab(self, name):
        self.tab_seg.set(name)
        self.tab_pdf.pack_forget()
        self.tab_img.pack_forget()
        (self.tab_pdf if name == "PDF → Gambar" else self.tab_img).pack(fill="both", expand=True)

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


if __name__ == "__main__":
    App().mainloop()
