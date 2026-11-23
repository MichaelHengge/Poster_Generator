"""Poster Generator – Flask + flaskwebgui desktop app.

    python app.py            -> desktop window (flaskwebgui)
    python app.py --browser  -> plain Flask dev server on http://127.0.0.1:5000
"""
import base64
import json
import re
import os
import sys
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import poster
from poster.fonts import family_list
from poster.structures import LAYOUT_STYLES
from poster.config import DEFAULTS, PAGE_SIZES, PALETTE_KEYS, PALETTE_LABELS, preset_dicts

BASE = Path(__file__).resolve().parent
USER_DIR = BASE / "user_data"
PALETTE_FILE = USER_DIR / "palettes.json"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # project files carry their images
poster.assets.IMAGE_DIR = USER_DIR / "images"


# ------------------------------------------------------------------ helpers
def load_user_palettes() -> dict:
    try:
        return json.loads(PALETTE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_user_palettes(p: dict):
    USER_DIR.mkdir(exist_ok=True)
    PALETTE_FILE.write_text(json.dumps(p, indent=2), encoding="utf-8")


def build(settings: dict):
    st = poster.merge_settings(settings)
    return st, poster.build_poster(st)


def filename(st, ext):
    return f"poster_{st['size'].replace(' ', '')}_{st['orientation']}.{ext}"


# ------------------------------------------------------------------ routes
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    return send_file(BASE / "static" / "favicon.ico", mimetype="image/x-icon")


@app.get("/manifest.webmanifest")
def manifest():
    return jsonify(
        name="Poster Generator", short_name="Posters", display="standalone", start_url="/",
        background_color="#EEF1F5", theme_color="#1F5FD0",
        icons=[{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
               {"src": "/static/icon-256.png", "sizes": "256x256", "type": "image/png"},
               {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
    )


@app.get("/api/config")
def config():
    return jsonify(
        defaults=DEFAULTS,
        sizes=list(PAGE_SIZES) + ["Custom"],
        palette_keys=PALETTE_KEYS,
        palette_labels=PALETTE_LABELS,
        presets=preset_dicts(),
        user_palettes=load_user_palettes(),
        layout_styles=LAYOUT_STYLES,
        fonts=family_list(),
    )


@app.post("/api/preview")
def preview():
    st, doc = build(request.get_json(force=True) or {})
    return jsonify(svg=poster.to_svg(doc, interactive=True), width=doc["W"], height=doc["H"], seed=st["seed"],
                   style=doc["style"], style_name=LAYOUT_STYLES.get(doc["style"], doc["style"]),
                   layout_key=doc["layout_key"], warnings=doc["warnings"],
                   tree_key=doc["tree_key"], tree_active=doc["tree_active"])


@app.post("/api/export/<fmt>")
def export(fmt):
    data = request.get_json(force=True) or {}
    st, doc = build(data.get("settings", {}))
    if fmt == "pdf":
        payload, mime = poster.to_pdf(doc), "application/pdf"
    elif fmt == "png":
        dpi = max(30, min(400, int(data.get("dpi", 150))))
        payload, mime = poster.pdf_to_png(poster.to_pdf(doc), dpi), "image/png"
    elif fmt == "pptx":
        payload = poster.to_pptx(doc)
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    elif fmt == "svg":
        payload, mime = poster.to_svg(doc).encode("utf-8"), "image/svg+xml"
    else:
        return jsonify(error="unknown format"), 400
    return send_file(BytesIO(payload), mimetype=mime, as_attachment=True, download_name=filename(st, fmt))


@app.route("/api/palettes", methods=["GET", "POST"])
def palettes():
    pals = load_user_palettes()
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        name = str(body.get("name", "")).strip()[:40]
        colors = body.get("colors", {})
        if not name or not all(re.fullmatch(r"#[0-9A-Fa-f]{6}", str(colors.get(k, ""))) for k in PALETTE_KEYS):
            return jsonify(error="Need a name and 8 hex colours"), 400
        pals[name] = {k: colors[k].upper() for k in PALETTE_KEYS}
        save_user_palettes(pals)
    return jsonify(pals)


@app.post("/api/move")
def move():
    """Move a section to another position, taking its box size along. Used for the drag preview and the drop."""
    from poster.layout import move_section
    data = request.get_json(force=True) or {}
    st = poster.merge_settings(data.get("settings", {}))
    try:
        frm, to = int(data.get("from", 0)), int(data.get("to", 0))
    except (TypeError, ValueError):
        return jsonify(error="bad positions"), 400
    res = move_section(st, frm, to)
    new = res.pop("settings")
    doc = poster.build_poster(new)
    res["svg"] = poster.to_svg(doc, interactive=True)
    hot = [e for e in doc["elements"] if e["type"] == "hotspot"]
    mi = res["moved_index"]
    res["moved"] = [hot[mi][k] for k in ("x", "y", "w", "h")] if mi < len(hot) else None
    res["layout_key"] = doc["layout_key"]
    return jsonify(res)


# ------------------------------------------------------------------ images (figures, logos)
@app.post("/api/image")
def upload_image():
    """Accepts a file upload ('file') or JSON {data: data-URL}. Returns {id, w, h}."""
    if "file" in request.files:
        raw = request.files["file"].read()
    else:
        data = str((request.get_json(force=True, silent=True) or {}).get("data", ""))
        if "," not in data:
            return jsonify(error="No image data"), 400
        raw = base64.b64decode(data.split(",", 1)[1])
    try:
        iid, w, h = poster.assets.store_image(raw)
    except Exception:
        return jsonify(error="That file is not an image this app can read"), 400
    return jsonify(id=iid, w=w, h=h)


@app.get("/api/image/<iid>")
def get_image(iid):
    full = request.args.get("full") == "1"
    if not re.fullmatch(r"[0-9a-f]{16}", iid):
        return "", 404
    data = poster.assets.load_image(iid)[0] if full and poster.assets.load_image(iid) else poster.assets.preview_image(iid)
    if not data:
        return "", 404
    resp = send_file(BytesIO(data), mimetype="image/jpeg" if data[:2] == b"\xff\xd8" else "image/png")
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # ids are content hashes
    return resp


def _used_images(st: dict) -> set[str]:
    c = st.get("content") or {}
    ids = {c.get("logo_left", "")} | set(c.get("logos_right") or [])
    for sec in st.get("sections") or []:
        ids |= {f.get("img", "") for f in (sec.get("figs") or {}).values() if isinstance(f, dict)}
    return {i for i in ids if i}


@app.post("/api/project/pack")
def project_pack():
    """Settings + the pictures they use, as one self-contained project file."""
    st = request.get_json(force=True) or {}
    images = {}
    for iid in _used_images(poster.merge_settings(st)):
        got = poster.assets.load_image(iid)
        if got:
            images[iid] = poster.assets.data_url(got[0])
    body = json.dumps({"app": "poster-generator", "version": 2, "settings": st, "images": images}, indent=1)
    return send_file(BytesIO(body.encode()), mimetype="application/json", as_attachment=True,
                     download_name="poster_project.json")


@app.post("/api/project/unpack")
def project_unpack():
    """Stores the pictures of a project file and returns its settings (older files are plain settings)."""
    data = request.get_json(force=True) or {}
    if "settings" not in data:
        return jsonify(settings=data)
    for url in (data.get("images") or {}).values():
        try:
            poster.assets.store_image(base64.b64decode(str(url).split(",", 1)[1]))
        except Exception:
            pass
    return jsonify(settings=data["settings"])


@app.delete("/api/palettes/<path:name>")
def delete_palette(name):
    pals = load_user_palettes()
    pals.pop(name, None)
    save_user_palettes(pals)
    return jsonify(pals)


if __name__ == "__main__":
    if "--browser" in sys.argv:
        app.run(debug=True, port=int(os.environ.get("PORT", 5000)))   # PORT lets a dev tool pick a free port
    else:
        from flaskwebgui import FlaskUI

        FlaskUI(app=app, server="flask", width=1600, height=1000, fullscreen=False).run()
