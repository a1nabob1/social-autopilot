"""Makes branded, full-resolution post images: square (1080x1080) for most platforms, a tall pin (1000x1500)
for Pinterest, and slides for carousels. Uses your page's own photo when it has one."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from .util import DATA, http, log

FONT_BOLD = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
FONT_REG = ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
_cache = {}


def font(size, bold=True):
    key = (size, bold)
    if key not in _cache:
        for name in FONT_BOLD if bold else FONT_REG:
            try:
                _cache[key] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _cache[key] = ImageFont.load_default(size)
    return _cache[key]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fetch_image(src):
    if not src:
        return None
    import hashlib
    cache = DATA / "cache" / (hashlib.md5(src.encode()).hexdigest() + ".img")
    try:
        if cache.exists():
            return Image.open(cache).convert("RGBA")
        if src.startswith("http"):
            r = http().get(src, timeout=30)
            r.raise_for_status()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(r.content)
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
        return Image.open(src).convert("RGBA")
    except Exception as e:
        log(f"image fetch failed {src}: {e}")
        return None


def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def fit_text(draw, text, width, max_h, start, minimum, bold=True, spacing=1.18):
    size = start
    while size >= minimum:
        f = font(size, bold)
        lines = wrap(draw, text, f, width)
        h = len(lines) * size * spacing
        if h <= max_h:
            return f, lines, size
        size -= 4
    f = font(minimum, bold)
    lines = wrap(draw, text, f, width)
    keep = max(1, int(max_h // (minimum * spacing)))
    if len(lines) > keep:
        lines = lines[:keep]
        lines[-1] = lines[-1].rstrip(".,") + "..."
    return f, lines, minimum


def background(w, h, brand, photo):
    p, s = hex_rgb(brand["primary"]), hex_rgb(brand["secondary"])
    base = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(base)
    for y in range(h):  # diagonal-ish gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(p[i] * (1 - t) + s[i] * t) for i in range(3)) + (255,))
    if photo is not None:
        ph = ImageOps.fit(photo, (w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(9))
        shade = Image.new("RGBA", (w, h), p + (215,))
        base = Image.alpha_composite(ph, shade)
    return base


def draw_footer(img, brand, d):
    w, h = img.size
    a = hex_rgb(brand["accent"])
    d.rectangle([0, h - 120, w, h], fill=(255, 255, 255, 245))
    d.rectangle([0, h - 126, w, h - 120], fill=a + (255,))
    d.text((60, h - 100), brand["name"], font=font(34), fill=hex_rgb(brand["primary"]))
    d.text((60, h - 58), f"{brand['phone']}   |   {brand['short']}", font=font(26, False), fill=(60, 60, 60))
    if brand.get("short_disclaimer"):
        f = font(17, False)
        txt = brand["short_disclaimer"]
        d.text((w - 60 - d.textlength(txt, font=f), h - 150), txt, font=f, fill=(235, 235, 235))


def paste_logo(img, brand):
    src = brand.get("logo") or brand.get("_icon")
    logo = fetch_image(src) if src else None
    if logo is None:
        return
    logo.thumbnail((110, 110), Image.LANCZOS)
    pad = Image.new("RGBA", (logo.width + 20, logo.height + 20), (255, 255, 255, 235))
    pad.alpha_composite(logo, (10, 10))
    img.alpha_composite(pad, (img.width - pad.width - 50, 50))


def card(w, h, brand, label, headline, sub, photo, page_no=None):
    img = background(w, h, brand, photo)
    d = ImageDraw.Draw(img)
    a = hex_rgb(brand["accent"])
    lf = font(30)
    lw = d.textlength(label, font=lf)
    d.rounded_rectangle([60, 70, 60 + lw + 44, 128], radius=29, fill=a + (255,))
    d.text((82, 80), label, font=lf, fill=(255, 255, 255))
    paste_logo(img, brand)
    usable = w - 120
    bottom = h - 190
    hf, hl, hs = fit_text(d, headline, usable, (bottom - 190) * (0.62 if sub else 0.9), 92 if w >= h else 96, 44)
    y = 190
    for line in hl:
        d.text((60, y), line, font=hf, fill=(255, 255, 255))
        y += int(hs * 1.18)
    if sub:
        y += 24
        d.rectangle([60, y, 180, y + 8], fill=a + (255,))
        y += 36
        sf, sl, ss = fit_text(d, sub, usable, bottom - y, 40, 26, bold=False, spacing=1.35)
        for line in sl:
            d.text((60, y), line, font=sf, fill=(235, 240, 245))
            y += int(ss * 1.35)
    if page_no:
        f = font(26)
        d.text((w - 60 - d.textlength(page_no, font=f), h - 175), page_no, font=f, fill=(255, 255, 255))
    draw_footer(img, brand, d)
    return img.convert("RGB")


def render(post, brand):
    out_dir = DATA / "images" / brand["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    photo = fetch_image(post.get("photo"))
    sub = "" if post["kind"] == "carousel" else _teaser(post["body"])
    files = {}
    sq = card(1080, 1080, brand, post["label"], post["headline"], sub, photo)
    files["square"] = _save(sq, out_dir / f"{post['id']}.png")
    pin = card(1000, 1500, brand, post["label"], post["headline"], _teaser(post["body"], 260), photo)
    files["pin"] = _save(pin, out_dir / f"{post['id']}-pin.png")
    if post.get("slides"):
        n = len(post["slides"]) + 1
        slides = [files["square"]]
        for i, s in enumerate(post["slides"], start=2):
            img = card(1080, 1080, brand, f"Q{i - 1}", s["h"], s["t"], None, f"{i}/{n}")
            slides.append(_save(img, out_dir / f"{post['id']}-{i}.png"))
        files["slides"] = slides
    post["images"] = files
    return files


def _teaser(text, limit=170):
    from .generate import trim
    return trim(text, limit)


def _save(img, path):
    img.save(path, "PNG", optimize=True)  # lossless, full size: no blurry thumbnails
    return str(Path(path).relative_to(DATA.parent)).replace("\\", "/")
