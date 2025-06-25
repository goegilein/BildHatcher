import sys
from PyQt6 import QtWidgets, uic, QtCore
from PyQt6.QtCore import QLocale
import ImageControlling
import ImageEditing
import NCDataGeneration
import Plotting
import Parsing
import TestStructures
import DataHandling
import ImageEditing
import Settings
import AutomatedProcessing


if __name__ == "__main__":

    #load the GUI
    app = QtWidgets.QApplication(sys.argv)

    # Set the locale to use a dot as the decimal separator
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    gui = uic.loadUi("BildHatcher.ui")
    
    #create the image canvas. has do be done programmatically as there is no QtDesigner element for it
    gui.image_scene = QtWidgets.QGraphicsScene()
    gui.image_canvas.setScene(gui.image_scene)
    gui.image_item = QtWidgets.QGraphicsPixmapItem()
    gui.image_scene.addItem(gui.image_item)
    
    
    gui.show()
        
    data_handler= DataHandling.DataHandler(gui)
    image_controller = ImageControlling.BaseFunctions(data_handler, gui)
    image_sizer = ImageControlling.ImageSizer(data_handler, gui)
    image_adjuster = ImageEditing.ImageAdjuster(data_handler, gui)
    immage_colorer = ImageEditing.ImageColorer(data_handler, gui)
    image_hatcher = NCDataGeneration.Hatcher(data_handler, gui)
    hatch_line_plotter = Plotting.HatchLinePlotter(data_handler, gui)
    test_structure = TestStructures.Teststructures(data_handler, gui)
    parser = Parsing.Parser(data_handler,gui)
    settings = Settings.Settings(gui)
    autmated_processor = AutomatedProcessing.AutomatedProcessor(data_handler, image_hatcher, parser, gui)
    sys.exit(app.exec())