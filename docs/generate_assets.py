"""
generate_assets.py
-------------------
Programmatically draws the app icon (icon.ico) and the README hero banner
(banner.png). Re-runnable, no design software needed.

Run:  python docs/generate_assets.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parent

# Brand colors
BLUE_TOP = (59, 130, 246)     # #3b82f6
BLUE_BOT = (29, 78, 216)      # #1d4ed8
NAVY = (15, 23, 42)           # #0f172a
WHITE = (255, 255, 255)
GRAY = (148, 163, 184)
GREEN = (52, 211, 153)

SEGOE = "C:/Windows/Fonts/segoeui.ttf"
SEGOE_B = "C:/Windows/Fonts/segoeuib.ttf"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _vgradient(size, top, bottom):
    """Vertical gradient image (drawn row by row — no numpy needed)."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


# ======================================================================
#  ICON  — rounded blue tile with inward "compress" chevrons + center bar
# ======================================================================
def make_icon():
    S = 512
    base = _vgradient((S, S), BLUE_TOP, BLUE_BOT).convert("RGBA")

    # Rounded-corner mask so the tile has soft edges.
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=110, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    d = ImageDraw.Draw(icon)
    cy = S // 2
    w = 40  # stroke width

    # Left chevron ">" pointing right (toward center)
    d.line([(120, cy - 110), (215, cy), (120, cy + 110)],
           fill=WHITE, width=w, joint="curve")
    # Right chevron "<" pointing left (toward center)
    d.line([(392, cy - 110), (297, cy), (392, cy + 110)],
           fill=WHITE, width=w, joint="curve")
    # Center "compressed seam" bar
    d.rounded_rectangle([S // 2 - 16, cy - 130, S // 2 + 16, cy + 130],
                        radius=16, fill=WHITE)

    # Save a PNG (for README) and a multi-size ICO (for the .exe + window).
    icon.save(DOCS / "icon.png")
    icon.save(DOCS / "icon.ico",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("[ok] icon.png + icon.ico")
    return icon


# ======================================================================
#  BANNER — hero image for the top of the README
# ======================================================================
def make_banner(icon_img):
    W, H = 1280, 460
    banner = _vgradient((W, H), NAVY, (30, 41, 90)).convert("RGBA")
    d = ImageDraw.Draw(banner)

    # Icon on the left
    ic = icon_img.resize((180, 180), Image.LANCZOS)
    banner.alpha_composite(ic, (70, 70))

    # Title + tagline
    d.text((290, 95), "MultiCompress", font=_font(SEGOE_B, 76), fill=WHITE)
    d.text((296, 188), "Compress video • images • audio • PDF — 100% offline, ₹0 forever",
           font=_font(SEGOE, 30), fill=GRAY)

    # Stat pills — drawn on a SEPARATE transparent layer so the translucent
    # fill alpha-composites correctly (drawing low-alpha directly onto the
    # banner just replaces pixels and loses the transparency).
    pills = [("−87% Video", GREEN), ("−86% Image", GREEN),
             ("−82% Audio", GREEN), ("Offline", BLUE_TOP), ("Free Forever", BLUE_TOP)]
    f = _font(SEGOE_B, 24)
    pad, gap, h, y = 20, 14, 52, 300

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    positions = []
    x = 296
    for text, color in pills:
        tw = od.textlength(text, font=f)
        od.rounded_rectangle([x, y, x + tw + pad * 2, y + h], radius=h // 2,
                             fill=(255, 255, 255, 28), outline=color, width=2)
        positions.append((x + pad, y + 12, text))
        x += tw + pad * 2 + gap

    banner = Image.alpha_composite(banner, overlay)

    # Now draw the pill TEXT on top of the composited pills.
    d = ImageDraw.Draw(banner)
    for tx, ty, text in positions:
        d.text((tx, ty), text, font=f, fill=WHITE)

    banner.convert("RGB").save(DOCS / "banner.png")
    print("[ok] banner.png")


if __name__ == "__main__":
    icon = make_icon()
    make_banner(icon)
    print("\nAssets written to docs/. Reference them in README.md.")
