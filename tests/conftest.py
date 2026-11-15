"""
Shared test fixtures.

The characterization tests drive the real application wiring (main.create_components) on an
offscreen Qt platform, so they capture the behaviour of the current code as golden files.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PyQt6 import QtWidgets  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def app_components(qapp):
    """A freshly wired main window with all controllers (not shown)."""
    import main

    gui = main.create_main_window()
    components = main.create_components(gui)
    components.gui = gui
    yield components
    # Detach the global event filters before Qt deletes the widgets, otherwise the
    # EventHandler callbacks fire on already deleted C++ objects during teardown.
    gui.removeEventFilter(components.event_handler)
    gui.image_canvas.viewport().removeEventFilter(components.event_handler)
    gui.deleteLater()
    qapp.processEvents()
