"""
Shared test fixtures.

The characterization tests drive the real application wiring (main.create_components) on an
offscreen Qt platform, so they capture the behaviour of the current code as golden files.
"""
import os
import sys
from pathlib import Path

import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BILDHATCHER_USER_DIR", tempfile.mkdtemp(prefix="bildhatcher_user_"))  # keep tests out of ~/Documents

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
    import MainLayout
    components.panel_buttons = MainLayout.build(gui, components)
    components.gui = gui
    yield components
    gui.deleteLater()
    qapp.processEvents()
