# Poster Generator

Desktop app (Flask + flaskwebgui) for creating scientific poster templates.

```
pip install -r requirements.txt
python app.py              # desktop window
python app.py --browser    # dev mode: http://127.0.0.1:5000 with auto-reload
```

## Features
- Two modes, switched in the top-left bar:
  - **Layout** – size, colours, style, layout and section arrangement (sample text and placeholders)
  - **Edit** – the poster's own content: click any text, figure, logo or the QR code on the preview to edit it
    in place, or use the fields in the panel (title, authors, affiliations, logos, section titles, text, figures
    and captions, footer). Drop picture files onto a figure or logo (or onto a section to give it a figure), drop
    text onto a text; drag a picture onto another picture (or a section text onto another) to swap them.
    Empty fields keep the sample text; text that is too long shrinks slightly and is flagged in the status bar.
  - Pictures are stored in `user_data/images`; **Save project** writes them into the project file
- Sizes A0–A4, 36×48 in, 24×36 in or custom; portrait / landscape
- 10 preset colour palettes; edit any colour and save your own (stored in `user_data/palettes.json`)
- Style: heading and body font (any of ~35 common families, if installed on the computer), section text
  alignment (left / justified / centred / right), background (solid, gradient, soft shapes, grid), cards (filled,
  filled + outline, outline only, none), header style, corner radius, text size, margins, shadows
- Header: switch title, authors and affiliations on/off (sample text - the real content is written later in
  PowerPoint/Illustrator), a placeholder logo on the left and 0–4 placeholder logos on the right
- Footer: contact / event sample text on/off and a QR code generator (bottom right)
- Layout styles: Classic columns, Columns + wide section, Hero key figure, Bento grid, Sidebar, Process flow
  (with arrows), Hero at bottom, Centre spotlight (big centre
  section, smaller ones all around), Hero top & bottom (three smaller in between), Two features (diagonal pair), Mosaic, or Auto (a different style per layout number)
- Process flow arrows (Layout mode): **Connect sections with arrows**, then click the sections on the poster in the
  click a section, then the section the arrow points to (two clicks per arrow) – it points right/left/up/down as the
  sections sit. Click an arrow to remove it. Styles: chevron, triangle, block, circle, line; colour and size adjustable.
  Sections that are not next to each other get a connector that runs behind the cards.
- Column distributions (1:1:1, 1:2, 1:2:1, … or any custom ratio) for the column-based styles
- Section editor: set the number of sections, add, remove, and drag ⋮⋮ to reorder; per-section figure
  placeholder (auto / always / never)
- On the preview: hover a section and click ✕ to delete it (with Undo), click a section to select it, drag a section onto another one to move it there – a live preview shows the result; the section takes its box
  and size along, a full-width row (e.g. the hero) moves as a whole, and the rest of the layout stays put
  (**Reset layout** returns to the generated layout),
  drag the gap between sections (or columns/rows) to resize them; double-click a gap or use
  **Reset sizes** to go back to automatic. Sizes are remembered per layout number.
- **Regenerate** (or press `R`) for a new random layout; `←`/`→` step through layouts; every layout number is reproducible
- Export: vector PDF, PNG (72–300 dpi), editable PowerPoint (native shapes and text boxes), SVG
- Drag the divider between the settings and the preview to give either side more room (double-click resets)
- Save/open a whole project (all settings, text and pictures) as `.json`; the last settings are restored on start

## Structure
| Path | Purpose |
|---|---|
| `app.py` | Flask routes and the desktop launcher |
| `poster/config.py` | Page sizes, palettes, default settings |
| `poster/layout.py` | Settings → list of elements in mm (the layout engine) |
| `poster/structures.py` | Layout styles: split the content area into section boxes |
| `poster/render_svg.py` | Elements → SVG (preview and SVG export) |
| `poster/render_pptx.py` | Elements → editable PowerPoint slide |
| `poster/export.py` | Elements → PDF with embedded fonts, and PNG (PyMuPDF) |
| `poster/fonts.py` | Finds installed font families (Windows, macOS, Linux font folders) |
| `templates/`, `static/` | The GUI |

Notes: PDF/PNG are drawn with PyMuPDF and embed the chosen fonts (Cairo is not required). Only fonts installed
on the computer are offered, because the preview, the PDF and PowerPoint all need them. PowerPoint slides are limited to 142 cm,
so larger custom sizes are scaled down proportionally in the `.pptx`.

## License

MIT – see [LICENSE](LICENSE).
