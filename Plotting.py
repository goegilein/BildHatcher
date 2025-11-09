from PyQt6 import QtWidgets, QtGui, QtCore
from pyqtgraph.opengl import GLViewWidget,GLLinePlotItem
import numpy as np
from HelperClasses import HatchData
from OpenGL.GL import glDisable, GL_LIGHTING, glClearColor,glEnable, glBlendFunc, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA


class HatchLinePlotter:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.pixel_per_mm = None
        self.image_matrix = None
        self.hatch_data = HatchData(None, None)
        self.plot_line_items=[]

        # Initialize GUI elements from the preloaded PyQt6 GUI
        self.plot_canvas = gui.plot_canvas  # QGraphicsView for the plot
        self.color_mode_plotting_combobox = gui.color_mode_plotting_combobox  # QComboBox for color mode
        self.white_threshold_plotting_spinbox = gui.white_threshold_plotting_spinbox  # QSpinBox for white threshold
        self.plot_button = gui.plot_hatch_button  # QPushButton for plotting active hatchlines
        self.plot_process_blocks_button = gui.plot_process_blocks_button # QPushButton for plotting active hatchblocks
        self.plot_linedwidth_spinbox = gui.plot_linewidth_spinbox  # QSpinBox for line width
        self.plot_linewidth_label = gui.plot_linewidth_label  # QLabel for line width
        self.plot_background_color_label = gui.plot_background_color_label  # QLabel for background color
        self.plot_background_color_button = gui.plot_background_color_button  # QPushButton for background color
        self.plot_background_color_edit = gui.plot_background_color_edit  # QLineEdit for background color

        # Initialize combobox values
        self.color_mode_plotting_combobox.addItems(["Color", "Black"])

        # Set default values for spinboxes
        self.white_threshold_plotting_spinbox.setRange(0, 255)
        self.white_threshold_plotting_spinbox.setValue(255)

        # Connect signals to methods
        self.plot_button.clicked.connect(self.plot_hatch_lines)
        self.plot_process_blocks_button.clicked.connect(self.plot_hatch_blocks)
        self.plot_linedwidth_spinbox.editingFinished.connect(self.redraw_plot)
        self.color_mode_plotting_combobox.currentIndexChanged.connect(self.plot_hatch_lines)
        self.plot_background_color_button.clicked.connect(lambda: self.choose_background_color(None))

        # Set up the PyQtGraph GLViewWidget for 3D plotting
        self.view = GLViewWidget()
        self.view.setBackgroundColor((255, 255, 255, 0))  # Set the background color to white
        self.choose_background_color(QtGui.QColor(255, 255, 255))  # Set the initial background color to white
        self.view.opts['distance'] = 50  # Set the initial distance of the camera
        self.view.setCameraPosition(elevation=90, azimuth=-90)
        self.plot_canvas.layout().addWidget(self.view)  # Add the GLViewWidget to the layout
        
        # Initialize OpenGL settings
        self.initializeGL()

    def add_data_to_plot_items(self, data):
        # Iterate over each hatch line
        for hatch_lines in data:
            # Calculate the total number of points, including NaN break points
            total_points = sum(len(polyline) + 1 for polyline in hatch_lines) - 1  # Add 1 NaN per polyline, except the last

            # Preallocate numpy arrays for positions and colors
            pos = np.zeros((total_points, 3), dtype=np.float32)  # Shape (N, 3)
            colors = np.zeros((total_points, 4), dtype=np.float32)  # Shape (N, 4)

            # Fill the numpy arrays
            index = 0
            for polyline in hatch_lines:
                for point in polyline:
                    # Fill position array
                    if (point.r+point.g+point.b)/3 > self.white_threshold_plotting_spinbox.value():
                        pos[index] = [np.nan, np.nan, np.nan]
                    else:
                        pos[index] = [point.x, point.y, point.z]

                    # Fill color array
                    if self.color_mode_plotting_combobox.currentText() == "Black":
                        colors[index] = [0, 0, 0, 1.0]
                    else:
                        colors[index] = [point.r / 255, point.g / 255, point.b / 255, 1.0]  # RGB values normalized to [0, 1]
                    
                    index += 1

                # Add a NaN break point to disconnect the line
                if index < total_points:  # Avoid adding NaN after the last polyline
                    pos[index] = [np.nan, np.nan, np.nan]
                    colors[index] = [0, 0, 0, 0]  # Invisible color
                    index += 1

            # Create a line item for the current hatch line and add it to the view
            line_item = GLLinePlotItem(pos=pos, color=colors, width=self.plot_linedwidth_spinbox.value(), mode='line_strip')
            self.plot_line_items.append(line_item)

    def plot_data(self):
        self.view.clear()
        for line_item in self.plot_line_items:
            line_item.setGLOptions("opaque")
            self.view.addItem(line_item)

    def plot_hatch_lines(self):
        """
        Example method implementing PyQtGraph to visualize the hatch data in a separate PyQt window.
        """
        # First, make sure to get handler data
        self.get_handler_data()

        if not self.hatch_data.hatch_clusters:
            return
        
        # Clear the existing plot and the plot items
        self.view.clear()
        self.plot_line_items=[]

        for hatch_cluster in self.hatch_data.hatch_clusters:
            self.add_data_to_plot_items(hatch_cluster.data)
        self.plot_data()
            
        
    def plot_hatch_blocks(self):
        process_listWidget = self.gui.process_listWidget
        selected_items = process_listWidget.selectedItems()
        if not selected_items:
            return  # No item selected

        # Clear the existing plot and the plot items
        self.view.clear()
        self.plot_line_items=[]

        for list_item in selected_items:
                process_block = list_item.data(QtCore.Qt.ItemDataRole.UserRole)  # Retrieve the stored ProcessBlock object
                self.add_data_to_plot_items(process_block.data)
        self.plot_data()

    

    def redraw_plot(self):
        """
        Redraw the plot with the current settings.
        """
        self.view.clear()
        for item in self.plot_line_items:
            item.width = self.plot_linedwidth_spinbox.value()
            item.mode = 'line_strip'
            item.setGLOptions("opaque")
            self.view.addItem(item)

    def initializeGL(self):
        """
        Enable blending and disable lighting for consistent line colors.
        """
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_BLEND)  # Enable blending
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)  # Set blending function
        glDisable(GL_LIGHTING)  # Disable lighting effects

    def choose_background_color(self,color=None):
        """
        Open a QColorDialog to choose the background color for the plot.
        """
        if color is None:
            color = QtWidgets.QColorDialog.getColor()

        if color.isValid():
            self.view.setBackgroundColor(color.getRgb())
            opposite_color = QtGui.QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())
            color_string = f"R{color.red()}, G{color.green()}, B{color.blue()}"
            self.plot_background_color_edit.setText(color_string)
            self.plot_background_color_edit.setStyleSheet(f"color: {opposite_color.name()}; background-color: {color.name()}")

    def get_handler_data(self):
        self.pixel_per_mm = self.data_handler.pixel_per_mm
        self.image_matrix = self.data_handler.image_matrix
        self.hatch_data = self.data_handler.hatch_data