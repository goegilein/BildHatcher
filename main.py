import sys
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
import CustomUiElements #this import is necessary to register custom ui elements for compilation


if __name__ == "__main__":

    #load the GUI
    app = QtWidgets.QApplication(sys.argv)

    # Set the locale to use a dot as the decimal separator
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    def resource_path(relative: str) -> Path:
        # When frozen, data files are in sys._MEIPASS
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS) / relative
        # When running from source
        return Path(__file__).resolve().parent / relative

    ui_path = resource_path("BildHatcher.ui")
    gui = uic.loadUi(ui_path)
    
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
    
    # gui.image_canvas.fitInView(gui.image_scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    # View navigation settings
    # self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
    # self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    # self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    # self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
    
    
    gui.show()
        
    data_handler= DataHandling.DataHandler(gui)
    event_handler = EventHandling.EventHandler(gui)
    image_controller = ImageControlling.BaseFunctions(data_handler, gui)
    image_sizer = ImageControlling.ImageMover(data_handler, event_handler, gui)
    image_adjuster = ImageEditing.ImageAdjuster(data_handler, gui)
    image_colorer = ImageEditing.ImageColorer(data_handler, event_handler, gui)
    image_hatcher = NCDataGeneration.Hatcher(data_handler, gui)
    hatch_line_plotter = Plotting.HatchLinePlotter(data_handler, gui)
    test_structure = TestStructures.Teststructures(data_handler, gui)
    parser = Parsing.Parser(data_handler,gui)
    settings = Settings.Settings(gui)
    autmated_processor = AutomatedProcessing.AutomatedProcessor(data_handler, image_hatcher, parser, gui)
    sys.exit(app.exec())