# BildHatcher

Turns images into laser toolpaths: colour images are prepared (scaling, colour reduction, painting, masks,
text/geometry overlays), every colour is filled with hatch lines, and the result is exported as G-code / J-code
for a laser machine (flat or wrapped around a cylinder).

## Setup

Python 3.14 (Windows). Install the dependencies – `requirements.txt` for running the app, `requirements-dev.txt`
additionally for the tests, the tools in `tools/` and building the executable:

```
python -m pip install -r requirements-dev.txt
```

## Run

```
python main.py
```

## Using the app

- **Toolbar:** load / save / new, the active tool and colour, zoom, re-center, grid, colour profile (database
  laser / material / type, used everywhere) and machine profile. Hover a pictogram for its name.
- **Settings panel (right):** the icon strip on the far right selects a group (Image, Text, Hatching,
  Automation); clicking the active group again closes the panel. Next to it, the rotated buttons show or hide
  the sections of that group – several can be open. The selection is remembered.
- **Hotkeys** (over the main window, not while typing in a field): `D` draw, `F` fill, `R` replace,
  `P` pick a colour from the image, `C` more colours, `T` transparent. They work with the panel closed.
- **Tool wheel:** hold the right mouse button over the image, move to a tool, release. A short right click
  keeps the wheel open; click a tool (centre or `Esc` closes).
- Undo / redo: `Ctrl+Z` / `Ctrl+Y`.

## Tests

```
python -m pytest
```

The tests run headless (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`) and take a few seconds.
`tests/test_characterization.py` compares the complete pipeline (image → hatching → post-processing → G-code)
with the files in `tests/golden/`. If an output change is intended, regenerate them and document the change in
`REVISION_PLAN.md`:

```
UPDATE_GOLDEN=1 python -m pytest tests/test_characterization.py
```

## Project structure

| Path | Content |
|---|---|
| `main.py` | Starts the app; `create_main_window()` / `create_components()` build the UI (also used by the tests) |
| `MainLayout.py` | Toolbar and settings panel (groups, sections, pictograms); section contents come from the .ui file |
| `Tools.py` | Hotkeys, active-tool indicator, tool wheel and canvas cursors (pen outline) for the colour tools |
| `icons.py` | Pictograms for the code-built parts; the icons live in `GUI_Files/icons/<meaning>.svg` (origins and licences: `GUI_Files/icons/SOURCES.md`) |
| `theme.py` | The app's look ("Atelier", after piupulaser.de), dark or bright (*Modes > Bright Mode*, remembered): renders `GUI_Files/styles/atelier.qss` with the mode's palette, loads the fonts, switches pictograms and code-drawn colours at run time |
| `core/` | Processing without Qt: `image_doc` (RGBA image model), `hatching` (hatch patterns), `fill` (flood fill), `toolpath` (layer/polyline model), `postprocess`, `gcode`, `machine` (machine profiles) |
| `ImageControlling.py` | Image list, load/save, size, rotate/mirror/crop, upscaling, zoom/pan |
| `ImageEditing.py` | Adjustments, quantization, painting/fill, contours |
| `Masks.py` | Mask drawing, editing and moving |
| `ColorProfile.py` / `Preferences.py` | Active colour-database profile / remembered settings (`preferences.json`) |
| `TextandGeometries.py` | Text and geometry overlays |
| `NCDataGeneration.py` | Hatching UI and worker thread, contours/DXF import |
| `Parsing.py` | Process blocks and export (G-code, J-code, txt) |
| `Plotting.py` | 3D preview of the toolpath |
| `DataHandling.py` | Application state: active image document, hatch data, masks, machine profile |
| `UndoRedo.py` | Undo/redo |
| `Database/` | Material/laser parameter database |
| `GUI_Files/` | Qt Designer file (`BildHatcher.ui`: section layouts, pictograms, tooltips, sizes, stylesheet) and icons |
| `GUI_Files/styles/` | Stylesheets: `atelier.qss` (the look, portable: a template whose `@tokens` come from the dark and bright palettes in its header; edit this file and run `python tools/apply_style.py` to copy the dark rendering into the .ui for Designer), `legacy_burgundy.qss` (the previous look) |
| `GUI_Files/fonts/` | Plus Jakarta Sans and Space Mono (SIL Open Font License, licence texts next to the fonts) |
| `tools/make_icons.py` | Draws BildHatcher's own pictograms and cursors (dark-theme colours) |
| `machine_profiles/` | Bundled machine profiles (JSON) |

Images are RGBA with a binary alpha: transparent pixels are background and never hatched (see
`core/image_doc.py`). Toolpaths are lists of `Layer`s (one per colour) with polylines as numpy arrays
(`core/toolpath.py`).

## User folder

`~/Documents/BildHatcher/` holds what the app writes:

- `laser_database.db` – the parameter database (copied from the bundled one on first start)
- `machine_profiles/` – machine profiles; add a machine by copying and editing a JSON file
  (fields: see `core/machine.py`), then restart. *Settings → Open Machine Profiles Folder* opens it.
- `libraries/realesrgan/` – the AI upscaling engine, downloaded on first use
- `preferences.json` – remembered UI state and the active colour profile
- `bildhatcher.log` – log file

## Build

```
python build_executable.py
```

Creates `dist/BildHatcher_v<version>.exe` (PyInstaller, one file). The version comes from `version.json`.

## Development

The code revision 2.0 is tracked in `REVISION_PLAN.md` (status, bug list, decisions).
