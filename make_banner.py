"""
Фирменный шаблон баннеров Cucumber Game / SteamGate.
Использование: python make_banner.py config.json out.jpg
config: { title, subtitle, accent(blue|green|gold), footer, items:[{img,name,tag,old,new}] }
  img  — URL или локальный путь к обложке
  tag  — плашка в углу карточки ("FREE" / "-80%"); '-...' красится зелёным
  old  — старая цена (зачёркивается), напр. "$18.68"  (необязательно)
  new  — новая цена/статус, напр. "бесплатно до 14 июня" или "$4.99" (необязательно)
Цвета взяты из globals.css сайта.
"""
import sys, json, io, os, urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W = 1080
PRIMARY = (102, 192, 244)   # синий
GREEN   = (57, 227, 164)    # изумруд
GOLD    = (240, 195, 109)   # золото
WHITE   = (236, 243, 250)
GRAY    = (158, 172, 192)
BG_TOP  = (10, 15, 22)
BG_MID  = (11, 21, 34)
BG_BOT  = (9, 13, 20)
ACCENTS = {"blue": PRIMARY, "green": GREEN, "gold": GOLD}

def font(sz, bold=True):
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
    col = Image.new("RGB", (1, h)); p = col.load()
    for y in range(h):
        t = y / (h - 1)
        if t < 0.5:
            tt = t/0.5; c = tuple(int(BG_TOP[i] + (BG_MID[i]-BG_TOP[i])*tt) for i in range(3))
        else:
            tt = (t-0.5)/0.5; c = tuple(int(BG_MID[i] + (BG_BOT[i]-BG_MID[i])*tt) for i in range(3))
        p[0, y] = c
    return col.resize((w, h))

def glow(canvas, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx-r, cy-r, cx+r, cy+r], fill=color + (alpha,))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(r * 0.55)))

def rounded(im, rad):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0]-1, im.size[1]-1], rad, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0)); out.paste(im, (0, 0), mask)
    return out

def tw(d, text, f):
    b = d.textbbox((0, 0), text, font=f); return b[2]-b[0], b[3]-b[1]

def text_with_glow(canvas, parts, y, gcolor, g=14):
    """parts = [(text,color,font)]; центрируется по W, со свечением."""
    d = ImageDraw.Draw(canvas)
    total = sum(tw(d, t, f)[0] for t, _, f in parts)
    x0 = (W - total)//2
    full = "".join(t for t, _, _ in parts)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x0, y), full, font=parts[0][2], fill=gcolor + (255,))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(g)))
    x = x0
    for t, col, f in parts:
        d.text((x, y), t, font=f, fill=col + (255,)); x += tw(d, t, f)[0]

def draw_price(d, x, y, cw, old, new):
    for sz in (28, 26, 24, 22, 20, 18):
        fo, fb = font(sz, False), font(sz, True)
        ow = tw(d, old, fo)[0] if old else 0
        aw = tw(d, "  →  ", fo)[0] if old else 0
        nw = tw(d, new, fb)[0]
        total = ow + aw + nw
        if total <= cw or sz == 18:
            break
    cx = x + (cw - total)//2
    if old:
        d.text((cx, y), old, font=fo, fill=GRAY + (255,))
        d.line([(cx, y + sz*0.52), (cx + ow, y + sz*0.52)], fill=GRAY + (255,), width=2)
        cx += ow
        d.text((cx, y), "  →  ", font=fo, fill=GRAY + (255,)); cx += aw
    d.text((cx, y), new, font=fb, fill=GREEN + (255,))

def fit_cover(im, cw, ch):
    tr, sr = ch / cw, im.height / im.width
    if sr > tr:
        nh = int(im.width * tr); t = (im.height - nh) // 2
        im = im.crop((0, t, im.width, t + nh))
    else:
        nw = int(im.height / tr); l = (im.width - nw) // 2
        im = im.crop((l, 0, l + nw, im.height))
    return im.resize((cw, ch), Image.LANCZOS)

def main(cfg_path, out_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    accent = ACCENTS.get(cfg.get("accent", "blue"), PRIMARY)
    items = cfg["items"]
    footer = cfg.get("footer", "Сыграй в любую новинку бесплатно")
    pad, gap, row_gap = 44, 28, 26
    n = len(items)
    cols = 1 if n == 1 else 2
    rows = (n + cols - 1) // cols
    cw = (W - pad*2 - gap*(cols-1)) // cols
    ch = int(cw * 215 / 460)   # единый размер карты (формат steam header)
    covers = [fit_cover(load_img(it["img"]), cw, ch) for it in items]

    top = 196              # старт карточек
    has_price = any(it.get("old") or it.get("new") for it in items)
    undercard = 50 + (46 if has_price else 0)   # имя (+ цена)
    footer_h = 70
    cell_h = ch + undercard
    H = top + rows*cell_h + (rows-1)*row_gap + footer_h

    canvas = vgrad(W, H).convert("RGBA")
    glow(canvas, 150, 70, 360, PRIMARY, 42)
    glow(canvas, W-160, 60, 340, GREEN, 30)
    glow(canvas, W//2, H-60, 300, GOLD, 18)

    # ── бренд (по центру, со свечением) ──
    bf = font(34)
    text_with_glow(canvas, [("CUCUMBER ", WHITE, bf), ("GAME", GREEN, bf)], 26, PRIMARY, g=16)
    d = ImageDraw.Draw(canvas)

    # ── заголовок (по центру, крупно, со свечением) + платформа (по центру) ──
    title = cfg["title"]
    for tsz in (60, 56, 50, 46):
        tf = font(tsz)
        if tw(d, title, tf)[0] <= W - pad*2:
            break
    tx = (W - tw(d, title, tf)[0]) // 2
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((tx, 80), title, font=tf, fill=accent + (255,))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(canvas)
    d.text((tx, 80), title, font=tf, fill=accent + (255,))
    if cfg.get("subtitle"):
        sf = font(22, False)
        d.text(((W - tw(d, cfg["subtitle"], sf)[0]) // 2, 152), cfg["subtitle"], font=sf, fill=GRAY + (255,))

    # ── карточки (сетка, ряды по центру) ──
    for r in range(rows):
        row_items = items[r*cols:(r+1)*cols]
        row_covers = covers[r*cols:(r+1)*cols]
        k = len(row_items)
        x0 = (W - (k*cw + (k-1)*gap)) // 2
        y = top + r*(cell_h + row_gap)
        for c, (im, it) in enumerate(zip(row_covers, row_items)):
            x = x0 + c*(cw+gap)
            bd = Image.new("RGBA", (cw+6, ch+6), (0, 0, 0, 0))
            ImageDraw.Draw(bd).rounded_rectangle([0, 0, cw+5, ch+5], 20, outline=accent + (200,), width=3)
            canvas.alpha_composite(bd, (x-3, y-3))
            canvas.alpha_composite(rounded(im, 18), (x, y))
            d = ImageDraw.Draw(canvas)
            tag = it.get("tag")
            if tag:
                tcol = GREEN if str(tag).startswith("-") else GOLD
                tagw = tw(d, tag, font(22))[0]
                d.rounded_rectangle([x+12, y+12, x+12+tagw+24, y+12+34], 17, fill=tcol + (235,))
                d.text((x+24, y+16), tag, font=font(22), fill=(12, 17, 26) + (255,))
            nf = font(28)
            d.text((x + (cw - tw(d, it["name"], nf)[0]) // 2, y+ch+12), it["name"], font=nf, fill=WHITE + (255,))
            if it.get("old") or it.get("new"):
                draw_price(d, x, y+ch+12+40, cw, it.get("old"), it.get("new", ""))

    # ── футер (по центру): CTA серым + сайт синим, авто-подгон ──
    if footer:
        site = "steamgate.online"; sep = "  ·  "
        for fsz in (24, 22, 20, 18):
            ff = font(fsz)
            cwf = tw(d, footer + sep, ff)[0]; swf = tw(d, site, ff)[0]
            if cwf + swf <= W - pad*2 or fsz == 18:
                break
        fx = (W - (cwf + swf)) // 2; fy = H - footer_h + 22
        d.text((fx, fy), footer + sep, font=ff, fill=GRAY + (255,))
        d.text((fx + cwf, fy), site, font=ff, fill=PRIMARY + (255,))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True)
    print("saved", canvas.size, round(os.path.getsize(out_path)/1024), "KB")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
