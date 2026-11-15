# BildHatcher

Turns images into laser toolpaths: colour images are prepared (scaling, colour reduction, painting, masks,
text/geometry overlays), every colour is filled with hatch lines, and the result is exported as G-code / J-code
for a laser machine (flat or wrapped around a cylinder).

## Setup

Python 3.14 (Windows). Install the dependencies:

```
python -m pip install -r requirements-dev.txt
```

## Run

```
python main.py
```

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
| `core/` | Processing without Qt: `image_doc` (RGBA image model), `hatching` (hatch patterns), `fill` (flood fill), `toolpath` (layer/polyline model), `postprocess`, `gcode`, `machine` (machine profiles) |
| `ImageControlling.py` | Image list, load/save, size, rotate/mirror/crop, upscaling, zoom/pan |
| `ImageEditing.py` | Adjustments, quantization, painting/fill, contours, masks |
| `TextandGeometries.py` | Text and geometry overlays |
| `NCDataGeneration.py` | Hatching UI and worker thread, contours/DXF import |
| `Parsing.py` | Process blocks and export (G-code, J-code, txt) |
| `Plotting.py` | 3D preview of the toolpath |
| `DataHandling.py` | Application state: active image document, hatch data, masks, machine profile |
| `UndoRedo.py` | Undo/redo |
| `Database/` | Material/laser parameter database |
| `GUI_Files/` | Qt Designer files |
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
- `bildhatcher.log` – log file

## Build

```
python build_executable.py
```

Creates `dist/BildHatcher_v<version>.exe` (PyInstaller, one file). The version comes from `version.json`.

## Development

The code revision 2.0 is tracked in `REVISION_PLAN.md` (status, bug list, decisions).
