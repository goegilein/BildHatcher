from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import QRectF
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
from sklearn.cluster import KMeans
import numpy as np
import collections
from Database.database_main import DatabaseNavigatorWidget,NavigatorMode
from HelperClasses import DBColorPalette
import random

class ImageAdjuster:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.image_matrix_base = None
        self.image_matrix_original = None
        self.image_current = None
        self.inverted_colors = False
        self.last_adjustment = "None"
        self.sharpness_old = 0
        self.brightness_old = 0
        self.contrast_old = 0
        self.masked_pixels_list = []
        self.dont_update = False 

        # Color control variable and entry field
        self.color_count_label = gui.color_count_label
        self.color_count_spinbox = gui.color_count_spinbox
        self.color_count_spinbox.setValue(256)
        self.color_count_spinbox.editingFinished.connect(self.quantize_image_color)

        # Color quantization method
        self.quantize_method_label = gui.quantize_method_label
        self.quantize_method_combobox = gui.quantize_method_combobox
        self.quantize_method_combobox.addItems(["DEFAULT", "MAXCOVERAGE", "FASTOCTREE", "MEDIANCUT", "GRAYSCALE"])
        self.quantize_method_combobox.setCurrentText("DEFAULT")
        self.quantize_method_combobox.currentTextChanged.connect(self.quantize_image_color)

        # Invert color button
        self.invert_color_button = gui.invert_color_button
        self.invert_color_button.clicked.connect(self.invert_colors)

        # Restore color button
        self.restore_original_color_button = gui.restore_original_color_button
        self.restore_original_color_button.clicked.connect(self.restore_original_color)

        # Sharpening/Blurring Slider
        self.sharpness_label = gui.sharpness_label
        self.sharpness_slider = gui.sharpness_slider
        self.sharpness_slider.setRange(-10, 10)
        self.sharpness_slider.setValue(0)
        self.sharpness_slider.valueChanged.connect(self.update_bright_cont_sharp)

        # Brightness Slider
        self.brightness_label = gui.brightness_label
        self.brightness_slider = gui.brightness_slider
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self.update_bright_cont_sharp)

        # Contrast Slider
        self.contrast_label = gui.contrast_label
        self.contrast_slider = gui.contrast_slider
        self.contrast_slider.setRange(-100, 100)
        self.contrast_slider.setValue(0)
        self.contrast_slider.valueChanged.connect(self.update_bright_cont_sharp)

        #simplyfying image button
        self.convolute_image_button = gui.convolute_image_button
        self.median_blur_spinbox = gui.median_blur_spinbox
        self.sigma_color_spinbox = gui.sigma_color_spinbox
        self.sigma_space_spinbox = gui.sigma_space_spinbox
        self.convolute_image_button.clicked.connect(lambda: self.convolute_image(
                                                                median_blur=self.median_blur_spinbox.value(),
                                                                sigma_color=self.sigma_color_spinbox.value(),
                                                                sigma_space=self.sigma_space_spinbox.value()))
        
        # Add a callback to reste all adjuments when a  new image is loaded
        #self.data_handler.add_image_changed_callback(self.restore_original_color) #depreciated, now tracking correctly in main image controller

    ## METHODS

    def update_current_image(self, *args):
        self.get_handler_data()
        if self.image_matrix_base is None:
            return
        try:
            # Ensure the color count is a valid integer
            num_colors = self.color_count_spinbox.value()
            if num_colors > 256:
                self.color_count_spinbox.setValue(256)
            if num_colors <= 0:
                return  # Invalid number of colors; do not proceed
        except ValueError:
            return  # Non-integer input; do not proceed
        
        # Always start with original image and do masking first
        self.image_current = Image.fromarray(self.image_matrix_base.copy())

        # Apply adjustments first
        self.image_current = self.update_bright_cont_sharp()

        # Apply image quantization
        self.image_current = self.quantize_image_color()

        # Invert image colors if active
        if self.inverted_colors:
            self.image_current = Image.eval(self.image_current, lambda x: 255 - x)
        
        # Update image data in handler
        self.set_handler_data(np.array(self.image_current))

    def update_bright_cont_sharp(self):
        """Apply sharpening and brightness adjustments based on slider values."""

        if self.dont_update:
            return

        #only get new image if last adjustment was not brightness
        if self.last_adjustment == "brightness":
            pass
        else:
            self.get_handler_data()
        if self.image_matrix_base is None:
            return
        else:
            image = Image.fromarray(self.image_matrix_base.copy())
        
        try:
            # Apply sharpening/blurring
            sharpness_value = self.sharpness_slider.value()
            enhancer_sharpness = ImageEnhance.Sharpness(image)
            sharpness_factor = 1 + (sharpness_value / 10)
            image = enhancer_sharpness.enhance(sharpness_factor)
            self.sharpness_old = sharpness_value

            # Apply brightness adjustment
            brightness_value = self.brightness_slider.value()
            enhancer_brightness = ImageEnhance.Brightness(image)
            brightness_factor = 1 + (brightness_value / 100)
            image = enhancer_brightness.enhance(brightness_factor)
            self.brightness_old = brightness_value

            # Contrast Adjustment
            contrast_value = self.contrast_slider.value()
            contrast_factor = 1 + (contrast_value / 100)
            enhancer_contrast = ImageEnhance.Contrast(image)
            image = enhancer_contrast.enhance(contrast_factor)
            self.contrast_old = contrast_value

            # Update the last adjustment type and return
            self.last_adjustment = "brightness"
            self.set_handler_data(np.array(image))

        except Exception as e:
            print(f"Error applying adjustments: {e}")

    def quantize_image_color(self):

        if self.dont_update:
            return
        
        #only get new image if last adjustment was not brightness
        try:
            # Ensure the color count is a valid integer
            num_colors = self.color_count_spinbox.value()
            if num_colors > 256:
                self.color_count_spinbox.setValue(256)
            if num_colors <= 0:
                return  # Invalid number of colors; do not proceed
        except ValueError:
            return  # Non-integer input; do not proceed
        
        if self.last_adjustment == "quantize":
            pass
        else:
            self.get_handler_data()
        if self.image_matrix_base is None:
            return
        else:
            image = Image.fromarray(self.image_matrix_base.copy())
        
        try:
            num_colors = self.color_count_spinbox.value()
            quantize_method = self.quantize_method_combobox.currentText()
            if quantize_method == "DEFAULT":
                image_matrix = np.array(image)
                # Flatten the image into a list of pixels
                pixels = image_matrix.reshape((-1, 3))
                 # Cluster pixels into dominant colors
                kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init='auto')
                kmeans.fit(pixels)
                new_colors = kmeans.cluster_centers_.astype("uint8")
                labels = kmeans.labels_

                # Recreate the image using the new colors
                simplified_image = new_colors[labels].reshape(image_matrix.shape)
                image = Image.fromarray(simplified_image)

            elif quantize_method == "GRAYSCALE":
                image = image.convert('L')  # Convert to grayscale
                image = image.quantize(colors=num_colors)  # Quantize to incremental grayscale values
                image = image.convert('RGB')  # Convert back to RGB for display

            else:
                quantize_method = getattr(Image, quantize_method)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                image = image.quantize(colors=num_colors, method=quantize_method)
                image = image.convert('RGB')  # Convert back to RGB for display

            # Update the last adjustment type and return the quantized image
            self.last_adjustment = "quantize"
            self.set_handler_data(np.array(image))

        except Exception as e:
            print(f"Error changing color scheme: {e}")
    
    def convolute_image(self, median_blur=5, sigma_color=100, sigma_space=100):

        """
        Simplifies a detailed image by smoothing.
        """

        if self.last_adjustment == "convoluted":
            pass
        else:
            self.get_handler_data()
        if self.image_matrix_base is None:
            return
        else:
            image_matrix = self.image_matrix_base.copy()

        # Show warning if median_blur is not odd
        if median_blur % 2 == 0:
            QtWidgets.QMessageBox.warning(
                self.gui, "Invalid Median Blur Size",
                "Median blur size must be an odd number. Change and try again."
            )
            return
        
        # Ensure the input image is in the right format
        if image_matrix.shape[2] == 3 and image_matrix.dtype != np.uint8:
            image_matrix = image_matrix.astype(np.uint8)

        # Apply edge-preserving smoothing
        smoothed = cv2.bilateralFilter(image_matrix, d=9, sigmaColor=sigma_color, sigmaSpace=sigma_space)

        # Optional extra smoothing to reduce small pixel noise
        smoothed = cv2.medianBlur(smoothed, median_blur)

        # Convert to PIL image for return
        #return Image.fromarray(simplified_image)
        self.last_adjustment = "convoluted"
        self.set_handler_data(smoothed)

    def invert_colors(self):
        try:
            self.inverted_colors = not self.inverted_colors
            self.image_current = Image.eval(self.image_current, lambda x: 255 - x)
            self.last_adjustment = "invert"
            #self.update_current_image()
        except Exception as e:
            print(f"Error inverting colors: {e}")
    
    def restore_original_color(self):
        try:
            self.dont_update = True  # Prevents unnecessary updates during restoration

            # Reset sliders
            self.sharpness_slider.setValue(0)
            self.brightness_slider.setValue(0)
            self.contrast_slider.setValue(0)

            # Reset quantizer
            self.color_count_spinbox.setValue(256)
            self.quantize_method_combobox.setCurrentText("DEFAULT")

            # Reset invert colors
            self.inverted_colors = False

            # Reset last adjustment tracker
            self.last_adjustment = "restored"

            original_image = self.data_handler.image_matrix_original.copy()

            #self.update_current_image()
            self.set_handler_data(original_image)

            self.dont_update = False  # Prevents unnecessary updates during restoration

        except Exception as e:
            print(f"Error restoring original color: {e}")

    def set_handler_data(self, image_matrix):
        self.data_handler.image_matrix= image_matrix

    def get_handler_data(self):
        self.image_matrix_base = self.data_handler.image_matrix.copy()

from PyQt6 import QtWidgets, QtCore, QtGui
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
import numpy as np
import collections
from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor, 
                         QPainterPath, QBrush)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QHBoxLayout, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem,
                             QLabel, QSlider)
from PyQt6.QtCore import Qt, QPointF

class ImageColorer(QtCore.QObject):
    
    def __init__(self, data_handler, event_handler, gui):
        super().__init__()  # Call the superclass constructor
        self.data_handler = data_handler
        self.event_handler = event_handler
        self.gui = gui
        self.contours_visible = False
        self.contours = []
        self.contours_list = []
        self.active_color = [255, 255, 255]

        # toggle flags for coloring and masking
        self.fill_color_on = False
        self.color_drawing_on = False  
        self.choose_color_on = False
        self.replace_color_on = False
        self.mask_drawing_on = False

        #Setup for pixel drawing
        self.pen_size = 1 # 1 pixel width

        self.temp_path_item = None
        self.current_path = None
        # self.data_handler.active_color_overlays = [] # Stack for Vector Items (Lightweight). Tracking datahandler!

        # Setup Pen for Pixel Art (Square Cap, No Aliasing)
        self.pixel_pen = QPen(QColor("red"), self.pen_size)
        self.pixel_pen.setCosmetic(False) # False = Scale with zoom (Width 1 means 1 image pixel, not 1 screen pixel)
        self.pixel_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        # Use SquareCap so single pixels are squares, not circles
        self.pixel_pen.setCapStyle(Qt.PenCapStyle.SquareCap) 

        # Add a label, input field and toggle button for drawing on the image
        self.toggle_draw_button = gui.toggle_draw_button
        self.toggle_draw_button.clicked.connect(lambda: self.set_single_toggle_state('color_drawing_on'))

        self.pen_width_label = gui.pen_width_label
        self.pen_width_spinbox = gui.pen_width_spinbox
        self.pen_width_spinbox.setValue(1)
        self.pen_width_spinbox.valueChanged.connect(self.set_pen_size)

        # Add a label, input field and toggle button for filling a color patch in the image
        self.fill_color_button = gui.fill_color_button
        self.fill_color_button.clicked.connect(lambda: self.set_single_toggle_state('fill_color_on'))

        # Add a label, input field and toggle button for replacing a color in the image
        self.replace_color_button = gui.replace_color_button
        self.replace_color_button.clicked.connect(lambda: self.set_single_toggle_state('replace_color_on'))

        # Button: select color from a color palette
        self.select_color_button = gui.select_color_button
        self.select_color_button.clicked.connect(self.select_color)

        # Button: pick color from image
        self.pick_from_image_button = gui.pick_from_image_button
        self.pick_from_image_button.clicked.connect(lambda: self.set_single_toggle_state('choose_color_on'))

        #Button: pick color from database
        self.pick_from_db_button = gui.pick_from_db_button
        self.pick_from_db_button.clicked.connect(self.select_color_from_db)

        # Label to display chosen color and initialize it
        self.color_edit = gui.color_edit
        self.set_active_color(self.active_color)

        # Add buttons to restore and undo mask steps original image
        self.restore_uncolored_image_button = gui.restore_uncolored_image_button
        self.restore_uncolored_image_button.clicked.connect(self.restore_uncolored_image)

        self.undo_color_button = gui.undo_color_button
        self.undo_color_button.clicked.connect(self.undo_coloring)

        #Add button to imprint color edits
        self.imprint_color_overlays_button = gui.imprint_color_overlays_button
        self.imprint_color_overlays_button.clicked.connect(self.imprint_color_overlays)

        # Add Show Contours toggle button
        self.draw_contour_button = gui.draw_contour_button
        self.draw_contour_button.clicked.connect(self.toggle_contours)

        # Add label and entry field for contour thickness
        self.contour_thickness_label = gui.contour_thickness_label
        self.contour_thickness_spinbox = gui.contour_thickness_spinbox
        self.contour_thickness_spinbox.setValue(1)
        self.contour_thickness_spinbox.valueChanged.connect(self.update_contours_thickness)

        # Add label and entry field for contour space
        self.contour_space_label = gui.contour_space_label
        self.contour_space_spinbox = gui.contour_space_spinbox
        self.contour_space_spinbox.setValue(1)
        self.contour_space_spinbox.valueChanged.connect(self.update_contours)

        # Add button and labels for database recoloring
        self.recolor_from_database_button = gui.recolor_from_database_button
        self.recolor_from_database_button.clicked.connect(self.recolor_color_from_db)
        self.recolor_laser_label = gui.recolor_laser_label
        self.recolor_material_label = gui.recolor_material_label
        self.recolor_type_label = gui.recolor_type_label

        # Add button to clean up image colors
        self.clean_up_image_colors_button = gui.clean_up_image_colors_button
        self.clean_up_image_colors_button.clicked.connect(self.clean_up_image_colors2)

        # Add mask drawing functionality
        self.mask_drawing_on = False
        self.mask_shape_mode = "rectangle"  # Can be "rectangle", "ellipse", or "polygon"
        self.data_handler.masks_list = []  # List of mask matrices
        self.mask_start_point_scene = None
        self.mask_obj = None
        self.current_mask_overlay_item = None
        self.polygon_points = []  # List of points for polygon drawing
        self.polygon_preview_item = None  # Current polygon preview

        # Buttons to toggle mask drawing mode for different shapes
        self.rectangle_mask_button = gui.rectangle_mask_button
        self.rectangle_mask_button.clicked.connect(lambda: self.set_single_toggle_state('mask_drawing_on'))
        
        self.ellipse_mask_button = gui.ellipse_mask_button
        self.ellipse_mask_button.clicked.connect(lambda: self.set_single_toggle_state('mask_drawing_on'))
            
        self.polygon_mask_button = gui.polygon_mask_button
        self.polygon_mask_button.clicked.connect(lambda: self.set_single_toggle_state('mask_drawing_on'))
        self.polygon_mask_button.toggled.connect(self.finish_polygon_mask)
        
        # Button to delete selected mask
        self.delete_mask_button = gui.delete_mask_button
        self.delete_mask_button.clicked.connect(self.delete_selected_mask)
        
        # Button to save selected mask
        self.save_mask_button = gui.save_mask_button
        self.save_mask_button.clicked.connect(self.save_selected_mask)
        
        # Button to clear all masks
        self.delete_all_masks_button = gui.delete_all_masks_button
        self.delete_all_masks_button.clicked.connect(self.clear_all_masks)
        
        # List widget to display masks
        self.masks_list_widget = gui.masks_list_widget
        # self.masks_list_widget.itemSelectionChanged.connect(self.on_mask_selected)

        #Event callbacks for handling gui interactions
        self.event_handler.add_canvas_event_callback(self.trigger_canvas_event)
        self.event_handler.add_global_event_callback(self.trigger_global_event)



    ### EVENT HANDLING METHODS ###

    def trigger_canvas_event(self, event):
        # Handle canvas viewport events (mouse clicks/drag)
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.on_canvas_left_click(event)
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            self.on_mouse_left_click_drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.on_mouse_left_release(event)
    
    def trigger_global_event(self, event):
        # Handle keyboard events from entire UI
        if event.type() == QtCore.QEvent.Type.KeyPress:
            self.on_key_press(event)

    def on_canvas_left_click(self, event):
        if self.choose_color_on:
            self.choose_color(event)
            self.pick_from_image_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        elif self.color_drawing_on:
            self.start_color_drawing(event)
        elif self.fill_color_on:
            self.fill_color_patch(event)
        elif self.replace_color_on:
            self.replace_color(event)
        elif self.mask_drawing_on:
            if self.mask_shape_mode == "rectangle":
                self.start_mask_rect(event)
            elif self.mask_shape_mode == "ellipse":
                self.start_mask_ellipse(event)
            elif self.mask_shape_mode == "polygon":
                self.add_polygon_point(event)
    
    def on_key_press(self, event):
        if event.key() == QtCore.Qt.Key.Key_Z and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self.undo_coloring()
        elif event.key() == QtCore.Qt.Key.Key_Return:
            if self.mask_drawing_on and self.mask_shape_mode == "polygon":
                self.finish_polygon_mask()
        elif event.key() == QtCore.Qt.Key.Key_Escape:
            if self.mask_drawing_on:
                self.cancel_mask_drawing()
        elif event.key() == QtCore.Qt.Key.Key_Backspace:
            if self.mask_drawing_on and self.mask_shape_mode == "polygon":
                self.remove_last_polygon_point()
    
    def on_mouse_left_click_drag(self, event):
        if self.mask_drawing_on and self.mask_start_point_scene is not None:
            if self.mask_shape_mode == "rectangle":
                self.update_mask_rect_preview(event)
            elif self.mask_shape_mode == "ellipse":
                self.update_mask_ellipse_preview(event)
        elif self.color_drawing_on:
            self.drag_color_drawing(event)
    
    def on_mouse_left_release(self, event):
        if self.mask_drawing_on:
            if self.mask_shape_mode == "rectangle":
                self.finish_mask_rect(event)
            elif self.mask_shape_mode == "ellipse":
                self.finish_mask_ellipse(event)
            # Note: polygon doesn't use drag, only clicks
        elif self.color_drawing_on:
            self.stop_color_drawing(event)

    def set_single_toggle_state(self, state_property):
        '''sets a single toggle state and resets all others, based on the passed state_property string and the sending button'''
        try:
            # Get sender button and its state to be set
            sender = self.sender()
            state = sender.isChecked()

            # Reset all toggle states and buttons
            self.choose_color_on = False
            self.color_drawing_on = False
            self.fill_color_on = False
            self.replace_color_on = False
            self.mask_drawing_on = False
            self.pick_from_image_button.setChecked(False)
            self.toggle_draw_button.setChecked(False)
            self.fill_color_button.setChecked(False)
            self.replace_color_button.setChecked(False)
            self.rectangle_mask_button.setChecked(False)
            self.ellipse_mask_button.setChecked(False)
            self.polygon_mask_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

            # Set only the desired state
            setattr(self, state_property, state)
            sender.setChecked(state)

            # Set cursor accordingly
            if state_property == 'choose_color_on':
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.PointingHandCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
            else:
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
            
            # Handle special case for mask drawing mode to set correct shape
            if state_property == 'mask_drawing_on' and state:
                if sender == self.rectangle_mask_button:
                    self.mask_shape_mode = "rectangle"
                elif sender == self.ellipse_mask_button:
                    self.mask_shape_mode = "ellipse"
                elif sender == self.polygon_mask_button:
                    self.mask_shape_mode = "polygon"
                    
        except Exception as e:
            print(f"Error in set_single_toggle_state: {e}")

    #### SELECT COLOR METHODS ####

    def select_color(self):
        # Open color chooser
        color_code = QtWidgets.QColorDialog.getColor()
        if color_code.isValid():
            active_color = [color_code.red(), color_code.green(), color_code.blue()]
            self.set_active_color(active_color)

    def select_color_from_db(self):
        def on_color_received(color_data):
            """Callback to handle the selected color from the database."""
             # 1. Get the color string from the dictionary
            color_string = color_data['color_rgb']  # e.g., "255,0,0"

            # 2. Split the string by the comma and convert each part to an integer
            active_color = [int(c) for c in color_string.split(',')]
            self.set_active_color(active_color)

        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Select Color")
        layout = QtWidgets.QVBoxLayout(dialog)
        navigator = DatabaseNavigatorWidget(mode=NavigatorMode.SELECT_COLOR, parent=dialog)
        navigator.selection_button_box.rejected.connect(dialog.reject)
        navigator.colorSelected.connect(on_color_received)
        layout.addWidget(navigator)
        dialog.exec()

    def choose_color(self, event):
        if not self.choose_color_on:
            return

        image_matrix = self.data_handler.image_matrix
        height_px, width_px = image_matrix.shape[:2]

        x_canvas = event.position().x()
        y_canvas = event.position().y()

        # calc image coordinates from canvas click
        x_img, y_img = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)

        # Ensure click is within image bounds
        if 0 <= x_img < width_px and 0 <= y_img < height_px:
            r, g, b = image_matrix[y_img, x_img]
            active_color = [int(r), int(g), int(b)]
            self.set_active_color(active_color)

        # Disable pick mode after one pick
        self.choose_color_on = False

    def set_active_color(self, color_list):
        self.active_color = color_list
        self.pixel_pen.setColor(QColor(*self.active_color))
        
        #show chosen color in the color display
        color = QtGui.QColor(*self.active_color)
        opposite_color = QtGui.QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())
        color_string = f"R{color.red()}, G{color.green()}, B{color.blue()}"
        self.color_edit.setText(color_string)
        self.color_edit.setStyleSheet(f"color: {opposite_color.name()}; background-color: {color.name()}")
    

    ### COLORING METHODS ###

    def set_pen_size(self):
        size = self.gui.pen_width_spinbox.value()
        self.pen_size = size
        self.pixel_pen.setWidth(size)

    def snap_to_pixel_grid(self, position: QPointF):
        """ 
        Forces coordinates to integers. 
        Example: 10.4 -> 10.5 (Center of pixel 10) or just 10.0 depending on preference.
        For QPainterPath drawing with SquareCap, pointing to the center of the pixel is usually best.
        """
        x = np.floor(position.x()) + 0.5
        y = np.floor(position.y()) + 0.5
        return QPointF(x, y)

    def start_color_drawing(self, event):
        # self.is_currently_drawing = True
        
        # Map mouse to scene
        pos_in_item = self.gui.image_item.mapFromScene(self.gui.image_canvas.mapToScene(event.pos()))
        # Snap to grid!
        snapped_pos = self.snap_to_pixel_grid(pos_in_item)
        
        self.current_path = QPainterPath(snapped_pos)
        
        #add as Children of the image item so they move with it and are clipped to its shape
        self.temp_path_item = QGraphicsPathItem(self.current_path, self.gui.image_item)
        self.temp_path_item.setPen(self.pixel_pen)
        self.temp_path_item.setZValue(10) # Layer above image
        
        # self.gui.image_scene.addItem(self.temp_path_item)

        # Add to vector stack for Undo
        self.data_handler.active_color_overlays.append(self.temp_path_item)

    def drag_color_drawing(self, event):
        if self.temp_path_item:

            pos_in_item = self.gui.image_item.mapFromScene(self.gui.image_canvas.mapToScene(event.pos()))
            snapped_pos = self.snap_to_pixel_grid(pos_in_item)
            
            # Optimization: Don't add point if we are on the same pixel
            if self.current_path.currentPosition() != snapped_pos:
                self.current_path.lineTo(snapped_pos)
                self.temp_path_item.setPath(self.current_path)

    def stop_color_drawing(self, event):
        # self.is_currently_drawing = False
        pass

    def fill_color_patch(self, event):
        """
        Flood-fill adapted for overlay logic.
        event_pos: QPointF (Scene Coordinates)
        """
        # 1. Get data
        # image_matrix = self._get_image_matrix() # This is RGBA
        image_matrix = self.data_handler.image_matrix
        if image_matrix is None: return

        h, w = image_matrix.shape[:2]
        x_canvas = event.position().x()
        y_canvas = event.position().y()

        # Bounds Check
        x_image, y_image = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)
        if not (0 <= x_image < w and 0 <= y_image < h): return

        # Compare colors (comparison must be in the same color space)
        # We assume image_matrix is RGBA
        target_color = image_matrix[y_image, x_image].copy() 
        fill_color_arr = np.array([self.active_color[0], self.active_color[1], self.active_color[2]], dtype=np.uint8)
        
        # Abort if color is equal (tolerance could be added here)
        if np.array_equal(target_color, fill_color_arr): return

        #2. see if there are any masks and if the clicked pixel is inside one
        active_mask = None
        mask_matrix = np.zeros_like(image_matrix)
        for color_mask in self.data_handler.masks_list:
            # if np.isnan(mask[y_img, x_img][0])==False:
            if color_mask[y_image, x_image] == 1:
                # Clicked inside a mask, do not replace color
                active_mask = color_mask
                mask_matrix[active_mask == 1] = image_matrix[active_mask == 1]
                break

        if active_mask is None:
            if self.data_handler.masks_list:
                active_mask = self.get_background_mask()
                mask_matrix[active_mask == 1] = image_matrix[active_mask == 1]
            else:
                mask_matrix = image_matrix

        # 3. BFS Algorithm (Numpy optimization is difficult for flood fill, so use Queue)
        # For extremely large images: skimage.segmentation.flood_fill would be faster,
        # but here we stick with pure Python/Numpy standard.
        
        color_mask = np.zeros((h, w), dtype=bool)
        queue = collections.deque([(y_image, x_image)])
        visited = set([(y_image, x_image)])
        
        while queue:
            cy, cx = queue.popleft()
            color_mask[cy, cx] = True
            
            # Check neighbors
            for dy, dx in [(-1,0), (1,0), (0,-1), (0,1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w:
                    if (ny, nx) not in visited:
                        # Check pixel color
                        if np.array_equal(mask_matrix[ny, nx][:3], target_color):
                            visited.add((ny, nx))
                            queue.append((ny, nx))

        # 34. Create overlay and add to stack
        if np.any(color_mask):
            overlay_item = self._create_overlay_from_mask(color_mask)
            # # Position overlay at same location as main image to account for panning
            # overlay_item.setPos(self.gui.image_item.pos())
            # self.gui.image_scene.addItem(overlay_item)
            self.data_handler.active_color_overlays.append(overlay_item) # Add to undo stack

    def replace_color(self, event):
        """
        Replaces color globally or based on logic.
        """
        image_matrix = self.data_handler.image_matrix
        if image_matrix is None: return

        h, w = image_matrix.shape[:2]
        x_canvas = event.position().x()
        y_canvas = event.position().y()

        # Bounds Check
        x_image, y_image = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)
        if not (0 <= x_image < w and 0 <= y_image < h): return

        # Identify target color (RGB)
        target_color = image_matrix[y_image, x_image].copy() 

        #see if there are any masks and if the clicked pixel is inside one
        active_mask = None
        mask_matrix = np.zeros_like(image_matrix)
        for color_mask in self.data_handler.masks_list:
            # if np.isnan(mask[y_img, x_img][0])==False:
            if color_mask[y_image, x_image] == 1:
                # Clicked inside a mask, do not replace color
                active_mask = color_mask
                mask_matrix[active_mask == 1] = image_matrix[active_mask == 1]
                break

        if active_mask is None:
            if self.data_handler.masks_list:
                active_mask = self.get_background_mask()
                mask_matrix[active_mask == 1] = image_matrix[active_mask == 1]
            else:
                mask_matrix = image_matrix


        # Create color_mask: which pixels are equal to the target color?
        # np.all checks over the last axis (Color Channels)
        # We compare only the first 3 channels (RGB), ignoring alpha
        color_mask = np.all(mask_matrix[:, :, :3] == target_color, axis=2)

        # Create overlay
        if np.any(color_mask):
            overlay_item = self._create_overlay_from_mask(color_mask)
            self.data_handler.active_color_overlays.append(overlay_item)

    def recolor_color_from_db(self):
        def on_profile_received(data):
            if data is not None:
                ids = data['identifiers']
                self.db_color_palette = DBColorPalette(data['parameters'], data['settings'])
                self.recolor_laser_label.setText(f"<b> {ids['laser']['name']} </b>")
                self.recolor_material_label.setText(f"<b> {ids['material']['name']} </b>")
                self.recolor_type_label.setText(f"<b> {ids['material_type']['name']} </b>")


        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Select Profile")
        layout = QtWidgets.QVBoxLayout(dialog)
        navigator=DatabaseNavigatorWidget(NavigatorMode.SELECT_PROFILE,parent=dialog)
        navigator.selection_button_box.rejected.connect(dialog.reject)
        navigator.profileSelected.connect(on_profile_received)
        layout.addWidget(navigator)
        dialog.exec()

        color_list = self.db_color_palette.get_color_list()
        if not color_list:
            print("No colors available in the database.")
            return
        
        # Recolor the entire image
        image_matrix = self.data_handler.image_matrix.copy()
        pixels = image_matrix.reshape(-1, 3)  # (num_pixels, 3)
        palette = np.stack(color_list)        # (num_palette, 3)

        # Compute squared distances: (num_pixels, num_palette)
        dists = np.sum((pixels[:, None, :] - palette[None, :, :]) ** 2, axis=2)

        # Find the index of the closest palette color for each pixel
        closest = np.argmin(dists, axis=1)  # (num_pixels,)

        # Map each pixel to its closest palette color
        recolored_pixels = palette[closest]  # (num_pixels, 3)

        # Reshape back to image
        recolored_image = recolored_pixels.reshape(image_matrix.shape)
        recolored_image = recolored_image.astype(np.uint8)

        h, w = recolored_image.shape[:2]
        
        # Convert to QImage
        # Assumption: new_image_matrix is uint8 RGB or RGBA
        if recolored_image.shape[2] == 3:
            fmt = QImage.Format.Format_RGB888
            bytes_per_line = w * 3
        else:
            fmt = QImage.Format.Format_RGBA8888
            bytes_per_line = w * 4
            
        img = QImage(recolored_image.data, w, h, bytes_per_line, fmt)
        img = img.copy() # Important: data copy
        
        # This is not a transparent overlay, but a completely new image
        # We simply place it on top.
        overlay_item = QGraphicsPixmapItem(QPixmap.fromImage(img), self.gui.image_item)
        overlay_item.setZValue(10)
        
        # overlay_item.setPos(self.gui.image_item.pos())
        # self.gui.image_scene.addItem(overlay_item)
        self.data_handler.active_color_overlays.append(overlay_item)

    def _create_overlay_from_mask(self, mask_boolean):
        """
        Efficiently converts a boolean mask (H, W) into a QGraphicsPixmapItem overlay.
        """
        h, w = mask_boolean.shape
        
        # 1. Create RGBA array (4 channels: R, G, B, Alpha)
        rgba_overlay = np.zeros((h, w, 4), dtype=np.uint8)
        
        # 2. Set color (r, g, b, alpha)
        r, g, b = self.active_color
        
        # 3. Only set pixels where the mask is True
        # Numpy broadcasting is extremely fast here (also for 4K/8K)
        # Set alpha to 255 for full opacity
        rgba_overlay[mask_boolean] = [r, g, b, 255]
        
        # 4. Convert to QImage
        # Format_RGBA8888 expects 4 bytes per pixel (R, G, B, A)
        overlay_img = QImage(rgba_overlay.data, w, h, QImage.Format.Format_RGBA8888)
        
        # 5. Create QGraphicsItem as child of image item
        pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(overlay_img), self.gui.image_item)
        pixmap_item.setZValue(10) # Above background
        return pixmap_item

    def imprint_color_overlays(self):
        """
        Bakes vector/overlay items into a pixel matrix and sends it to data_handler.
        Does NOT update the image_item directly.
        """
        if not self.data_handler.active_color_overlays:
            return 
        
        # 1. get copy of current pixmap
        current_pixmap = self.gui.image_item.pixmap()
        result_pixmap = current_pixmap.copy()

        # 2. set painter on copy
        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # CompositionMode is SourceOver by default, which is correct for overlays.
        
        for item in self.data_handler.active_color_overlays:
            # as items are children of image item, their coordinates are relative to it
            if isinstance(item, QGraphicsPathItem):
                painter.setPen(item.pen())
                painter.drawPath(item.path())
            
            elif isinstance(item, QGraphicsPixmapItem):
                painter.drawPixmap(item.offset().toPoint(), item.pixmap())
            
            # remove items from secene as they are now baked in
            self.gui.image_scene.removeItem(item)
            
        painter.end()

        # 3. ensure list is cleared
        self.data_handler.active_color_overlays.clear()
        
        # 4. QPixmap -> QImage -> Numpy Array conversion
        image = result_pixmap.toImage()
        
        # esnure correct image format
        if image.format() != QImage.Format.Format_RGBA8888:
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        
        width = image.width()
        height = image.height()
        
        ptr = image.bits()
        ptr.setsize(height * width * 4)
        
        # copy buffer so python owns the data
        arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4)).copy()
        
        self.data_handler.image_matrix = arr[:,:,:3]  # Drop alpha as we work in RGB only
    

    def restore_uncolored_image(self):
        if self.data_handler.active_color_overlays:
            for item in self.data_handler.active_color_overlays:
                self.gui.image_scene.removeItem(item)
            self.data_handler.active_color_overlays.clear()
            self.temp_path_item = None
            self.current_path = None

    def undo_coloring(self, event=None):
        """ Handles both Vector Undo and Pixel Undo transparently. """
        
        # Priority 1: Undo active vector drawings (not yet imprinted)
        if self.data_handler.active_color_overlays:
            # Remove last drawn stroke
            last_item = self.data_handler.active_color_overlays.pop()
            self.gui.image_scene.removeItem(last_item)
            return

        # Priority 2: Undo Imprint (Revert pixel changes)
        # if self.pixel_history:
        #     # Restore last saved pixmap
        #     previous_pixmap = self.pixel_history.pop()
        #     self.background_item.setPixmap(previous_pixmap)
        #     print("Undid imprint (restored pixels).")
        # else:
        #     print("Nothing to undo.")
        

    ### CONTOUR METHODS ###

    def toggle_contours(self):
        if not self.contours_visible:
            # Outlines are currently not visible; show them
            self.draw_contour_button.setText("Delete Contours")
            self.contours_visible = True
        else:
            # Outlines are visible; hide them
            self.draw_contour_button.setText("Draw Contours")
            self.contours_visible = False

        self.update_contours()

    def update_contours(self, event=None):
        if self.contours_visible:
            self.find_image_contours()
        else:
            self.contours = []
            self.contours_list = []
        self.data_handler.contours = self.contours
        self.data_handler.contours_list = self.contours_list

    def find_image_contours(self):
        """Find and display the outlines of the image."""
        try:
            # First delete all existing contours
            self.data_handler.contours = []
            # Get the current image data without any contours
            image_array = self.data_handler.image_matrix.copy()

            # Apply edge detection (Canny Edge Detector)
            edges = cv2.Canny(image_array, threshold1=50, threshold2=150)

            # Make edges "wider" by dilation
            kernel = np.ones((self.contour_space_spinbox.value(), self.contour_space_spinbox.value()), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)

            # Find contours from the edges
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            # to find also nested contours use cv2.RETR_TREE as second argument
            self.contours = [self.active_color, self.contour_thickness_spinbox.value(), contours]
            self.contours_list = []
            for idx, contour in enumerate(self.contours[2]):
                # Convert contour to a list of (x, y) tuples
                polyline = contour.squeeze().tolist()
                # Perform further processing as needed
                self.contours_list.append(polyline)

        except Exception as e:
            print(f"Error finding image outlines: {e}")

    def update_contours_thickness(self, *args):
        if self.contours:
            self.contours[1] = self.contour_thickness_spinbox.value()
            self.data_handler.contours = self.contours
    
    def clean_up_image_colors2(self):
        """
        Cleans up the current image by separating it into color patches, applying median blur to each patch,
        and recombining them, taking the darker color if a pixel is colored in multiple patches.
        """
        image_matrix = self.data_handler.image_matrix.copy()
        if image_matrix is None:
            return
        # Find all unique colors (excluding white)
        unique_colors = np.unique(image_matrix.reshape(-1, 3), axis=0)
        
        # Ask user if he wants to continue if more than 10 colors are present
        if len(unique_colors) > 10:
            reply = QtWidgets.QMessageBox.question(
                self.gui, "Too many colors",
                f"This image has {len(unique_colors)} different colors. "
                "Do you want to continue cleaning up the image.\nIt might take very long if more than 10 colors are present?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
        white = np.array([255, 255, 255], dtype=np.uint8)
        color_patches = []
        for color in unique_colors:
            if np.all(color == white):
                continue
            # Create a mask for this color
            mask = np.all(image_matrix == color, axis=-1)
            patch = np.ones_like(image_matrix, dtype=np.uint8) * 255
            patch[mask] = color
            # Apply median blur to the patch
            patch_blur = cv2.medianBlur(patch, 5)
            color_patches.append(patch_blur)
        if not color_patches:
            return
        # Recombine patches: for each pixel, take the darkest color (lowest sum)
        combined = np.ones_like(image_matrix, dtype=np.uint8) * 255
        for patch in color_patches:
            # Where patch is not white, compare to current combined
            mask = ~np.all(patch == 255, axis=-1)
            # For those pixels, if patch is darker, use it
            current = combined[mask]
            candidate = patch[mask]
            # Compare sum of RGB (lower is darker)
            darker = np.sum(candidate, axis=-1) < np.sum(current, axis=-1)
            # Update only where candidate is darker
            indices = np.where(mask)
            if len(indices[0]) > 0:
                darker_indices = np.where(darker)[0]
                for idx in darker_indices:
                    combined[indices[0][idx], indices[1][idx]] = candidate[idx]
        # Update the data handler with the cleaned image
        self.data_handler.image_matrix_adjusted = combined
        self.data_handler.image_matrix = combined

    def clean_up_image_colors(self):
        """
        Finds contours in the image, then for each contour pixel, sets its color to the most common color among its 1st and 2nd order neighbors.
        If there are multiple most common colors, one is chosen at random.
        Returns a new image matrix with smoothed contours.
        """
        self.clean_up_image_colors2()
        image_matrix = self.data_handler.image_matrix.copy()
        # Find contours using OpenCV (convert to grayscale first)
        gray = cv2.cvtColor(image_matrix, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, threshold1=50, threshold2=150)
        # kernel = np.ones((3, 3), np.uint8)
        # edges = cv2.dilate(edges, kernel, iterations=1)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        # Copy image to modify
        result = image_matrix.copy()
        height, width = image_matrix.shape[:2]

        # Helper to get neighbors (1st and 2nd order)
        def get_neighbors(y, x):
            neighbors = []
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width:
                        # Only consider 1st and 2nd order neighbors
                        if abs(dy) == 2 or abs(dx) == 2 or abs(dy) == 1 or abs(dx) == 1:
                            neighbors.append(tuple(result[ny, nx]))
            return neighbors

        for contour in contours:
            for pt in contour:
                y, x = pt[0][1], pt[0][0]
                neighbors = get_neighbors(y, x)
                if not neighbors:
                    continue
                # Count occurrences of each color
                color_counts = {}
                for color in neighbors:
                    color_counts[color] = color_counts.get(color, 0) + 1
                max_count = max(color_counts.values())
                most_common_colors = [color for color, count in color_counts.items() if count == max_count]
                # Pick one at random if tie
                chosen_color = random.choice(most_common_colors)
                result[y, x] = chosen_color

        # Update the data handler with the cleaned image
        self.data_handler.image_matrix_adjusted = result
        self.data_handler.image_matrix = result
    

    #Image Masking Functions
    def start_mask_rect(self, event):
        """Start drawing a rectangular mask."""
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        
        # Convert viewport coordinates to scene coordinates
        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(x_canvas, y_canvas)
        self.mask_start_point_scene = (x_scene, y_scene)
        # self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)

    def update_mask_rect_preview(self, event):
        """Update the preview of the rectangular mask being drawn."""
        if self.mask_start_point_scene is None:
            return
        
        x_canvas = event.position().x()
        y_canvas = event.position().y()

        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(x_canvas, y_canvas)
        # Remove old overlay if exists
        if self.current_mask_overlay_item is not None:
            self.gui.image_scene.removeItem(self.current_mask_overlay_item)
        
        # Create rectangle from start point to current point
        x_start, y_start = self.mask_start_point_scene
        width = x_scene - x_start
        height = y_scene - y_start
        
        # Draw dotted rectangle overlay
        self.mask_obj = QRectF(int(x_start), int(y_start), int(width), int(height))
        self.current_mask_overlay_item = QtWidgets.QGraphicsRectItem(self.mask_obj)
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        self.current_mask_overlay_item.setPen(pen)
        self.current_mask_overlay_item.setBrush(QtGui.QBrush())
        self.gui.image_scene.addItem(self.current_mask_overlay_item)

    def finish_mask_rect(self, event):
        """Finish drawing the rectangular mask and create the mask matrix."""
        if self.mask_obj is None or self.mask_start_point_scene is None:
            return
        
        # Add current overlay to the list of overlays, plot it permanently and reset current overlay
        if self.current_mask_overlay_item is not None:
            new_mask_overlay_item = self.current_mask_overlay_item
            self.data_handler.mask_overlays.append(new_mask_overlay_item)
            self.gui.image_scene.removeItem(self.current_mask_overlay_item)
            self.current_mask_overlay_item = None

            # Replot from overlays
            self.gui.image_scene.addItem(self.data_handler.mask_overlays[-1])
        
        # Convert canvas coordinates to image coordinates
        x_start_scene, y_start_scene = self.mask_start_point_scene
        x_end_canvas = event.position().x()
        y_end_canvas = event.position().y()

        x_start_img, y_start_img = self.data_handler.scene_to_image_coords(x_start_scene, y_start_scene)
        x_end_img, y_end_img = self.data_handler.canvas_to_image_coords(x_end_canvas, y_end_canvas)

        # Normalize coordinates
        x_min = min(x_start_img, x_end_img)
        x_max = max(x_start_img, x_end_img)
        y_min = min(y_start_img, y_end_img)
        y_max = max(y_start_img, y_end_img)
        
        # Create mask matrix
        image_matrix = self.data_handler.image_matrix
        height, width = image_matrix.shape[:2]
        
        # Create mask with zeros for pixels outside the selected area
        mask_matrix = np.zeros((height, width), dtype=image_matrix.dtype)
        
        # Fill selected area with ones
        for y in range(max(0, y_min), min(height, y_max + 1)):
            for x in range(max(0, x_min), min(width, x_max + 1)):
                mask_matrix[y, x] = 1

        # Store the mask
        self.data_handler.masks_list.append(mask_matrix)
        self.update_masks_list_widget()
        
        # Reset
        self.mask_start_point_scene = None
        self.mask_obj = None

    def start_mask_ellipse(self, event):
        """Start drawing an elliptical mask."""
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        
        # Convert viewport coordinates to scene coordinates
        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(x_canvas, y_canvas)
        self.mask_start_point_scene = (x_scene, y_scene)

    def update_mask_ellipse_preview(self, event):
        """Update the preview of the elliptical mask being drawn."""
        if self.mask_start_point_scene is None:
            return
        
        x_canvas = event.position().x()
        y_canvas = event.position().y()

        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(x_canvas, y_canvas)
        
        # Remove old overlay if exists
        if self.current_mask_overlay_item is not None:
            self.gui.image_scene.removeItem(self.current_mask_overlay_item)
        
        # Create ellipse from start point to current point
        x_start, y_start = self.mask_start_point_scene
        width = x_scene - x_start
        height = y_scene - y_start
        
        # Draw dotted ellipse overlay
        self.mask_obj = QRectF(int(x_start), int(y_start), int(width), int(height))
        self.current_mask_overlay_item = QtWidgets.QGraphicsEllipseItem(self.mask_obj)
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        self.current_mask_overlay_item.setPen(pen)
        self.current_mask_overlay_item.setBrush(QtGui.QBrush())
        self.gui.image_scene.addItem(self.current_mask_overlay_item)

    def finish_mask_ellipse(self, event):
        """Finish drawing the elliptical mask and create the mask matrix."""
        if self.mask_obj is None or self.mask_start_point_scene is None:
            return
        
        # Add current overlay to the list of overlays, plot it permanently and reset current overlay
        if self.current_mask_overlay_item is not None:
            new_mask_overlay_item = self.current_mask_overlay_item
            self.data_handler.mask_overlays.append(new_mask_overlay_item)
            self.gui.image_scene.removeItem(self.current_mask_overlay_item)
            self.current_mask_overlay_item = None

            # Replot from overlays
            self.gui.image_scene.addItem(self.data_handler.mask_overlays[-1])
        
        # Convert scene coordinates to image coordinates
        x_start_scene, y_start_scene = self.mask_start_point_scene
        x_end_canvas = event.position().x()
        y_end_canvas = event.position().y()

        x_start_img, y_start_img = self.data_handler.scene_to_image_coords(x_start_scene, y_start_scene)
        x_end_img, y_end_img = self.data_handler.canvas_to_image_coords(x_end_canvas, y_end_canvas)

        # Get ellipse bounds
        x_min = min(x_start_img, x_end_img)
        x_max = max(x_start_img, x_end_img)
        y_min = min(y_start_img, y_end_img)
        y_max = max(y_start_img, y_end_img)
        
        # Create mask matrix
        image_matrix = self.data_handler.image_matrix
        height, width = image_matrix.shape[:2]
        
        # Create mask with zeros for pixels outside the selected area
        mask_matrix = np.zeros((height, width), dtype=image_matrix.dtype)
        
        # Calculate ellipse parameters
        center_x = (x_min + x_max) / 2.0
        center_y = (y_min + y_max) / 2.0
        radii_x = (x_max - x_min) / 2.0
        radii_y = (y_max - y_min) / 2.0
        
        # Fill pixels inside ellipse with ones
        if radii_x > 0 and radii_y > 0:
            for y in range(max(0, y_min), min(height, y_max + 1)):
                for x in range(max(0, x_min), min(width, x_max + 1)):
                    # Check if point is inside ellipse using the ellipse equation
                    dx = (x - center_x) / radii_x
                    dy = (y - center_y) / radii_y
                    if dx * dx + dy * dy <= 1.0:
                        mask_matrix[y, x] = 1
        
        # Store the mask
        self.data_handler.masks_list.append(mask_matrix)
        self.update_masks_list_widget()
        
        # Reset
        self.mask_start_point_scene = None
        self.mask_obj = None

    def add_polygon_point(self, event):
        """Add a point to the polygon mask."""
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        
        # Convert to image coordinates
        x_img, y_img = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)
        
        # Add point to the list
        self.polygon_points.append((x_img, y_img))
        
        # Update preview
        self.update_polygon_preview()
    
    def remove_last_polygon_point(self):
        """Remove the last point added to the polygon."""
        if self.polygon_points:
            self.polygon_points.pop()
            self.update_polygon_preview()

    def update_polygon_preview(self):
        """Update the visual preview of the polygon being drawn."""
        # Remove old preview if exists
        if self.polygon_preview_item is not None:
            self.gui.image_scene.removeItem(self.polygon_preview_item)
            self.polygon_preview_item = None
        
        if len(self.polygon_points) < 2:
            return
        
        # Convert image coordinates to scene coordinates
        scene_points = []
        for x_img, y_img in self.polygon_points:
            x_scene, y_scene = self.data_handler.image_to_scene_coords(x_img, y_img)
            scene_points.append(QtCore.QPointF(x_scene, y_scene))
        
        # If we have 3+ points, draw a closed polygon
        if len(scene_points) >= 3:
            polygon = QtGui.QPolygonF(scene_points)
            self.polygon_preview_item = QtWidgets.QGraphicsPolygonItem(polygon)
        else:
            # Draw lines connecting the points
            path = QtGui.QPainterPath()
            path.moveTo(scene_points[0])
            for point in scene_points[1:]:
                path.lineTo(point)
            self.polygon_preview_item = QtWidgets.QGraphicsPathItem(path)
        
        # Style the preview
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        self.polygon_preview_item.setPen(pen)
        self.polygon_preview_item.setBrush(QtGui.QBrush())
        
        self.gui.image_scene.addItem(self.polygon_preview_item)

    def finish_polygon_mask(self):
        """Finalize the polygon mask and create the mask matrix."""
        
        # Remove preview
        if self.polygon_preview_item is not None:
            self.gui.image_scene.removeItem(self.polygon_preview_item)
            self.polygon_preview_item = None

        #simply clear if just a single point or line
        if len(self.polygon_points) < 3:
            self.polygon_points = []
            return
        
        # Create polygon overlay for permanent display
        scene_points = []
        for x_img, y_img in self.polygon_points:
            x_scene, y_scene = self.data_handler.image_to_scene_coords(x_img, y_img)
            scene_points.append(QtCore.QPointF(x_scene, y_scene))
        
        polygon = QtGui.QPolygonF(scene_points)
        polygon_item = QtWidgets.QGraphicsPolygonItem(polygon)
        
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        polygon_item.setPen(pen)
        polygon_item.setBrush(QtGui.QBrush())
        
        self.data_handler.mask_overlays.append(polygon_item)
        self.gui.image_scene.addItem(polygon_item)
        
        # Create mask matrix using point-in-polygon test
        image_matrix = self.data_handler.image_matrix
        height, width = image_matrix.shape[:2]
        
        # Create mask with zeros for pixels outside the polygon
        mask_matrix = np.zeros((height, width), dtype=image_matrix.dtype)
        
        # Use OpenCV to create a filled polygon mask
        pts = np.array(self.polygon_points, dtype=np.int32)
        cv2.fillPoly(mask_matrix, [pts], 1)
        
        self.data_handler.masks_list.append(mask_matrix)
        self.update_masks_list_widget()
        
        # Reset polygon points
        self.polygon_points = []
    
    def cancel_mask_drawing(self):
        """Cancel the current mask drawing operation."""
        # Remove preview
        if self.current_mask_overlay_item is not None:
            self.gui.image_scene.removeItem(self.current_mask_overlay_item)
            self.current_mask_overlay_item = None
        
        # Remove polygon preview
        if self.polygon_preview_item is not None:
            self.gui.image_scene.removeItem(self.polygon_preview_item)
            self.polygon_preview_item = None
        
        # Reset state
        self.mask_start_point_scene = None
        self.mask_obj = None
        self.polygon_points = []

    def update_masks_list_widget(self):
        """Update the masks list widget display."""
        self.masks_list_widget.clear()
        for idx, mask in enumerate(self.data_handler.masks_list):
            non_nan_count = np.count_nonzero(mask == 1)
            item_text = f"Mask {idx + 1} ({non_nan_count} pixels)"
            self.masks_list_widget.addItem(item_text)

    # def on_mask_selected(self):
    #     """Handle mask selection in the list widget."""
    #     selected_items = self.masks_list_widget.selectedItems()
    #     if selected_items:
    #         index = self.masks_list_widget.row(selected_items[0])
    #         # You can visualize the selected mask here if needed
    #         print(f"Selected mask {index}")

    def delete_selected_mask(self):
        """Delete the currently selected mask."""
        selected_items = self.masks_list_widget.selectedItems()
        if selected_items:
            index = self.masks_list_widget.row(selected_items[0])
            self.data_handler.masks_list.pop(index)
            self.gui.image_scene.removeItem(self.data_handler.mask_overlays[index])
            self.data_handler.mask_overlays.pop(index)
            self.update_masks_list_widget()

    def save_selected_mask(self):
        """Save the currently selected mask as an image file with actual image pixels."""
        selected_items = self.masks_list_widget.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self.gui, "No Mask Selected", "Please select a mask to save.")
            return
        
        index = self.masks_list_widget.row(selected_items[0])
        active_mask = self.data_handler.masks_list[index]
        
        # Find the minimum bounding rectangle containing all True (1) values
        rows = np.where(np.any(active_mask == 1, axis=1))[0]
        cols = np.where(np.any(active_mask == 1, axis=0))[0]
        
        if len(rows) == 0 or len(cols) == 0:
            QtWidgets.QMessageBox.warning(self.gui, "Empty Mask", "The selected mask contains no pixels.")
            return
        
        row_min, row_max = rows[0], rows[-1]
        col_min, col_max = cols[0], cols[-1]
        
        # Extract the bounding rectangle from the mask and image
        mask_cropped = active_mask[row_min:row_max+1, col_min:col_max+1]
        image_cropped = self.data_handler.image_matrix[row_min:row_max+1, col_min:col_max+1]
        
        # Fill the output image with pixels where mask==1, white elsewhere
        output_image = np.ones_like(image_cropped) * 255
        output_image[mask_cropped == 1] = image_cropped[mask_cropped == 1]
        
        # Get save file path from user
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.gui, 
            "Save Mask", 
            "", 
            "PNG Files (*.png);;BMP Files (*.bmp);;JPEG Files (*.jpg *.jpeg)"
        )
        
        if file_path:
            try:
                image = Image.fromarray(output_image.astype(np.uint8))
                # Add DPI information based on current pixel_per_mm
                dpi = round(self.data_handler.pixel_per_mm * 25.4)
                # Save with DPI metadata
                image.save(file_path, dpi=(dpi, dpi))
                QtWidgets.QMessageBox.information(self.gui, "Success", f"Mask saved successfully to:\n{file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self.gui, "Error Saving Mask", f"Error saving mask: {e}")

    def clear_all_masks(self):
        """Clear all masks."""
        reply = QtWidgets.QMessageBox.question(
            self.gui, "Clear All Masks",
            "Are you sure you want to delete all masks?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.data_handler.masks_list.clear()
            self.update_masks_list_widget()
            for overlay in self.data_handler.mask_overlays:
                self.gui.image_scene.removeItem(overlay)
            self.data_handler.mask_overlays.clear()

    def get_background_mask(self):
        """
        Get the mask matrix containing all pixels NOT covered by any other masks.
        Returns a matrix with NaN where any mask covers it, and original pixels elsewhere.
        """
        image_matrix = self.data_handler.image_matrix
        height, width = image_matrix.shape[:2]
        
        # Start with full image
        # background_mask = image_matrix.copy().astype(np.float32)
        background_mask = np.ones((height, width), dtype=np.uint8)
        
        # Set pixels covered by any mask to 0
        for mask in self.data_handler.masks_list:
            # Where mask equals 1, set background to 0
            # covered = ~np.isnan(mask[:,:,0])
            covered = mask == 1
            # background_mask[covered] = np.nan
            background_mask[covered] = 0
        
        return background_mask

    def get_all_masks_with_background(self):
        """
        Get a dictionary containing all masks plus the background mask.
        Returns: {'mask_0': array, 'mask_1': array, ..., 'background': array}
        """
        all_masks = {}
        for idx, mask in enumerate(self.data_handler.masks_list):
            all_masks[f'mask_{idx}'] = mask
        all_masks['background'] = self.get_background_mask()
        return all_masks

        
