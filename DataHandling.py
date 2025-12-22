from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtGui import QPixmap, QImage, QPixmap
import cv2
from HelperClasses import HatchData

class DataHandler:
    def __init__(self, gui):
        self.gui = gui
        self.image_canvas = self.gui.image_canvas
        self.export_frame = self.gui.export_frame
        self.active_hatch_label = self.gui.active_hatch_label
        self.image_scene = gui.image_scene
        self.image_item = gui.image_item
        self.image_changed_callback_list = []  # List to hold callbacks for image changes
        self.image_resized_callback_list = []  # List to hold callbacks for image resizing

        #values to handle
        self._hatch_data = HatchData(None, None)
        self.pixel_per_mm = None
        self.pixel_per_mm_original = None
        self.image_matrix = None
        self._image_matrix_adjusted = None  # Use underscore to indicate "private" variable
        self.image_matrix_original = None
        self._image_matrix_original = None
        self.image_original = None
        self.center_for_hatch = None
        self.contours = None
        self._contours=None
        self.contours_list=[]
        # self.image_scaling=1 #depreciated
        self._masked_pixels_list=[]

        #masks
        self.masks_list = []  # List of mask matrices
        self.mask_overlays = []  # List of QGraphicsRectItem overlays

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
    
    #create a watcher for pixel_per_mm. 
    @property
    def pixel_per_mm(self):
        return self._pixel_per_mm
    
    @pixel_per_mm.setter
    def pixel_per_mm(self, new_value):
        self._pixel_per_mm = new_value
        for callback in self.image_resized_callback_list:
            callback()
    
    def add_image_resized_callback(self, callback):
        """Add a callback to be called when the image is resized."""
        if callable(callback):
            self.image_resized_callback_list.append(callback)
        else:
            raise ValueError("Callback must be callable")

    #create a watcher for image_matrix. When image_matrix is updated, display the image
    @property
    def image_matrix_adjusted(self):
        return self._image_matrix_adjusted

    @image_matrix_adjusted.setter
    def image_matrix_adjusted(self, new_value):
        self._image_matrix_adjusted = new_value
        self.set_and_display_image(sender='image')
    
    #create a watcher for masked_pixels_list. 
    @property
    def masked_pixels_list(self):
        return self._masked_pixels_list
    
    @masked_pixels_list.setter
    def masked_pixels_list(self, new_value):
        if len(new_value)>=len(self._masked_pixels_list):
            sender = 'mask'
        else:
            sender = 'image'
        self._masked_pixels_list = new_value
        self.set_and_display_image(sender=sender)

    #create a watcher for contours
    @property
    def contours(self):
        return self._contours
    
    @contours.setter
    def contours(self, new_value):
        self._contours = new_value
        self.set_and_display_image(sender='contour')

    #create a watcher for the hatch_data type. when it is changed, update the active_hatch_label
    @property
    def hatch_data(self):
        return self._hatch_data
    
    @hatch_data.setter
    def hatch_data(self, new_value):
        self._hatch_data = new_value
        self.update_active_hatch_label()

    def set_and_display_image(self, sender = 'image', *args):
        try:
            if self._image_matrix_adjusted is None or (self._image_matrix_adjusted.size == 1 and self._image_matrix_adjusted.item() is None):
                return
            
            #put all image edits together depending on the sender

            #start with adjusted image and first apply the pixel masking
            if sender == 'mask':
                if self.masked_pixels_list:
                    self.image_matrix= self.mask_pixels(self.image_matrix.copy(), self.masked_pixels_list, only_last=True)
            else:
                #if self.masked_pixels_list:
                self.image_matrix= self.mask_pixels(self._image_matrix_adjusted.copy(), self.masked_pixels_list)

            #then write the contours into the image
            if self.contours:
                cv2.drawContours(self.image_matrix, self.contours[2], contourIdx=-1, color=self.contours[0], thickness=self.contours[1])

            # Get the image dimensions in pixels
            height_px, width_px = self.image_matrix.shape[:2]

            # Convert image’s actual width to mm
            width_mm = width_px / self.pixel_per_mm
            height_mm = height_px / self.pixel_per_mm

            # Get the current zoom scale from the canvas transform
            transform = self.gui.image_canvas.transform()
            zoom_scale = transform.m11()  # Get the x-scale factor from the transform matrix
            zoom_scale = 1
            #rescale the display width (in pixels) with the images original pixel per mm to reflect a change in pixel sizes change
            display_width_px = int(width_mm * zoom_scale * self.pixel_per_mm_original)
            display_height_px = int(height_mm * zoom_scale * self.pixel_per_mm_original)
            #create an Image object from the image matrix
            image = Image.fromarray(self.image_matrix)

            # Determine the resampling filter based on the Pillow version
            if hasattr(Image, 'Resampling'):
                # For Pillow 9.1.0 and above
                resample_filter = Image.Resampling.LANCZOS
            else:
                # For older versions of Pillow
                resample_filter = Image.ANTIALIAS  # Or Image.LANCZOS

            #this resizes the image to account for dpi scaling
            image_resized = image.resize((display_width_px, display_height_px), resample=resample_filter)

            # Convert to QImage for display in PyQt6
            image_resized = image_resized.convert("RGB")
            image_qt = QImage(image_resized.tobytes(), image_resized.width, image_resized.height, image_resized.width * 3, QImage.Format.Format_RGB888)
            self.image_item.setPixmap(QPixmap.fromImage(image_qt))
            self.image_canvas.setSceneRect(0, 0, display_width_px, display_height_px)

        except Exception as e:
            print(f"Error displaying image: {e}")
    
    def mask_pixels(self, image_matrix, masked_pixel_list, only_last=False):

        # Get the image dimensions in pixels
        height_px, width_px = image_matrix.shape[:2]
        # If we have 4 channels, we'll set alpha to 0. If we have 3 channels, we can set them to white (or black).
        channels = image_matrix.shape[2] if len(image_matrix.shape) > 2 else 1
        
        # Define a helper to set the pixel "masked"
        def set_masked(px, py, color=[255,255,255]):
            if 0 <= px < width_px and 0 <= py < height_px:
                if channels == 4:
                    # RGBA: set alpha to 0
                    image_matrix[py, px, 3] = 0
                elif channels == 3:
                    # RGB: set to white (or black, or whatever "no color" means in your case)
                    image_matrix[py, px] = color
                else:
                    # Grayscale: set to 255 (white)
                    image_matrix[py, px] = 255

        if only_last:
            #only mask the last entry in the list
            masked_pixel_list = [masked_pixel_list[-1]]

        for masked_pixels in masked_pixel_list:
            for idx, pixel in enumerate(masked_pixels):
                if idx==0:
                    continue #first entry specifices the color of the mask
                set_masked(pixel[0], pixel[1], masked_pixels[0])

        return image_matrix

    def update_active_hatch_label(self):
        self.active_hatch_label.setText("Active: " + self._hatch_data.type)
    
    def reset_edits(self):
        self._contours=None
        self.contours_list = []
        #self._masked_pixels_list = []
    
    def canvas_to_image_coords(self, x_canvas, y_canvas):
        image_matrix = self.image_matrix

        # Dimensions of the underlying image data
        height_px, width_px = image_matrix.shape[:2]

        # These are the final display dimensions used in display_image()
        width_mm = width_px / self.pixel_per_mm
        height_mm = height_px / self.pixel_per_mm
        display_width_px = int(width_mm * self.pixel_per_mm_original)
        display_height_px = int(height_mm * self.pixel_per_mm_original)

        # Compute the scaling factors between the displayed image and the original
        if width_px == 0 or height_px == 0:
            return
        scale_x = display_width_px / width_px
        scale_y = display_height_px / height_px

        # Use the graphics view's built-in method to convert viewport to scene coordinates
        scene_point = self.gui.image_canvas.mapToScene(int(x_canvas), int(y_canvas))
        
        # Get the image item position (in scene coordinates)
        img_pos = self.gui.image_item.pos()
        
        # Actual click coordinates relative to the top-left of the image item in scene coords
        click_x_display = scene_point.x() - img_pos.x()
        click_y_display = scene_point.y() - img_pos.y()

        # Convert display coords to original image coords
        x_img = int(click_x_display / scale_x)
        y_img = int(click_y_display / scale_y)

        return x_img, y_img

    def image_to_canvas_coords(self, x_img, y_img):
        """Convert image coordinates to canvas coordinates"""
        try:
            image_matrix = self.image_matrix

            # Dimensions of the underlying image data
            height_px, width_px = image_matrix.shape[:2]

            # These are the final display dimensions (without zoom - zoom is at scene level)
            width_mm = width_px / self.pixel_per_mm
            height_mm = height_px / self.pixel_per_mm
            display_width_px = int(width_mm * self.pixel_per_mm_original)
            display_height_px = int(height_mm * self.pixel_per_mm_original)

            # Compute the scaling factors between the displayed image and the original
            if width_px == 0 or height_px == 0:
                return
            scale_x = display_width_px / width_px
            scale_y = display_height_px / height_px

            # Get the image item position in scene coordinates
            img_pos = self.gui.image_item.pos()

            # Calculate display coordinates from image coordinates
            display_x = x_img * scale_x
            display_y = y_img * scale_y
            
            # Calculate scene coordinates (add image item offset)
            scene_x = display_x + img_pos.x()
            scene_y = display_y + img_pos.y()
            
            # Use the graphics view's built-in method to convert scene to viewport coordinates
            scene_point = QtCore.QPointF(scene_x, scene_y)
            viewport_point = self.gui.image_canvas.mapFromScene(scene_point)
            
            return viewport_point.x(), viewport_point.y()
        
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

            # Dimensions of the underlying image data
            image_matrix = self.image_matrix
            height_px, width_px = image_matrix.shape[:2]

            # These are the final display dimensions used in display_image()
            width_mm = width_px / self.pixel_per_mm
            height_mm = height_px / self.pixel_per_mm
            display_width_px = int(width_mm * self.pixel_per_mm_original)
            display_height_px = int(height_mm * self.pixel_per_mm_original)

            # Compute the scaling factors between the displayed image and the original
            if width_px == 0 or height_px == 0:
                return
            scale_x = display_width_px / width_px
            scale_y = display_height_px / height_px

            # Convert scene coords to original image coords
            x_img = int(rel_x_scene / scale_x)
            y_img = int(rel_y_scene / scale_y)

            return x_img, y_img

        except Exception as e:
            print(f"Error converting scene to image coordinates: {e}")
            return None
    
    def image_to_scene_coords(self, x_img, y_img):
        """Convert image coordinates to scene coordinates"""
        try:
            image_matrix = self.image_matrix

            # Dimensions of the underlying image data
            height_px, width_px = image_matrix.shape[:2]

            # These are the final display dimensions (without zoom - zoom is at scene level)
            width_mm = width_px / self.pixel_per_mm
            height_mm = height_px / self.pixel_per_mm
            display_width_px = int(width_mm * self.pixel_per_mm_original)
            display_height_px = int(height_mm * self.pixel_per_mm_original)

            # Compute the scaling factors between the displayed image and the original
            if width_px == 0 or height_px == 0:
                return
            scale_x = display_width_px / width_px
            scale_y = display_height_px / height_px

            # Calculate display coordinates from image coordinates
            display_x = x_img * scale_x
            display_y = y_img * scale_y

            # Get the image item position in scene coordinates
            img_pos = self.gui.image_item.pos()

            # Calculate scene coordinates (add image item offset)
            scene_x = display_x + img_pos.x()
            scene_y = display_y + img_pos.y()

            return scene_x, scene_y

        except Exception as e:
            print(f"Error converting image to scene coordinates: {e}")
            return None