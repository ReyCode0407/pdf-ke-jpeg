"""Ikon PIXORA: kotak gradien oranye ke teal dengan halaman dokumen.
Dipakai oleh aplikasi (ikon jendela) dan untuk membuat icon.ico saat build."""
from PIL import Image, ImageChops, ImageDraw

PDF_RGB = (255, 107, 61)
JPG_RGB = (52, 217, 197)
DARK_RGB = (6, 17, 15)


def make_icon(size=256):
    s = size
    v = Image.linear_gradient("L").resize((s, s))
    grad = ImageChops.add(v, v.transpose(Image.Transpose.ROTATE_90), scale=2)  # gradien diagonal
    base = Image.composite(Image.new("RGB", (s, s), JPG_RGB), Image.new("RGB", (s, s), PDF_RGB), grad)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.28), fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(base, (0, 0), mask)

    d = ImageDraw.Draw(img)
    w = max(2, int(s * 0.07))
    x0, y0, x1, y1 = s * 0.30, s * 0.20, s * 0.70, s * 0.80
    fold = s * 0.18
    d.line([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1), (x0, y0)],
           fill=DARK_RGB, width=w, joint="curve")
    d.line([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill=DARK_RGB, width=w, joint="curve")
    d.line([(s * 0.38, s * 0.66), (s * 0.48, s * 0.55), (s * 0.55, s * 0.62), (s * 0.63, s * 0.50)],
           fill=DARK_RGB, width=w, joint="curve")
    return img


if __name__ == "__main__":
    big = make_icon(256)
    big.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon.ico dibuat")
