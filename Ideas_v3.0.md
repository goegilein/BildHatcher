# Ideas for v3.0 – BildHatcher as a module of a larger laser suite

Status: **loose ideas, nothing decided.** A Qt-based machine control application already exists. It gets
reworked first; only then are both brought together and this document is worked out in detail.

## Goal

BildHatcher keeps working on its own, but can also be plugged into a host application as one module next to
others – in particular a module for direct machine control (connect, stream G-code, status, pause, emergency stop).

## Stack

- **Python + Qt, but PySide6 instead of PyQt6.**
  - Python stays the right language for the core: image processing and geometry (NumPy, OpenCV, Shapely,
    scikit-image). Hot paths could move to Rust (PyO3) one at a time if ever needed – no rewrite.
  - PySide6 is the official Qt for Python under the LGPL; PyQt6 is GPL or commercial. This matters as soon as
    the suite is sold.
  - Switching is mostly mechanical: imports, `uic.loadUi` → `QUiLoader` / `pyside6-uic`. The .ui file, the
    Atelier stylesheet and `theme.py` stay as they are.

### Not chosen (for now)

- Web UI (TypeScript + Tauri / Electron): closest to the web shop's look, but pixel editing of large images and
  the bridge to Python / Rust are costly. Only worth it if the suite has to run in a browser.
- C++ / Qt: fastest, but much slower to develop for a small team.
- C# (WPF / Avalonia): solid, but loses the Python image-processing ecosystem; WPF is Windows-only.

## Architecture sketch

1. **Core without Qt** (`bildhatcher-core`, an installable package): image document, hatching, post-processing,
   tool paths, G-code. `core/` is the start of it. It hands out tool-path objects; G-code text is only produced
   by the exporter or the machine control.
2. **BildHatcher UI as a plugin:** a Qt widget with a small interface (open a document, get the tool path,
   signal "tool path ready"). The host finds modules via Python entry points and docks them as tabs / docks.
3. **Shared services in the host:** theme (Atelier, dark / bright – already built to be portable), undo,
   preferences, machine profiles, logging.
4. **Machine control in its own process** (asyncio; serial via pyserial or network): G-code streaming with
   acknowledgements, status, pause / resume, emergency stop – behind a message interface (Qt signals over IPC,
   or ZeroMQ / WebSocket). Reason: safety. If the UI hangs while hatching a large image, the machine must still
   stop in a controlled way. Machine control never runs in the UI thread.

## Possible steps (after the machine control rework)

1. Move to PySide6.
2. Make `core/` a standalone package with its own tests (the golden G-code tests move along).
3. Define the plugin interface and the tool-path exchange format.
4. Fit the reworked machine control in as a separate process next to it.

## Open questions

- Which parts of the existing machine control fit this picture, and what does its rework change?
- Tool-path exchange format between the modules (objects in-process, a serialized format between processes?).
- One shared document / project file for the whole suite, or one per module?
- Who owns the machine profiles – the host or the machine control?
