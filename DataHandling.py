from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtGui import QPixmap, QImage
from core import image_doc, machine
import cv2
from HelperClasses import HatchData, ObservableList
import logging
import numpy as np
from UndoRedo import UndoRedoManager

log = logging.getLogger(__name__)

class DataHandler:
    def __init__(self, gui):
        self.gui = gui
        self.undo_manager = UndoRedoManager(gui, self)
        self.image_changed_callback_list = []  # called when another image document becomes active
        self.image_resized_callback_list = []  # List to hold callbacks for image resizing
        self.image_shape_changed_callback_list = []  # called when the pixel dimensions of image_matrix change

        #values to handle
        self._hatch_data = HatchData(None, None)
        self.active_document = None  # core.image_doc.ImageDocument shown on the canvas; owns pixels and pixel size
        self.machine_profile = machine.default_profile()  # core.machine.MachineProfile, chosen in the export tab
        self._displayed_shape = None
        self.default_pixel_per_mm = 96/25.4  # Default pixel per mm value (96 DPI / 25.4 mm/inch)
        self.center_for_hatch = None
        self.contours_list=[]
        self.scale_factor = 1.0  # Scale factor between image and canvas display
        # overlay items from color editing and drawable overlays are tracked here
        self.active_color_overlays = ObservableList(on_change=self.update_color_ovleray_imprint_button)
        self.text_overlays = ObservableList(on_change=self.update_tg_ovleray_imprint_button)
        self.geometry_overlays = ObservableList(on_change=self.update_tg_ovleray_imprint_button)

        # masks
        self.masks_list = [] # List of mask matrices
        self.mask_info = []  # List of mask info dictionaries
        self.active_mask_index = -1  # Index of the currently active mask
        self.mask_overlays = [] # List of QGraphicsRectItem overlays

    def set_active_document(self, document):
        """Make `document` (or None) the active image and notify the image-changed callbacks."""
        self.active_document = document
        if document is None:
            self.gui.image_item.setPixmap(QPixmap())
            self._displayed_shape = None
        else:
            self.set_and_display_image()
        for callback in self.image_changed_callback_list:
            callback()

    # The active document is the single source of truth: these properties read/write it directly.
    @property
    def image_matrix(self):
        return self.active_document.image_matrix if self.active_document is not None else None

    @image_matrix.setter
    def image_matrix(self, new_value):
        if self.active_document is None:
            log.warning("image_matrix set without an active document - ignored")
            return
        self.active_document.image_matrix = image_doc.normalize(new_value)  # RGBA with binary alpha, see core/image_doc.py
        self.set_and_display_image()

    @property
    def image_matrix_original(self):
        return self.active_document.original_image_matrix if self.active_document is not None else None

    @property
    def pixel_per_mm(self):
        return self.active_document.pixel_per_mm if self.active_document is not None else None

    @pixel_per_mm.setter
    def pixel_per_mm(self, new_value):
        if self.active_document is not None:
            self.active_document.pixel_per_mm = new_value

    def add_image_changed_callback(self, callback):
        """Add a callback to be called when another image becomes active."""
        if callable(callback):
            self.image_changed_callback_list.append(callback)
        else:
            raise ValueError("Callback must be callable")

    #add a callback list for image resized. These are called when the image display size changes (if scale factor is updated, and AFTER the image has been redrawn)
    def add_image_resized_callback(self, callback):
        """Add a callback to be called when the image is resized."""
        if callable(callback):
            self.image_resized_callback_list.append(callback)
        else:
            raise ValueError("Callback must be callable")

    #create a watcher for the hatch_data type. when it is changed, update the active_hatch_label
    @property
    def hatch_data(self):
        return self._hatch_data
    
    @hatch_data.setter
    def hatch_data(self, new_value):
        self._hatch_data = new_value
        self.update_active_hatch_label()

    def set_and_display_image(self, *args):
        try:
            if self.image_matrix is None:
                return

            # Get the image dimensions in pixels
            height_px, width_px = self.image_matrix.shape[:2]

            # B17: masks etc. are pixel matrices of the displayed size -> notify when it changes
            if self._displayed_shape is not None and self._displayed_shape != (height_px, width_px):
                for callback in self.image_shape_changed_callback_list:
                    callback()
            self._displayed_shape = (height_px, width_px)

            image_array = np.ascontiguousarray(self.image_matrix)
            image_qt = QImage(image_array.data, width_px, height_px, width_px * 4, QImage.Format.Format_RGBA8888)

            # Display the image at native resolution (the canvas draws a checkerboard behind transparent pixels)
            self.gui.image_item.setPixmap(QPixmap.fromImage(image_qt))
            
            # Calculate display scale based on pixel_per_mm ratio
            # This determines how large pixels appear on the canvas
            #self.scale_factor =  self.pixel_per_mm_original / self.pixel_per_mm if self.pixel_per_mm_original else 1.0
            scale_factor =  self.default_pixel_per_mm / self.pixel_per_mm 
            
            # Apply the scale to the image item (visual zoom only, no pixel data change)
            self.gui.image_item.setScale(scale_factor)
            
            # Update scene rect to account for the scaled display
            display_width_px = width_px * scale_factor
            display_height_px = height_px * scale_factor
            self.gui.image_canvas.setSceneRect(0, 0, display_width_px, display_height_px)

            #notify resize if scale factor changed
            if self.scale_factor != scale_factor:
                self.scale_factor = scale_factor
                for callback in self.image_resized_callback_list:
                    callback()

            #update the color count label
            unique_color_count = self.get_unique_color_count()
            self.gui.number_of_colors_label.setText(f"#Colors: {unique_color_count}")

        except Exception as e:
            log.exception("Error displaying image")

    def update_active_hatch_label(self):
        self.gui.active_hatch_label.setText("Active: " + self._hatch_data.type)
    
    def update_color_ovleray_imprint_button(self):
        # if self.active_color_overlays or self.text_overlays or self.geometry_overlays:
        if self.active_color_overlays:
            self.gui.imprint_color_overlays_button.setEnabled(True)
        else:
            self.gui.imprint_color_overlays_button.setEnabled(False)
    
    def update_tg_ovleray_imprint_button(self):
        if self.text_overlays or self.geometry_overlays:
            self.gui.imprint_selected_tg_overlays_button.setEnabled(True)
        else:
            self.gui.imprint_selected_tg_overlays_button.setEnabled(False)
    
    def reset_edits(self):
        self.contours_list = []
    
    def get_unique_color_count(self):
        """Get the number of unique colors in the image matrix efficiently.
        
        Returns:
            int: Number of unique colors in the image
        """
        try:
            if self.image_matrix is None:
                return 0
            
            # opaque colours only (transparent background is not a colour); one uint32 per RGBA pixel
            img = np.ascontiguousarray(self.image_matrix)
            packed = img.view(np.uint32).reshape(-1)
            return len(np.unique(packed[img[..., 3].reshape(-1) > 0]))
                
        except Exception as e:
            print(f"Error getting unique color count: {e}")
            return 0
    
    #Coordinate conversion functions
    def canvas_to_image_coords(self, x_canvas, y_canvas):
        """Convert canvas (viewport) coordinates to image coordinates"""

        # Use the graphics view's built-in method to convert viewport to image coordinates
        image_pos = self.gui.image_item.mapFromScene(self.gui.image_canvas.mapToScene(int(x_canvas), int(y_canvas)))

        x_img = int(image_pos.x())
        y_img = int(image_pos.y())

        return x_img, y_img

    def image_to_canvas_coords(self, x_img, y_img):
        """Convert image coordinates to canvas coordinates"""
        try:
            # Use the graphics item's built-in method to convert image to scene coordinates            
            canvas_pos = self.gui.image_canvas.mapFromScene(self.gui.image_item.mapToScene(int(x_img), int(y_img)))

            return canvas_pos.x(), canvas_pos.y()
        
        except Exception as e:
            print(f"Error converting image to canvas coordinates: {e}")
            return None
    
    def canvas_to_scene_coords(self, x_canvas, y_canvas):
        """Convert canvas (viewport) coordinates to scene coordinates"""
        try:
            # Use the graphics view's built-in method to convert viewport to scene coordinates
            scene_point = self.gui.image_canvas.mapToScene(int(x_canvas), int(y_canvas))
            return scene_point.x(), scene_point.y()
        except Exception as e:
            print(f"Error converting canvas to scene coordinates: {e}")
            return None
    
    def scene_to_canvas_coords(self, x_scene, y_scene):
        """Convert scene coordinates to canvas (viewport) coordinates"""
        try:
            scene_point = QtCore.QPointF(x_scene, y_scene)
            viewport_point = self.gui.image_canvas.mapFromScene(scene_point)
            return viewport_point.x(), viewport_point.y()
        except Exception as e:
            print(f"Error converting scene to canvas coordinates: {e}")
            return None
    
    def scene_to_image_coords(self, x_scene, y_scene):
        """Convert scene coordinates to image coordinates"""
        try:
            # Get the image item position (in scene coordinates)
            img_pos = self.gui.image_item.pos()

            # Actual coordinates relative to the top-left of the image item in scene coords
            rel_x_scene = x_scene - img_pos.x()
            rel_y_scene = y_scene - img_pos.y()

            # Use the stored scale factor
            scale_factor = self.scale_factor

            # Convert scene coords to original image coords
            x_img = int(rel_x_scene / scale_factor)
            y_img = int(rel_y_scene / scale_factor)

            return x_img, y_img

        except Exception as e:
            print(f"Error converting scene to image coordinates: {e}")
            return None
    
    def image_to_scene_coords(self, x_img, y_img):
        """Convert image coordinates to scene coordinates"""
        try:
            # Calculate display coordinates from image coordinates using scale factor
            display_x = x_img * self.scale_factor
            display_y = y_img * self.scale_factor

            # Get the image item position in scene coordinates
            img_pos = self.gui.image_item.pos()

            # Calculate scene coordinates (add image item offset)
            scene_x = display_x + img_pos.x()
            scene_y = display_y + img_pos.y()

            return scene_x, scene_y

        except Exception as e:
            print(f"Error converting image to scene coordinates: {e}")
            return None
    
