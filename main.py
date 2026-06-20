import sys
import json
from pathlib import Path
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import QLocale
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor, 
                         QPainterPath, QBrush)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem
import ImageControlling
import ImageEditing
import NCDataGeneration
import Plotting
import Parsing
import TestStructures
import DataHandling
import Settings
import AutomatedProcessing
import EventHandling
import TextandGeometries
from PathManager import get_gui_file_path, get_settings_path
import CustomUiElements #this import is necessary to register custom ui elements for compilation

# Load version - handle both frozen and non-frozen environments
if getattr(sys, 'frozen', False):
    # Running as compiled executable from PyInstaller
    BASE_DIR = Path(sys._MEIPASS)
else:
    # Running as normal Python script
    BASE_DIR = Path(__file__).resolve().parent

with open(BASE_DIR / "version.json") as f:
    version_data = json.load(f)
    VERSION = f"{version_data['major']}.{version_data['minor']}.{version_data['patch']}"


#Define paths using PathManager
MAIN_GUI_PATH = get_gui_file_path("BildHatcher.ui")

if __name__ == "__main__":

    #load the GUI
    app = QtWidgets.QApplication(sys.argv)

    gui = uic.loadUi(MAIN_GUI_PATH)
    
    #create the image canvas. has to be done programmatically as there is no QtDesigner element for it
    gui.image_scene = QtWidgets.QGraphicsScene()
    gui.image_canvas.setScene(gui.image_scene)
    gui.image_item = QtWidgets.QGraphicsPixmapItem()
    gui.image_scene.addItem(gui.image_item)

    # --- CRITICAL FOR PIXEL ART LOOK ---
    # 1. Disable Antialiasing (No smooth edges)
    # 2. Disable SmoothPixmapTransform (Show pixels as sharp blocks when zoomed in)
    gui.image_canvas.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    gui.image_canvas.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

    # cut all children (overlay drawings) of the image item at its edges.
    gui.image_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
    
    # Set window title with version
    gui.setWindowTitle(f"BildHatcher - v{VERSION}")
    
    gui.show()
        
    data_handler= DataHandling.DataHandler(gui)
    event_handler = EventHandling.EventHandler(gui)
    image_controller = ImageControlling.BaseFunctions(data_handler, gui)
    image_sizer = ImageControlling.ImageMover(data_handler, event_handler, gui)
    image_adjuster = ImageEditing.ImageAdjuster(data_handler, gui)
    image_colorer = ImageEditing.ImageColorer(data_handler, event_handler, gui)
    overlay_store = TextandGeometries.OverlayStore(gui.image_item)
    overlay_manager = TextandGeometries.TextGeometryOverlayManager(data_handler, overlay_store, gui, event_handler)

    image_hatcher = NCDataGeneration.Hatcher(data_handler, gui)
    hatch_line_plotter = Plotting.HatchLinePlotter(data_handler, gui)
    test_structure = TestStructures.Teststructures(data_handler, gui)
    parser = Parsing.Parser(data_handler,gui)
    settings = Settings.Settings(gui)
    autmated_processor = AutomatedProcessing.AutomatedProcessor(data_handler, image_hatcher, parser, gui)
    sys.exit(app.exec())