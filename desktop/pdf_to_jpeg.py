"""PDF -> JPEG Studio
Aplikasi desktop modern untuk mengubah PDF menjadi gambar JPEG.
Dependensi: customtkinter, pymupdf, pillow
"""
import os
import sys
import threading
import subprocess
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#7C5CFF"
ACCENT_HOVER = "#6747F0"
CARD = "#1E1F2B"
BG = "#13141C"


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
        self.title("PDF → JPEG Studio")
        self.geometry("780x700")
        self.minsize(720, 660)
        self.configure(fg_color=BG)

        self.files = []
        self.out_dir = os.path.join(os.path.expanduser("~"), "Pictures", "PDF2JPEG")
        self.busy = False
        self._build_ui()

    # ------------------------------------------------------------ UI
    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16)

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            header, text="📄 → 🖼️  PDF to JPEG Studio",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="Ubah halaman PDF jadi gambar JPEG berkualitas tinggi, cepat dan mudah.",
            text_color="#9aa0b4",
        ).pack(anchor="w")

        # File card
        fc = self._card(self)
        fc.pack(fill="x", padx=24, pady=8)
        row = ctk.CTkFrame(fc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(row, text="File PDF", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkButton(row, text="Hapus semua", width=100, fg_color="#2c2e3f", hover_color="#3a3d52",
                      command=self.clear_files).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row, text="+ Tambah PDF", width=120, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.add_files).pack(side="right")
        self.file_box = ctk.CTkTextbox(fc, height=90, fg_color="#171824", corner_radius=10)
        self.file_box.pack(fill="x", padx=16, pady=(0, 14))
        self._refresh_files()

        # Output card
        oc = self._card(self)
        oc.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(oc, text="Folder tujuan", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 6))
        orow = ctk.CTkFrame(oc, fg_color="transparent")
        orow.pack(fill="x", padx=16, pady=(0, 14))
        self.out_entry = ctk.CTkEntry(orow, fg_color="#171824", border_width=0, height=36)
        self.out_entry.pack(side="left", fill="x", expand=True)
        self.out_entry.insert(0, self.out_dir)
        ctk.CTkButton(orow, text="Pilih…", width=80, height=36, fg_color="#2c2e3f",
                      hover_color="#3a3d52", command=self.choose_out).pack(side="left", padx=(8, 0))

        # Settings card
        sc = self._card(self)
        sc.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(sc, text="Pengaturan", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4))

        self.dpi_label = ctk.CTkLabel(sc, text="Resolusi: 150 DPI")
        self.dpi_label.pack(anchor="w", padx=16)
        self.dpi = ctk.CTkSlider(sc, from_=72, to=300, number_of_steps=19, button_color=ACCENT,
                                 progress_color=ACCENT, command=self._dpi_changed)
        self.dpi.set(150)
        self.dpi.pack(fill="x", padx=16, pady=(2, 8))

        self.q_label = ctk.CTkLabel(sc, text="Kualitas JPEG: 90")
        self.q_label.pack(anchor="w", padx=16)
        self.quality = ctk.CTkSlider(sc, from_=40, to=100, number_of_steps=60, button_color=ACCENT,
                                     progress_color=ACCENT, command=self._q_changed)
        self.quality.set(90)
        self.quality.pack(fill="x", padx=16, pady=(2, 8))

        prow = ctk.CTkFrame(sc, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(prow, text="Halaman (kosong = semua, contoh 1-3,5):").pack(side="left")
        self.pages_entry = ctk.CTkEntry(prow, width=140, fg_color="#171824", border_width=0)
        self.pages_entry.pack(side="left", padx=10)

        # Convert
        self.btn = ctk.CTkButton(self, text="🚀  Konversi Sekarang", height=48,
                                 font=ctk.CTkFont(size=16, weight="bold"),
                                 fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=14,
                                 command=self.start)
        self.btn.pack(fill="x", padx=24, pady=(10, 6))

        self.progress = ctk.CTkProgressBar(self, progress_color=ACCENT, height=10)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=24, pady=(4, 4))
        self.status = ctk.CTkLabel(self, text="Siap.", text_color="#9aa0b4")
        self.status.pack(anchor="w", padx=26)

        self.log = ctk.CTkTextbox(self, height=90, fg_color=CARD, corner_radius=12)
        self.log.pack(fill="both", expand=True, padx=24, pady=(6, 6))
        self.log.configure(state="disabled")

        ctk.CTkButton(self, text="📂 Buka folder hasil", fg_color="transparent", border_width=1,
                      border_color="#2c2e3f", hover_color="#2c2e3f",
                      command=self.open_out).pack(pady=(0, 14))

    # ------------------------------------------------------ helpers
    def _dpi_changed(self, v):
        self.dpi_label.configure(text=f"Resolusi: {int(v)} DPI")

    def _q_changed(self, v):
        self.q_label.configure(text=f"Kualitas JPEG: {int(v)}")

    def _refresh_files(self):
        self.file_box.configure(state="normal")
        self.file_box.delete("1.0", "end")
        if self.files:
            self.file_box.insert("end", "\n".join(f"• {os.path.basename(f)}" for f in self.files))
        else:
            self.file_box.insert("end", "Belum ada file. Klik “+ Tambah PDF”.")
        self.file_box.configure(state="disabled")

    def _log(self, msg):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _do)

    def _set_status(self, text, value=None):
        def _do():
            self.status.configure(text=text)
            if value is not None:
                self.progress.set(value)
        self.after(0, _do)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Pilih PDF", filetypes=[("PDF", "*.pdf")])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._refresh_files()

    def clear_files(self):
        self.files = []
        self._refresh_files()

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
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    # --------------------------------------------------- conversion
    def start(self):
        if self.busy:
            return
        if not self.files:
            messagebox.showwarning("Belum ada file", "Tambahkan minimal satu file PDF.")
            return
        out = self.out_entry.get().strip()
        if not out:
            messagebox.showwarning("Folder tujuan", "Pilih folder tujuan dulu.")
            return
        self.busy = True
        self.btn.configure(state="disabled", text="⏳ Memproses…")
        args = (list(self.files), out, int(self.dpi.get()), int(self.quality.get()),
                self.pages_entry.get())
        threading.Thread(target=self._work, args=args, daemon=True).start()

    def _work(self, files, out, dpi, quality, pages_text):
        total_done = 0
        try:
            # hitung total halaman untuk progress bar
            plan = []
            for f in files:
                with fitz.open(f) as d:
                    plan.append((f, parse_pages(pages_text, d.page_count)))
            grand = sum(len(p) for _, p in plan) or 1
            zoom = dpi / 72.0
            for f, pages in plan:
                stem = os.path.splitext(os.path.basename(f))[0]
                dest = os.path.join(out, stem)
                os.makedirs(dest, exist_ok=True)
                self._log(f"▶ {os.path.basename(f)} ({len(pages)} halaman)")
                with fitz.open(f) as doc:
                    for idx in pages:
                        pix = doc[idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        img.save(os.path.join(dest, f"{stem}_page_{idx + 1:03d}.jpg"),
                                 "JPEG", quality=quality, optimize=True)
                        total_done += 1
                        self._set_status(f"Memproses {total_done}/{grand}…", total_done / grand)
            self._set_status("Selesai! ✅", 1.0)
            self._log(f"✅ Selesai: {total_done} gambar disimpan di {out}")
            self.after(0, lambda: messagebox.showinfo("Selesai", f"{total_done} gambar berhasil dibuat."))
        except Exception as e:  # noqa: BLE001
            self._set_status("Terjadi error ❌", 0)
            self._log(f"❌ Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.busy = False
            self.after(0, lambda: self.btn.configure(state="normal", text="🚀  Konversi Sekarang"))


if __name__ == "__main__":
    App().mainloop()
