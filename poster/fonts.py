"""Font discovery: finds a curated set of font families installed on this computer.

The same family must work in three places, which is why we only offer installed fonts:
  * the browser preview (SVG text, uses the installed font by name)
  * the PDF/PNG export (the font file is embedded by PyMuPDF)
  * the PowerPoint export (font referenced by name)
If a family is missing, Helvetica / Times (built into PyMuPDF) are used as fallback.
"""
import os
import sys
from functools import lru_cache
from pathlib import Path

import pymupdf

# family, generic, regular files, bold files, italic files (first existing file wins)
FAMILIES = [
    # --- sans-serif
    ("Arial", "sans-serif", ["arial.ttf", "Arial.ttf"], ["arialbd.ttf", "Arial Bold.ttf"], ["ariali.ttf", "Arial Italic.ttf"]),
    ("Aptos", "sans-serif", ["Aptos.ttf"], ["Aptos-Bold.ttf"], ["Aptos-Italic.ttf"]),
    ("Calibri", "sans-serif", ["calibri.ttf"], ["calibrib.ttf"], ["calibrii.ttf"]),
    ("Candara", "sans-serif", ["candara.ttf"], ["candarab.ttf"], ["candarai.ttf"]),
    ("Century Gothic", "sans-serif", ["gothic.ttf"], ["gothicb.ttf"], ["gothici.ttf"]),
    ("Corbel", "sans-serif", ["corbel.ttf"], ["corbelb.ttf"], ["corbeli.ttf"]),
    ("Gill Sans MT", "sans-serif", ["gil_____.ttf"], ["gilb____.ttf"], ["gili____.ttf"]),
    ("Segoe UI", "sans-serif", ["segoeui.ttf"], ["segoeuib.ttf"], ["segoeuii.ttf"]),
    ("Tahoma", "sans-serif", ["tahoma.ttf"], ["tahomabd.ttf"], []),
    ("Trebuchet MS", "sans-serif", ["trebuc.ttf"], ["trebucbd.ttf"], ["trebucit.ttf"]),
    ("Verdana", "sans-serif", ["verdana.ttf"], ["verdanab.ttf"], ["verdanai.ttf"]),
    ("Helvetica Neue", "sans-serif", ["HelveticaNeue.ttc"], [], []),
    ("Inter", "sans-serif", ["Inter-Regular.ttf", "Inter-Regular.otf"], ["Inter-Bold.ttf", "Inter-Bold.otf"], ["Inter-Italic.ttf"]),
    ("Lato", "sans-serif", ["Lato-Regular.ttf"], ["Lato-Bold.ttf"], ["Lato-Italic.ttf"]),
    ("Montserrat", "sans-serif", ["Montserrat-Regular.ttf"], ["Montserrat-Bold.ttf"], ["Montserrat-Italic.ttf"]),
    ("Noto Sans", "sans-serif", ["NotoSans-Regular.ttf"], ["NotoSans-Bold.ttf"], ["NotoSans-Italic.ttf"]),
    ("Open Sans", "sans-serif", ["OpenSans-Regular.ttf"], ["OpenSans-Bold.ttf"], ["OpenSans-Italic.ttf"]),
    ("Roboto", "sans-serif", ["Roboto-Regular.ttf", "Roboto-VariableFont_wdth,wght.ttf"], ["Roboto-Bold.ttf"],
     ["Roboto-Italic.ttf", "Roboto-Italic-VariableFont_wdth,wght.ttf"]),
    ("Source Sans 3", "sans-serif", ["SourceSans3-Regular.ttf", "SourceSans3-Regular.otf"], ["SourceSans3-Bold.ttf"], ["SourceSans3-It.ttf"]),
    ("DejaVu Sans", "sans-serif", ["DejaVuSans.ttf"], ["DejaVuSans-Bold.ttf"], ["DejaVuSans-Oblique.ttf"]),
    ("Liberation Sans", "sans-serif", ["LiberationSans-Regular.ttf"], ["LiberationSans-Bold.ttf"], ["LiberationSans-Italic.ttf"]),
    # --- serif
    ("Times New Roman", "serif", ["times.ttf", "Times New Roman.ttf"], ["timesbd.ttf", "Times New Roman Bold.ttf"], ["timesi.ttf", "Times New Roman Italic.ttf"]),
    ("Georgia", "serif", ["georgia.ttf", "Georgia.ttf"], ["georgiab.ttf", "Georgia Bold.ttf"], ["georgiai.ttf", "Georgia Italic.ttf"]),
    ("Cambria", "serif", ["cambria.ttc"], ["cambriab.ttf"], ["cambriai.ttf"]),
    ("Constantia", "serif", ["constan.ttf"], ["constanb.ttf"], ["constani.ttf"]),
    ("Garamond", "serif", ["gara.ttf"], ["garabd.ttf"], ["garait.ttf"]),
    ("Book Antiqua", "serif", ["bkant.ttf"], ["antquab.ttf"], ["antquai.ttf"]),
    ("Palatino Linotype", "serif", ["pala.ttf"], ["palab.ttf"], ["palai.ttf"]),
    ("Bookman Old Style", "serif", ["bookos.ttf"], ["bookosb.ttf"], ["bookosi.ttf"]),
    ("Merriweather", "serif", ["Merriweather-Regular.ttf"], ["Merriweather-Bold.ttf"], ["Merriweather-Italic.ttf"]),
    ("Noto Serif", "serif", ["NotoSerif-Regular.ttf"], ["NotoSerif-Bold.ttf"], ["NotoSerif-Italic.ttf"]),
    ("Source Serif 4", "serif", ["SourceSerif4-Regular.ttf"], ["SourceSerif4-Bold.ttf"], ["SourceSerif4-It.ttf"]),
    ("DejaVu Serif", "serif", ["DejaVuSerif.ttf"], ["DejaVuSerif-Bold.ttf"], ["DejaVuSerif-Italic.ttf"]),
    ("Liberation Serif", "serif", ["LiberationSerif-Regular.ttf"], ["LiberationSerif-Bold.ttf"], ["LiberationSerif-Italic.ttf"]),
]

DEFAULT_FAMILY = "Arial"
_BUILTIN = {  # PyMuPDF base-14 fallbacks: (regular, bold, italic)
    "sans-serif": ("helv", "hebo", "heit"),
    "serif": ("tiro", "tibo", "tiit"),
}


def _font_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform.startswith("win"):
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
                Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Microsoft/Windows/Fonts"]
    elif sys.platform == "darwin":
        dirs = [Path("/Library/Fonts"), Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
                home / "Library/Fonts"]
    else:
        dirs = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local/share/fonts", home / ".fonts"]
    return [d for d in dirs if d.is_dir()]


@lru_cache(maxsize=1)
def _file_index() -> dict[str, str]:
    """lower-case file name -> full path, for all font files in the font folders."""
    idx = {}
    for d in _font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    idx.setdefault(f.lower(), os.path.join(root, f))
    return idx


def _find(names) -> str | None:
    idx = _file_index()
    for n in names:
        p = idx.get(n.lower())
        if p:
            return p
    return None


@lru_cache(maxsize=1)
def available() -> dict[str, dict]:
    """{family: {generic, regular, bold, italic}} for the installed curated families."""
    out = {}
    for name, generic, reg, bold, ital in FAMILIES:
        r = _find(reg)
        if not r:
            continue
        out[name] = {"generic": generic, "regular": r, "bold": _find(bold), "italic": _find(ital)}
    return out


def family_list() -> list[dict]:
    av = available()
    return [{"name": n, "generic": v["generic"], "bold": bool(v["bold"])} for n, v in av.items()]


def resolve(family: str) -> str:
    """The family that will actually be used (falls back to Arial or the built-in Helvetica)."""
    av = available()
    if family in av:
        return family
    return DEFAULT_FAMILY if DEFAULT_FAMILY in av else family


def generic(family: str) -> str:
    info = available().get(family)
    if info:
        return info["generic"]
    return "serif" if "serif" in family.lower() and "sans" not in family.lower() else "sans-serif"


def css_family(family: str) -> str:
    g = generic(family)
    fallback = "Arial, Helvetica, sans-serif" if g == "sans-serif" else "'Times New Roman', Times, serif"
    return f"'{family}', {fallback}"


def font_file(family: str, bold=False, italic=False) -> str | None:
    info = available().get(family)
    if not info:
        return None
    if bold and info["bold"]:
        return info["bold"]
    if italic and info["italic"]:
        return info["italic"]
    return info["regular"]


@lru_cache(maxsize=128)
def get_font(family: str, bold=False, italic=False) -> pymupdf.Font:
    path = font_file(family, bold, italic)
    if path:
        try:
            return pymupdf.Font(fontfile=path)
        except Exception:
            pass
    reg, b, it = _BUILTIN[generic(family)]
    return pymupdf.Font(fontname=b if bold else it if italic else reg)
