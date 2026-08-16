"""Generuje app.ico (ikona News Reader) — uruchom: python make_icon.py"""

import os
from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 24, 32, 48, 64, 128, 256]
BG = (26, 92, 240, 255)
FG = (255, 255, 255, 255)
RING = (255, 255, 255, 210)


def _font(size):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 2
    d.rounded_rectangle((1, 1, size - 2, size - 2), radius=int(size * 0.22), fill=BG)
    d.rounded_rectangle((int(size * 0.10), int(size * 0.10), int(size * 0.90), int(size * 0.90)),
                        radius=int(size * 0.16), outline=RING, width=max(1, size // 32))
    f = _font(int(size * 0.66))
    d.text((size / 2, size / 2), "N", font=f, fill=FG, anchor="mm")
    return img


def main():
    images = [_draw(s) for s in SIZES]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print("Zapisano:", out)


if __name__ == "__main__":
    main()
