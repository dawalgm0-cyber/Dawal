"""Generate DAWAL rider PWA icons (navy field + orange location pin)."""

import os

from PIL import Image, ImageDraw

NAVY = (26, 58, 92)
ORANGE = (244, 130, 10)
WHITE = (255, 255, 255)
OUT = os.path.join(os.path.dirname(__file__), "..", "icons")
os.makedirs(OUT, exist_ok=True)


def pin(size, pad_frac=0.0):
    img = Image.new("RGBA", (size, size), NAVY + (255,))
    d = ImageDraw.Draw(img)
    pad = int(size * pad_frac)
    inner = size - 2 * pad
    # location pin: a circle head + a triangle tail, orange, with a navy dot.
    cx = size / 2
    head_r = inner * 0.24
    head_cy = pad + inner * 0.36
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=ORANGE)
    tip_y = pad + inner * 0.86
    d.polygon([(cx - head_r * 0.82, head_cy + head_r * 0.55),
               (cx + head_r * 0.82, head_cy + head_r * 0.55),
               (cx, tip_y)], fill=ORANGE)
    dot_r = head_r * 0.42
    d.ellipse([cx - dot_r, head_cy - dot_r, cx + dot_r, head_cy + dot_r], fill=NAVY)
    return img


def save(img, name):
    img.convert("RGB").save(os.path.join(OUT, name))
    print("wrote", name, img.size)


save(pin(192), "icon-192.png")
save(pin(512), "icon-512.png")
# maskable: extra padding so the pin survives platform mask cropping
save(pin(512, pad_frac=0.14), "icon-maskable-512.png")
