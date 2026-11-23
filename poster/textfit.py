"""Text measurement and wrapping, using the metrics of the real (installed) font files."""
from .fonts import get_font

MM_PER_PT = 25.4 / 72


def width_mm(text: str, size_pt: float, font: str = "Arial", bold: bool = False, italic: bool = False) -> float:
    try:
        return get_font(font, bold, italic).text_length(text, fontsize=size_pt) * MM_PER_PT
    except Exception:
        return len(text) * size_pt * 0.5 * MM_PER_PT


def wrap(text: str, max_w: float, size_pt: float, font="Arial", bold=False) -> list[list[str]]:
    """Wrap text to max_w (mm). Returns a list of paragraphs, each a list of lines."""
    paras = []
    for para in text.split("\n"):
        words = para.split()
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}" if cur else w
            if cur and width_mm(trial, size_pt, font, bold) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = trial
        lines.append(cur)
        paras.append(lines)
    return paras


def n_lines(paras) -> int:
    return sum(len(p) for p in paras)


LOREM = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore "
    "et dolore magna aliqua ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi ut "
    "aliquip ex ea commodo consequat duis aute irure dolor in reprehenderit in voluptate velit esse cillum "
    "dolore eu fugiat nulla pariatur excepteur sint occaecat cupidatat non proident sunt in culpa qui "
    "officia deserunt mollit anim id est laborum curabitur pretium tincidunt lacus nulla gravida orci a "
    "odio nullam varius turpis et commodo pharetra est eros bibendum elit nec luctus magna felis "
    "sollicitudin mauris integer in mauris eu nibh euismod gravida duis ac tellus et risus vulputate "
    "vehicula donec lobortis risus a elit etiam tempor ut ullamcorper ligula eu tempor congue eros est"
).split()


def placeholder_text(rng, words: int) -> str:
    out, sent = [], []
    start = rng.randrange(len(LOREM))
    for i in range(words):
        sent.append(LOREM[(start + i * 7) % len(LOREM)])
        if len(sent) > rng.randint(9, 16):
            out.append(" ".join(sent).capitalize() + ".")
            sent = []
    if sent:
        out.append(" ".join(sent).capitalize() + ".")
    return " ".join(out)


def fill_lines(rng, max_w, max_lines, size_pt, font="Arial") -> list[str]:
    """Generate placeholder text that fills exactly up to max_lines lines."""
    if max_lines <= 0:
        return []
    est_words = int(max_lines * max(3, max_w / (size_pt * MM_PER_PT * 2.9))) + 10
    lines = wrap(placeholder_text(rng, est_words), max_w, size_pt, font)[0][:max_lines]
    if lines:
        last = lines[-1].rstrip(" ,")
        lines[-1] = last if last.endswith(".") else last + "."
    return lines
