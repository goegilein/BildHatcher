# BildHatcher – Code Revision 2.0

Living plan for the major revision of the codebase. Work happens on branch **`code_rev_2.0`**.
This file is the single source of truth for status – update it in the same commit as the work it describes.

- Baseline commit: `93966c1` (main). All `file:line` references below refer to that commit and will drift as work proceeds.
- Status markers in task lists: `[ ]` open · `[~]` in progress · `[x]` done · `[-]` dropped (give reason). Keep the **Current status** table up to date.
- Task IDs (e.g. `B03`, `P4.2`) are stable – reference them in commit messages, e.g. `B03: fix jcode save path handling`.

---

## Current status

| Phase | State | Notes |
|---|---|---|
| 0 – Safety net & hygiene | done (except P0.3 pptx) | tests: `python -m pytest` |
| 1 – Bug fixes | done | B17, B22 partly deferred to P6.4 / P6.10 |
| 2 – Core model & state | **next** | |
| 3 – Transparency | open | |
| 4 – Hatching engine | open | |
| 5 – Output | open | |
| 6 – Editing tools | open | |
| 7 – Polish | open | |

Bug table (section 4) uses the words `open` / `partial` / `done`; phase task lists use checkboxes.

---

## 0. How to work with this plan

1. Pull `code_rev_2.0` before starting on any machine.
2. Pick the next open task of the current phase (phases are ordered; tasks inside a phase mostly are not).
3. Mark it `[~]` when starting a larger task, `[x]` when done, and add a line to the **Work Log** (section 9).
4. New findings go into the matching section with a new ID; never renumber existing IDs.
5. Decisions that change the plan go into **Decisions** (section 7).

---

## 1. Goals

- **Simpler structure:** separate pure processing logic (numpy, testable) from Qt UI code.
- **One source of truth** for image, toolpath and settings state – no manual copy/sync between modules.
- **Faster:** vectorized hatching, post-processing, G-code generation and plotting.
- **More stable:** no GUI access from worker threads, real error reporting, regression tests.
- **Transparency as background model** instead of "white = background" (see section 2).

---

## 2. Concept: Transparency as background

### Current state
"Background" is decided redundantly in many places:
- hatching: `sum(color)/3 > white_threshold` ([NCDataGeneration.py:331](NCDataGeneration.py#L331))
- parsing: same check, own spinbox ([Parsing.py:444](Parsing.py#L444))
- plotting: same check, own spinbox ([Plotting.py:621](Plotting.py#L621))
- hardcoded `[255,255,255]` in crop background, cut to mask, save mask, split colors, combine images, clean-up, move mask (white cutout), new blank image.
- Loading composites alpha onto white ([ImageControlling.py:268-275](ImageControlling.py#L268-L275)); imprinting drops alpha ([ImageEditing.py:1483](ImageEditing.py#L1483)).

### Target model
- Images are stored as **`uint8` RGBA, invariant `alpha ∈ {0, 255}`**. Maps 1:1 to PNG, Qt (`Format_RGBA8888`) and undo snapshots.
- Processing functions receive `(rgb, opaque_mask)`; transparent pixels are **always ignored** by hatching, parsing, plotting, quantization, colour counting, recolouring.
- White becomes a normal, hatchable colour.

### Rules
- **Load:** binarize alpha with a threshold (default 128). Semi-transparent edge pixels are composited over white, then set fully opaque (keeps anti-aliased edge colours).
- **RGB files without alpha:** option "treat pure white as background" – **default ON** for backward compatibility.
- **Brightness threshold** survives as a one-shot image tool: "make colours brighter than X transparent". Downstream thresholds (hatching/parsing/plotting spinboxes) are removed.
- **Filters** (blur, bilateral, sharpen, enhance): before filtering, fill transparent RGB with nearest opaque colour (`cv2.inpaint` or dilate), filter, then re-apply the mask – prevents background colour bleeding into edges.
- **New UI:** eraser tool (paint transparent), "transparent" colour swatch, checkerboard canvas background.
- **Save:** PNG/SVG keep alpha; JPEG/BMP composite over white (or user colour).

---

## 3. Target architecture

```
bildhatcher/
  core/                  # pure numpy, NO Qt imports – unit-testable
    image_doc.py         # ImageDocument: rgba, pixel_per_mm, original, name, center, masks (geometry)
    color.py             # label map, palette, unique colours, ΔE matching
    toolpath.py          # Toolpath / Layer(color, speed, pwr, polylines: list[ndarray(N,3)], burn flags)
    transform.py         # single image-px <-> machine-mm transform (flip, center, ppm)
    hatching/engine.py   # sample curves -> run-length encode labels -> segments per label
    hatching/patterns.py # meander / crossed / circular / spiral / radial = curve generators
    cylinder.py          # cylindrical clustering + mapping
    contours.py          # region outlines, canny contours
    dxf_import.py        # via ezdxf.path + flattening()
    postprocess.py       # RDP simplify, constant/over drive
    gcode.py             # streaming writer + MachineProfile
    machine_profiles/*.json
  ui/                    # one controller per tab; only binds widgets <-> core/state
  state.py               # AppState(QObject): documents, active doc, toolpath, process blocks, signals
  settings.py            # declarative widget registry -> generic save/load
  workers.py             # QThread workers that receive frozen settings dataclasses
tests/                   # pytest; core only, plus characterization tests
```

### Key design decisions
- **AppState with Qt signals** (`image_changed`, `image_geometry_changed`, `toolpath_changed`, …) replaces the property-setter callback lists in `DataHandler`, `ObservableList`, and all `get_handler_data` / `set_handler_data` copying. Each image exists exactly once as an `ImageDocument`; the image list widget is only a view.
- **Toolpath as arrays:** colour/speed/power live on the layer, not on every point. Move type is implicit (first point = travel, rest = burn) plus an optional per-vertex `burn` flag array for lead-in/over-drive moves. `deepcopy` becomes cheap; plotting/G-code vectorize.
- **Immutable results:** hatching/contour/test-structure generators return new `Toolpath` objects; nothing mutates shared instances.
- **Workers never touch widgets:** settings are collected on the GUI thread into a frozen dataclass; workers only emit `progress`, `result`, `error` signals.

---

## 4. Bug list (fix in Phase 1, in the current code)

| ID | Status | Location | Problem |
|---|---|---|---|
| B01 | done | [NCDataGeneration.py:1083](NCDataGeneration.py#L1083) | DXF ARC: `segments` is a float → `range()` TypeError; degrees treated as radians. Any DXF with an ARC fails. `contour_from_dxf` also appends to previous clusters instead of resetting. |
| B02 | done | [NCDataGeneration.py:206-209](NCDataGeneration.py#L206-L209), [:284](NCDataGeneration.py#L284) | Automatic mode busy-waits; if hatching returns `None` (e.g. image too large for cylinder) `waiting_for_worker` is never cleared → app hangs at 100 % CPU. |
| B03 | done | `HatchingWorker` / `create_hatching_worker` | Worker thread reads spinboxes, sets labels, calls `processEvents()`, reads `progress_dialog.value()` – not thread-safe. Signal `finished` shadows `QThread.finished`. Progress dialog never closed on success. |
| B04 | done | [NCDataGeneration.py:488/497](NCDataGeneration.py#L488) | CylEquidistX: `point_outside=True` is overwritten with `False` a few lines later → first point of a line never treated as outside (same pattern in `hatch_radial`). |
| B05 | done | [TestStructures.py](TestStructures.py) (all generators) | `hatch_clusters` set to plain lists instead of `HatchCluster` → `add_process_block` and plotting raise AttributeError. Test structures are unusable. |
| B06 | done | [Parsing.py:415](Parsing.py#L415) | `.txt` export uses non-existent `process_block.data` → always fails. File naming inconsistent (`_block-` vs `_cluster-`). |
| B07 | done | [Parsing.py:235](Parsing.py#L235), [:260](Parsing.py#L260) | jcode: cancelling save dialog → crash on `open('')`. If path doesn't end in `.jcode`, cluster files get the main file's name and overwrite it. Header written before "no blocks" check. |
| B08 | done | [Parsing.py:320-323](Parsing.py#L320-L323) | `save_gcode` appends the footer after every cluster and once more at the end. |
| B09 | done | [Parsing.py:440](Parsing.py#L440) | `line_collection[0][0]` IndexError when a colour produced no lines. |
| B10 | done | [PostProcessing.py:389-392](PostProcessing.py#L389-L392) | "Maximize Lines" angle accumulation is wrong: on a perfectly straight polyline every 2nd point is kept → at most halves point count. |
| B11 | done | [PostProcessing.py:419](PostProcessing.py#L419) | `set_drive_mode` crashes for polylines with < 2 points; zero-length segments → NaN (division by zero in `elongate_line`). Dead statement at line 442. |
| B12 | done | [ImageEditing.py:1098](ImageEditing.py#L1098), [:1150](ImageEditing.py#L1150) | Flood fill "Similar Color" / "Diagonals + Similar": without masks the matrix is `uint8` → subtraction wraps around, tolerance check wrong. |
| B13 | done | [ImageEditing.py:1738](ImageEditing.py#L1738) | "Clean up colors" uses the colour-count spinbox (default 256) as kernel size; allocates H×W×N float32. |
| B14 | done | [ImageEditing.py:1323](ImageEditing.py#L1323), [:1334](ImageEditing.py#L1334) | DB recolour: cancelling profile dialog → AttributeError (or silently reuses old profile). Distance array pixels×palette×3 can exhaust memory. |
| B15 | done | [ImageControlling.py:1219](ImageControlling.py#L1219) | Hatch centre computed from the *original* image shape → wrong after rotate/crop of non-square images. |
| B16 | done | [ImageControlling.py:469](ImageControlling.py#L469) | Unlocked-ratio resize result discarded (dead code; checkbox disabled). Remove or implement. |
| B17 | partial | masks (ImageEditing) | Mask matrices not cleared/transformed after rotate/crop/upscale/image switch → shape mismatch in flood fill/replace. Mask outlines live in scene coords → drift after pixel-size change. |
| B18 | done | [Point.pos setter, HelperClasses.py](HelperClasses.py) | Asserts shape `(1,3)` instead of `(3,)`. (Obsoleted by P2 data model, fix only if touched.) |
| B19 | done | [Settings.py](Settings.py) | Comboboxes persisted by index (breaks when items change); hatching/plotting thresholds and several other parameters not saved. |
| B20 | done | [ImageControlling.py:636](ImageControlling.py#L636) | `combine_images`: `avg_color` always `[0,0,0]` → monochrome is always black; Python per-pixel loop. |
| B21 | done | Plotting.initializeGL | Raw GL calls without a current GL context → `GLError 1282` (crashes headless start; worked in the app only by accident). Calls were redundant – removed. |
| B22 | partial | ImageUpscaling | Runs `realesrgan-x4plus` with `-s 2` (verify model supports it); blocking subprocess on UI thread; upscaler mutates `data_handler.image_matrix` as side effect. Vendored engine lacks the `models/` folder, so `is_engine_available()` is always False and the ~33 MB download runs anyway; in a frozen build it would download into the PyInstaller temp dir. |
| B23 | done | [NCDataGeneration.py:174](NCDataGeneration.py#L174) | `get_sorted_unique_colors` sums `uint8` tuples → overflow (RuntimeWarning in tests); colour processing order is effectively arbitrary instead of bright→dark. Fixing it changes golden outputs (order only). |
| B24 | done | [PathManager.py](PathManager.py) | Uses `GUI_files` while the folder is `GUI_Files` – only works on case-insensitive file systems (Windows). |
| B25 | done | [EventHandling.py](EventHandling.py) | Event filter keeps firing during teardown → `RuntimeError: wrapped C/C++ object … has been deleted` on exit. |
| B26 | done | [NCDataGeneration.py:115](NCDataGeneration.py#L115) | Cylinder radius < laser distance (17 mm, hardcoded) → `acos` of a value < −1 → NaN; worked only by accident. Clipped. (Laser distance belongs into the machine profile, P5.1.) |
| B27 | done | [ImageControlling.py](ImageControlling.py) `combine_images`, `change_image` | Combining with all images selected crashed (pixel size read from an already removed item); `change_image` then wrote into a non-existing active item. |

---

## 5. Phases and tasks

### Phase 0 – Safety net & hygiene  `[~]` (only P0.3 pptx left)
- [x] P0.1 Untrack `__pycache__/` and `Database/__pycache__/` (`git rm --cached`), extend `.gitignore`.
- [x] P0.2 Remove `GUI_Files/BildHatcher_backup.ui`, `GUI_Files/BildHatcher_KI-changes.ui`, obsolete tkinter `profiler.py` (history keeps them).
- [~] P0.3 Vendored Real-ESRGAN removed, engine downloads into `~/Documents/BildHatcher/libraries/realesrgan` (done). Open: `Data-Architecture.pptx` (replace by section 3 of this file?).
- [x] P0.4 Pin `requirements.txt` versions; add `requirements-dev.txt` (pytest).
- [x] P0.5 Introduce `logging` (one config in `main.py`); new code uses `log` instead of `print`. (Replacing existing `print`s happens per module as it is touched / P7.3.)
- [x] P0.6 **Characterization tests:** headless run (`QT_QPA_PLATFORM=offscreen`) of current hatcher + post-processor + parser on 3–4 reference images (flat meander, circular, cylindrical, contours) → store G-code as golden files in `tests/golden/`. Used to verify Phase 2 ports. Seed `random` for RandomMeander/Circular.

### Phase 1 – Bug fixes in current code  `[x]`
- [x] P1.1 Fix B01–B27 (see table). Remaining parts: B17 mask outline drift after pixel-size change → P6.4; B22 upscaler threading/side effects → P6.10.
- [x] P1.2 Regenerate golden files where a fix intentionally changes output (document which). → None needed: all 14 golden outputs unchanged (B23 happened to keep the test colours' order; B04/B10 do not trigger on the golden inputs). New golden file: `test_structure_filled_squares_horz`.

### Phase 2 – Core model & state  `[ ]`
- [ ] P2.1 Create package layout (section 3); move pure functions out of UI classes.
- [ ] P2.2 `ImageDocument` (initially RGB, RGBA in Phase 3) incl. per-document hatch center and mask geometry.
- [ ] P2.3 `AppState(QObject)` with signals; replace `DataHandler` callbacks, `ObservableList`, `get/set_handler_data`; image list widget becomes a view of `AppState.documents`.
- [ ] P2.4 `Toolpath` / `Layer` array model; adapters from/to old `HatchData` while porting.
- [ ] P2.5 `core/transform.py`: one image-px ↔ machine-mm transform; remove ad-hoc flips (`np.flipud`, `height - y - 1`, center flip).
- [ ] P2.6 Port existing hatching, contours, DXF, test structures, post-processing, G-code **1:1** onto the new model; verify against golden files.
- [ ] P2.7 Consolidate the three duplicated `_sync_matrix` implementations in `UndoRedo.py` into one helper operating on `AppState`.
- [ ] P2.8 Unit tests for core modules.

### Phase 3 – Transparency  `[ ]`
- [ ] P3.1 RGBA storage with binarized alpha; loader rules (section 2); "white as background" option for RGB files.
- [ ] P3.2 Display: RGBA pixmap, checkerboard background brush.
- [ ] P3.3 Remove downstream white thresholds (hatching/parsing/plotting); add "brighter than X → transparent" tool.
- [ ] P3.4 Replace all hardcoded white logic (crop background, cut to mask, save mask, split, combine, cleanup, move-mask cutout, new blank).
- [ ] P3.5 Quantization/k-means/recolour/colour count only on opaque pixels; filter edge handling (inpaint → filter → re-mask).
- [ ] P3.6 Imprint keeps alpha; eraser tool; transparent swatch.
- [ ] P3.7 Save: alpha for PNG/SVG, composite for JPEG/BMP; drop "white as transparent" checkbox (or keep as conversion).
- [ ] P3.8 Config/backward compatibility check with old images & configs.

### Phase 4 – Hatching engine  `[ ]`
- [ ] P4.1 Label map once per cluster (`np.unique(..., return_inverse=True)`, background = −1).
- [ ] P4.2 Generic engine: vectorized curve sampling → label lookup → run detection via `np.diff` → segments for **all labels in one pass**.
- [ ] P4.3 Patterns as curve generators (meander, crossed, circular, spiral, radial); removes the 5 duplicated loops. CylEquidistX mapping vectorized.
- [ ] P4.4 Meander ordering per label (alternating direction) preserved; seeded RNG for random patterns (seed saved in settings).
- [ ] P4.5 Optional: exact pixel-edge intersection for straight lines (DDA) – segment ends independent of step size.
- [ ] P4.6 Worker with frozen `HatchSettings`; signals only; automatic mode continues on result signal (no busy loop); proper cancel.
- [ ] P4.7 Benchmark old vs. new (record numbers in Work Log); compare output against golden files (tolerances documented).

### Phase 5 – Output (post-processing, G-code, plotting)  `[ ]`
- [ ] P5.1 `MachineProfile` JSON (**user-facing feature**, multiple machines planned – see Q1): header/footer, laser mode & power mode commands, enclosure fan, air assist, acceleration (now hardcoded 3000 mm/s²), travel speed (now hardcoded 100), over-drive fit parameters. Snapmaker Artisan = first profile.
- [ ] P5.2 Streaming, vectorized G-code / jcode / txt writer; shared block/iteration loop for all formats.
- [ ] P5.3 Replace "Maximize Lines" by Ramer–Douglas–Peucker with tolerance in mm.
- [ ] P5.4 Constant/Over Drive rewritten on arrays with guards (short polylines, zero-length segments).
- [ ] P5.5 `set_speed_and_pwr` on layers (no per-point loop, no full deepcopy incl. image matrix).
- [ ] P5.6 Plotting: one `GLLinePlotItem` per layer, vectorized position/colour arrays.
- [ ] P5.7 DB colour matching: parse palette once, optional ΔE (Lab) distance.

### Phase 6 – Image editing tools  `[ ]`
- [ ] P6.1 Non-destructive adjustment pipeline `result = pipeline(base, params)`; slider debounce (~50 ms); undo stores parameter changes.
- [ ] P6.2 K-means on sample (~50k opaque px), predict all; optional Lab space.
- [ ] P6.3 Flood fill via `cv2.floodFill` / connected components for all modes ("Fill Lines" = `target & dilate(fill, r)`).
- [ ] P6.4 (incl. rest of B17) Masks: geometry as source of truth, rasterize with `cv2.rectangle/ellipse/fillPoly`; outlines as children of `image_item` in image coords; transform/clear on geometry change; extract `MaskManager` from `ImageColorer`.
- [ ] P6.5 Colour overlays cropped to bounding box (not full-size RGBA per fill); pixmap overlays imprinted in numpy, vector items via QPainter into RGBA layer.
- [ ] P6.6 Vectorize split colours, combine images, clean-up colours/clusters (remove unused `clean_up_clusters` if still unused).
- [ ] P6.7 Contours: new mode "region outlines" via `findContours` on per-colour masks (`CHAIN_APPROX_NONE` + `approxPolyDP`); keep Canny mode.
- [ ] P6.8 DXF import via `ezdxf.path` + `flattening(tolerance)` (supports splines, ellipses, bulges).
- [ ] P6.9 Undo: memory-based limit (MB) instead of 50 full images; optional changed-region storage.
- [ ] P6.10 Upscaler in worker thread; no side effects on state (see B22). Verify the 4x-then-resize path with the real engine (not covered by tests).
- [ ] P6.11 Grid and center cross as children of `image_item` (follow pan/zoom/rescale correctly).

### Phase 7 – Polish  `[ ]`
- [ ] P7.1 Declarative settings registry; save combobox text; one config file with sections (image / hatching / output); load old configs.
- [ ] P7.2 Single UI language (see open question Q2) – currently mixed German/English.
- [ ] P7.3 User-facing error dialogs / status bar instead of silent `print`; remove blanket `try/except`.
- [ ] P7.4 Update `build_executable.py` for new package layout; bump version to 2.0.0.
- [ ] P7.5 README: architecture overview, dev setup, running tests.

---

## 6. Open questions

| ID | Question | Answer |
|---|---|---|
| Q1 | Is the Snapmaker Artisan the only target machine, or should machine profiles be a real user-facing feature? | Multiple machines will follow → machine profiles become a user-facing feature (P5.1). |
| Q2 | UI language: English or German? | **English.** |
| Q3 | Keep vendored Real-ESRGAN binaries in git? | **Removed** from git; download-on-demand into `~/Documents/BildHatcher/libraries/realesrgan`. |
| Q4 | Default for "treat pure white as background" on RGB load (proposed: ON). | **ON.** |

---

## 7. Decisions

| Date | Decision |
|---|---|
| 2026-11-15 | Revision happens on branch `code_rev_2.0`; this file tracks status. |
| 2026-11-15 | Background is modelled via binary alpha (RGBA, alpha ∈ {0,255}) instead of white. |
| 2026-11-15 | Machine profiles are a user-facing feature (Q1). UI language is English (Q2). White-as-background default ON for RGB images (Q4). |
| 2026-11-15 | `main.py` exposes `create_main_window()` / `create_components(gui)` so tests build the real app wiring headless. |

---

## 8. Known performance hotspots (for benchmarking)

- Hatching: per-sample Python loop, once per colour ([NCDataGeneration.py:500-557](NCDataGeneration.py#L500-L557) and siblings).
- `get_sorted_unique_colors` via `set(map(tuple, ...))`.
- Flood fill: Python BFS with `np.array_equal` per pixel.
- Rect/ellipse mask rasterization: Python double loops.
- `split_colors`, `combine_images`: per-pixel Python loops.
- K-means on all pixels.
- `copy.deepcopy` of full `HatchData` (incl. input image matrices) per process block.
- Per-point loops in plotting, post-processing, G-code.
- Undo: up to 50 × 2 full image copies; repeated `.copy()` during state sync.

---

## 9. Work Log

| Date | Task(s) | Notes |
|---|---|---|
| 2026-11-15 | – | Full code review done, plan created on branch `code_rev_2.0`. |
| 2026-11-15 | P0.1, P0.2, P0.4, P0.5, P0.6, B21 | Untracked `__pycache__`, removed backup `.ui` files + obsolete tkinter `profiler.py`, pinned requirements (+ `requirements-dev.txt`), logging setup, `main.py` split into factory functions. Characterization tests: `python -m pytest` (14 golden G-code files in `tests/golden/`, 1 strict xfail for B05; ~20 s). New findings B23–B25. |
| 2026-11-15 | Q3, B24 | Vendored Real-ESRGAN removed (download into user folder); build script no longer references missing `settings/` and `libraries/`; `GUI_Files` casing fixed. |
| 2026-11-15 | P1: B01–B27 | Hatching worker rewritten to be thread-safe (settings collected on GUI thread, single completion slot on `QThread.finished`, `QEventLoop` wait in automatic mode; note: `QProgressDialog.close()` emits `canceled`, and slots on non-QObject receivers run in the emitting thread – both handled). All other Phase-1 bugs fixed, new findings B26/B27. Tests: 23 passing (`tests/test_bugfixes.py` added). One full run once took 17 min, not reproducible (5 reruns ~3.5 s). Not done: manual GUI click-through of the fixed features. |
