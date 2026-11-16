import sys
import json
import logging
import logging.handlers
from pathlib import Path
from types import SimpleNamespace
from PyQt6 import QtWidgets, uic
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QGraphicsItem
import ImageControlling
import ImageEditing
import NCDataGeneration
import Plotting
import Parsing
import TestStructures
import DataHandling
import Settings
import ColorProfile
import AutomatedProcessing
import EventHandling
import TextandGeometries
from PathManager import get_gui_file_path, get_base_dir, USER_DIR
import CustomUiElements  # noqa: F401  # this import is necessary to register custom ui elements for compilation

log = logging.getLogger(__name__)

# Define paths using PathManager
MAIN_GUI_PATH = get_gui_file_path("BildHatcher.ui")


LOG_FILE = USER_DIR / "bildhatcher.log"


def setup_logging(level=logging.INFO):
    """Console + rotating log file (the built app has no console)."""
    handlers = [logging.StreamHandler()]
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def show_unhandled_exception(exc_type, exc, tb):
    """sys.excepthook: log and show the error instead of letting PyQt abort the application."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    if QtWidgets.QApplication.instance() is not None:
        QtWidgets.QMessageBox.critical(
            None, "Unexpected Error",
            f"{exc_type.__name__}: {exc}\n\nThe action was not completed. Details are in the log file:\n{LOG_FILE}")


def load_version():
    """Read version.json (works for source and PyInstaller builds)."""
    version_file = get_base_dir() / "version.json"
    try:
        with open(version_file) as f:
            data = json.load(f)
        return f"{data['major']}.{data['minor']}.{data['patch']}"
    except Exception as e:
        log.warning("Could not read %s: %s", version_file, e)
        return "unknown"


def create_main_window():
    """Load the main window from the .ui file and set up the image canvas."""
    gui = uic.loadUi(MAIN_GUI_PATH)

    # create the image canvas. has to be done programmatically as there is no QtDesigner element for it
    gui.image_scene = QtWidgets.QGraphicsScene()
    gui.image_canvas.setScene(gui.image_scene)
    gui.image_item = QtWidgets.QGraphicsPixmapItem()
    gui.image_scene.addItem(gui.image_item)

    # Pixel art look: no antialiasing, no smooth pixmap transform (sharp pixels when zoomed in)
    gui.image_canvas.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    gui.image_canvas.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

    # cut all children (overlay drawings) of the image item at its edges. The shape must be the full rectangle,
    # otherwise transparent pixels would clip away overlays and the checkerboard drawn on them.
    gui.image_item.setShapeMode(QtWidgets.QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
    gui.image_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
    gui.image_canvas.checkerboard_item = gui.image_item  # checkerboard behind transparent pixels
    return gui


def create_components(gui):
    """Wire up all controllers on an already created main window. Returns them as a namespace."""
    c = SimpleNamespace()
    c.data_handler = DataHandling.DataHandler(gui)
    c.color_profiles = ColorProfile.ColorProfileController(c.data_handler, gui)  # P8.5: one active DB profile
    c.data_handler.color_profiles = c.color_profiles
    c.event_handler = EventHandling.EventHandler(gui)
    c.image_controller = ImageControlling.BaseFunctions(c.data_handler, gui)
    c.image_sizer = ImageControlling.ImageMover(c.data_handler, c.event_handler, gui)
    c.image_adjuster = ImageEditing.ImageAdjuster(c.data_handler, gui)
    c.image_colorer = ImageEditing.ImageColorer(c.data_handler, c.event_handler, gui)
    c.overlay_store = TextandGeometries.OverlayStore(gui.image_item)
    c.overlay_manager = TextandGeometries.TextGeometryOverlayManager(c.data_handler, c.overlay_store, gui, c.event_handler)

    # Setup Undo / Redo direct QActions on menubar and keyboard shortcuts (Ctrl+Z, Ctrl+Y)
    menubar = getattr(gui, "menubar", None) or gui.menuBar()
    if menubar and hasattr(c.data_handler, "undo_manager"):
        c.data_handler.undo_manager.setup_menubar(menubar)

    c.image_hatcher = NCDataGeneration.Hatcher(c.data_handler, gui)
    c.hatch_line_plotter = Plotting.HatchLinePlotter(c.data_handler, gui)
    c.test_structure = TestStructures.Teststructures(c.data_handler, gui)
    c.parser = Parsing.Parser(c.data_handler, gui)
    c.settings = Settings.Settings(gui)
    c.automated_processor = AutomatedProcessing.AutomatedProcessor(c.data_handler, c.image_hatcher, c.parser, gui)
    return c


def main():
    setup_logging()
    sys.excepthook = show_unhandled_exception
    app = QtWidgets.QApplication(sys.argv)

    gui = create_main_window()
    gui.setWindowTitle(f"BildHatcher - v{load_version()}")

    def close_confirm(event):
        reply = QtWidgets.QMessageBox.question(
            gui,
            "Close BildHatcher",
            "Are you sure you want to close the application?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    gui.closeEvent = close_confirm
    gui.show()

    components = create_components(gui)  # noqa: F841  # keep references alive for the app lifetime
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
