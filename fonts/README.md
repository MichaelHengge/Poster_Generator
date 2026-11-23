# Fonts folder

Font files are **not** shipped with the Poster Generator. Put `.ttf` files of the families below into this folder
and the app offers them in the font menus – in the preview and in PDF/PNG exports (the fonts are embedded),
even if they are not installed on the computer. Restart the app after adding fonts.

| Family | Where to get it | Copy these files into this folder |
|---|---|---|
| JetBrains Mono | https://www.jetbrains.com/lp/mono/ (or https://github.com/JetBrains/JetBrainsMono/releases) | from `fonts/ttf/` in the zip: `JetBrainsMono-Regular.ttf`, `JetBrainsMono-Bold.ttf`, `JetBrainsMono-Italic.ttf` |
| Roboto | https://fonts.google.com/specimen/Roboto → *Get font* → *Download all* | from `static/` in the zip: `Roboto-Regular.ttf`, `Roboto-Bold.ttf`, `Roboto-Italic.ttf` |
| Open Sans | https://fonts.google.com/specimen/Open+Sans → *Get font* → *Download all* | from `static/` in the zip: `OpenSans-Regular.ttf`, `OpenSans-Bold.ttf`, `OpenSans-Italic.ttf` |

Notes
- The file names must match (the app looks for exactly these names). Regular is required; Bold and Italic are
  used when present. Use the *static* files, not the variable `...[wght].ttf` ones.
- All three families are free (SIL Open Font License). Keep the licence file from the download next to the fonts
  if you pass the folder on.
- Instead of copying them here you can also install the fonts on the computer – the app finds installed fonts too.
  Fonts in this folder are preferred.
- For PowerPoint export, the fonts must be installed on the computer that opens the `.pptx`; otherwise PowerPoint
  substitutes another font.
- Other families the app knows (Inter, Lato, Montserrat, Source Sans 3, Source Code Pro, IBM Plex Mono, …) can be
  added the same way; the expected file names are listed in `FAMILIES` in `poster/fonts.py`.

This folder's contents are ignored by git (see `.gitignore`); only this README is tracked.
