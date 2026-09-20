"""Generate RCS brand assets for the ClaimPilot testing agent.

Logo:   224x224 PNG w/ transparency, <=50KB
Banner: 1440x448 PNG, <=200KB
Brand color: #1A56DB (deep blue) — contrast vs white ~ 5.9:1 (>=4.5 required).
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.dirname(os.path.abspath(__file__))
BRAND = (26, 86, 219)      # #1A56DB
BRAND_DARK = (17, 58, 150)
WHITE = (255, 255, 255)


def _font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_logo():
    size = 224
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # rounded blue square
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=44, fill=BRAND + (255,))
    # a simple shield / checkmark motif = "claim protected"
    d.rounded_rectangle([64, 40, 160, 150], radius=16, fill=WHITE + (255,))
    d.line([(78, 96), (104, 122), (150, 66)], fill=BRAND + (255,), width=14, joint="curve")
    # "CP" wordmark
    f = _font(52)
    d.text((size / 2, 185), "ClaimPilot", font=_font(26), fill=WHITE + (255,), anchor="mm")
    path = os.path.join(OUT, "logo.png")
    img.save(path, "PNG", optimize=True)
    return path


def make_banner():
    w, h = 1440, 448
    img = Image.new("RGB", (w, h), BRAND)
    d = ImageDraw.Draw(img)
    # diagonal darker band for depth
    d.polygon([(0, h), (w, 0), (w, h)], fill=BRAND_DARK)
    d.text((80, h / 2 - 40), "ClaimPilot", font=_font(96), fill=WHITE, anchor="lm")
    d.text((84, h / 2 + 52), "File your claim in minutes", font=_font(40), fill=(220, 230, 255), anchor="lm")
    path = os.path.join(OUT, "banner.png")
    img.save(path, "PNG", optimize=True)
    return path


if __name__ == "__main__":
    lp = make_logo()
    bp = make_banner()
    for p in (lp, bp):
        kb = os.path.getsize(p) / 1024
        print(f"{os.path.basename(p)}: {kb:.1f} KB -> {p}")
