from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtGui import QPixmap, QImage, QPixmap
import cv2
from HelperClasses import HatchData, ObservableList
import numpy as np

class DataHandler:
    def __init__(self, gui):
        self.gui = gui
        self.image_changed_callback_list = []  # List to hold callbacks for image changes (edits to original_image_matrix)
        self.image_resized_callback_list = []  # List to hold callbacks for image resizing

        #values to handle
        self._hatch_data = HatchData(None, None)
        self.pixel_per_mm = None
        self.default_pixel_per_mm = 96/25.4  # Default pixel per mm value (96 DPI / 25.4 mm/inch)
        self.image_matrix = None
        self.image_matrix_original = None
        self._image_matrix_original = None
        self.center_for_hatch = None
        self.contours_list=[]
        self.scale_factor = 1.0  # Scale factor between image and canvas display
        #overlay items from color editing are tracked here
        self.active_color_overlays = ObservableList(on_change=self.update_imprint_button)

        #masks
        self.masks_list = [] # List of mask matrices
        self.mask_info = []  # List of mask info dictionaries
        self.active_mask_index = -1  # Index of the currently active mask
        self.mask_overlays = [] # List of QGraphicsRectItem overlays

    #create a watcher for the original image matrix. When the original image matrix is changed it means a new image was loaded.
    @property
    def image_matrix_original(self):
        return self._image_matrix_original
      
    @image_matrix_original.setter
    def image_matrix_original(self, new_value):
        self._image_matrix_original = new_value
        # call all callbacks in the list to notfiy the fucntions that the image has changed
        for callback in self.image_changed_callback_list:
            callback() 
    
    def add_image_changed_callback(self, callback):
        """Add a callback to be called when the image changes."""
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

    #create a watcher for image_matrix. When image_matrix is updated, display the image
    @property
    def image_matrix(self):
        return self._image_matrix

    @image_matrix.setter
    def image_matrix(self, new_value):
        self._image_matrix = new_value
        self.set_and_display_image()

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
            if self._image_matrix is None or (self._image_matrix.size == 1 and self._image_matrix.item() is None):
                return

            # Get the image dimensions in pixels
            height_px, width_px = self.image_matrix.shape[:2]

            # Fast preview resize using OpenCV
            image_array = np.array(self.image_matrix, dtype=np.uint8)
            image_qt = QImage(image_array.data, width_px, height_px, width_px * 3, QImage.Format.Format_RGB888)
            
            # Display the image at native resolution
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
            print(f"Error displaying image: {e}")

    def update_active_hatch_label(self):
        self.gui.active_hatch_label.setText("Active: " + self._hatch_data.type)
    
    def update_imprint_button(self):
        if self.active_color_overlays:
            self.gui.imprint_color_overlays_button.setEnabled(True)
        else:
            self.gui.imprint_color_overlays_button.setEnabled(False)
    
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
            
            # Get the image matrix
            img = self.image_matrix
            
            # Handle different image formats
            if len(img.shape) == 3 and img.shape[2] == 3:
                # RGB image - reshape to 2D where each row is a color (R, G, B)
                # This allows us to use unique on rows instead of individual pixels
                # Reshape to (height*width, 3) and get unique rows
                reshaped = img.reshape(-1, img.shape[2])
                # Convert to structured array for efficient unique counting
                struct_array = np.ascontiguousarray(reshaped).view(np.dtype((np.void, reshaped.dtype.itemsize * reshaped.shape[1])))
                unique_colors = np.unique(struct_array)
                return len(unique_colors)
            elif len(img.shape) == 2:
                # Grayscale image
                return len(np.unique(img))
            else:
                # Handle other formats by flattening
                return len(np.unique(img))
                
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
    
