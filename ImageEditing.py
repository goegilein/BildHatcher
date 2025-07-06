from PyQt6 import QtWidgets, QtCore, QtGui
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
        self.data_handler.add_image_changed_callback(self.restore_original_color)

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
        self.data_handler.image_matrix_adjusted = image_matrix

    def get_handler_data(self):
        self.image_matrix_base = self.data_handler.image_matrix.copy()

from PyQt6 import QtWidgets, QtCore, QtGui
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
import numpy as np
import collections

class ImageColorer(QtCore.QObject):
    
    def __init__(self, data_handler, gui):
        super().__init__()  # Call the superclass constructor
        self.data_handler = data_handler
        self.gui = gui
        self.updating_scaling = False  # Flag to control trace callback
        self.grid_on = False  # Flag to control grid drawing
        self.masking_on = False  # toggle flag for masking
        self.masked_pixels_list = [[]]  # list to store masked pixels
        self.choose_color_on = False
        self.contours_visible = False
        self.contours = []
        self.contours_list = []
        self.active_color = [255, 255, 255]
        self.fill_color_on = False
        self.replace_color_on = False

        # Add a label, input field and toggle button for masking the image
        self.toggle_draw_button = gui.toggle_draw_button
        self.toggle_draw_button.clicked.connect(self.toggle_masking)

        self.pen_width_label = gui.pen_width_label
        self.pen_width_spinbox = gui.pen_width_spinbox
        self.pen_width_spinbox.setValue(1)

        # Add a label, input field and toggle button for filling a color patch in the image
        self.fill_color_button = gui.fill_color_button
        self.fill_color_button.clicked.connect(self.toggle_fill)

        # Add a label, input field and toggle button for replacing a color in the image
        self.replace_color_button = gui.replace_color_button
        self.replace_color_button.clicked.connect(self.toggle_replace_color)

        # Bind left-click for masking (down + drag + release)
        self.gui.image_canvas.viewport().installEventFilter(self)

        # Button: select color from a color palette
        self.select_color_button = gui.select_color_button
        self.select_color_button.clicked.connect(self.select_color)

        # Button: pick color from image
        self.pick_from_image_button = gui.pick_from_image_button
        self.pick_from_image_button.clicked.connect(self.toggle_choose_color)

        #Button: pick color from database
        self.pick_from_db_button = gui.pick_from_db_button
        self.pick_from_db_button.clicked.connect(self.select_color_from_db)

        # Label to display chosen color and initialize it
        self.color_edit = gui.color_edit
        self.show_chosen_color()

        # Add buttons to restore and undo mask steps original image
        self.restore_unmasked_image_button = gui.restore_unmasked_image_button
        self.restore_unmasked_image_button.clicked.connect(self.restore_unmasked_image)

        self.undo_masking_button = gui.undo_masking_button
        self.undo_masking_button.clicked.connect(self.undo_masking)

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

        #Add button and labels for data base recoloring
        self.recolor_from_database_button = gui.recolor_from_database_button
        self.recolor_from_database_button.clicked.connect(self.recolor_color_from_db)
        self.recolor_laser_label = gui.recolor_laser_label
        self.recolor_material_label = gui.recolor_material_label
        self.recolor_type_label = gui.recolor_type_label

        #Add button to clean up image colors
        self.clean_up_image_colors_button = gui.clean_up_image_colors_button
        self.clean_up_image_colors_button.clicked.connect(self.clean_up_image_colors)

        # Bind some hotkeys
        #self.gui.installEventFilter(self)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.on_canvas_click(event)
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            self.drag_mask(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.stop_mask(event)
        return super().eventFilter(source, event)

    def on_canvas_click(self, event):
        if self.choose_color_on:
            self.choose_color(event)
            self.pick_from_image_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        elif self.masking_on:
            self.start_mask(event)
        elif self.fill_color_on:
            self.fill_color_patch(event)
        else:
            self.replace_color(event)
            self.replace_color_button.setChecked(False)
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def toggle_choose_color(self, event=None):
        # Enable picking from canvas
        self.choose_color_on = not self.choose_color_on
        self.masking_on = False
        self.fill_color_on = False
        self.replace_color_on = False
        self.pick_from_image_button.setChecked(self.choose_color_on)
        self.toggle_draw_button.setChecked(False)
        self.fill_color_button.setChecked(False)
        self.replace_color_button.setChecked(False)
        self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.PointingHandCursor if self.choose_color_on else QtCore.Qt.CursorShape.ArrowCursor)

    def toggle_masking(self, event=None):
        self.masking_on = not self.masking_on
        self.choose_color_on = False
        self.fill_color_on = False
        self.replace_color_on = False
        self.pick_from_image_button.setChecked(False)
        self.toggle_draw_button.setChecked(self.masking_on)
        self.fill_color_button.setChecked(False)
        self.replace_color_button.setChecked(False)
        self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if self.masking_on else QtCore.Qt.CursorShape.ArrowCursor)

    def toggle_fill(self, event=None):
        self.fill_color_on = not self.fill_color_on
        self.choose_color_on = False
        self.masking_on = False
        self.replace_color_on = False
        self.pick_from_image_button.setChecked(False)
        self.toggle_draw_button.setChecked(False)
        self.fill_color_button.setChecked(self.fill_color_on)
        self.replace_color_button.setChecked(False)
        self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if self.fill_color_on else QtCore.Qt.CursorShape.ArrowCursor)

    def toggle_replace_color(self, event=None):
        self.replace_color_on = not self.replace_color_on
        self.choose_color_on = False
        self.masking_on = False
        self.fill_color_on = False
        self.pick_from_image_button.setChecked(False)
        self.toggle_draw_button.setChecked(False)
        self.fill_color_button.setChecked(False)
        self.replace_color_button.setChecked(self.replace_color_on)
        self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor if self.replace_color_on else QtCore.Qt.CursorShape.ArrowCursor)

    def reset_toggle_buttons(self, event=None):
        self.choose_color_on = False
        self.masking_on = False
        self.fill_color_on = False
        self.replace_color_on = False
        self.pick_from_image_button.setChecked(False)
        self.toggle_draw_button.setChecked(False)
        self.fill_color_button.setChecked(False)
        self.replace_color_button.setChecked(False)
        self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def start_mask(self, event):
        if self.masking_on:
            self.masked_pixels_list.append([self.active_color])  # create a new entry in the pixel list when starting a new mask
            self.apply_mask(event)

    def drag_mask(self, event):
        if self.masking_on:
            self.apply_mask(event)

    def stop_mask(self, event):
        if self.masking_on:
            pass

    def apply_mask(self, event):
        """
        Apply Mask to clicked pixel of current image in data handler. store masked pixels for later use.
        Pass image matrix with applied mask to DataHandler for visualization of each masking step
        Do a full image calculation only on button release
        """
        image_matrix = self.data_handler.image_matrix
        # Convert canvas coords to image coords, then mask those pixels
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        radius = self.pen_width_spinbox.value() - 1
        masked_pixel = self.get_mask_pixels(image_matrix, x_canvas, y_canvas, radius)

        self.masked_pixels_list[-1] += masked_pixel

        self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()

    def restore_unmasked_image(self):
        self.masked_pixels_list = [[]]
        self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()

    def undo_masking(self, event=None):
        if len(self.masked_pixels_list) > 2:
            self.masked_pixels_list.pop()
            self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()
        else:
            self.restore_unmasked_image()

    def get_mask_pixels(self, image_matrix, x_canvas, y_canvas, radius):
        """Mask pixels in a radius around (x_canvas, y_canvas) on the displayed image."""
        if image_matrix is None:
            return []

        mask_pixels = []

        # calc image coordinates from canvas click
        x_img, y_img = self.canvas_to_image_coords(x_canvas, y_canvas)

        # Circular mask around (x_img, y_img)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    px = x_img + dx
                    py = y_img + dy
                    mask_pixels.append([px, py])

        return mask_pixels

    def canvas_to_image_coords(self, x_canvas, y_canvas):
        image_matrix = self.data_handler.image_matrix

        # Dimensions of the underlying image data
        height_px, width_px = image_matrix.shape[:2]

        # These are the final display dimensions used in display_image()
        width_mm = width_px / self.data_handler.pixel_per_mm
        height_mm = height_px / self.data_handler.pixel_per_mm
        display_width_px = int(width_mm * self.data_handler.image_scaling * self.data_handler.pixel_per_mm_original)
        display_height_px = int(height_mm * self.data_handler.image_scaling * self.data_handler.pixel_per_mm_original)

        # Compute the scaling factors between the displayed image and the original
        if width_px == 0 or height_px == 0:
            return
        scale_x = display_width_px / width_px
        scale_y = display_height_px / height_px

        # Get canvas dimensions
        canvas_width = self.gui.image_canvas.viewport().width()
        canvas_height = self.gui.image_canvas.viewport().height()
        x_center = canvas_width / 2
        y_center = canvas_height / 2

        #get offset of the image item
        img_offset_x = self.gui.image_item.x()
        img_offset_y = self.gui.image_item.y()

        #finally we need the state of the invisible scroll bars of the scene to offset its position
        scrollbar_x = self.gui.image_canvas.horizontalScrollBar()
        scrollbar_y = self.gui.image_canvas.verticalScrollBar()

        scrollbar_pos_x = scrollbar_x.value()
        scrollbar_pos_y = scrollbar_y.value()

        scrollbar_mean_x= (scrollbar_x.maximum()-scrollbar_x.minimum())/2
        scrollbar_mean_y = (scrollbar_y.maximum()-scrollbar_y.minimum())/2

        scrollbar_offset_x = scrollbar_pos_x-scrollbar_mean_x
        scrollbar_offset_y = scrollbar_pos_y-scrollbar_mean_y
        
        # Actual click coordinates relative to the top-left of the displayed image
        click_x_display = x_canvas - x_center + display_width_px / 2 - img_offset_x + scrollbar_offset_x
        click_y_display = y_canvas - y_center + display_height_px / 2 - img_offset_y + scrollbar_offset_y

        # Convert display coords to original image coords
        x_img = int(click_x_display / scale_x)
        y_img = int(click_y_display / scale_y)

        return x_img, y_img

    def select_color(self):
        # Open color chooser
        color_code = QtWidgets.QColorDialog.getColor()
        if color_code.isValid():
            self.active_color = [color_code.red(), color_code.green(), color_code.blue()]
            self.show_chosen_color()

    def select_color_from_db(self):
        def on_color_received(color_data):
            """Callback to handle the selected color from the database."""
             # 1. Get the color string from the dictionary
            color_string = color_data['color_rgb']  # e.g., "255,0,0"

            # 2. Split the string by the comma and convert each part to an integer
            self.active_color = [int(c) for c in color_string.split(',')]
            self.show_chosen_color()
            
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
        x_img, y_img = self.canvas_to_image_coords(x_canvas, y_canvas)

        # Ensure click is within image bounds
        if 0 <= x_img < width_px and 0 <= y_img < height_px:
            r, g, b = image_matrix[y_img, x_img]
            self.active_color = [int(r), int(g), int(b)]
            self.show_chosen_color()

        # Disable pick mode after one pick
        self.choose_color_on = False

    def show_chosen_color(self):
        color = QtGui.QColor(*self.active_color)
        opposite_color = QtGui.QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())
        color_string = f"R{color.red()}, G{color.green()}, B{color.blue()}"
        self.color_edit.setText(color_string)
        self.color_edit.setStyleSheet(f"color: {opposite_color.name()}; background-color: {color.name()}")

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

    def fill_color_patch(self, event):
        """
        Flood-fill for all connected pixels sharing the clicked color.
        Returns a list of [px, py] for all changed (filled) pixels.
        """
        if not self.fill_color_on:
            return

        if self.data_handler.image_matrix is None:
            return []
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        x_img, y_img = self.canvas_to_image_coords(x_canvas, y_canvas)

        image = self.data_handler.image_matrix.copy()
        height, width = image.shape[:2]
        if not (0 <= x_img < width and 0 <= y_img < height):
            return []

        old_color = tuple(image[y_img, x_img])
        new_color = tuple(self.active_color)
        if old_color == new_color:
            return []

        masked_pixels = []
        queue = collections.deque()
        queue.append((y_img, x_img))

        while queue:
            cy, cx = queue.popleft()
            if 0 <= cy < height and 0 <= cx < width:
                if tuple(image[cy, cx]) == old_color:
                    image[cy, cx] = new_color
                    masked_pixels.append([cx, cy])

                    # 4-direction neighbors
                    queue.append((cy + 1, cx))
                    queue.append((cy - 1, cx))
                    queue.append((cy, cx + 1))
                    queue.append((cy, cx - 1))

        masked_pixels = [self.active_color] + masked_pixels

        self.masked_pixels_list.append(masked_pixels)
        self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()

    def replace_color(self, event):
        """
        Recolors all pixels matching old_color with self.active_color, regardless of connectivity.
        Returns a list of [px, py] for all changed pixels.
        """
        if not self.replace_color_on:
            return
        # disable replace color mode
        self.replace_color_on = False

        if self.data_handler.image_matrix is None:
            return []
        image = self.data_handler.image_matrix.copy()

        x_canvas = event.position().x()
        y_canvas = event.position().y()
        x_img, y_img = self.canvas_to_image_coords(x_canvas, y_canvas)

        old_color = tuple(image[y_img, x_img])

        mask = np.all(image == old_color, axis=-1)
        changed_coords = np.argwhere(mask)  # shape: (N, 2) for row, col

        # Convert (row, col) -> [col, row] for consistency
        masked_pixels = [[col, row] for row, col in changed_coords]
        masked_pixels = [self.active_color] + masked_pixels

        self.masked_pixels_list.append(masked_pixels)
        self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()

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
        
        #recolor the entire image
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
        
        # Update the data handler with the recolored image
        self.masked_pixels_list = [[]]
        self.data_handler.masked_pixels_list = self.masked_pixels_list.copy()
        #self.data_handler.image_matrix = recolored_image
        self.data_handler.image_matrix_adjusted = recolored_image
    
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

        
