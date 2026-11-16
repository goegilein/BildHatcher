from contextlib import nullcontext
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import QRectF
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
import numpy as np
from Database.database_main import DatabaseNavigatorWidget,NavigatorMode
from HelperClasses import DBColorPalette
import random
from UndoRedo import ColorOverlayAction, ImprintColorOverlaysAction, ImageMatrixAction
from core import fill, image_doc, palette
import ColorProfile
from Masks import MaskTools
import logging

log = logging.getLogger(__name__)

class ImageAdjuster:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.undo_manager = getattr(data_handler, "undo_manager", None)
        self.image_matrix_base = None
        self.image_matrix_original = None
        self.inverted_colors = False
        self.last_adjustment = "None"
        self.sharpness_old = 0
        self.brightness_old = 0
        self.contrast_old = 0
        self.masked_pixels_list = []
        self.dont_update = False
        self.pre_slider_matrix = None
        self._last_output = None  # image array last written by this adjuster (B33)
        # coalesce slider ticks: the full-resolution image is recomputed at most every 40 ms
        self._slider_timer = QtCore.QTimer()
        self._slider_timer.setSingleShot(True)
        self._slider_timer.setInterval(40)
        self._slider_timer.timeout.connect(self.update_bright_cont_sharp)

        self.data_handler.add_image_changed_callback(self.reset_cached_image)

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
        self.sharpness_slider.valueChanged.connect(self._slider_timer.start)
        self.sharpness_slider.sliderPressed.connect(self._on_slider_pressed)
        self.sharpness_slider.sliderReleased.connect(lambda: self._on_slider_released("Sharpness"))

        # Brightness Slider
        self.brightness_label = gui.brightness_label
        self.brightness_slider = gui.brightness_slider
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self._slider_timer.start)
        self.brightness_slider.sliderPressed.connect(self._on_slider_pressed)
        self.brightness_slider.sliderReleased.connect(lambda: self._on_slider_released("Brightness"))

        # Contrast Slider
        self.contrast_label = gui.contrast_label
        self.contrast_slider = gui.contrast_slider
        self.contrast_slider.setRange(-100, 100)
        self.contrast_slider.setValue(0)
        self.contrast_slider.valueChanged.connect(self._slider_timer.start)
        self.contrast_slider.sliderPressed.connect(self._on_slider_pressed)
        self.contrast_slider.sliderReleased.connect(lambda: self._on_slider_released("Contrast"))

        #simplyfying image button
        self.convolute_image_button = gui.convolute_image_button
        self.median_blur_spinbox = gui.median_blur_spinbox
        self.sigma_color_spinbox = gui.sigma_color_spinbox
        self.sigma_space_spinbox = gui.sigma_space_spinbox
        self.convolute_image_button.clicked.connect(lambda: self.convolute_image(
                                                                median_blur=self.median_blur_spinbox.value(),
                                                                sigma_color=self.sigma_color_spinbox.value(),
                                                                sigma_space=self.sigma_space_spinbox.value()))

    def _on_slider_pressed(self):
        if self.data_handler.image_matrix is not None:
            self.pre_slider_matrix = self.data_handler.image_matrix.copy()

    def _on_slider_released(self, name):
        if self._slider_timer.isActive():  # apply the final value before recording the undo step
            self._slider_timer.stop()
            self.update_bright_cont_sharp()
        if self.pre_slider_matrix is not None and self.data_handler.image_matrix is not None:
            post_matrix = self.data_handler.image_matrix.copy()
            if self.undo_manager and not np.array_equal(self.pre_slider_matrix, post_matrix):
                active_item = getattr(getattr(self.undo_manager, "image_controller", None), "active_image_item", None)
                action = ImageMatrixAction(
                    self.data_handler, self.gui, getattr(self.undo_manager, "image_controller", None),
                    self.pre_slider_matrix, post_matrix,
                    self.data_handler.pixel_per_mm, self.data_handler.pixel_per_mm,
                    image_item=active_item,
                    description=f"{name} Adjust"
                )
                self.undo_manager.push_action(action)
        self.pre_slider_matrix = None

    ## METHODS

    def _base(self, kind):
        """Image the adjustment `kind` starts from (B33): its previous base as long as the current image is still
        this adjuster's own last result of `kind` (moving a slider again, re-quantizing with another colour count);
        otherwise the current image - so edits made in between are kept and nothing is applied twice."""
        current = self.data_handler.image_matrix
        if current is None:
            self.image_matrix_base = None
            return None
        if not (self.last_adjustment == kind and current is self._last_output and self.image_matrix_base is not None):
            self.image_matrix_base = current.copy()
            if kind == "brightness":
                # the new base already contains the effect of all sliders that were not moved now -> show them at 0
                for slider, attr in ((self.sharpness_slider, "sharpness_old"), (self.brightness_slider, "brightness_old"),
                                     (self.contrast_slider, "contrast_old")):
                    if slider.value() == getattr(self, attr):
                        slider.blockSignals(True)
                        slider.setValue(0)
                        slider.blockSignals(False)
                        setattr(self, attr, 0)
        return self.image_matrix_base

    def _write(self, kind, image):
        self.set_handler_data(image)
        self.last_adjustment = kind
        self._last_output = self.data_handler.image_matrix

    def reset_cached_image(self):
        """Invalidate adjustment state when a different image becomes active."""
        self.image_matrix_base = None
        self.image_matrix_original = None
        self.last_adjustment = "None"

    def update_bright_cont_sharp(self):
        """Apply sharpening and brightness adjustments based on slider values."""

        if self.dont_update:
            return

        if self._base("brightness") is None:
            return
        image = Image.fromarray(image_doc.rgb_filled(self.image_matrix_base))

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

            self._write("brightness", image_doc.with_rgb(self.image_matrix_base, np.array(image)))

        except Exception:
            log.exception("Error applying adjustments")
    def quantize_image_color(self):

        if self.dont_update:
            return

        ctx = self.undo_manager.record_image_matrix("Quantize Colors") if self.undo_manager else nullcontext()
        with ctx:
            self._quantize_image_color_exec()

    def _quantize_image_color_exec(self):
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
        
        if self._base("quantize") is None:
            return
        opaque = image_doc.opaque_mask(self.image_matrix_base)
        if not opaque.any():
            return
        # all opaque pixels as a 1 x N image, so every quantizer only sees real colours
        image = Image.fromarray(self.image_matrix_base[opaque][None, :, :3])

        try:
            num_colors = self.color_count_spinbox.value()
            quantize_method = self.quantize_method_combobox.currentText()
            if quantize_method == "DEFAULT":
                image_matrix = np.array(image)
                # Flatten the image into a list of pixels
                pixels = image_matrix.reshape((-1, 3))
                # P6.2/P8.2: k-means on the distinct colours (weighted by count) in the perceptual CIELAB space
                simplified_image = palette.kmeans_quantize(pixels, num_colors).reshape(image_matrix.shape)
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

            result = self.image_matrix_base.copy()
            result[opaque, :3] = np.array(image)[0]
            self._write("quantize", result)

        except Exception:
            log.exception("Error changing color scheme")
    def convolute_image(self, median_blur=5, sigma_color=100, sigma_space=100):

        """
        Simplifies a detailed image by smoothing.
        """
        ctx = self.undo_manager.record_image_matrix("Convolute Image") if self.undo_manager else nullcontext()
        with ctx:
            if self._base("convoluted") is None:
                return
            image_matrix = self.image_matrix_base.copy()

            # Show warning if median_blur is not odd
            if median_blur % 2 == 0:
                QtWidgets.QMessageBox.warning(
                    self.gui, "Invalid Median Blur Size",
                    "Median blur size must be an odd number. Change and try again."
                )
                return
            
            # Apply edge-preserving smoothing (on RGB with white background, alpha is kept)
            smoothed = cv2.bilateralFilter(image_doc.rgb_filled(image_matrix), d=9, sigmaColor=sigma_color, sigmaSpace=sigma_space)

            # Optional extra smoothing to reduce small pixel noise
            smoothed = cv2.medianBlur(smoothed, median_blur)

            self._write("convoluted", image_doc.with_rgb(image_matrix, smoothed))

    def invert_colors(self):
        try:
            ctx = self.undo_manager.record_image_matrix("Invert Colors") if self.undo_manager else nullcontext()
            with ctx:
                self.inverted_colors = not self.inverted_colors
                image = self.data_handler.image_matrix
                if image is not None:
                    self.last_adjustment = "invert"
                    self.set_handler_data(image_doc.with_rgb(image, 255 - image[..., :3]))
        except Exception:
            log.exception("Error inverting colors")
    def restore_original_color(self):
        try:
            ctx = self.undo_manager.record_image_matrix("Restore Colors") if self.undo_manager else nullcontext()
            with ctx:
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

        except Exception:
            log.exception("Error restoring original color")
    def set_handler_data(self, image_matrix):
        self.data_handler.image_matrix= image_matrix

from PyQt6 import QtWidgets, QtCore, QtGui
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
import numpy as np
from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor, 
                         QPainterPath, QBrush)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QHBoxLayout, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem,
                             QLabel, QSlider)
from PyQt6.QtCore import Qt, QPointF

class ImageColorer(MaskTools, QtCore.QObject):
    
    def __init__(self, data_handler, event_handler, gui):
        super().__init__()  # Call the superclass constructor
        self.data_handler = data_handler
        self.event_handler = event_handler
        self.gui = gui
        self.undo_manager = getattr(data_handler, "undo_manager", None)
        self.active_color = [255, 255, 255, 255]  # RGBA, alpha 0 = transparent (erases)

        #Flags and variables for contouring
        self.contours_visible = False
        self.contours_list = []
        self.contour_mask = None  # bool (H, W): pixels of the last found contours
        self.contour_overlay_item = None

        # toggle flags for coloring and masking
        self.flood_fill_color_on = False
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
        self.flood_fill_button = gui.flood_fill_button
        self.flood_fill_button.clicked.connect(lambda: self.set_single_toggle_state('flood_fill_color_on'))
        self.flood_fill_mode_combobox = gui.flood_fill_mode_combobox
        self.fill_options_grid_layout = gui.fill_options_grid_layout
        self.flood_fill_parameter_value = 0
        self.limit_color = [0, 0, 0, 255]
        self.limit_color_choose_on = False
        self.limit_color_source_dropdown = None
        self.limit_color_indicator = None
        self.fill_option_spinbox = None
        self.fill_option_label = None
        self.clear_fill_options_layout()
        self.flood_fill_mode_combobox.currentTextChanged.connect(self.update_fill_options_ui)
        self.update_fill_options_ui(self.flood_fill_mode_combobox.currentText())

        # Add a label, input field and toggle button for replacing a color in the image
        self.replace_color_button = gui.replace_color_button
        self.replace_color_button.clicked.connect(lambda: self.set_single_toggle_state('replace_color_on'))

        # Color Chooser button and display
        self.default_color_buttons_layout = gui.default_color_buttons_layout
        self.setup_default_color_buttons()

        self.select_color_button = gui.select_color_color_button
        self.select_color_button.clicked.connect(lambda: self.apply_selected_color(self.select_color()))

        self.pick_color_from_image_button = gui.pick_color_from_image_button
        self.pick_color_from_image_button.clicked.connect(lambda: self.set_single_toggle_state('choose_color_on'))

        self.pick_color_from_db_button = gui.pick_color_from_db_button
        self.pick_color_from_db_button.clicked.connect(lambda: self.apply_selected_color(self.select_color_from_db()))

        self.active_color_dislplay_edit = gui.active_color_dislplay_edit
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

        #Add combobox for contour mode
        self.contouring_mode_combobox = gui.contouring_mode_combobox
        self.contouring_mode_combobox.addItem("color regions")  # P6.7
        self.contouring_mode_combobox.currentTextChanged.connect(self.find_image_contours)

        #Add spinbox for contour sensitivity
        self.contour_sensitivity_spinbox = gui.contour_sensitivity_spinbox
        self.contour_sensitivity_spinbox.valueChanged.connect(self.find_image_contours)

        # Add label and entry field for contour thickness
        self.contour_thickness_label = gui.contour_thickness_label
        self.contour_thickness_spinbox = gui.contour_thickness_spinbox
        self.contour_thickness_spinbox.setValue(1)
        self.contour_thickness_spinbox.valueChanged.connect(self.find_image_contours)

        # Add label and entry field for contour space
        self.contour_space_label = gui.contour_space_label
        self.contour_space_spinbox = gui.contour_space_spinbox
        self.contour_space_spinbox.setValue(1)
        self.contour_space_spinbox.valueChanged.connect(self.find_image_contours)

        # Add button and labels for database recoloring (labels show the active colour profile, P8.5)
        self.recolor_from_database_button = gui.recolor_from_database_button
        self.recolor_from_database_button.clicked.connect(self.recolor_color_from_db)
        self.recolor_laser_label = gui.recolor_laser_label
        self.recolor_material_label = gui.recolor_material_label
        self.recolor_type_label = gui.recolor_type_label
        self.data_handler.color_profiles.callbacks.append(self.show_color_profile)
        self.show_color_profile(self.data_handler.color_profile)

        # Add button to clean up image colors
        self.clean_up_image_colors_button = gui.clean_up_image_colors_button
        self.clean_up_image_colors_button.clicked.connect(self.clean_up_image_colors)

        self._init_masks(gui)  # P8.4: mask state and buttons (Masks.py)


        #Event callbacks for handling gui interactions
        self.event_handler.add_canvas_event_callback(self.trigger_canvas_event)
        self.event_handler.add_global_event_callback(self.trigger_global_event)
        self.data_handler.image_shape_changed_callback_list.append(self.reset_masks)  # B17
        self.data_handler.add_image_resized_callback(self.refresh_mask_outlines)  # B17: pixel size changed


    #### UI SETUP METHODS ####
    def setup_default_color_buttons(self):
        self.default_color_buttons_layout.setContentsMargins(0, 0, 0, 0) # Removes outer padding

        # Define  9 default colors (using Hex codes)
        colors = [
            "#FF0000", "#00FF00", "#0000FF", # Row 0: Red, Green, Blue
            "#FFFF00", "#FF00FF", "#00FFFF", # Row 1: Yellow, Magenta, Cyan
            "#000000", "#888888", "#FFFFFF"  # Row 2: Black, Gray, White
        ]

        def hex_to_rgb(hex_string):
            """Converts a hex color string like '#FF0000' to an RGB list [255, 0, 0]."""
            # Strip the '#' symbol from the start of the string
            hex_string = hex_string.lstrip('#')
        
            # Grab pairs of characters (0:2, 2:4, 4:6) and convert them from base-16 to base-10 integers
            return [int(hex_string[i:i+2], 16) for i in (0, 2, 4)]

        # Generate the buttons dynamically
        for index, hex_color in enumerate(colors):
            btn = QtWidgets.QPushButton()
            btn.setFixedSize(25, 25) # Forces the button to be a small square
            
            # Use Qt Style Sheets to set the background color
            # Added a 1px border so lighter colors (like white) don't vanish into the background
            btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #444; border-radius: 3px;")

            rgb_color = hex_to_rgb(hex_color)
            
            # 4. Connect the click event
            # The 'c=hex_color' trick is required to capture the variable properly inside the loop
            btn.clicked.connect(lambda checked, c=rgb_color: self.set_active_color(c))

            # 5. Calculate the row and column based on the index
            row = index // 3
            col = index % 3
            
            # Add the button to the layout
            self.default_color_buttons_layout.addWidget(btn, row, col)

        transparent_btn = QtWidgets.QPushButton("Transparent")
        transparent_btn.setToolTip("Paint/fill with transparency: the area becomes background and is not hatched")
        transparent_btn.clicked.connect(lambda checked: self.set_active_color(list(image_doc.TRANSPARENT)))
        self.default_color_buttons_layout.addWidget(transparent_btn, 3, 0, 1, 3)
    
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
        # Check if clicking on an edit handle (only in edit mode)
        if self.mask_edit_mode:
            items_at_pos = self.gui.image_canvas.items(event.pos())
            for item in items_at_pos:
                if item in self.edit_handles:
                    self.dragging_handle = item
                    return
        
        if self.choose_color_on:
            color = self.choose_color(event)
            self.pick_color_from_image_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            if color is not None:
                self.set_active_color(color)
        elif self.limit_color_choose_on:
            color = self.choose_limit_color(event)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            if color is not None:
                self.set_limit_color(color)
        elif self.color_drawing_on:
            self.start_color_drawing(event)
        elif self.flood_fill_color_on:
            mode = self.flood_fill_mode_combobox.currentText()
            self.flood_fill(event, mode)
        elif self.replace_color_on:
            self.replace_color(event)
        elif self.mask_drawing_on:
            if self.mask_shape_mode == "rectangle":
                self.start_mask_rect(event)
            elif self.mask_shape_mode == "ellipse":
                self.start_mask_ellipse(event)
            elif self.mask_shape_mode == "polygon":
                self.add_polygon_point(event)
        elif self.move_mask_on:
            self.on_move_mask_press(event)
    
    def on_key_press(self, event):
        if event.key() == QtCore.Qt.Key.Key_Z and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            # Handled globally by UndoRedoManager QAction (Ctrl+Z)
            return
        elif event.key() == QtCore.Qt.Key.Key_Y and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            # Handled globally by UndoRedoManager QAction (Ctrl+Y / Ctrl+Shift+Z)
            return
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
        # Check if we're dragging an edit handle
        if self.dragging_handle is not None:
            self.drag_edit_handle(event)
        elif self.mask_drawing_on and self.mask_start_point_scene is not None:
            if self.mask_shape_mode == "rectangle":
                self.update_mask_rect_preview(event)
            elif self.mask_shape_mode == "ellipse":
                self.update_mask_ellipse_preview(event)
        elif self.color_drawing_on:
            self.drag_color_drawing(event)
        elif self.move_mask_on:
            self.on_move_mask_drag(event)
    
    def on_mouse_left_release(self, event):
        if self.dragging_handle is not None:
            self.finish_drag_edit_handle(event)
        elif self.mask_drawing_on:
            if self.mask_shape_mode == "rectangle":
                self.finish_mask_rect(event)
            elif self.mask_shape_mode == "ellipse":
                self.finish_mask_ellipse(event)
            # Note: polygon doesn't use drag, only clicks
        elif self.color_drawing_on:
            self.stop_color_drawing(event)
        elif self.move_mask_on:
            self.on_move_mask_release(event)

    def set_single_toggle_state(self, state_property):
        '''sets a single toggle state and resets all others, based on the passed state_property string and the sending button'''
        try:
            # Get sender button and its state to be set
            sender = self.sender()

            #check if sender has isChecked method (it should, but just to be safe)
            if hasattr(sender, 'isChecked'):
                state = sender.isChecked()
            else:
                state = None
            
            # Reset all toggle states and buttons
            self.choose_color_on = False
            self.color_drawing_on = False
            self.flood_fill_color_on = False
            self.replace_color_on = False
            self.mask_drawing_on = False
            self.mask_edit_mode = False
            self.move_mask_on = False
            self.pick_color_from_image_button.setChecked(False)
            self.toggle_draw_button.setChecked(False)
            self.flood_fill_button.setChecked(False)
            self.replace_color_button.setChecked(False)
            self.rectangle_mask_button.setChecked(False)
            self.ellipse_mask_button.setChecked(False)
            self.polygon_mask_button.setChecked(False)
            self.edit_mask_button.setChecked(False)
            self.move_masked_area_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

            #use emptty string to only reset all states
            if not state_property or state is None:
                return
            
            


            # Set only the desired state
            setattr(self, state_property, state)
            sender.setChecked(state)

            # Set cursor accordingly
            if state_property == 'choose_color_on':
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.PointingHandCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
            
            # Handle special case for mask drawing mode to set correct shape
            if state_property == 'mask_drawing_on' and state:
                if sender == self.rectangle_mask_button:
                    self.mask_shape_mode = "rectangle"
                    self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
                elif sender == self.ellipse_mask_button:
                    self.mask_shape_mode = "ellipse"
                    self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
                elif sender == self.polygon_mask_button:
                    self.mask_shape_mode = "polygon"
                    self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if state else QtCore.Qt.CursorShape.ArrowCursor)
            
            # Handle mask edit mode
            if state_property == 'mask_edit_mode':
                if state:
                    # Show edit handles if a mask is already selected
                    self.show_edit_handles_for_selected()
            # Clear edit handles when exiting edit mode
            if self.mask_edit_mode == False:
                self.clear_edit_handles()
                    
        except Exception:
            log.exception("Error in set_single_toggle_state")
    #### SELECT COLOR METHODS ####

    def select_color(self):
        # Open color chooser
        color_code = QtWidgets.QColorDialog.getColor()
        if color_code.isValid():
            return [color_code.red(), color_code.green(), color_code.blue()]
        return None

    def select_color_from_db(self):
        """A colour of the active colour profile (P8.5); without one, browse the whole database."""
        palette = self.data_handler.color_profile
        if palette is not None:
            return ColorProfile.pick_color_dialog(self.gui, palette)
        selected_color = {'value': None}

        def on_color_received(color_data):
            color_string = color_data['color_rgb']  # e.g., "255,0,0"
            selected_color['value'] = [int(c) for c in color_string.split(',')]
            dialog.accept()

        dialog = QtWidgets.QDialog(self.gui)
        dialog.setWindowTitle("Select Color")
        layout = QtWidgets.QVBoxLayout(dialog)
        navigator = DatabaseNavigatorWidget(mode=NavigatorMode.SELECT_COLOR, parent=dialog)
        navigator.selection_button_box.rejected.connect(dialog.reject)
        navigator.colorSelected.connect(on_color_received)
        layout.addWidget(navigator)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return selected_color['value']
        return None

    def apply_selected_color(self, color):
        if color is not None:
            self.set_active_color(color)

    def choose_color(self, event):
        if not self.choose_color_on:
            return None

        image_matrix = self.data_handler.image_matrix
        height_px, width_px = image_matrix.shape[:2]

        x_canvas = event.position().x()
        y_canvas = event.position().y()

        # calc image coordinates from canvas click
        x_img, y_img = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)

        selected_color = None
        if 0 <= x_img < width_px and 0 <= y_img < height_px:
            selected_color = [int(v) for v in image_matrix[y_img, x_img]]

        # Disable pick mode after one pick
        self.choose_color_on = False
        return selected_color

    def set_active_color(self, color_list):
        """color_list: [r, g, b] or [r, g, b, a]; a == 0 selects the transparent colour (eraser)."""
        self.active_color = [int(v) for v in color_list] + [255] * (4 - len(color_list))
        if self.active_color[3] == 0:
            self.active_color = list(image_doc.TRANSPARENT)
            self.pixel_pen.setBrush(QBrush(QPixmap.fromImage(self._checker_qimage(8, 8))))
            self.active_color_dislplay_edit.setText("Transparent")
            self.active_color_dislplay_edit.setStyleSheet("color: black; background-color: white")
            return
        self.pixel_pen.setColor(QColor(*self.active_color[:3]))

        #show chosen color in the color display
        color = QtGui.QColor(*self.active_color[:3])
        opposite_color = QtGui.QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())
        color_string = f"R{color.red()}, G{color.green()}, B{color.blue()}"
        self.active_color_dislplay_edit.setText(color_string)
        self.active_color_dislplay_edit.setStyleSheet(f"color: {opposite_color.name()}; background-color: {color.name()}")

    @property
    def erasing(self):
        return self.active_color[3] == 0

    @staticmethod
    def _checker_rgba(h, w):
        """Light checkerboard (4 px squares): the look of 'will become transparent'."""
        yy, xx = np.indices((h, w))
        gray = np.where(((yy // 4) + (xx // 4)) % 2 == 0, 255, 204).astype(np.uint8)
        return np.dstack([gray, gray, gray, np.full((h, w), 255, np.uint8)])

    def _checker_qimage(self, h, w):
        return QImage(np.ascontiguousarray(self._checker_rgba(h, w)).data, w, h, QImage.Format.Format_RGBA8888).copy()

    def set_limit_color(self, color_list):
        self.limit_color = color_list
        self.update_limit_color_indicator()

    def update_limit_color_indicator(self):
        if self.limit_color_indicator is None:
            return
        r, g, b = self.limit_color[:3]
        style = f"background-color: rgb({r}, {g}, {b}); border: 1px solid #444;"
        self.limit_color_indicator.setStyleSheet(style)

    def clear_fill_options_layout(self):
        while self.fill_options_grid_layout.count():
            item = self.fill_options_grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout is not None:
                    while layout.count():
                        child = layout.takeAt(0)
                        if child.widget() is not None:
                            child.widget().deleteLater()

    def update_fill_options_ui(self, mode):
        self.clear_fill_options_layout()
        self.limit_color_choose_on = False

        if mode in ["Regular", "To Contours"]:
            return

        if mode in ["Similar Color", "Diagonals + Similar"]:
            self.show_fill_spinbox("Similarity")
        elif mode == "Fill Lines":
            self.show_fill_spinbox("Tolerance")
        elif mode == "To Color":
            self.show_to_color_options()

    def show_fill_spinbox(self, label_text):
        self.fill_option_label = QtWidgets.QLabel(label_text)
        self.fill_option_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fill_option_spinbox = QtWidgets.QSpinBox()
        self.fill_option_spinbox.setMinimum(0)
        self.fill_option_spinbox.setMaximum(255)
        self.fill_option_spinbox.setValue(self.flood_fill_parameter_value)
        self.fill_option_spinbox.valueChanged.connect(self.on_fill_parameter_changed)
        self.fill_options_grid_layout.addWidget(self.fill_option_label, 0, 0)
        self.fill_options_grid_layout.addWidget(self.fill_option_spinbox, 1, 0)

    def on_fill_parameter_changed(self, value):
        self.flood_fill_parameter_value = value

    def show_to_color_options(self):
        label = QtWidgets.QLabel("Pick Limit color")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        combo = QtWidgets.QComboBox()
        combo.addItem("Choose source...")
        combo.addItem("Color Palette")
        combo.addItem("Image")
        combo.addItem("Database")
        combo.currentTextChanged.connect(self.on_limit_color_source_changed)
        self.limit_color_source_dropdown = combo

        self.limit_color_indicator = QtWidgets.QLabel()
        self.limit_color_indicator.setFixedSize(48, 24)
        self.limit_color_indicator.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.limit_color_indicator.setAutoFillBackground(True)
        self.update_limit_color_indicator()

        self.fill_options_grid_layout.addWidget(label, 0, 0)
        self.fill_options_grid_layout.addWidget(combo, 0, 1)
        self.fill_options_grid_layout.addWidget(self.limit_color_indicator, 0, 2)
        self.fill_options_grid_layout.setColumnStretch(1, 1)

    def on_limit_color_source_changed(self, source):
        if source == "Color Palette":
            self.prompt_limit_color_from_palette()
            if self.limit_color_source_dropdown is not None:
                self.limit_color_source_dropdown.setCurrentIndex(0)
        elif source == "Image":
            self.limit_color_choose_on = True
        elif source == "Database":
            self.prompt_limit_color_from_db()
            if self.limit_color_source_dropdown is not None:
                self.limit_color_source_dropdown.setCurrentIndex(0)

    def prompt_limit_color_from_palette(self):
        dialog = QtWidgets.QDialog(self.gui)
        dialog.setWindowTitle("Pick Limit Color")
        layout = QtWidgets.QGridLayout(dialog)

        colors = [
            "#FFFFFF", "#000000", "#FF0000", "#00FF00", "#0000FF",
            "#FFFF00", "#FF00FF", "#00FFFF", "#808080", "#800000",
            "#008000", "#000080", "#808000", "#800080", "#008080",
            "#C0C0C0"
        ]

        def hex_to_rgb(hex_string):
            hex_string = hex_string.lstrip('#')
            return [int(hex_string[i:i+2], 16) for i in (0, 2, 4)]

        def on_palette_color(chosen_color):
            self.set_limit_color(chosen_color + [255])
            dialog.accept()
            if self.limit_color_source_dropdown is not None:
                self.limit_color_source_dropdown.setCurrentIndex(0)

        for index, hex_color in enumerate(colors):
            btn = QtWidgets.QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #444;")
            rgb_color = hex_to_rgb(hex_color)
            btn.clicked.connect(lambda checked, c=rgb_color: on_palette_color(c))
            layout.addWidget(btn, index // 8, index % 8)

        dialog.exec()

    def prompt_limit_color_from_db(self):
        color = self.select_color_from_db()
        if color is not None:
            self.set_limit_color(color + [255])
        if self.limit_color_source_dropdown is not None:
            self.limit_color_source_dropdown.setCurrentIndex(0)

    def choose_limit_color(self, event):
        image_matrix = self.data_handler.image_matrix
        if image_matrix is None:
            self.limit_color_choose_on = False
            return

        height_px, width_px = image_matrix.shape[:2]
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        x_img, y_img = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)

        if 0 <= x_img < width_px and 0 <= y_img < height_px:
            self.set_limit_color([int(v) for v in image_matrix[y_img, x_img]])

        self.limit_color_choose_on = False
        if self.limit_color_source_dropdown is not None:
            self.limit_color_source_dropdown.setCurrentIndex(0)

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
        self.temp_path_item.erases = self.erasing
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
        if self.temp_path_item is not None:
            if self.undo_manager:
                action = ColorOverlayAction(
                    [self.temp_path_item],
                    self.gui.image_scene,
                    self.data_handler.active_color_overlays,
                    description="Brush Stroke"
                )
                self.undo_manager.push_action(action)
            self.temp_path_item = None
            self.current_path = None

    def flood_fill(self, event, mode = "Regular"):
        """Flood fill from the clicked pixel; the result becomes a colour overlay (imprinted later)."""
        image_matrix = self.data_handler.image_matrix
        if image_matrix is None:
            return
        x_image, y_image = self.data_handler.canvas_to_image_coords(event.position().x(), event.position().y())
        self.flood_fill_at(x_image, y_image, mode)

    def flood_fill_at(self, x_image, y_image, mode="Regular"):
        image_matrix = self.data_handler.image_matrix
        h, w = image_matrix.shape[:2]
        if not (0 <= x_image < w and 0 <= y_image < h):
            return
        if np.array_equal(image_matrix[y_image, x_image], self.active_color):
            return  # already the fill colour

        # the fill stays inside the clicked mask, or outside of all masks if clicked on the background
        region = None
        for mask in self.data_handler.masks_list:
            if mask[y_image, x_image] == 1:
                region = mask == 1
                break
        else:
            if self.data_handler.masks_list:
                region = self.get_background_mask() == 1

        color_mask = fill.fill_region(
            image_matrix, (x_image, y_image), mode, tolerance=self.flood_fill_parameter_value,
            fill_color=self.active_color, limit_color=self.limit_color, region=region, contour_mask=self.contour_mask)

        # create overlay and add to stack
        if np.any(color_mask):
            overlay_item = self._create_overlay_from_mask(color_mask)
            self.data_handler.active_color_overlays.append(overlay_item) # Add to undo stack
            if self.undo_manager:
                action = ColorOverlayAction(
                    [overlay_item],
                    self.gui.image_scene,
                    self.data_handler.active_color_overlays,
                    description="Flood Fill"
                )
                self.undo_manager.push_action(action)

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
        mask_matrix = np.full(image_matrix.shape, -1, dtype=np.int16)  # use signed sentinel so white pixels do not collide with invalid marker
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
        color_mask = np.all(mask_matrix == target_color, axis=2)

        # Create overlay
        if np.any(color_mask):
            overlay_item = self._create_overlay_from_mask(color_mask)
            self.data_handler.active_color_overlays.append(overlay_item)
            if self.undo_manager:
                action = ColorOverlayAction(
                    [overlay_item],
                    self.gui.image_scene,
                    self.data_handler.active_color_overlays,
                    description="Replace Color"
                )
                self.undo_manager.push_action(action)

    def show_color_profile(self, palette):
        ids = getattr(palette, "identifiers", None)
        for label, key in ((self.recolor_laser_label, "laser"), (self.recolor_material_label, "material"),
                           (self.recolor_type_label, "material_type")):
            label.setText(f"<b> {ids[key]['name']} </b>" if ids else "-")

    def recolor_color_from_db(self):
        """Recolour the image with the colours of the active colour profile (P8.5; asked for if none is set)."""
        if self.data_handler.image_matrix is None:
            return
        palette = self.data_handler.color_profiles.require()
        if palette is None:  # B14: no profile chosen
            return

        color_list = palette.get_color_list()
        if not color_list:
            log.error("No colors available in the database.")
            return
        
        # Recolor all opaque pixels; transparent pixels stay transparent (alpha of the overlay = alpha of the image)
        image_matrix = self.data_handler.image_matrix.copy()
        pixels = image_matrix[..., :3].reshape(-1, 3)  # (num_pixels, 3)
        palette = np.stack(color_list)        # (num_palette, 3)

        # B14: match only the unique colours (pixels x palette x 3 could exhaust memory)
        unique_colors, inverse = np.unique(pixels, axis=0, return_inverse=True)
        dists = np.sum((unique_colors[:, None, :].astype(np.int64) - palette[None, :, :]) ** 2, axis=2)
        closest = np.argmin(dists, axis=1)  # (num_unique,)

        # Map each pixel to its closest palette color
        recolored_pixels = palette[closest][inverse.reshape(-1)]  # (num_pixels, 3)

        # Reshape back to image
        recolored_image = image_doc.with_rgb(image_matrix, recolored_pixels.reshape(image_matrix.shape[:2] + (3,)))

        h, w = recolored_image.shape[:2]
        img = QImage(recolored_image.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        img = img.copy() # Important: data copy
        
        # This is not a transparent overlay, but a completely new image
        # We simply place it on top.
        overlay_item = QGraphicsPixmapItem(QPixmap.fromImage(img), self.gui.image_item)
        overlay_item.setZValue(10)
        
        # overlay_item.setPos(self.gui.image_item.pos())
        # self.gui.image_scene.addItem(overlay_item)
        self.data_handler.active_color_overlays.append(overlay_item)
        if self.undo_manager:
            action = ColorOverlayAction(
                [overlay_item],
                self.gui.image_scene,
                self.data_handler.active_color_overlays,
                description="DB Recolor"
            )
            self.undo_manager.push_action(action)

    def _create_overlay_from_mask(self, mask_boolean):
        """
        Efficiently converts a boolean mask (H, W) into a QGraphicsPixmapItem overlay.
        """
        # P6.5: the pixmap only covers the bounding box of the mask (placed there via setOffset)
        rows, cols = np.flatnonzero(mask_boolean.any(axis=1)), np.flatnonzero(mask_boolean.any(axis=0))
        y0, x0 = (rows[0], cols[0]) if len(rows) else (0, 0)
        y1, x1 = (rows[-1] + 1, cols[-1] + 1) if len(rows) else (1, 1)
        mask_boolean = mask_boolean[y0:y1, x0:x1]
        h, w = mask_boolean.shape

        # 1. Create RGBA array (4 channels: R, G, B, Alpha)
        rgba_overlay = np.zeros((h, w, 4), dtype=np.uint8)

        # 2./3. Only set pixels where the mask is True; transparent colour shows a checkerboard and erases on imprint
        if self.erasing:
            rgba_overlay[mask_boolean] = self._checker_rgba(y1, x1)[y0:y1, x0:x1][mask_boolean]  # pattern aligned to the image
        else:
            rgba_overlay[mask_boolean] = self.active_color
        
        # 4. Convert to QImage
        # Format_RGBA8888 expects 4 bytes per pixel (R, G, B, A)
        overlay_img = QImage(rgba_overlay.data, w, h, QImage.Format.Format_RGBA8888)
        
        # 5. Create QGraphicsItem as child of image item
        pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(overlay_img), self.gui.image_item)
        pixmap_item.setOffset(float(x0), float(y0))
        pixmap_item.setZValue(10) # Above background
        pixmap_item.erases = self.erasing
        return pixmap_item

    def imprint_color_overlays(self):
        """
        Bakes vector/overlay items into a pixel matrix and sends it to data_handler.
        Does NOT update the image_item directly.
        """
        if not self.data_handler.active_color_overlays:
            return 
        
        before_matrix = self.data_handler.image_matrix.copy() if self.data_handler.image_matrix is not None else None
        imprinted_items = list(self.data_handler.active_color_overlays)

        # Update the logical mask geometry if one was being moved
        self.update_logical_mask_matrices()
        
        # 1. get copy of current pixmap
        current_pixmap = self.gui.image_item.pixmap()
        result_pixmap = current_pixmap.copy()

        # 2. set painter on copy
        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # CompositionMode is SourceOver by default, which is correct for overlays.
        
        overlay_items = list(self.data_handler.active_color_overlays)
        # overlay_items.extend(self.data_handler.text_overlays)
        # overlay_items.extend(self.data_handler.geometry_overlays)

        for item in overlay_items:
            erases = getattr(item, "erases", False)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut if erases
                                       else QPainter.CompositionMode.CompositionMode_SourceOver)
            if isinstance(item, QGraphicsPathItem):
                painter.setPen(item.pen())
                painter.drawPath(item.path())
            elif isinstance(item, QGraphicsPixmapItem):
                draw_point = (item.pos() + item.offset()).toPoint()
                painter.drawPixmap(draw_point, item.pixmap())
                
            #this is text and geometries that do not have a direct painter method, but implement a custom one
            elif hasattr(item, 'paint_to_painter'):
                painter.save()
                painter.translate(item.pos())
                painter.setTransform(item.transform(), True)
                item.paint_to_painter(painter)
                painter.restore()
            else:
                # Fall back to a generic scene render if no direct painter method exists.
                try:
                    painter.save()
                    painter.translate(item.pos())
                    painter.setTransform(item.transform(), True)
                    if hasattr(item, 'paint'):
                        item.paint(painter, None, None)
                    painter.restore()
                except Exception:
                    pass

            if item.scene() is not None:
                self.gui.image_scene.removeItem(item)

        painter.end()

        # 3. ensure lists are cleared
        self.data_handler.active_color_overlays.clear()
        self.data_handler.text_overlays.clear()
        self.data_handler.geometry_overlays.clear()
        
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
        
        self.data_handler.image_matrix = arr  # RGBA; the data handler binarizes the alpha

        after_matrix = self.data_handler.image_matrix.copy()
        if self.undo_manager and before_matrix is not None:
            active_item = getattr(getattr(self.undo_manager, "image_controller", None), "active_image_item", None)
            if active_item is None and hasattr(self.gui, "images_ListWidget"):
                active_item = self.gui.images_ListWidget.currentItem()
            action = ImprintColorOverlaysAction(
                self.data_handler, self.gui, getattr(self.undo_manager, "image_controller", None),
                before_matrix, after_matrix, imprinted_items,
                self.gui.image_scene, self.data_handler.active_color_overlays,
                image_item=active_item,
                description="Imprint Color Overlays"
            )
            self.undo_manager.push_action(action)

        #ensure to reset contours
        self.contours_visible = False
        self.contour_overlay_item = None
        self.draw_contour_button.setText("Draw Contours")
        self.draw_contour_button.setChecked(False)

        #ensure to restet mask moving
        self.disable_move_mask_mode()

    def restore_uncolored_image(self):
        if self.data_handler.active_color_overlays:
            for item in self.data_handler.active_color_overlays:
                self.gui.image_scene.removeItem(item)
            self.data_handler.active_color_overlays.clear()
            self.temp_path_item = None
            self.current_path = None

    def undo_coloring(self, event=None):
        """ Handles both Vector Undo and Pixel Undo transparently via UndoRedoManager. """
        if getattr(self, "undo_manager", None) and self.undo_manager.undo():
            return
        
        # Priority 1: Undo active vector drawings (not yet imprinted)
        if self.data_handler.active_color_overlays:
            # Remove last drawn stroke/item
            last_item = self.data_handler.active_color_overlays.pop()
            if last_item.scene() is not None:
                self.gui.image_scene.removeItem(last_item)
            
            # If the item we just undid was the moving mask...
            if last_item == self.moving_mask_item:
                # 1. Pop and remove the white cutout
                if self.white_cutout_item in self.data_handler.active_color_overlays:
                    self.data_handler.active_color_overlays.remove(self.white_cutout_item)
                if self.white_cutout_item and self.white_cutout_item.scene() is not None:
                    self.gui.image_scene.removeItem(self.white_cutout_item)
                
                # 2. Reset the dotted mask boundary back to its original position
                if self.detached_mask_index >= 0 and self.detached_mask_index < len(self.data_handler.mask_overlays):
                    boundary_item = self.data_handler.mask_overlays[self.detached_mask_index]
                    boundary_item.setPos(0, 0)
                
                # 3. Clear the tracking variables
                self.detached_mask_index = -1
                self.moving_mask_item = None
                self.white_cutout_item = None

            if hasattr(self.data_handler, "update_color_ovleray_imprint_button"):
                self.data_handler.update_color_ovleray_imprint_button()
            if hasattr(self.gui, "image_canvas") and self.gui.image_canvas:
                self.gui.image_canvas.viewport().update()
            if hasattr(self.gui, "image_scene") and self.gui.image_scene:
                self.gui.image_scene.update()
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
            self.find_image_contours()

        else:
            # Outlines are visible; hide them
            self.draw_contour_button.setText("Draw Contours")
            self.contours_visible = False
            # Hide overlay instead of removing it
            if self.contour_overlay_item is not None:
                self.contour_overlay_item.hide()
                if self.contour_overlay_item in self.data_handler.active_color_overlays:
                    self.data_handler.active_color_overlays.remove(self.contour_overlay_item) # Remove from undo stack when hidden

    def find_image_contours(self):
        """Find contours and create an overlay for display."""
        try:
            # Remove old overlay if it exists
            if self.contour_overlay_item is not None:
                self.gui.image_scene.removeItem(self.contour_overlay_item)
                if self.contour_overlay_item in self.data_handler.active_color_overlays:
                    self.data_handler.active_color_overlays.remove(self.contour_overlay_item)
                self.contour_overlay_item = None
            
            

            # Get the current image data
            image_matrix = image_doc.rgb_filled(self.data_handler.image_matrix)
            height, width = image_matrix.shape[:2]

            # Only apply edge detection to the masked region if there is one, otherwise to the whole image
            threshold1 = self.contour_sensitivity_spinbox.value()
            threshold2 = threshold1*3
            if self.data_handler.active_mask_index != -1:
                active_mask = self.data_handler.masks_list[self.data_handler.active_mask_index]
                # Use original image for edge detection, but only inside the mask
                edges = cv2.Canny(image_matrix, threshold1=threshold1, threshold2=threshold2)
                # Zero out edges outside the mask
                edges[active_mask == 0] = 0
            else:
                edges = cv2.Canny(image_matrix, threshold1=threshold1, threshold2=threshold2)

            # threshold1: Lower = more edges detected (more sensitive)
            # threshold2: Should be 2-3x threshold1

            # Make edges "wider" by dilation
            kernel = np.ones((self.contour_space_spinbox.value(), self.contour_space_spinbox.value()), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)

            # Find contours from the edges
            if self.contouring_mode_combobox.currentText() == "color regions":
                # P6.7: exact outline of every area of one colour (no edge detection, independent of sensitivity)
                rgba = self.data_handler.image_matrix
                packed = np.ascontiguousarray(rgba).view(np.uint32)[..., 0]
                region = np.ones((height, width), bool)
                if self.data_handler.active_mask_index != -1:
                    region = self.data_handler.masks_list[self.data_handler.active_mask_index] == 1
                contours = []
                for color in np.unique(packed[(rgba[..., 3] > 0) & region]):
                    color_mask = ((packed == color) & region).astype(np.uint8)
                    contours.extend(cv2.findContours(color_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)[0])
            elif self.contouring_mode_combobox.currentText() == "only external":
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            elif self.contouring_mode_combobox.currentText() == "all":
                contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            
            # cv2.RETR_EXTERNAL - Only extremnp.outerer contours (current, fastest)
            # cv2.RETR_LIST - All contours, no hierarchy
            # cv2.RETR_TREE - All contours with full hierarchy (parent-child relationships)
            # cv2.RETR_CCOMP - All contours in 2-level hierarchy
            
            # Create a mask with all the actual contour pixels
            contour_mask = np.zeros((height, width), dtype=np.uint8)
            # Draw contours on the mask with thickness
            cv2.drawContours(contour_mask, contours, -1, 1, thickness=self.contour_thickness_spinbox.value())

            # contour pixels are the boundary of the "To Contours" flood fill
            self.contour_mask = contour_mask == 1

            # Create overlay from the contour mask
            self.contour_overlay_item = self._create_overlay_from_mask(contour_mask.astype(bool))

            # Set overlay visibility based on contours_visible flag
            if self.contour_overlay_item is not None:
                if self.contours_visible:
                    self.contour_overlay_item.show()
                    self.data_handler.active_color_overlays.append(self.contour_overlay_item)
                else:
                    self.contour_overlay_item.hide()
                    if self.contour_overlay_item in self.data_handler.active_color_overlays:
                        self.data_handler.active_color_overlays.remove(self.contour_overlay_item)
            
            # Finally store contours as list of polylines and pass to datahandler for NC-Data Generation
            self.contours_list = []
            for idx, contour in enumerate(contours):
                # Convert contour to a list of (x, y) tuples
                polyline = contour.squeeze().tolist()
                # Perform further processing as needed
                self.contours_list.append(polyline)
            self.data_handler.contours_list = self.contours_list

        except Exception:
            log.exception("Error finding image outlines")
    def clean_up_image_colors(self):
        """P8.3: reduce the image to a few clear colour areas without anti-aliasing traces (see core/palette.py)."""
        if self.data_handler.image_matrix is None:
            return
        params = getattr(self, "_cleanup_params", {"n_colors": 8, "min_region": 6, "edge_threshold": 12.0})
        dialog = QtWidgets.QDialog(self.gui)
        dialog.setWindowTitle("Clean Up Colors")
        form = QtWidgets.QFormLayout(dialog)
        n_colors = QtWidgets.QSpinBox(minimum=1, maximum=64, value=params["n_colors"])
        n_colors.setToolTip("Number of colours of the result")
        min_region = QtWidgets.QSpinBox(minimum=1, maximum=10000, value=params["min_region"], suffix=" px")
        min_region.setToolTip("Colour areas smaller than this are merged into their neighbour")
        edge = QtWidgets.QDoubleSpinBox(minimum=1, maximum=100, value=params["edge_threshold"], decimals=1)
        edge.setToolTip("Colour difference (delta E) between neighbouring pixels that counts as an edge; "
                        "smaller = more pixels are treated as edge blends")
        form.addRow("Colors", n_colors)
        form.addRow("Min. region size", min_region)
        form.addRow("Edge sensitivity", edge)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._cleanup_params = {"n_colors": n_colors.value(), "min_region": min_region.value(), "edge_threshold": edge.value()}
        self.apply_color_cleanup(**self._cleanup_params)

    def apply_color_cleanup(self, n_colors=8, min_region=6, edge_threshold=12.0):
        ctx = self.undo_manager.record_image_matrix("Clean Up Colors") if self.undo_manager else nullcontext()
        with ctx:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                self.data_handler.image_matrix = palette.pixel_art_cleanup(
                    self.data_handler.image_matrix, n_colors, min_region, edge_threshold)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
