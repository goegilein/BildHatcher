from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QFileDialog, QListWidgetItem
from PyQt6.QtWidgets import QGraphicsLineItem
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QColor
from PIL import Image
import numpy as np
import io
from collections import defaultdict
from HelperClasses import ImgObj

class BaseFunctions:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.image_dimension_frame = gui.image_dimension_frame
        self.image_lister_frame = gui.image_lister_frame
        self.image_original = None
        self.image = None
        self.image_matrix = None
        self.default_dpi = 96  # Assuming 96 DPI by default
        self.pixel_per_mm = self.default_dpi / 25.4  # Image scaling in real space
        self.changeing_image = False
        self.updating_dimensions = False
        self.active_image_item = None

        # Create File Menu
        self.menubar = gui.menubar
        self.actionLoad_image = gui.actionLoad_Image
        self.actionLoad_image.triggered.connect(self.load_image)
        self.actionSave_image = gui.actionSave_Image
        self.actionSave_image.triggered.connect(self.save_image)
        self.actionReset_image = gui.actionReset_Image
        self.actionReset_image.triggered.connect(self.reset_image)

        # Add variable, label and entry field for image width (image dimension frame)
        self.width_spinbox = gui.width_spinbox
        self.width_spinbox.setRange(0, 10000)
        self.width_spinbox.editingFinished.connect(self.update_dimensions)

        # Add variable, label and entry field for image height (image dimension frame)
        self.height_spinbox = gui.height_spinbox
        self.height_spinbox.setRange(0, 10000)
        self.height_spinbox.editingFinished.connect(self.update_dimensions)

        # Add variable and check box for image ratio (image dimension frame)
        self.lock_ratio_check = gui.lock_ratio_check
        self.lock_ratio_check.setChecked(True)
        self.lock_ratio_check.setEnabled(False)

        #Add button to reset image size
        self.reset_image_size_button = gui.reset_image_size_button
        self.reset_image_size_button.clicked.connect(self.reset_image_size)

        # Add image button
        self.add_image_button = gui.add_image_button
        self.add_image_button.clicked.connect(self.add_image)

        # Keep changes button
        self.keep_changes_button = gui.keep_changes_button
        self.keep_changes_button.clicked.connect(self.keep_changes)

        # Remove image button
        self.remove_image_button = gui.remove_image_button
        self.remove_image_button.clicked.connect(self.remove_image)

        # Split color button
        self.split_color_button = gui.split_color_button
        self.split_color_button.clicked.connect(self.split_colors)

        # Combine image button
        self.combine_image_button = gui.combine_image_button
        self.combine_image_button.clicked.connect(self.combine_images)

        #Flip image button
        self.rot_image_180_button = gui.rot_image_180_button
        self.rot_image_180_button.clicked.connect(self.rot_image_180)

        # Monochrome check box
        self.monochrome_check = gui.monochrome_check

        # Add list to manage gCode_blocks
        self.images_ListWidget = gui.images_ListWidget

        # Bind event for selection change
        self.images_ListWidget.itemSelectionChanged.connect(self.change_image)

    def load_image(self, file_path):
        file_path, _ = QFileDialog.getOpenFileName()
        if file_path:
            try:
                # Open and convert image to RGB
                self.image_original = Image.open(file_path).convert('RGB')
                self.image = Image.open(file_path).convert('RGB')
                self.image_matrix = np.array(self.image)
                # Ensure image_matrix is (H, W, 3)
                if self.image_matrix.ndim == 2:
                    # Grayscale image, convert to RGB
                    self.image_matrix = np.stack([self.image_matrix]*3, axis=-1)
                elif self.image_matrix.shape[-1] != 3:
                    # Remove alpha or extra channels
                    self.image_matrix = self.image_matrix[..., :3]

                # Check if image has DPI info, otherwise use default
                dpi = self.image.info.get('dpi', (self.default_dpi, self.default_dpi))[0] if hasattr(self.image, 'info') else self.default_dpi
                self.pixel_per_mm = dpi / 25.4  # Update image
                self.pixel_per_mm_original = self.pixel_per_mm
                filename = file_path.split("/")[-1]
                self.changeing_image = True
                img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
                self.add_listbox_item(img_obj, filename, set_selected=True)
                self.changeing_image = False
                self.set_handler_data(new_image = True)
                self.update_dimension_fields()
            except Exception as e:
                print(f"Error loading image: {e}")

    def add_listbox_item(self, img_obj:ImgObj, name:str, set_selected=False):
        item = QListWidgetItem(name)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
        self.images_ListWidget.addItem(item)
        if set_selected:
            # Clear all selections and select only the new item
            self.images_ListWidget.clearSelection()
            item.setSelected(True)
            self.images_ListWidget.setCurrentItem(item)
            self.active_image_item = item

    def save_image(self):
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Image", "", "PNG Files (*.png);;BMP Files (*.bmp);;JPEG Files (*.jpg *.jpeg)"
        )
        if file_path:
            try:
                self.get_handler_data()
                image = Image.fromarray(self.image_matrix)
                # Calculate DPI from current pixel_per_mm
                dpi = round(self.pixel_per_mm * 25.4)
                # Save with DPI metadata (works for PNG, BMP, and JPEG)
                image.save(file_path, dpi=(dpi, dpi))
            except Exception as e:
                print(f"Error saving image: {e}")        

    def reset_image(self):
        self.image = self.image_original.copy()
        self.image_matrix = np.array(self.image)
        self.pixel_per_mm = self.default_dpi / 25.4  # Update image scaling
        self.set_handler_data(new_image=True)
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
        self.update_dimension_fields()

    def update_dimensions(self):
        sender =self.gui.sender()   
        if self.updating_dimensions:
            return
        try:
            self.get_handler_data()
            new_width_mm = float(self.width_spinbox.value())
            new_height_mm = float(self.height_spinbox.value())
            # new_width = new_width_mm * self.pixel_per_mm
            # new_height = new_height_mm * self.pixel_per_mm
            if self.lock_ratio_check.isChecked():  # If ratio is locked we simply rescale the DPI. This maintains the image information
                if sender == self.width_spinbox:#.hasFocus():
                    new_pixel_per_mm = self.image_matrix.shape[1] / new_width_mm
                    self.pixel_per_mm = new_pixel_per_mm
                else:
                    new_pixel_per_mm = self.image_matrix.shape[0] / new_height_mm
                    self.pixel_per_mm = new_pixel_per_mm
            else:
                new_width = new_width_mm * self.pixel_per_mm
                new_height = new_height_mm * self.pixel_per_mm
                self.image_matrix = np.array(Image.fromarray(self.image_matrix).resize((int(new_width), int(new_height))))
            self.set_handler_data(new_image = False)
            img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.update_dimension_fields()
        except Exception as e:
            print(f"Error updating dimensions: {e}")

    def update_dimension_fields(self):
        height, width = self.image_matrix.shape[:2]
        width_mm = width / self.pixel_per_mm
        height_mm = height / self.pixel_per_mm
        self.updating_dimensions = True
        self.width_spinbox.setValue(width_mm)
        self.height_spinbox.setValue(height_mm)
        self.updating_dimensions = False

    def reset_image_size(self):
        self.pixel_per_mm = self.pixel_per_mm_original
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
        self.set_handler_data(new_image = False)   
        self.update_dimension_fields()

    def split_colors(self):
        self.get_handler_data()
        current_image_matrix = np.array(self.image_matrix.copy())
        height, width, num_colors = current_image_matrix.shape
        clusters = defaultdict(lambda: np.ones((height, width, num_colors), dtype=np.uint8) * 255)

        # Find all unique colors (excluding white) and disply a warning if there are too many colors
        unique_colors = np.unique(current_image_matrix.reshape(-1, 3), axis=0)
        if len(unique_colors) > 10:
            reply = QtWidgets.QMessageBox.question(
                self.gui, "Too many colors",
                f"This image has {len(unique_colors)} different colors. "
                "Do you want to continue cleaning up the image.\nIt might take very long if more than 10 colors are present?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return

        # Find unique image colors
        for i in range(height):
            for j in range(width):
                color = tuple(current_image_matrix[i, j])
                if sum(np.array(color, dtype=np.uint64)) == 765:  # Skip the white channel
                    continue
                clusters[color][i, j] = np.array([color[0], color[1], color[2]])

        # Add the images to list
        self.changeing_image = True
        sel_image_item = self.images_ListWidget.selectedItems()[-1]
        image_name = sel_image_item.text()
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.add_listbox_item(img_obj, image_name + "_unsplit", set_selected=True)
        for color, cluster in clusters.items():
            img_obj = ImgObj(cluster, self.pixel_per_mm, self.pixel_per_mm_original)
            self.add_listbox_item(img_obj, str(color))
        self.changeing_image = False

    def add_image(self):
        self.get_handler_data()
        sel_image_item = self.active_image_item
        image_name = sel_image_item.text()
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.add_listbox_item(img_obj, image_name + "_edited", set_selected=True)

    def keep_changes(self):
        self.get_handler_data()
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
        self.set_handler_data(new_image = True)
    
    def rot_image_180(self):
        self.get_handler_data()
        self.image_matrix = np.flipud(np.fliplr(self.image_matrix))
        img_obj = ImgObj(self.image_matrix.copy(), self.pixel_per_mm, self.pixel_per_mm_original)
        self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
        self.set_handler_data(new_image = True)

    def remove_image(self):
        selected_items = self.images_ListWidget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            row = self.images_ListWidget.row(item)
            self.images_ListWidget.takeItem(row)
        if self.images_ListWidget.count() > 0:
            self.images_ListWidget.setCurrentRow(self.images_ListWidget.count() - 1)

    def change_image(self):
        if self.changeing_image:
            return

        sel_image_item = self.images_ListWidget.selectedItems()
        if not sel_image_item or len(sel_image_item) != 1:
            return
        self.changeing_image = True
        img_obj = sel_image_item[0].data(QtCore.Qt.ItemDataRole.UserRole)
        self.image = Image.fromarray(img_obj.image_matrix)
        self.image_matrix = img_obj.image_matrix.copy()
        self.pixel_per_mm = img_obj.pixel_per_mm
        self.pixel_per_mm_original = img_obj.pixel_per_mm_original
        self.data_handler.reset_edits()
        self.set_handler_data(new_image=True)
        self.update_dimension_fields()
        self.changeing_image = False
        self.active_image_item = sel_image_item[0]

    def combine_images(self):
        selected_images = self.images_ListWidget.selectedItems()
        combined_image = np.ones_like(selected_images[0].data(QtCore.Qt.ItemDataRole.UserRole), dtype=np.uint8) * 255
        avg_color = np.array([0, 0, 0])


        for image_item in selected_images:
            patch = image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            # Where patch is not white, compare to current combined
            mask = ~np.all(patch == 255, axis=-1)
            # For those pixels, if patch is darker, use it
            current = combined_image[mask]
            candidate = patch[mask]
            # Compare sum of RGB (lower is darker)
            darker = np.sum(candidate, axis=-1) < np.sum(current, axis=-1)
            # Update only where candidate is darker
            indices = np.where(mask)
            if len(indices[0]) > 0:
                darker_indices = np.where(darker)[0]
                for idx in darker_indices:
                    combined_image[indices[0][idx], indices[1][idx]] = candidate[idx]

        # Make the combined_image monochrome if checked (use avg_color)
        if self.monochrome_check.isChecked():
            white_mask = np.all(combined_image == [255, 255, 255], axis=-1)
            color_mask = ~white_mask
            combined_image[color_mask] = avg_color.astype(np.uint8)

        self.remove_image()
        img_obj = ImgObj(combined_image, self.pixel_per_mm, self.pixel_per_mm_original)
        self.add_listbox_item(img_obj, "combined", set_selected=True)

    def set_handler_data(self, new_image = False):
        self.data_handler.pixel_per_mm = self.pixel_per_mm
        self.data_handler.default_pixel_per_mm = self.default_dpi / 25.4
        self.data_handler.image_matrix = self.image_matrix.copy()
        if new_image:
            self.data_handler.image_original = self.image_original
            self.data_handler.image_matrix_original = self.image_matrix

    def get_handler_data(self):
        self.image_matrix = self.data_handler.image_matrix
    
class ImageMover(QtCore.QObject):
    def __init__(self, data_handler, event_handler, gui):
        super().__init__()
        self.data_handler = data_handler
        self.event_handler = event_handler
        self.gui = gui
        self.image_canvas = gui.image_canvas
        self.image_scene = gui.image_scene
        self.updating_scaling = False  # Flag to control trace callback
        self.grid_on = False  # Flag to control grid drawing
        self.masking_on = False  # toggle flag for masking
        self.masked_pixels = []  # currently masked pixels; put an empty list as start list
        self.masked_pixels_list = [[]]  # list to store masked pixels
        self.choose_color_on = False
        self.setting_image_center = False
        self.showing_image_center = False
        self.current_image_center = None  # x, y in image coordinates

        # Add a slider to control the display size
        self.zoom_slider = gui.zoom_slider
        self.zoom_slider.setRange(10, 1000)
        self.zoom_slider.setValue(100)  # Default to 100%
        self.zoom_slider.valueChanged.connect(self.update_zoom_from_slider)

        # Add a button to reset the zoom factor to 100%
        self.reset_zoom_button = gui.reset_zoom_button
        self.reset_zoom_button.clicked.connect(self.reset_zoom)

        # Add an entry field to control the display size
        self.zoom_spinbox = gui.zoom_spinbox
        self.zoom_spinbox.setRange(10, 1000)
        self.zoom_spinbox.setValue(100)
        self.zoom_spinbox.valueChanged.connect(self.update_zoom_from_spinbox)

        #Add a button to recenter the image
        self.recenter_image_button = gui.recenter_image_button
        self.recenter_image_button.clicked.connect(self.recenter_image)

        # Add label and entry field for grid distance
        self.grid_distance_label = gui.grid_distance_label
        self.grid_distance_spinbox = gui.grid_distance_spinbox
        self.grid_distance_spinbox.setValue(10)
        self.grid_distance_spinbox.valueChanged.connect(self.update_grid)

        # Add a toggle button for the grid
        self.grid_toggle_button = gui.grid_toggle_button
        self.grid_toggle_button.clicked.connect(self.toggle_grid)

        self.image_item = gui.image_item

        #Image Center
        self.h_center_spinbox = gui.h_center_spinbox
        self.v_center_spinbox = gui.v_center_spinbox
        self.reset_image_center_button = gui.reset_image_center_button
        self.set_image_center_button = gui.set_image_center_button
        self.show_image_center_button = gui.show_image_center_button
        self.reset_image_center_button.clicked.connect(self.reset_image_center_to_default)
        self.set_image_center_button.clicked.connect(self.toggle_set_image_center)
        self.show_image_center_button.clicked.connect(self.toggle_show_image_center)

        self.data_handler.add_image_changed_callback(self.reset_image_center_to_default)
        self.data_handler.add_image_resized_callback(self.reset_image_center_to_current)

        #Event callbacks for handling gui interactions
        self.event_handler.add_canvas_event_callback(self.trigger_canvas_event)

    def trigger_canvas_event(self, event):
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.RightButton:
            self.start_drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.RightButton:
            self.drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.RightButton:
            self.stop_drag(event)
        elif event.type() == QtCore.QEvent.Type.Wheel:
            self.on_mouse_wheel(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.set_image_center(event)


    def start_drag(self, event):
        self.image_canvas.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        self.drag_start_pos = event.pos()

    def drag(self, event, dx=0, dy=0):
        if event is not None:
            # Use the actual mouse event
            delta = event.pos() - self.drag_start_pos
        else:
            # Use passed-in deltas or default to zero
            delta = QtCore.QPoint(dx, dy)
        new_x = self.image_item.x() + delta.x()
        new_y = self.image_item.y() + delta.y()

        # Get item and viewport sizes
        item_rect = self.image_item.boundingRect()
        viewport_size = self.image_canvas.viewport().size()
        
        # Get the zoom scale from the canvas transform
        transform = self.image_canvas.transform()
        zoom_scale = transform.m11()  # Get the scale factor
        
        # Calculate dimensions
        unscaled_width = item_rect.width()
        unscaled_height = item_rect.height()
        scaled_width = unscaled_width * zoom_scale
        scaled_height = unscaled_height * zoom_scale
        
        viewport_width = viewport_size.width()
        viewport_height = viewport_size.height()

        # Clamp to prevent dragging off-canvas, ensuring canvas is always filled
        if scaled_width > viewport_width:
            # Image is larger than viewport - no gaps allowed
            # Convert viewport bounds to scene coordinates by dividing by zoom_scale
            max_x = (viewport_width - scaled_width) / zoom_scale
            new_x = max(max_x, min(new_x, 0))
        else:
            # Image is smaller than viewport - center it
            max_x = (viewport_width - scaled_width) / 2 / zoom_scale
            new_x = max(-max_x, min(new_x, max_x))
            
        if scaled_height > viewport_height:
            # Image is larger than viewport - no gaps allowed
            # Convert viewport bounds to scene coordinates by dividing by zoom_scale
            max_y = (viewport_height - scaled_height) / zoom_scale
            new_y = max(max_y, min(new_y, 0))
        else:
            # Image is smaller than viewport - center it
            max_y = (viewport_height - scaled_height) / 2 / zoom_scale
            new_y = max(-max_y, min(new_y, max_y))

        # Calculate the actual delta applied after clamping
        actual_delta_x = new_x - self.image_item.x()
        actual_delta_y = new_y - self.image_item.y()

        # Move the image item
        self.image_item.setPos(new_x, new_y)
        
        # Move all other items in the scene (grid lines, center cross, etc.)
        moved_items = set()  # Track items that have already been moved
        moved_items.add(self.image_item)

        for item in self.image_scene.items():
            if item != self.image_item:
                # Skip if this item is a child of an already moved item
                parent = item.parentItem()
                if parent and parent in moved_items:
                    continue
                
                if isinstance(item, QtWidgets.QGraphicsLineItem) and item.zValue() == 1:
                    #this is a grid line. dont move those!
                    continue
                current_pos = item.pos()
                item.setPos(current_pos.x() + actual_delta_x, current_pos.y() + actual_delta_y)
                moved_items.add(item)
        
        if event is not None:
            self.drag_start_pos = event.pos()

    def stop_drag(self, event):
        self.image_canvas.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def recenter_image(self):
        item_rect = self.image_item.boundingRect()
        viewport_size = self.image_canvas.viewport().size()
        max_x = viewport_size.width() - item_rect.width()
        max_y = viewport_size.height() - item_rect.height()

        if max_x>0: #case: image is smaller than viewport
            actual_delta_x = -self.image_item.x()
            actual_delta_y = -self.image_item.y()
            self.image_item.setPos(0, 0)
        else:
            actual_delta_x = (max_x/2) - self.image_item.x()
            actual_delta_y = (max_y/2) - self.image_item.y()
            self.image_item.setPos(max_x/2, max_y/2)
        
        # Move all other items in the scene (grid lines, center cross, etc.)
        for item in self.image_scene.items():
            if item != self.image_item:
                if isinstance(item, QtWidgets.QGraphicsLineItem) and item.zValue() == 1:
                    #this is a grid line. dont move those!
                    continue
                current_pos = item.pos()
                item.setPos(current_pos.x() + actual_delta_x, current_pos.y() + actual_delta_y)
        

    def update_zoom_from_slider(self):
        if not self.updating_scaling:
            self.updating_scaling = True
            self.zoom_spinbox.setValue(self.zoom_slider.value())
            self.apply_scene_zoom()
            self.updating_scaling = False

    def update_zoom_from_spinbox(self):
        if not self.updating_scaling:
            self.updating_scaling = True
            self.zoom_slider.setValue(self.zoom_spinbox.value())
            self.apply_scene_zoom()
            self.updating_scaling = False

    def apply_scene_zoom(self):
        """Apply zoom transformation to the entire scene"""
        zoom_percent = self.zoom_spinbox.value()
        scale_factor = zoom_percent / 100.0
        
        # Create a new transform
        transform = QtGui.QTransform()
        transform.scale(scale_factor, scale_factor)
        
        # Apply the transform to the scene
        self.image_canvas.setTransform(transform)

    def on_mouse_wheel(self, event):
        if not self.updating_scaling:
            self.updating_scaling = True

            # Calculate the new zoom value
            delta = event.angleDelta().y() / 120  # Typically, event.angleDelta().y() is a multiple of 120
            new_value = int(self.zoom_spinbox.value() * (1 + delta * 0.1))  # Adjust zoom step as needed
            new_value = max(10, min(1000, new_value))  # Ensure the value stays within bounds
            self.zoom_spinbox.setValue(new_value)
            self.zoom_slider.setValue(new_value)

            # Apply the zoom to the scene
            self.apply_scene_zoom()

            self.updating_scaling = False
            
    def reset_zoom(self):
        self.updating_scaling = True
        self.zoom_slider.setValue(100)  # Reset the slider to 100%
        self.zoom_spinbox.setValue(100)  # Reset the spinbox to 100%
        self.apply_scene_zoom()  # Apply the reset zoom to the scene
        self.updating_scaling = False

    def toggle_grid(self):
        if self.grid_on:
            self.grid_toggle_button.setText("Show Grid")
        else:
            self.grid_toggle_button.setText("Hide Grid")
        self.grid_on = not self.grid_on
        self.update_grid()

    def update_grid(self):
        # Clear previously added lines
        for item in self.image_scene.items():
            if isinstance(item, QtWidgets.QGraphicsLineItem) and item.zValue() == 1:
                self.image_scene.removeItem(item)

        if self.grid_on and self.grid_distance_spinbox.value() > 0:
            grid_distance_mm = self.grid_distance_spinbox.value()
            pixel_per_mm_original = self.data_handler.pixel_per_mm_original  # has to work on original image scaling to account for changes in pixel size
            grid_distance_px = grid_distance_mm * pixel_per_mm_original #* self.data_handler.image_scaling

            viewport_size = self.image_canvas.viewport().size()
            width = viewport_size.width()
            height = viewport_size.height()

            # Draw vertical grid lines and always start from the middle
            x = 0
            while x < width:
                line = self.image_scene.addLine(x, -height, x, height, QtGui.QPen(QtCore.Qt.GlobalColor.gray))
                line.setZValue(1)  # Ensure the grid lines are in front of the image
                if not x==0:
                    line = self.image_scene.addLine(-x, -height, -x, height, QtGui.QPen(QtCore.Qt.GlobalColor.gray))
                    line.setZValue(1)  # Ensure the grid lines are in front of the image
                x += grid_distance_px

            # Draw horizontal grid lines
            y = 0
            while y < height:
                line = self.image_scene.addLine(-width, y, width, y, QtGui.QPen(QtCore.Qt.GlobalColor.gray))
                line.setZValue(1)  # Ensure the grid lines are in front of the image
                if not y==0:
                    line = self.image_scene.addLine(-width, -y, width, -y, QtGui.QPen(QtCore.Qt.GlobalColor.gray))
                    line.setZValue(1)  # Ensure the grid lines are in front of the image
                y += grid_distance_px

    def toggle_set_image_center(self):
        if self.set_image_center_button.isChecked():
            self.setting_image_center = True
        else:
            self.setting_image_center = False

    def set_image_center(self, event):
        if self.setting_image_center:
            x_canvas = event.position().x()
            y_canvas = event.position().y()

            new_x, new_y = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)
            self.current_image_center = [new_x, new_y]

            self.update_image_center()

            #turn off the setting mode
            self.set_image_center_button.setChecked(False)
            self.setting_image_center = False

    def reset_image_center_to_default(self):
        if self.data_handler.image_matrix_original is None:
            self.data_handler.center_for_hatch = None
            return
        
        self.current_image_center = [(self.data_handler.image_matrix_original.shape[1]-1)/2,
                        (self.data_handler.image_matrix_original.shape[0]-1)/2]
        
        self.update_image_center()
    
    def reset_image_center_to_current(self):
        if self.current_image_center is None:
            self.reset_image_center_to_default()
        else:
            self.update_image_center()

    
    def update_image_center(self):

        self.data_handler.center_for_hatch = self.current_image_center

        #update gui as well
        pixel_per_mm = self.data_handler.pixel_per_mm
        x_mm = self.current_image_center[0] / pixel_per_mm
        y_mm = self.current_image_center[1] / pixel_per_mm
        self.gui.h_center_spinbox.setValue(x_mm)
        self.gui.v_center_spinbox.setValue(y_mm)

        self.redraw_center_cross()
    
    def toggle_show_image_center(self):
        if self.showing_image_center:
            # Remove any existing crosses
            for item in self.image_scene.items():
                if isinstance(item, QGraphicsLineItem) and item.zValue() == 2:
                    self.image_scene.removeItem(item)
            self.show_image_center_button.setText("Show Image Center")
        else:
            self.show_image_center_button.setText("Hide Image Center")

        self.showing_image_center = not self.showing_image_center
        self.redraw_center_cross()

    def redraw_center_cross(self):
        """Draw a cross at the specified image coordinates"""
        try:
            # Remove any existing crosses
            for item in self.image_scene.items():
                if isinstance(item, QGraphicsLineItem) and item.zValue() == 2:
                    self.image_scene.removeItem(item)

            if not self.showing_image_center:
                return

            #get scene coordinates directly
            scene_x,scene_y = self.data_handler.image_to_scene_coords(self.current_image_center[0], self.current_image_center[1])
            
            # Define cross size (adjust as needed)
            cross_size = 20
            
            # Create horizontal and vertical lines
            horizontal_line = QGraphicsLineItem(
                scene_x - cross_size, scene_y,
                scene_x + cross_size, scene_y
            )
            vertical_line = QGraphicsLineItem(
                scene_x, scene_y - cross_size,
                scene_x, scene_y + cross_size
            )
            
            # Set line appearance
            pen = QPen(QColor(255, 0, 0))  # Red color
            pen.setWidth(2)
            horizontal_line.setPen(pen)
            vertical_line.setPen(pen)
            
            # Set z-value to ensure cross is above image and grid
            horizontal_line.setZValue(2)
            vertical_line.setZValue(2)
            
            # Add lines to scene
            self.image_scene.addItem(horizontal_line)
            self.image_scene.addItem(vertical_line)
            
        except Exception as e:
            print(f"Error drawing center cross: {e}")
        



