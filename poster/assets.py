"""Image helpers: uploaded logos, gradients and QR codes."""
import base64
import io
from functools import lru_cache

import qrcode
from PIL import Image


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def rgb_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def mix(c1: str, c2: str, t: float) -> str:
    """Blend c1 towards c2 by t (0 -> c1, 1 -> c2)."""
    a, b = hex_rgb(c1), hex_rgb(c2)
    return rgb_hex([x + (y - x) * t for x, y in zip(a, b)])


def luminance(c: str) -> float:
    r, g, b = (v / 255 for v in hex_rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rel_lum(c: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = hex_rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(c1: str, c2: str) -> float:
    a, b = sorted((_rel_lum(c1), _rel_lum(c2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def readable(bg: str, *candidates: str, min_ratio: float = 3.0) -> str:
    """First candidate with enough contrast on bg, else the best one."""
    for c in candidates:
        if contrast(c, bg) >= min_ratio:
            return c
    return max(candidates, key=lambda c: contrast(c, bg))


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@lru_cache(maxsize=32)
def decode_logo(data_url: str) -> tuple[bytes, float] | None:
    """Decode a data-URL image into (png_bytes, aspect w/h). Downscales big images."""
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGBA")
        img.thumbnail((2000, 2000), Image.LANCZOS)
        bbox = img.getchannel("A").getbbox()  # trim fully transparent borders
        if bbox:
            img = img.crop(bbox)
        return png_bytes(img), img.width / img.height
    except Exception:
        return None


@lru_cache(maxsize=32)
def gradient_png(c1: str, c2: str, direction: str = "horizontal", w: int = 1200, h: int = 1200) -> bytes:
    a, b = hex_rgb(c1), hex_rgb(c2)
    if direction == "horizontal":
        line = Image.new("RGB", (w, 1))
        line.putdata([tuple(int(a[i] + (b[i] - a[i]) * x / (w - 1)) for i in range(3)) for x in range(w)])
        return png_bytes(line.resize((w, 8)))
    if direction == "vertical":
        col = Image.new("RGB", (1, h))
        col.putdata([tuple(int(a[i] + (b[i] - a[i]) * y / (h - 1)) for i in range(3)) for y in range(h)])
        return png_bytes(col.resize((8, h)))
    # diagonal
    # diagonal: mask = (x + y) / 2 built from two linear gradients
    from PIL import ImageChops
    gy = Image.linear_gradient("L").resize((w, h))              # 0 (top) -> 255 (bottom)
    gx = gy.transpose(Image.TRANSPOSE)                           # 0 (left) -> 255 (right)
    mask = ImageChops.add(gx, gy, scale=2.0)
    img = Image.composite(Image.new("RGB", (w, h), b), Image.new("RGB", (w, h), a), mask)
    return png_bytes(img)


@lru_cache(maxsize=16)
def qr_matrix(url: str) -> tuple[tuple[bool, ...], ...]:
    qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url or " ")
    qr.make(fit=True)
    return tuple(tuple(row) for row in qr.get_matrix())


def qr_png(matrix, dark="#000000", light="#FFFFFF", px=24) -> bytes:
    n = len(matrix)
    img = Image.new("RGB", (n, n), hex_rgb(light))
    d = hex_rgb(dark)
    for y, row in enumerate(matrix):
        for x, v in enumerate(row):
            if v:
                img.putpixel((x, y), d)
    return png_bytes(img.resize((n * px, n * px), Image.NEAREST))


def data_url(data: bytes) -> str:
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode()


# ---------------------------------------------------------------- image store (figures and logos)
# Uploaded pictures live in user_data/images/<id>.png|jpg so previews and settings only carry the id.
IMAGE_DIR = None   # set by the app


def store_image(raw: bytes) -> tuple[str, int, int]:
    """Normalise an uploaded image (max 2400 px, PNG if transparent else JPEG) and store it. Returns (id, w, h)."""
    import hashlib
    img = Image.open(io.BytesIO(raw))
    img.load()
    has_alpha = img.mode in ("RGBA", "LA", "P") and img.convert("RGBA").getchannel("A").getextrema()[0] < 255
    img = img.convert("RGBA" if has_alpha else "RGB")
    img.thumbnail((2400, 2400), Image.LANCZOS)
    buf = io.BytesIO()
    if has_alpha:
        img.save(buf, "PNG", optimize=True)
    else:
        img.save(buf, "JPEG", quality=90)
    data = buf.getvalue()
    iid = hashlib.sha1(data).hexdigest()[:16]
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGE_DIR / f"{iid}.{'png' if has_alpha else 'jpg'}"
    if not path.exists():
        path.write_bytes(data)
    return iid, img.width, img.height


def _image_path(iid: str):
    if not IMAGE_DIR or not iid:
        return None
    for ext in ("png", "jpg"):
        p = IMAGE_DIR / f"{iid}.{ext}"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=64)
def load_image(iid: str) -> tuple[bytes, float] | None:
    """(bytes, aspect w/h) of a stored image, or None."""
    p = _image_path(iid)
    if not p:
        return None
    data = p.read_bytes()
    with Image.open(io.BytesIO(data)) as im:
        return data, im.width / im.height


@lru_cache(maxsize=64)
def preview_image(iid: str, size: int = 900) -> bytes | None:
    """Small version for the on-screen preview and the editor thumbnails."""
    got = load_image(iid)
    if not got:
        return None
    img = Image.open(io.BytesIO(got[0]))
    img.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    if img.mode == "RGBA":
        img.save(buf, "PNG")
    else:
        img.convert("RGB").save(buf, "JPEG", quality=82)
    return buf.getvalue()
