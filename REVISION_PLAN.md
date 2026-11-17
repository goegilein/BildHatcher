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
| 2 – Core model & state | done | P2.1 rest → Phase 4, masks per document → P6.4 |
| 3 – Transparency | done | |
| 4 – Hatching engine | done | 13–33× faster, exact edges for lines, random seed |
| 5 – Output | done | machine profiles, RDP, fast drive modes |
| 6 – Editing tools | done | fill/quantize/clean-up fast, B17/B33 fixed |
| 7 – Polish | done | version 2.0.0 |
| 8 – UI rework & image tools | done (P8.9 optional) | branch not merged yet – user decides |
| 9 – Compact UI, hotkeys, tool wheel | **planning** | decisions Q9.x open |

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
| B17 | done | masks (ImageEditing) | Mask matrices not cleared/transformed after rotate/crop/upscale/image switch → shape mismatch in flood fill/replace. Mask outlines live in scene coords → drift after pixel-size change. |
| B18 | done | [Point.pos setter, HelperClasses.py](HelperClasses.py) | Asserts shape `(1,3)` instead of `(3,)`. (Obsoleted by P2 data model, fix only if touched.) |
| B19 | done | [Settings.py](Settings.py) | Comboboxes persisted by index (breaks when items change); hatching/plotting thresholds and several other parameters not saved. |
| B20 | done | [ImageControlling.py:636](ImageControlling.py#L636) | `combine_images`: `avg_color` always `[0,0,0]` → monochrome is always black; Python per-pixel loop. |
| B21 | done | Plotting.initializeGL | Raw GL calls without a current GL context → `GLError 1282` (crashes headless start; worked in the app only by accident). Calls were redundant – removed. |
| B22 | done | ImageUpscaling | Runs `realesrgan-x4plus` with `-s 2` (verify model supports it); blocking subprocess on UI thread; upscaler mutates `data_handler.image_matrix` as side effect. Vendored engine lacks the `models/` folder, so `is_engine_available()` is always False and the ~33 MB download runs anyway; in a frozen build it would download into the PyInstaller temp dir. |
| B23 | done | [NCDataGeneration.py:174](NCDataGeneration.py#L174) | `get_sorted_unique_colors` sums `uint8` tuples → overflow (RuntimeWarning in tests); colour processing order is effectively arbitrary instead of bright→dark. Fixing it changes golden outputs (order only). |
| B24 | done | [PathManager.py](PathManager.py) | Uses `GUI_files` while the folder is `GUI_Files` – only works on case-insensitive file systems (Windows). |
| B25 | done | [EventHandling.py](EventHandling.py) | Event filter keeps firing during teardown → `RuntimeError: wrapped C/C++ object … has been deleted` on exit. |
| B26 | done | [NCDataGeneration.py:115](NCDataGeneration.py#L115) | Cylinder radius < laser distance (17 mm, hardcoded) → `acos` of a value < −1 → NaN; worked only by accident. Clipped. (Laser distance belongs into the machine profile, P5.1.) |
| B27 | done | [ImageControlling.py](ImageControlling.py) `combine_images`, `change_image` | Combining with all images selected crashed (pixel size read from an already removed item); `change_image` then wrote into a non-existing active item. |
| B28 | done | [NCDataGeneration.py](NCDataGeneration.py) `get_handler_data` | Image rows are flipped as r → H−1−r, but the hatch center as cy → H−cy: every image-based output was shifted by one pixel in −y (0.1 mm at 10 px/mm). Fix changes all image goldens: meander/contour/cylinder outputs are a pure +1 px y shift, circle/spiral/radial are resampled around the true center. |
| B29 | done | [ImageEditing.py](ImageEditing.py) `invert_colors` | Inverted a cached copy (`image_current`) instead of the current image: from the second invert on, all edits made in between were lost. |
| B30 | done | [core/hatching.py](core/hatching.py) `_pixel_index` (former `int(y)==int(y-0.5)` rounding in every pattern loop) | Rounding was wrong for coordinates < 0.5: [−1.5, 0) mapped to pixel 0 and [0, 1.5) to pixel 1, so the bottom and left image edges were shifted by up to one pixel and lines overshot there. |
| B32 | done | [core/fill.py](core/fill.py) (former `ImageColorer.flood_fill`) | With masks, "To Contours" and "To Color" ignored the mask boundary (they do not compare colours, so the out-of-mask sentinel had no effect) and filled beyond it. |
| B33 | done | [ImageEditing.py](ImageEditing.py) `ImageAdjuster` | The adjustment base was only re-read when the adjustment *type* changed: slider values were applied a second time after another edit (brightness → quantize → contrast doubled the brightness), and re-quantizing after painting discarded the painting. |

---

## 5. Phases and tasks

### Phase 0 – Safety net & hygiene  `[~]` (only P0.3 pptx left)
- [x] P0.1 Untrack `__pycache__/` and `Database/__pycache__/` (`git rm --cached`), extend `.gitignore`.
- [x] P0.2 Remove `GUI_Files/BildHatcher_backup.ui`, `GUI_Files/BildHatcher_KI-changes.ui`, obsolete tkinter `profiler.py` (history keeps them).
- [x] P0.3 Vendored Real-ESRGAN removed, engine downloads into `~/Documents/BildHatcher/libraries/realesrgan`. `Data-Architecture.pptx` kept and updated (P8.8).
- [x] P0.4 Pin `requirements.txt` versions; add `requirements-dev.txt` (pytest).
- [x] P0.5 Introduce `logging` (one config in `main.py`); new code uses `log` instead of `print`. (Replacing existing `print`s happens per module as it is touched / P7.3.)
- [x] P0.6 **Characterization tests:** headless run (`QT_QPA_PLATFORM=offscreen`) of current hatcher + post-processor + parser on 3–4 reference images (flat meander, circular, cylindrical, contours) → store G-code as golden files in `tests/golden/`. Used to verify Phase 2 ports. Seed `random` for RandomMeander/Circular.

### Phase 1 – Bug fixes in current code  `[x]`
- [x] P1.1 Fix B01–B27 (see table). Remaining parts: B17 mask outline drift after pixel-size change → P6.4; B22 upscaler threading/side effects → P6.10.
- [x] P1.2 Regenerate golden files where a fix intentionally changes output (document which). → Phase 1: none needed. (B28 in Phase 2 regenerated all image goldens, see bug table.) Phase 1 detail: all 14 golden outputs unchanged (B23 happened to keep the test colours' order; B04/B10 do not trigger on the golden inputs). New golden file: `test_structure_filled_squares_horz`.

### Phase 2 – Core model & state  `[x]` (P2.1 rest and P2.2 mask/center per document move to Phases 4 / 6)

Done in sub-steps, each one green against the golden files:
- [x] **2a** Qt-free `core/` package for the output stage: `core/postprocess.py` (was `PostProcessing.py`, plus `apply_speed_and_power` – formerly `Parser.set_speed_and_pwr`, GUI values now passed in), `core/gcode.py` (header/footer/G-code/txt generation). `Parsing.py` only collects GUI values and writes files.
- [x] **2b** Array toolpath model (P2.4) – `core/toolpath.py`: `Layer(color, polylines, speed, power)`, polyline = ndarray (N,4) rows `(x, y, z, move)`. Hatching output, cylinder wrap (vectorized), contours/DXF, post-processing, G-code/txt, plotting (vectorized) and test structures ported; `Point` removed. Goldens byte-identical.
- [x] **2c** `core/image_doc.py` `ImageDocument` (was `ImgObj`) is owned by the image list; `DataHandler.image_matrix` / `pixel_per_mm` / `image_matrix_original` read and write the active document directly (`set_active_document`). All `get_handler_data` syncing removed; upscaler works on a copy without side effects (rest of B22: threading → P6.10); undo actions share one `restore_image` helper (P2.7) that refuses to restore into a removed image.
- [x] **2d** Coordinate transform (P2.5): only two image→machine conversions exist (hatcher center flip, contour export), so no extra module. Review found **B28** (1 px y offset), fixed at the source.

- [x] P2.1 Create package layout (section 3); move pure functions out of UI classes. (output stage 2a, toolpath 2b, image document 2c, hatching patterns 4a)
- [~] P2.2 `ImageDocument` (initially RGB, RGBA in Phase 3). Per-document hatch center and mask geometry: not yet (masks → P6.4).
- [x] P2.3 Single source of truth for image state. *Changed:* no new `AppState` class – `DataHandler` is the app state; its plain callback lists and `ObservableList` stay (they work and are synchronous; Qt signals would only add churn). See Decisions.
- [x] P2.4 `Layer` array model (no adapters needed – ported in one step, see 2b). `HatchData`/`HatchCluster` kept as containers for now.
- [x] P2.5 Image-px ↔ machine-mm conversion checked; *changed:* no `core/transform.py` (two call sites only), B28 fixed instead.
- [x] P2.6 Port existing hatching, contours, DXF, test structures, post-processing, G-code **1:1** onto the new model; verify against golden files. (2b)
- [x] P2.7 Consolidate the three duplicated `_sync_matrix` implementations in `UndoRedo.py` into one helper (`restore_image`).
- [x] P2.8 Unit tests for core modules (post-processing B10/B11, toolpath via goldens, image state).

### Phase 3 – Transparency  `[x]`
- [x] P3.1 RGBA storage with binarized alpha (`core/image_doc.normalize`, applied in `ImageDocument` and on every `DataHandler.image_matrix` write; transparent pixels are always `(0,0,0,0)`); loader rules (section 2); "File → Load: Pure White as Transparent" (default on).
- [x] P3.2 Display: RGBA pixmap; the canvas (`CustomUiElements.NoScrollGraphicsView.drawBackground`) draws a checkerboard in screen pixels behind the image, so the squares keep their size at every zoom/pixel size (first version as scene item scaled with the zoom). Image item uses `BoundingRectShape`, otherwise transparent pixels would clip overlays.
- [x] P3.3 Downstream white thresholds removed from hatching/parsing/plotting/automatic (widgets hidden, removal from `.ui` in P7); "File → Make Bright Colors Transparent..." (mean RGB > X, default 230 – same rule as the old thresholds) with undo.
- [x] P3.4 Replace all hardcoded white logic (crop background, cut to mask, save mask, split, combine, cleanup, move-mask cutout, new blank = transparent). `split_colors` vectorized, unused `clean_up_clusters` removed.
- [x] P3.5 Quantization (all methods)/k-means/recolour/colour count only on opaque pixels. Filters (sharpness/brightness/contrast/bilateral/Canny) run on RGB with white background and keep the alpha. *shortcut:* white fill instead of inpainting at the edges (same behaviour as before).
- [x] P3.6 Imprint keeps alpha; "Transparent" colour button = eraser for brush/fill/replace (checkerboard preview, `DestinationOut` on imprint).
- [x] P3.7 Save: alpha for PNG/SVG, white background for JPEG/BMP; save-format dialog with the "white as transparent" checkbox removed (plain file dialog).
- [x] P3.8 Old RGB images load as before (white → background); old configs: `white_threshold_parsing` key is ignored. Golden G-code unchanged.

### Phase 4 – Hatching engine  `[x]`

- [x] **4a** `core/hatching.py`: the five per-pixel loops replaced by one vectorized engine (walks for meander/radial, point chains for circle/spiral; colours as label image). Exact port: all goldens byte-identical. Benchmark (6 colours, 0.1 mm step): 800×600 px 1.3–2.6 s → 0.11–0.18 s; 2400×1800 px 11–23 s → 0.7–0.9 s.
- [x] **4b** B30 fixed (`floor(v + 0.5)`). Existing goldens unchanged (their shapes do not touch the image edges); new golden case `full_bleed_*` with colours up to all edges pins the edge behaviour.
- [x] P4.1 Label map once per cluster (`hatching.label_colors`, packed RGB keys; background = −1).
- [x] P4.2 Generic engine: vectorized curve sampling → label lookup → run detection. *Changed:* still one pass per colour (colours can have different hatch distance / random angle); the per-colour pass is vectorized, which removed the cost. One shared pass for equal settings: not needed (see benchmark).
- [x] P4.3 Patterns share `_walk`/`_segments`/`_chains`; the 5 duplicated loops (~500 lines) are gone. CylEquidistX mapping vectorized.
- [x] P4.4 Meander ordering per label (alternating direction) preserved; random numbers drawn in the old order. "Random Seed" field in the hatching settings (0 = random each time, otherwise reproducible RandomMeander/Circular; saved in the hatching config).
- [x] P4.5 Exact pixel-edge intersection for straight lines (meander, crossed, radial; incl. CylEquidistX via the inverse cylinder mapping): `_line_segments` cuts each line at all pixel boundaries. The hatch precision now only sets the tolerance for these lines: segments and gaps shorter than precision/2 (pixel-corner clips) are dropped/bridged. Circles/spirals are still sampled with the precision. Goldens regenerated: burn length +1.4…2.8 % (old sampling lost up to 1.5 steps per segment), endpoints moved by typically half a step (0.05 mm), a few corner fragments fewer. Property test: segments never leave their colour, length matches fine sampling.
- [x] P4.6 Worker gets its settings as a dict collected on the GUI thread; signals only; `QEventLoop` in automatic mode; cancel via progress callback (done in Phase 1, B02/B03).
- [x] P4.7 Benchmark old vs. new (see 4a); outputs byte-identical.

### Phase 5 – Output (post-processing, G-code, plotting)  `[x]`

Measured first (Circular, 2400×1800 px, 780k points): speed/power + copy 0.02 s, Maximize Lines 7.0 s, Constant Drive 11.2 s, G-code text 1.5 s.
- [x] **5a** Post-processing: RDP for Maximize Lines (7.0 → 3.0 s, fewer points), drive modes vectorized (11.2 → 0.24 s).
- [x] **5b** Machine profiles (P5.1). Writer (P5.2) left as is after measuring.
- [x] P5.1 `core/machine.py` `MachineProfile` from JSON: header/footer, laser/power modes, air assist, enclosure fan, burn power format, feedrate, rapid speed, acceleration, over-drive fit, cylinder laser distance. Bundled `machine_profiles/snapmaker_artisan_40w.json` (reproduces the old output byte-identically) is copied to `~/Documents/BildHatcher/machine_profiles`; users add profiles there (Settings → Open Machine Profiles Folder). "Machine" drop-down in the export tab fills the laser/power/air drop-downs; stored in the hatching config and in every process block. *Not done:* profile editor in the UI; mapping of database lasers to profiles.
- [-] P5.2 Streaming/vectorized writer: not needed – 780k lines take 1.5 s.
- [x] P5.3 "Maximize Lines" = Ramer–Douglas–Peucker, tolerance 0.01 mm (*shortcut:* constant `MAXIMIZE_LINES_TOLERANCE`). Golden: 792 → 252 burn moves, same length.
- [x] P5.4 Constant/Over Drive on arrays (corners as the only Python loop). *Changed semantics for interior points:* the old `angle_sum` state was never reset between polylines and only dropped exactly collinear points; now: corners sharper than 10° get lead-out/lead-in, exactly collinear points are dropped, everything else is kept. Goldens (2-point lines) byte-identical.
- [x] P5.5 Speed/power per layer (2b). Deep copy measured at 0.02 s → left as is.
- [x] P5.6 Plotting: one `GLLinePlotItem` per layer, vectorized position/colour arrays (2b).
- [-] P5.7 DB colour matching: called once per colour, cost negligible; ΔE would change results without a request.

### Phase 6 – Image editing tools  `[x]`
- [x] P6.1 Adjustments start from a base image that is reused only while the current image is still the adjuster's own last result (B33); otherwise the current image becomes the base and the unmoved sliders show 0. Slider updates debounced (40 ms). *Changed:* no full parameter pipeline / parameter-based undo (snapshot undo + memory budget is enough).
- [x] P6.2 K-means on the distinct colours weighted by pixel count (same objective as all pixels), random sample above 100k colours; 64 colours on 800×600: 3.0 → 0.1 s, same error. Lab space: not done.
- [x] P6.3 `core/fill.py`: all 7 fill modes as "allowed pixels" + `cv2.connectedComponents`; verified against a reference BFS; 4 Mpx fill < 1 s (old Python BFS: minutes). Contours kept as a bool mask instead of a pixel list.
- [x] P6.4 Masks: outlines follow pixel-size changes (rest of B17, `refresh_mask_outlines`); rectangle/ellipse rasterization vectorized (`_fill_mask_shape`, identical to the old loops); masks are cleared when the image size changes (B17). *Not done:* separate `MaskManager` class / outlines as image-item children – the masks work, the move would only be churn.
- [x] P6.5 Fill/replace overlays are cropped to the bounding box of the filled area (`setOffset`). Imprint stays QPainter-based (works with the cropped items).
- [x] P6.6 Split/combine vectorized (Phase 1/3), `clean_up_clusters` removed (Phase 3); clean-up colours keeps a running maximum instead of an H×W×colours float array (identical result, verified against the old algorithm).
- [x] P6.7 Contour mode "color regions": exact outline of every colour area (`findContours` per colour, inside the active mask); Canny modes kept.
- [x] P6.8 DXF import via `ezdxf.path.make_path` + `flattening(0.01 mm)`: lines, (LW)polylines incl. bulges (were drawn straight), circles, arcs, ellipses, splines; unsupported entities (text, block references) are skipped with a warning if nothing is left.
- [x] P6.9 Undo keeps the newest actions within 512 MB of image snapshots (and max. 50). Changed-region storage: not done.
- [x] P6.10 Upscaler runs in a `QThread` (status messages via queued signal), no side effects (2c). *Open:* verify the 4x-then-resize path with the real engine (not covered by tests).
- [x] P6.11 Checked: grid and center cross live in the scene, so they follow pan/zoom; the cross is redrawn on rescale. Fixed: the grid only covered one viewport size around the origin (missing when zoomed out) – now image + one view size, redrawn on zoom, max. 500 lines per direction.

### Phase 7 – Polish  `[x]`

- [x] Old white-threshold widgets (8) removed from `BildHatcher.ui` and the code that hid them.
- [x] P7.1 Settings: one key → widget table (B19), comboboxes stored by text, old index configs load, hatching config also stores machine profile and random seed. *Not done:* single config file with sections (separate image/hatching files kept).
- [x] P7.2 UI is English (the German texts were in the image load/save code, translated in Phase 3; no German strings left in `.py`/`.ui`).
- [x] P7.3 All `print` → `logging` (with tracebacks in `except` blocks); log file `~/Documents/BildHatcher/bildhatcher.log` (rotating, 1 MB – the built app has no console); `sys.excepthook` shows unhandled exceptions in a message box instead of PyQt aborting the app. *Changed:* existing `try/except` blocks are kept (some catch routine cases like an empty image list), they now log with traceback.
- [x] P7.4 Version 2.0.0; build bundles `machine_profiles/` and now also the seed database `Database/laser_database.db` (was never bundled, the exe always started with an empty database); non-ASCII console output of the build script removed (crashed with redirected output). Built and started `dist/BildHatcher_v2.0.0.exe` (startup ~30 s for the one-file unpacking; creates log file and profile folder).
- [x] P7.5 `README.md`: setup, run, tests/goldens, project structure, user folder, machine profiles, build.

---

### Phase 8 – UI rework & image tools  `[x]`

Requested after Phase 7 (branch is not merged into `main` before this phase is done).

- [x] **P8.1 One config file.** Settings → *Save Config* writes all keys into one `.json`; Today two files (image / hatching settings) for historical reasons; "Load Config" already accepts both. One "Save Config" with all keys; old `_imageconfig` / `_hatchingconfig` files keep loading.
- [x] **P8.2 K-means in a perceptual colour space.** `core/palette.kmeans_quantize`: Quantization (DEFAULT) clusters in CIELAB instead of RGB.
- [x] **P8.3 Pixel-art clean-up (new "Clean Up Colors").** `core/palette.pixel_art_cleanup`, dialog with colours / min. region / edge sensitivity, undo. Found while testing: wide halos (e.g. from bicubic scaling) count as flat areas → only core pixels the palette represents well (ΔE < 2 × threshold) are trusted; all others take their colour from labelled neighbours, growing outwards. 2400×1800 px: 1.5 s (8 colours) – 4 s (3 colours). Replaces the old majority vote. Reduce an image to a few clear, distinct colour areas without the anti-aliasing traces that quantization + smoothing leave at edges:
  1. palette from the *core* pixels only (pixels whose neighbourhood is uniform, so edge blends cannot become palette colours), k-means in CIELAB;
  2. core pixels → nearest palette colour; edge pixels → nearest colour *among the palette colours of the neighbouring core pixels* (a red/blue blend becomes red or blue, never a third colour that happens to be close);
  3. regions smaller than a minimum size are merged into the neighbouring colour they share the longest border with;
  4. transparency is kept (transparent pixels never take part, opaque pixels never become transparent).
  Pure function in `core/`, verified on synthetic anti-aliased images (result has exactly the palette colours, no blend colours, shapes preserved).
- [x] **P8.4 Mask code in its own module**: `Masks.py` (930 lines moved unchanged: drawing, editing, moving, list, save). *Changed:* `MaskTools` is a mixin of `ImageColorer` instead of a separate object – the mask tools share the colorer's one-active-tool toggles, canvas event routing and overlay/imprint system, so a separate object would need many cross-references.
- [x] **P8.5 Global colour database profile.** `ColorProfile.py`: `ColorProfileController` holds `data_handler.color_profile`, remembers it in `USER_DIR/preferences.json` and restores it from the database on startup; recolour, automatic hatching and the DB colour pickers use it (the pickers show the profile's colours directly; without a profile the old database navigator). All user-folder paths now come from `PathManager.USER_DIR` (`BILDHATCHER_USER_DIR` overrides it, tests use a temp folder). One active laser/material profile for the whole app (chosen once in the toolbar, switchable), used by DB recolour, automatic hatching and the DB colour pickers instead of choosing it in every dialog.
- [x] **P8.6 Toolbar ("hotbar").** `MainLayout.build_toolbar`: Load/Save/New | *Image* drop-down (rotate, mirror ×2, crop background, cut to mask, upscale ×2, Make Bright Colors Transparent, white-as-transparent on load) | zoom (%), Reset Zoom, Re-center, Grid + distance (mm) | Color Profile | Machine. File actions, image operations (rotate, mirror, crop background, cut to mask, upscale, *Make Bright Colors Transparent*, keep changes, …), view controls (zoom, re-center, grid, image center), active colour-database profile and machine profile.
- [x] **P8.7 Settings panel on the right.** `MainLayout.build_panel`: vertical strip with rotated short labels (tooltips = full names), groups Image | Text | Hatching | Automate; opened sections stacked in a scroll area, all closed → only the strip; section header closes the section; new sections *Images* (list + list operations) and *Size & Center*; the block under the canvas is gone. Section contents still come from the `.ui`. Closing *Color*/*Masks* switches off their canvas tools (was: tab switch). *Decided 2026-11-16:* no tabs – one strip with all sections grouped by workflow (separators); several sections can be open (content scrolls, strip stays); the image list becomes a panel section; strip buttons with rotated text. No more partially visible sections / scrolling to reach a section toggle: a vertical strip of section toggle buttons on the right edge (always visible); the shown sections are stacked next to it; with all sections hidden the panel collapses to the button strip. The image list / dimensions block under the canvas moves into the panel.
- [x] **P8.8 Update `Data-Architecture.pptx`**: 5 slides – modules (UI / state / core / files), image model & editing, toolpath data model, pipeline with its configuration sources, and the 1.x diagram for comparison. Native PowerPoint shapes (editable), app colours, colour-coded layers.
- [ ] P8.9 Open points from Phase 2–7 that stay open unless requested: machine-profile editor, DB laser ↔ machine-profile link, changed-region undo.

### Phase 9 – Compact UI, hotkeys, tool wheel  `[ ]` (draft, 2026-11-17)

Requested after Phase 8. Order = dependencies (icons first, then panel structure, then the sections, then hotkeys and the wheel).

- [ ] **P9.1 Icon set + helper.** One consistent pictogram set (see Q9.1), `icons.py`: `icon(name)` coloured in the app colours, cached; tooltips carry the former button texts (+ hotkey).
- [ ] **P9.2 Toolbar & menus.** Load / Save / New as the common pictograms; *Image ▾* drop-down removed (its operations move back into the Images section, P9.4); *Load: Pure White as Transparent* only in the Settings menu; *Make Bright Colors Transparent* removed from the File menu (Images section). Zoom / grid / colour profile / machine stay in the toolbar. New: indicator of the active colour tool (needed once tools are switched by hotkeys while the panel is closed, P9.8).
- [ ] **P9.3 Panel navigation, two levels (1.4).** Top level: one button per group (Image, Text, Hatching, Automation) – single select, clicking the active one closes the panel. Below: the toggle buttons of the active group's subsections (multi select). Per group the selection of subsections is remembered (also across restarts, `preferences.json`); only the active group's sections are shown. Layout of the two levels: Q9.2.
- [ ] **P9.4 No fixed width / no stretching (1.3).** Sections keep their natural (compact) size and are left/top aligned; the panel is as wide as the widest *visible* section (no fixed width, nothing stretched). The old section headers with the show/hide function are removed (2.); a small title stays where useful.
- [ ] **P9.5 Section merges.** *Contours/Outlines* into *Hatch* (2.4); *Laser* + *J-Code* → *Automation* (2.5). Groups afterwards: Image (Images, Size & Center, Adjust, Color, Masks) · Text · Hatching (Hatch, Tests, Export) · Automation.
- [ ] **P9.6 Images section (2.1).** Icon-button grid: add, remove, split, combine, **combine monochrome (own button, checkbox removed)**, rotate, mirror H/V, crop background, cut to mask, upscale (AI / keep colours), make bright colours transparent. *Keep Changes*: proposal → remove (Q9.5).
- [ ] **P9.7 Color section (2.2), designed for a narrow vertical panel.** Row of equal-size tool buttons (draw, fill, replace, pick from image) – below them **one fixed-height options area** (stacked pages: pen width / fill mode + its options / …) so switching modes never resizes the UI; colour row (active colour, 3×3 palette + transparent, more colours, DB colour); actions (undo step, imprint, restore); *Recolor from Database* = one button (profile shown in the toolbar only); contouring and clean-up compact.
- [ ] **P9.8 Text section (2.3).** Vertical: properties on top in a compact grid (font, size, B / I / U / S as toggle buttons with the usual symbols, fill / outline colour, outline width, width / height with icon labels), overlay list at the bottom.
- [ ] **P9.9 Remaining sections iconified** (Adjust, Masks, Size & Center, Hatch, Tests, Export, Automation): icons where they are unambiguous, compact grid layouts.
- [ ] **P9.10 Hotkeys (4).** Draw, Fill, Replace, Pick from Image, More Colors (+ proposal: Transparent / eraser colour, Undo/Redo stay Ctrl+Z/Y): application-wide, independent of whether the panel/section is visible, same effect as the button; ignored while a text/number field has the keyboard focus (otherwise typing a text overlay would switch tools). Keys: Q9.4. Colour tools no longer switch off when the Color section is closed (Phase 8 behaviour) – the toolbar indicator shows the active tool instead.
- [ ] **P9.11 Tool wheel for touch mode (5).** Holding the pen button over the canvas opens a radial menu with the hotkey tools around the pen position; hovering highlights, releasing selects, releasing in the centre cancels. Trigger: see Q9.6.
- [ ] **P9.12 Tests, screenshots, docs** (README, architecture slide 1).

**Open questions**
- Q9.1 Icon source.
- Q9.2 Layout of the two navigation levels.
- Q9.3 Where the compact section layouts live: `.ui` (Designer) or code.
- Q9.4 Hotkey keys.
- Q9.5 *Keep Changes* – it sets the current image as new restore point for *Restore Original Colors* (and resets the hatch centre); with undo this is mostly redundant → remove?
- Q9.6 Wheel trigger: Windows reports the pen's barrel button as a right mouse button – use that (also lets mouse users hold the right button)? Needs a test on the real device.

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
| 2026-11-15 | `core/` lives at the repo root next to the UI modules (no extra `bildhatcher/` wrapper package); UI modules move into `ui/` only if it pays off later. |
| 2026-11-15 | Toolpath move codes: `MOVE_TRAVEL`=0, `MOVE_BURN`=1, `MOVE_RAPID`=2 (lead-in travel at the fixed rapid speed of the drive post-processing). Speed/power are per layer. |
| 2026-11-15 | `DataHandler` stays the application state object (no separate `AppState`); it exposes the active `ImageDocument` through properties. Callback lists / `ObservableList` are kept. |
| 2026-11-15 | Phase 3: transparent pixels are stored as `(0,0,0,0)` and `normalize()` is the single choke point (any RGB result becomes opaque RGBA). The transparent colour is an eraser; erasing overlays are drawn as a checkerboard and imprinted with `DestinationOut`. |
| 2026-11-15 | Machine profiles are plain JSON files (bundled default + user folder), no editor yet. The user folder can be overridden with `BILDHATCHER_PROFILE_DIR` (tests). |
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
| 2026-11-15 | 2a | Output stage moved into Qt-free `core/` (`gcode.py`, `postprocess.py`); functions moved by script (unchanged code), goldens identical. |
| 2026-11-15 | 2b | Array toolpath model, `Point` removed from all modules; per-point Python objects gone from hatch output, post-processing, G-code and plotting. 24 tests, goldens unchanged. Hatch sampling loops themselves are still Python (Phase 4). |
| 2026-11-15 | 2c, P2.7 | Image state has one owner (`ImageDocument` in the image list); 11 `get_handler_data` sync calls and several full-image copies per action removed. New `tests/test_image_state.py` (switching keeps edits, upscale leaves source untouched, undo after removing an image, undo rotation). 28 tests. |
| 2026-11-15 | 2d, B28 | One-pixel y offset of all image-based hatching fixed; goldens regenerated and verified move-by-move (pure +0.1 mm Y shift where the sampling is unchanged). Phase 2 complete, 29 tests. |
| 2026-11-15 | Phase 3 | Transparency as background end to end (load/save/display/edit/hatch/export/plot); white thresholds replaced by "Make Bright Colors Transparent"; B29 found and fixed. `tests/test_transparency.py`, 37 tests, goldens unchanged. Not covered by tests: brush eraser strokes, move-mask cutout, AI upscale path. |
| 2026-11-15 | P3.2 | Feedback: checkerboard squares changed size with zoom (texture in image coordinates). Now drawn by the canvas in screen pixels (constant 8 px squares). |
| 2026-11-15 | 4a | Vectorized hatching engine in `core/hatching.py`, goldens byte-identical, 13–33× faster on 2400×1800 px. First version was only 3–6× faster: `np.unique(axis=0)` for the colour labels took 3.2 s, replaced by packed 1-D keys. Suspected endless loop for very wide CylEquidistX clusters checked against the old code: does not occur. |
| 2026-11-15 | 4b, B30 | Edge rounding fixed; full-bleed golden cases added (fail with the old rounding). 42 tests. |
| 2026-11-15 | P4.4 | Random seed setting (own `random.Random` instance, does not touch the global random state). |
| 2026-11-15 | P4.5 | Exact edges for straight hatch lines; meander/radial goldens regenerated (other goldens unchanged), geometric property test added. Speed unchanged (2400×1800 px: 0.8–1.0 s). 44 tests. |
| 2026-11-15 | 5a | RDP + vectorized drive modes; `tests/test_postprocess.py`. 47 tests. |
| 2026-11-15 | 5b | Machine profiles; `tests/test_machine.py` (old header/footer reproduced, second profile changes commands/options). 50 tests. |
| 2026-11-15 | P6.2, P6.3, B32 | Vectorized flood fill (`tests/test_fill.py`), weighted k-means. 54 tests. |
| 2026-11-15 | B17 (rest), P6.11 | Mask outlines follow pixel-size changes; grid covers the visible area. 55 tests. |
| 2026-11-15 | P6.9, P6.10, B22 | Undo memory budget; upscaling in a worker thread. 57 tests. |
| 2026-11-15 | P6.1, B33 | Correct adjustment base, debounced sliders. 59 tests. |
| 2026-11-15 | P6.8 | DXF via ezdxf paths. 59 tests. |
| 2026-11-15 | P6.4–P6.7 | Cropped overlays, memory-light clean-up, colour-region contours, vectorized mask shapes. Phase 6 complete, 63 tests. |
| 2026-11-15 | P7.2, P7.3 | Logging everywhere, log file, error dialog for unhandled exceptions. 64 tests. |
| 2026-11-15 | P7 | Hidden threshold widgets removed from the `.ui`. |
| 2026-11-15 | P7.4, P7.5 | Version 2.0.0, build checked (exe starts), README. All phases done. |
| 2026-11-16 | Phase 8 | New phase planned (UI rework, pixel-art clean-up, global colour profile, single config, Lab k-means, mask module, architecture slides). |
| 2026-11-16 | P8.1 | Single config file. |
| 2026-11-16 | P8.2, P8.3 | CIELAB k-means, pixel-art clean-up (`tests/test_palette.py`: exact palette, no blend colours, no islands, fewer wrong pixels than plain k-means). `LOKY_MAX_CPU_COUNT` set to skip a 2 s core-detection subprocess of joblib. 69 tests. |
| 2026-11-16 | P8.4 | Mask code in `Masks.py`; dead variables removed. 69 tests. |
| 2026-11-16 | P8.5 | Global colour profile, central user folder. `tests/test_color_profile.py`, 71 tests. |
| 2026-11-16 | P8.6, P8.7 | Toolbar and settings panel (`MainLayout.py`, `tests/test_layout.py`); checked via real-platform screenshots. Open: panel width = minimum width of the widest section (three-column Designer layouts). 73 tests. |
| 2026-11-16 | P8.8 | Architecture slides rebuilt (checked via PowerPoint rendering). Phase 8 done except optional P8.9. |
| 2026-11-17 | Phase 9 | Draft plan (compact UI with pictograms, two-level panel, section reworks, hotkeys, tool wheel); open questions Q9.1–Q9.6. |
