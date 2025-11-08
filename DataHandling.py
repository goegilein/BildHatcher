from PIL import Image
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
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
        self.image_scaling=1
        self._masked_pixels_list=[]

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

            #rescale the display width (in pixels) with the images original pixel per mm to reflect a change in pixel sizes change
            display_width_px = int(width_mm * self.image_scaling * self.pixel_per_mm_original)
            display_height_px = int(height_mm * self.image_scaling * self.pixel_per_mm_original)

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
        display_width_px = int(width_mm * self.image_scaling * self.pixel_per_mm_original)
        display_height_px = int(height_mm * self.image_scaling * self.pixel_per_mm_original)

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

    def image_to_canvas_coords(self, x_img, y_img):
        """Convert image coordinates to canvas coordinates"""
        try:
            image_matrix = self.image_matrix

            # Dimensions of the underlying image data
            height_px, width_px = image_matrix.shape[:2]

            # These are the final display dimensions used in display_image()
            width_mm = width_px / self.pixel_per_mm
            height_mm = height_px / self.pixel_per_mm
            display_width_px = int(width_mm * self.image_scaling * self.pixel_per_mm_original)
            display_height_px = int(height_mm * self.image_scaling * self.pixel_per_mm_original)

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

            display_x = x_img * scale_x
            display_y = y_img * scale_y
            
            # Calculate canvas coordinates
            x_canvas = display_x + x_center - display_width_px / 2 + img_offset_x - scrollbar_offset_x
            y_canvas = display_y + y_center - display_height_px / 2 + img_offset_y - scrollbar_offset_y

            # # Calculate final canvas coordinates
            # x_canvas = display_x + (canvas_width - display_width_px) / 2 - scrollbar_offset_x
            # y_canvas = display_y + (canvas_height - display_height_px) / 2 - scrollbar_offset_y

            return x_canvas, y_canvas

        except Exception as e:
            print(f"Error converting image to canvas coordinates: {e}")
            return None