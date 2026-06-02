"""
Фирменный шаблон баннеров Cucumber Game / SteamGate.
Использование: python make_banner.py config.json out.jpg
config: { title, subtitle, accent(blue|green|gold), footer, items:[{img,name,tag}] }
  img  — URL или локальный путь к обложке (любой ширины, ratio свободный)
  tag  — текст плашки в углу карточки (напр. "FREE" или "-80%"); '-...' красится зелёным
Цвета взяты из globals.css сайта.
"""
import sys, json, io, os, urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W = 1080
PRIMARY = (102, 192, 244)   # синий
GREEN   = (57, 227, 164)    # изумруд
GOLD    = (240, 195, 109)   # золото
PURPLE  = (161, 120, 255)
WHITE   = (236, 243, 250)
GRAY    = (158, 172, 192)
BG_TOP  = (10, 15, 22)
BG_MID  = (11, 21, 34)
BG_BOT  = (9, 13, 20)
CARD_BG = (15, 24, 39)
ACCENTS = {"blue": PRIMARY, "green": GREEN, "gold": GOLD}

def font(sz, bold=True):
    # Кроссплатформенно: Windows (локально) -> Linux DejaVu (облако) -> bundled fallback
    cands = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    )
    for p in cands:
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=sz)
    except Exception:
        return ImageFont.load_default()

def load_img(src):
    if str(src).startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=25).read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    return Image.open(src).convert("RGB")

def vgrad(w, h):
    col = Image.new("RGB", (1, h))
    p = col.load()
    for y in range(h):
        t = y / (h - 1)
        if t < 0.5:
            tt = t / 0.5; c = tuple(int(BG_TOP[i] + (BG_MID[i]-BG_TOP[i])*tt) for i in range(3))
        else:
            tt = (t-0.5)/0.5; c = tuple(int(BG_MID[i] + (BG_BOT[i]-BG_MID[i])*tt) for i in range(3))
        p[0, y] = c
    return col.resize((w, h))

def glow(canvas, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx-r, cy-r, cx+r, cy+r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.55))
    canvas.alpha_composite(layer)

def rounded(im, rad):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0]-1, im.size[1]-1], rad, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out

def text_glow(canvas, xy, text, fnt, color, gcolor=None, g=10):
    if gcolor:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(xy, text, font=fnt, fill=gcolor + (255,))
        layer = layer.filter(ImageFilter.GaussianBlur(g))
        canvas.alpha_composite(layer)
    ImageDraw.Draw(canvas).text(xy, text, font=fnt, fill=color + (255,))

def tw(draw, text, fnt):
    b = draw.textbbox((0, 0), text, font=fnt); return b[2]-b[0], b[3]-b[1]

def main(cfg_path, out_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    accent = ACCENTS.get(cfg.get("accent", "blue"), PRIMARY)
    items = cfg["items"]
    pad, gap = 44, 28
    n = len(items)
    cards_w = W - pad*2
    cw = (cards_w - gap*(n-1)) // n
    covers = []
    for it in items:
        im = load_img(it["img"])
        ch = int(im.height * cw / im.width)
        covers.append(im.resize((cw, ch), Image.LANCZOS))
    ch = covers[0].height
    top = 196
    label_h = 46
    footer_h = 78
    H = top + ch + label_h + footer_h

    canvas = vgrad(W, H).convert("RGBA")
    glow(canvas, 150, 70, 360, PRIMARY, 46)
    glow(canvas, W-160, 60, 340, GREEN, 34)
    glow(canvas, W-220, H-80, 320, GOLD, 22)
    d = ImageDraw.Draw(canvas)

    # ── top brand bar ──
    d.rounded_rectangle([pad, 34, pad+30, 64], 8, fill=GREEN + (255,))
    d.text((pad+44, 36), "CUCUMBER", font=font(26), fill=WHITE + (255,))
    wc, _ = tw(d, "CUCUMBER ", font(26))
    d.text((pad+44+wc, 36), "GAME", font=font(26), fill=GREEN + (255,))
    site = "steamgate.online"
    sw, _ = tw(d, site, font(24))
    d.text((W-pad-sw, 38), site, font=font(24), fill=PRIMARY + (255,))
    # divider
    line = Image.new("RGBA", (W, 3), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line)
    for x in range(pad, W-pad):
        t = (x-pad)/(W-2*pad)
        a = int(180 * (1 - abs(t-0.5)*2))
        c = PRIMARY if t < 0.5 else GREEN
        ld.point((x, 1), fill=c + (a,))
    canvas.alpha_composite(line, (0, 78))

    # ── title + subtitle ──
    text_glow(canvas, (pad, 88), cfg["title"], font(52), accent, gcolor=accent, g=11)
    d = ImageDraw.Draw(canvas)
    if cfg.get("subtitle"):
        d.text((pad, 158), cfg["subtitle"], font=font(24, False), fill=GRAY + (255,))

    # ── cards ──
    x = pad
    for im, it in zip(covers, items):
        card = rounded(im, 18)
        # border
        bd = Image.new("RGBA", (im.width+6, im.height+6), (0, 0, 0, 0))
        ImageDraw.Draw(bd).rounded_rectangle([0, 0, im.width+5, im.height+5], 20, outline=accent + (200,), width=3)
        canvas.alpha_composite(bd, (x-3, top-3))
        canvas.alpha_composite(card, (x, top))
        d = ImageDraw.Draw(canvas)
        # tag pill
        tag = it.get("tag")
        if tag:
            tcol = GREEN if str(tag).startswith("-") else GOLD
            tagw, _ = tw(d, tag, font(22))
            d.rounded_rectangle([x+12, top+12, x+12+tagw+24, top+12+34], 17, fill=tcol + (235,))
            d.text((x+24, top+16), tag, font=font(22), fill=(12, 17, 26) + (255,))
        # name
        d.text((x+2, top+ch+12), it["name"], font=font(28), fill=WHITE + (255,))
        x += cw + gap

    # ── footer ──
    foot = cfg.get("footer", "")
    if foot:
        fw, _ = tw(d, foot, font(24))
        d.text(((W-fw)//2, H-footer_h+24), foot, font=font(24), fill=GRAY + (255,))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True)
    print("saved", canvas.size, round(os.path.getsize(out_path)/1024), "KB")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
