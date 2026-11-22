from contextlib import contextmanager
import base64
import os
import re
from pathlib import Path
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QFileDialog, QListWidgetItem
from PyQt6.QtWidgets import QGraphicsLineItem
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QColor, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6 import uic
from PIL import Image
import numpy as np
import io
from collections import defaultdict
import logging
from core import image_doc
from core.image_doc import ImageDocument

log = logging.getLogger(__name__)
from PathManager import get_gui_file_path
from ImageUpscaling import ImageUpscaler


class BaseFunctions:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.undo_manager = getattr(data_handler, "undo_manager", None)
        if self.undo_manager is not None:
            self.undo_manager.set_image_controller(self)
        self.image_dimension_frame = gui.image_dimension_frame
        self.images_frame = gui.images_frame
        self.default_dpi = 96  # Assuming 96 DPI by default
        self.last_save_filter = "PNG Files (*.png)"
        self.last_directory = ""  # load / save dialogs open where the last image came from / went to
        self.changeing_image = False
        self.updating_dimensions = False
        self.active_image_item = None

        # Create File Menu
        self.menubar = gui.menubar
        self.actionLoad_image = gui.actionLoad_Image
        self.actionLoad_image.triggered.connect(self.load_image)
        self.actionSave_image = gui.actionSave_Image
        self.actionSave_image.triggered.connect(self.save_image)
        self.actionNew_Blank = gui.actionNew_Blank
        self.actionNew_Blank.triggered.connect(self.open_new_blank)
        # Images without alpha channel: treat pure white as transparent background (default on, Q4)
        self.action_white_is_background = QtGui.QAction("Load: Pure White as Transparent", gui)
        self.action_white_is_background.setCheckable(True)
        self.action_white_is_background.setChecked(True)
        gui.settings_menu.addAction(self.action_white_is_background)  # P9.2: a setting, only in the Settings menu
        # replaces the old white thresholds of hatching/parsing/plotting (mean RGB > threshold -> background);
        # P9.2: reached through the image operations, not the File menu
        self.action_bright_to_transparent = QtGui.QAction("Make Bright Colors Transparent...", gui)
        self.action_bright_to_transparent.triggered.connect(lambda: self.make_bright_transparent())
        # self.actionReset_image = gui.actionReset_Image
        # self.actionReset_image.triggered.connect(self.reset_image)

        # Add variable, label and entry field for image width (image dimension frame)
        self.width_spinbox = gui.width_spinbox
        self.width_spinbox.setRange(0, 10000)
        self.width_spinbox.editingFinished.connect(self.update_dimensions)

        # Add variable, label and entry field for image height (image dimension frame)
        self.height_spinbox = gui.height_spinbox
        self.height_spinbox.setRange(0, 10000)
        self.height_spinbox.editingFinished.connect(self.update_dimensions)

        #Add variable, label and entry field for pixel size (image dimension frame)
        self.pixel_size_spinbox = gui.pixel_size_spinbox
        self.pixel_size_spinbox.setRange(0, 10000)
        self.pixel_size_spinbox.editingFinished.connect(self.update_dimensions)

        # Add variable and entry field for image resolution (image dimension frame)
        self.image_resolution_edit = gui.image_resolution_edit
        self.image_resolution_edit.setReadOnly(True)

        # Add variable and check box for image ratio (image dimension frame)
        self.lock_ratio_check = gui.lock_ratio_check
        self.lock_ratio_check.setChecked(True)
        self.lock_ratio_check.setEnabled(False)

        #Add button to reset image size
        self.reset_image_size_button = gui.reset_image_size_button
        self.reset_image_size_button.clicked.connect(self.reset_image_size)

        # Upscale buttons
        self.upscale_button = gui.upscale_button
        self.upscale_button.clicked.connect(self.upscale_active_image)

        self.upscale_preserving_button = gui.upscale_preserving_button
        self.upscale_preserving_button.clicked.connect(lambda: self.upscale_active_image(preserve_palette=True))

        # Add image button
        self.add_image_button = gui.add_image_button
        self.add_image_button.clicked.connect(self.add_image)

        # "Set as Original" (was: Keep Changes): the current image becomes the restore point
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
        self.combine_image_button.clicked.connect(lambda: self.combine_images())
        self.combine_monochrome_button = gui.combine_monochrome_button  # P9.6: was the monochrome checkbox
        self.combine_monochrome_button.clicked.connect(lambda: self.combine_images(monochrome=True))
        gui.bright_transparent_button.clicked.connect(lambda: self.make_bright_transparent())  # P9.6

        #Flip image button
        self.rot_image_90_button = gui.rot_image_90_button
        self.rot_image_90_button.clicked.connect(self.rot_image_90_clockwise)

        # Mirror buttons
        self.mirror_image_horizontal_button = gui.mirror_image_horizontal_button
        self.mirror_image_horizontal_button.clicked.connect(self.mirror_image_horizontal)

        self.mirror_image_vertical_button = gui.mirror_image_vertical_button
        self.mirror_image_vertical_button.clicked.connect(self.mirror_image_vertical)

        # Cut to masked button
        self.cut_to_mask_button = gui.cut_to_mask_button
        self.cut_to_mask_button.clicked.connect(self.cut_to_mask)

        # Crop background button
        self.crop_background_button = gui.crop_background_button
        self.crop_background_button.clicked.connect(self.crop_background)

        # Add list to manage gCode_blocks
        self.images_ListWidget = gui.images_ListWidget

        # Bind event for selection change
        self.images_ListWidget.itemSelectionChanged.connect(self.change_image)

    def load_image(self, file_path=None):
        if not file_path or not isinstance(file_path, (str, Path)):
            file_path, _ = QFileDialog.getOpenFileName(
                self.gui,
                "Load Image",
                self.last_directory,
                "Image Files (*.png *.jpg *.jpeg *.bmp *.svg *.webp *.gif *.tiff);;SVG Files (*.svg);;All Files (*)"
            )
        if not file_path:
            return
        file_path = str(file_path)
        self.last_directory = os.path.dirname(os.path.abspath(file_path))
        try:
            image_matrix, pixel_per_mm = self.read_image_file(file_path, self.action_white_is_background.isChecked())
            self.changeing_image = True
            img_obj = ImageDocument(image_matrix, image_matrix, pixel_per_mm, pixel_per_mm)
            self.add_listbox_item(img_obj, os.path.basename(file_path), set_selected=True)
            self.changeing_image = False
            self.set_handler_data(new_image=True)
            self.update_dimension_fields()
            # Center image on loading
            self.gui.image_canvas.centerOn(self.gui.image_item)
        except Exception as e:
            log.exception("Error loading image")
            QtWidgets.QMessageBox.critical(self.gui, "Error Loading Image", f"Could not load the image:\n{e}")

    def read_image_file(self, file_path, white_is_background=True):
        """Read an image file as RGBA with binary alpha (see core/image_doc.py). Returns (image, pixel_per_mm)."""
        if file_path.lower().endswith(".svg"):
            renderer = QSvgRenderer(file_path)
            if not renderer.isValid():
                raise ValueError(f"Invalid or unreadable SVG file: {file_path}")

            viewbox = renderer.viewBox()
            size = renderer.defaultSize()
            width = viewbox.width() if viewbox.width() > 0 else size.width()
            height = viewbox.height() if viewbox.height() > 0 else size.height()
            if width <= 0:
                width = 800
            if height <= 0:
                height = 600

            qimg = QImage(width, height, QImage.Format.Format_RGBA8888)
            qimg.fill(QColor(0, 0, 0, 0))  # unpainted areas stay transparent
            painter = QPainter(qimg)
            renderer.render(painter)
            painter.end()

            ptr = qimg.bits()
            ptr.setsize(qimg.sizeInBytes())
            bytes_per_line = qimg.bytesPerLine()
            arr = np.frombuffer(ptr, np.uint8).reshape((height, bytes_per_line))[:, :width * 4].reshape((height, width, 4))
            image_matrix = image_doc.from_rgba(arr)

            pixel_per_mm = self.default_dpi / 25.4
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(1024)
                match = re.search(r'width="([0-9.]+)mm"', content)
                if match:
                    w_mm = float(match.group(1))
                    if w_mm > 0:
                        pixel_per_mm = width / w_mm
            except Exception:
                pass
            return image_matrix, pixel_per_mm

        raw_image = Image.open(file_path)
        if "A" in raw_image.mode or "transparency" in raw_image.info:
            image_matrix = image_doc.from_rgba(np.array(raw_image.convert("RGBA")))
        else:
            image_matrix = image_doc.from_rgb(np.array(raw_image.convert("RGB")), white_is_background)

        dpi_info = raw_image.info.get("dpi", (self.default_dpi, self.default_dpi))
        dpi = dpi_info[0] if isinstance(dpi_info, (tuple, list)) and dpi_info else dpi_info
        if not dpi or dpi <= 0:
            dpi = self.default_dpi
        return image_matrix, dpi / 25.4

    def make_bright_transparent(self, threshold=None):
        """Pixels with mean RGB > threshold become transparent background (asks for the threshold if None)."""
        if self.data_handler.image_matrix is None:
            return
        if threshold is None:
            threshold, ok = QtWidgets.QInputDialog.getInt(
                self.gui, "Make Bright Colors Transparent",
                "Pixels brighter than this value (mean of R, G, B; 0-255)\nbecome transparent background:", 230, 0, 255)
            if not ok:
                return
        with self._record_matrix("Bright Colors to Transparent"):
            image = self.data_handler.image_matrix.copy()
            image[image[..., :3].mean(axis=-1) > threshold] = 0
            self.data_handler.image_matrix = image

    def open_new_blank(self):
        """Open the New Blank dialog to create a blank image."""
        dialog = NewBlankDialog(self.gui, self)
        dialog.show()

    def add_listbox_item(self, img_obj:ImageDocument, name:str, set_selected=False):
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
        if not self.active_image_item:
            QtWidgets.QMessageBox.warning(self.gui, "Save Image", "There is no active image to save.")
            return

        # PNG/SVG keep the transparent background, JPEG/BMP get a white one
        filters = ["PNG Files (*.png)", "SVG Files (*.svg)", "JPEG Files (*.jpg *.jpeg)", "BMP Files (*.bmp)"]
        base_name = os.path.splitext(self.active_image_item.text())[0]
        default_path = os.path.join(self.last_directory, base_name) if self.last_directory else base_name
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self.gui, "Save Image", default_path, ";;".join(filters), initialFilter=self.last_save_filter
        )
        if not file_path:
            return
        self.last_directory = os.path.dirname(os.path.abspath(file_path))
        self.last_save_filter = selected_filter or self.last_save_filter
        if not os.path.splitext(file_path)[1]:
            file_path += "." + re.search(r"\*\.(\w+)", self.last_save_filter).group(1)
        try:
            self.write_image_file(file_path, self.get_active_img_obj().image_matrix, self.get_active_pixel_per_mm())
        except Exception as e:
            log.exception("Error saving image")
            QtWidgets.QMessageBox.critical(self.gui, "Error Saving Image", f"Could not save the image:\n{e}")

    def write_image_file(self, file_path, image_matrix, pixel_per_mm):
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        dpi = round(pixel_per_mm * 25.4) if pixel_per_mm else self.default_dpi
        if ext in ("jpg", "jpeg", "bmp"):
            Image.fromarray(image_doc.composite(image_matrix), mode="RGB").save(
                file_path, format="JPEG" if ext != "bmp" else "BMP", dpi=(dpi, dpi))
            return
        pil_image = Image.fromarray(image_matrix, mode="RGBA")
        if ext != "svg":
            pil_image.save(file_path, format="PNG", dpi=(dpi, dpi))
            return

        height, width = image_matrix.shape[:2]
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG", dpi=(dpi, dpi))
        b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
        width_str = f"{width / pixel_per_mm:.4f}mm" if pixel_per_mm and pixel_per_mm > 0 else f"{width}px"
        height_str = f"{height / pixel_per_mm:.4f}mm" if pixel_per_mm and pixel_per_mm > 0 else f"{height}px"
        svg_content = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width_str}" height="{height_str}" viewBox="0 0 {width} {height}" version="1.1">
  <image width="{width}" height="{height}" preserveAspectRatio="none" image-rendering="pixelated"
         href="data:image/png;base64,{b64_data}" xlink:href="data:image/png;base64,{b64_data}"/>
</svg>
'''
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(svg_content)

    @contextmanager
    def _record_matrix(self, description):
        """Helper to record matrix operations with UndoRedoManager."""
        if self.undo_manager:
            with self.undo_manager.record_image_matrix(description, target_item=self.active_image_item):
                yield
        else:
            yield

    def update_dimensions(self):
        sender =self.gui.sender()   
        if self.updating_dimensions:
            return
        try:
            with self._record_matrix("Update Dimensions"):

                if sender == self.pixel_size_spinbox:
                    new_pixel_per_mm = 1 / float(self.pixel_size_spinbox.value())
                    self.set_active_pixel_per_mm(new_pixel_per_mm)
                else:
                    new_width_mm = float(self.width_spinbox.value())
                    new_height_mm = float(self.height_spinbox.value())
                    
                    image_matrix = self.get_active_image_matrix()
                    # The ratio is always locked: rescale the pixel size, the pixel data stays untouched
                    if sender == self.width_spinbox:
                        self.set_active_pixel_per_mm(image_matrix.shape[1] / new_width_mm)
                    else:
                        self.set_active_pixel_per_mm(image_matrix.shape[0] / new_height_mm)
                self.set_handler_data(new_image = False)
                self.update_dimension_fields()
        except Exception as e:
            log.exception("Error updating dimensions")
    def update_dimension_fields(self):
        height, width = self.get_active_image_matrix().shape[:2]
        width_mm = width / self.get_active_pixel_per_mm()
        height_mm = height / self.get_active_pixel_per_mm()
        self.updating_dimensions = True
        self.width_spinbox.setValue(width_mm)
        self.height_spinbox.setValue(height_mm)
        self.pixel_size_spinbox.setValue(1 / self.get_active_pixel_per_mm())
        self.updating_dimensions = False

        # Keep zoom ceiling aligned with current pixel size in mm.
        pixel_size_mm = 1.0 / self.get_active_pixel_per_mm() if self.get_active_pixel_per_mm() else 1.0
        max_zoom = max(1, int(1000.0 / pixel_size_mm))
        self.gui.zoom_slider.setMaximum(max_zoom)
        self.gui.zoom_spinbox.setMaximum(max_zoom)
        if self.gui.zoom_slider.value() > max_zoom:
            self.gui.zoom_slider.setValue(max_zoom)
        if self.gui.zoom_spinbox.value() > max_zoom:
            self.gui.zoom_spinbox.setValue(max_zoom)

        self.image_resolution_edit.setText(f"{width} x {height}")

    def reset_image_size(self):
        with self._record_matrix("Reset Image Size"):
            pixel_per_mm = self.get_active_pixel_per_mm_original()
            img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            img_obj.pixel_per_mm = pixel_per_mm
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.set_handler_data(new_image = False)   
            self.update_dimension_fields()

    def split_colors(self):
        """One new image per colour; all other pixels transparent."""
        current_image_matrix = self.get_active_image_matrix()
        packed = np.ascontiguousarray(current_image_matrix).view(np.uint32)[..., 0]
        colors = np.unique(packed[current_image_matrix[..., 3] > 0])
        if len(colors) > 10:
            reply = QtWidgets.QMessageBox.question(
                self.gui, "Too many colors",
                f"This image has {len(colors)} different colors. Do you want to split it into {len(colors)} images?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return

        self.changeing_image = True
        image_name = self.active_image_item.text()
        ppm, ppm_original = self.get_active_pixel_per_mm(), self.get_active_pixel_per_mm_original()
        self.add_listbox_item(ImageDocument(current_image_matrix, current_image_matrix, ppm, ppm_original), image_name + "_unsplit", set_selected=True)
        for color in colors:
            layer = np.where((packed == color)[..., None], current_image_matrix, 0).astype(np.uint8)
            rgb = tuple(int(v) for v in np.array([color], np.uint32).view(np.uint8)[:3])
            self.add_listbox_item(ImageDocument(layer, layer, ppm, ppm_original), str(rgb))
        self.changeing_image = False

    def add_image(self):
        image_name = self.active_image_item.text()
        img_obj = ImageDocument(self.get_active_image_matrix(), self.get_active_image_matrix(), self.get_active_pixel_per_mm(), self.get_active_pixel_per_mm_original())
        self.add_listbox_item(img_obj, image_name + "_edited", set_selected=True)

    def keep_changes(self):
        with self._record_matrix("Set as Original"):
            img_obj = ImageDocument(self.get_active_image_matrix(), self.get_active_image_matrix(), self.get_active_pixel_per_mm(), self.get_active_pixel_per_mm_original())
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.set_handler_data(new_image = True)
    
    def rot_image_180(self):
        with self._record_matrix("Rotate 180°"):
            image_matrix = np.flipud(np.fliplr(self.get_active_image_matrix()))
            img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            img_obj.image_matrix = image_matrix.copy()
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.set_handler_data(new_image = True)
    
    def rot_image_90_clockwise(self):
        with self._record_matrix("Rotate 90° CW"):
            image_matrix = np.rot90(self.get_active_image_matrix(), k=-1)  # Rotate 90 degrees clockwise
            img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            img_obj.image_matrix = image_matrix.copy()
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.set_handler_data(new_image = True)
    
    def mirror_image_horizontal(self):
        with self._record_matrix("Mirror Horizontal"):
            image_matrix = np.fliplr(self.get_active_image_matrix())
            img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            img_obj.image_matrix = image_matrix.copy()
            self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)
            self.set_handler_data(new_image = True)

    def mirror_image_vertical(self):
        with self._record_matrix("Mirror Vertical"):
            image_matrix = np.flipud(self.get_active_image_matrix())
            img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
            img_obj.image_matrix = image_matrix.copy()
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
        
        if self.images_ListWidget.count() == 0:
            self.active_image_item = None

            # Clear the image canvas and the data handler
            self.data_handler.set_active_document(None)
        
        #ensure to reset the image bounds
        self.gui.image_scene.setSceneRect(self.gui.image_item.boundingRect())

    def change_image(self):
        if self.changeing_image:
            return
        
        #get new selction and check if only one item is selected
        newly_selected = self.images_ListWidget.selectedItems()
        if not newly_selected or len(newly_selected) != 1:
            return
        
        #load new item
        self.changeing_image = True
        self.active_image_item = newly_selected[0]
        self.data_handler.reset_edits()
        self.set_handler_data(new_image=True)
        self.update_dimension_fields()
        self.changeing_image = False       

    def combine_images(self, monochrome=False):
        selected_images = self.images_ListWidget.selectedItems()
        if not selected_images:
            return
        combined_image = np.zeros_like(selected_images[0].data(QtCore.Qt.ItemDataRole.UserRole).image_matrix)

        for image_item in selected_images:
            patch = image_item.data(QtCore.Qt.ItemDataRole.UserRole).image_matrix
            if patch.shape != combined_image.shape:
                QtWidgets.QMessageBox.warning(self.gui, "Combine Images", "All selected images must have the same size.")
                return
            # darkest opaque colour wins (sum of RGB, int to avoid uint8 overflow); transparent pixels never win
            brightness = lambda img: np.where(img[..., 3] > 0, img[..., :3].sum(axis=-1, dtype=np.int32), 1000)
            darker = brightness(patch) < brightness(combined_image)
            combined_image[darker] = patch[darker]

        # monochrome: all coloured pixels get their average colour (B20: was always black)
        if monochrome:
            color_mask = combined_image[..., 3] > 0
            if color_mask.any():
                combined_image[color_mask] = combined_image[color_mask].mean(axis=0).astype(np.uint8)

        # B27: read the pixel size before removing, the active item may be one of the removed images
        first_obj = selected_images[0].data(QtCore.Qt.ItemDataRole.UserRole)
        self.remove_image()
        img_obj = ImageDocument(combined_image, combined_image, first_obj.pixel_per_mm, first_obj.pixel_per_mm_original)
        self.add_listbox_item(img_obj, "combined", set_selected=True)

    def cut_to_mask(self):

        if self.data_handler.active_mask_index ==-1:
            QtWidgets.QMessageBox.warning(self.gui, "No Mask Selected", "Please select a mask to cut to.")
            return
        
        #store data first
        active_mask = self.data_handler.masks_list[self.data_handler.active_mask_index]  # Assuming single active mask for simplicity
        
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
        
        # keep pixels where mask==1, transparent elsewhere
        output_image = np.zeros_like(image_cropped)
        output_image[mask_cropped == 1] = image_cropped[mask_cropped == 1]

        image_name = self.active_image_item.text()
        img_obj = ImageDocument(output_image, output_image, self.get_active_pixel_per_mm(), self.get_active_pixel_per_mm_original())
        self.add_listbox_item(img_obj, image_name + "_cut", set_selected=True)

    def crop_background(self):
        #store data first
        
        # Create a copy of the image matrix
        image_matrix = self.data_handler.image_matrix.copy()
        
        # Get the bounding box of the image
        h, w = image_matrix.shape[:2]
        
        background_mask = image_matrix[..., 3] == 0
        
        # Find the bounding rectangle of the non-background pixels
        rows = np.where(~background_mask)[0]
        cols = np.where(~background_mask)[1]
        
        if len(rows) == 0 or len(cols) == 0:
            QtWidgets.QMessageBox.warning(self.gui, "Empty Image", "The image contains only background pixels.")
            return
        
        row_min, row_max = rows.min(), rows.max()
        col_min, col_max = cols.min(), cols.max()
        
        # Extract the bounding rectangle from the image
        image_cropped = image_matrix[row_min:row_max+1, col_min:col_max+1]
        
        # Create a new image object with the cropped image
        img_obj = ImageDocument(image_cropped, image_cropped, self.get_active_pixel_per_mm(), self.get_active_pixel_per_mm_original())
        
        # Add the cropped image to the list
        image_name = self.active_image_item.text()
        self.add_listbox_item(img_obj, image_name + "_cropped", set_selected=True)

    def upscale_active_image(self, preserve_palette = False):
        """Upscale the currently selected active image by 2x using the ImageUpscaler module."""
        import os
        if not self.active_image_item:
            QtWidgets.QMessageBox.warning(self.gui, "Upscale Image", "No image is currently selected.")
            return

        # 1. Retrieve the active item's ImgObj
        img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not img_obj or img_obj.image_matrix is None:
            QtWidgets.QMessageBox.warning(self.gui, "Upscale Image", "Invalid active image data.")
            return

        # Get original filename
        active_name = self.active_image_item.text()
        if active_name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            base, ext = os.path.splitext(active_name)
            upscaled_name = f"{base}_2x{ext}"
        else:
            upscaled_name = f"{active_name}_2x"

        # Initialize progress feedback dialog
        progress_dialog = QtWidgets.QProgressDialog(
            "Initializing upscaling...", "Cancel", 0, 100, self.gui
        )
        progress_dialog.setWindowTitle("AI Image Upscaling (2x)")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress_dialog.show()
        QtWidgets.QApplication.processEvents()

        def status_callback(msg):
            progress_dialog.setLabelText(msg)
            if "Downloading" in msg and "%" in msg:
                try:
                    pct = int(msg.split("%")[0].split()[-1])
                    progress_dialog.setValue(pct)
                except Exception:
                    pass
            elif "upscaling" in msg:
                progress_dialog.setValue(50)
            elif "completed" in msg:
                progress_dialog.setValue(100)

        try:
            # P6.10: download + engine run in a worker thread; the dialog stays responsive
            worker = _UpscaleWorker(ImageUpscaler(img_obj.image_matrix.copy()), preserve_palette)
            worker.status.connect(status_callback, QtCore.Qt.ConnectionType.QueuedConnection)
            loop = QtCore.QEventLoop()
            worker.finished.connect(loop.quit)
            worker.start()
            loop.exec()
            worker.wait()
            if worker.error is not None:
                raise worker.error
            upscaled_rgb = worker.result

            if upscaled_rgb is None:
                QtWidgets.QMessageBox.critical(self.gui, "Upscale Image", "Upscaling failed.")
                return

            # Double the pixel density so physical dimensions in millimeters are perfectly preserved
            new_pixel_per_mm = img_obj.pixel_per_mm * 2
            # new_pixel_per_mm_orig = img_obj.pixel_per_mm_original * 2

            # Create new ImgObj with upscaled parameters
            upscaled_img_obj = ImageDocument(
                upscaled_rgb.copy(),
                upscaled_rgb.copy(),
                new_pixel_per_mm,
                new_pixel_per_mm
            )

            # Prevent recursive selection change locks
            self.changeing_image = True
            self.add_listbox_item(upscaled_img_obj, upscaled_name, set_selected=True)
            self.changeing_image = False

            # Set handler data and display new image
            self.set_handler_data(new_image=True)
            self.update_dimension_fields()

            # Center canvas on the upscaled image
            self.gui.image_canvas.centerOn(self.gui.image_item)

            QtWidgets.QMessageBox.information(
                self.gui, "Upscale Image",
                f"Image upscaled successfully by 2x!\nNew size: {upscaled_rgb.shape[1]}x{upscaled_rgb.shape[0]} pixels."
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(self.gui, "Upscale Image", f"An error occurred during upscaling: {str(e)}")
        finally:
            progress_dialog.close()


    #simple getter and setter functions for active image properties
    def get_active_image_matrix(self):
        return self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole).image_matrix.copy()
    
    def get_active_original_image_matrix(self):
        return self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole).original_image_matrix.copy()
    
    def get_active_pixel_per_mm(self):
        return self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole).pixel_per_mm
    
    def set_active_pixel_per_mm(self, new_pixel_per_mm):
        img_obj = self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)
        img_obj.pixel_per_mm = new_pixel_per_mm
        self.active_image_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)

        # Keep the zoom ceiling in sync with the current pixel size.
        if hasattr(self.gui, "zoom_slider") and hasattr(self.gui, "zoom_spinbox"):
            pixel_size_mm = 1.0 / new_pixel_per_mm if new_pixel_per_mm and new_pixel_per_mm > 0 else 1.0
            max_zoom = max(1, int(1000.0 / pixel_size_mm))
            self.gui.zoom_slider.setMaximum(max_zoom)
            self.gui.zoom_spinbox.setMaximum(max_zoom)
            self.gui.zoom_slider.setValue(min(self.gui.zoom_slider.value(), max_zoom))
            self.gui.zoom_spinbox.setValue(min(self.gui.zoom_spinbox.value(), max_zoom))
    
    def get_active_pixel_per_mm_original(self):
        return self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole).pixel_per_mm_original
    
    def get_active_img_obj(self):
        return self.active_image_item.data(QtCore.Qt.ItemDataRole.UserRole)

    def set_handler_data(self, new_image = False):
        """Show the active item's document. new_image=True: (re)activate it and notify image-changed callbacks."""
        if new_image:
            self.data_handler.set_active_document(self.get_active_img_obj())
        else:
            self.data_handler.set_and_display_image()

        #ensure to reset the image bounds
        self.gui.image_scene.setSceneRect(self.gui.image_item.boundingRect())
    
class _UpscaleWorker(QtCore.QThread):
    """Runs ImageUpscaler.upscale (2x) off the GUI thread; status messages are emitted as a signal."""
    status = QtCore.pyqtSignal(str)

    def __init__(self, upscaler, preserve_palette):
        super().__init__()
        self.upscaler, self.preserve_palette = upscaler, preserve_palette
        self.result, self.error = None, None

    def run(self):
        try:
            self.result = self.upscaler.upscale(scale=2, model="realesrgan-x4plus", use_gpu=True,
                                                status_callback=self.status.emit, preserve_palette=self.preserve_palette)
        except Exception as e:
            self.error = e


class ImageMover(QtCore.QObject):
    def __init__(self, data_handler, event_handler, gui):
        super().__init__()
        self.data_handler = data_handler
        self.event_handler = event_handler
        self.gui = gui
        self.image_canvas = gui.image_canvas
        self.image_scene = gui.image_scene
        self.image_item = gui.image_item
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
        default_pixel_size_mm = 1.0 / self.data_handler.default_pixel_per_mm
        default_max_zoom = max(1, int(1000.0 / default_pixel_size_mm))
        self.zoom_slider.setRange(1, default_max_zoom)
        self.zoom_slider.setValue(100)  # Default to 100%
        self.zoom_slider.valueChanged.connect(self.update_zoom_from_slider)

        # Add a button to reset the zoom factor to 100%
        self.reset_zoom_button = gui.reset_zoom_button
        self.reset_zoom_button.clicked.connect(self.reset_zoom)

        # Add an entry field to control the display size
        self.zoom_spinbox = gui.zoom_spinbox
        self.zoom_spinbox.setRange(1, default_max_zoom)
        self.zoom_spinbox.setValue(100)
        self.zoom_spinbox.valueChanged.connect(self.update_zoom_from_spinbox)

        def update_zoom_limits_from_pixel_size():
            pixel_per_mm = self.data_handler.pixel_per_mm or self.data_handler.default_pixel_per_mm
            pixel_size_mm = 1.0 / pixel_per_mm if pixel_per_mm > 0 else 1.0
            max_zoom = max(1, int(1000.0 / pixel_size_mm))
            self.zoom_slider.setMaximum(max_zoom)
            self.zoom_spinbox.setMaximum(max_zoom)
            if self.zoom_slider.value() > max_zoom:
                self.zoom_slider.setValue(max_zoom)
            if self.zoom_spinbox.value() > max_zoom:
                self.zoom_spinbox.setValue(max_zoom)

        self.data_handler.add_image_changed_callback(update_zoom_limits_from_pixel_size)
        self.data_handler.add_image_resized_callback(update_zoom_limits_from_pixel_size)

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

        # Touchscreen support hook
        self.touch_screen_mode = False
        self._in_multitouch_gesture = False
        self.actionTouchscreen_Mode = getattr(gui, "actionTouchscreen_Mode", None)
        if self.actionTouchscreen_Mode:
            self.actionTouchscreen_Mode.setCheckable(True)
            self.actionTouchscreen_Mode.triggered.connect(self.set_touch_screen_mode)

        #Event callbacks for handling gui interactions
        self.event_handler.add_canvas_event_callback(self.trigger_canvas_event)

    def set_touch_screen_mode(self, enabled):
        self.touch_screen_mode = enabled
        self.image_canvas.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_AcceptTouchEvents, enabled)
        if not enabled:
            self._in_multitouch_gesture = False
        # (P10.6: the spin box arrows are always visible – set in the .ui)


    def trigger_canvas_event(self, event):
        if event.type() in (QtCore.QEvent.Type.TouchBegin, QtCore.QEvent.Type.TouchUpdate, QtCore.QEvent.Type.TouchEnd):
            if self.touch_screen_mode:
                return self.handle_touch_event(event)

        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.start_drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.MiddleButton:
            self.drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.stop_drag(event)
        elif event.type() == QtCore.QEvent.Type.Wheel:
            self.on_mouse_wheel(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.set_image_center(event)

    def get_current_max_zoom(self):
        pixel_per_mm = self.data_handler.pixel_per_mm or self.data_handler.default_pixel_per_mm
        if pixel_per_mm <= 0:
            return 1000
        pixel_size_mm = 1.0 / pixel_per_mm
        return max(1, int(1000.0 / pixel_size_mm))

    def clamp_zoom_value(self, value):
        max_zoom = self.get_current_max_zoom()
        return max(1, min(max_zoom, int(value)))

    def handle_touch_event(self, event):
        points = event.points()
        active_points = [p for p in points if p.state() != QtGui.QEventPoint.State.Released]
        
        if len(active_points) == 2:
            self._in_multitouch_gesture = True
            if event.type() == QtCore.QEvent.Type.TouchUpdate:
                p1, p2 = active_points[0], active_points[1]
                pos1, pos2 = p1.position(), p2.position()
                last_pos1, last_pos2 = p1.lastPosition(), p2.lastPosition()
                
                # Calculate distance
                dx = pos1.x() - pos2.x()
                dy = pos1.y() - pos2.y()
                curr_dist = (dx*dx + dy*dy) ** 0.5
                
                ldx = last_pos1.x() - last_pos2.x()
                ldy = last_pos1.y() - last_pos2.y()
                last_dist = (ldx*ldx + ldy*ldy) ** 0.5
                
                # Calculate center
                curr_center_x = (pos1.x() + pos2.x()) / 2.0
                curr_center_y = (pos1.y() + pos2.y()) / 2.0
                last_center_x = (last_pos1.x() + last_pos2.x()) / 2.0
                last_center_y = (last_pos1.y() + last_pos2.y()) / 2.0
                
                # Pan
                delta_x = curr_center_x - last_center_x
                delta_y = curr_center_y - last_center_y
                
                h_bar = self.image_canvas.horizontalScrollBar()
                v_bar = self.image_canvas.verticalScrollBar()
                h_bar.setValue(int(round(h_bar.value() - delta_x)))
                v_bar.setValue(int(round(v_bar.value() - delta_y)))
                
                # Zoom
                if last_dist > 0.1 and abs(curr_dist - last_dist) > 0.1:
                    scale_factor = curr_dist / last_dist
                    if not self.updating_scaling:
                        self.updating_scaling = True
                        new_value = int(round(self.zoom_spinbox.value() * scale_factor))
                        new_value = self.clamp_zoom_value(new_value)
                        self.zoom_spinbox.setValue(new_value)
                        self.zoom_slider.setValue(new_value)
                        self.apply_scene_zoom()
                        self.updating_scaling = False
            event.accept()
            return True
            
        if getattr(self, '_in_multitouch_gesture', False):
            if event.type() == QtCore.QEvent.Type.TouchEnd or len(active_points) == 0:
                self._in_multitouch_gesture = False
            event.accept()
            return True
            
        return False

    def start_drag(self, event):
        self.image_canvas.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        self.drag_start_pos = event.pos()

    def drag(self, event):
        if event is None: return
        
        # Calculate how many pixels the mouse moved in the viewport
        delta = event.pos() - self.drag_start_pos
        
        # Grab the view's scrollbars (the "camera" controls)
        h_bar = self.image_canvas.horizontalScrollBar()
        v_bar = self.image_canvas.verticalScrollBar()
        
        # Move the scrollbars in the opposite direction of the mouse drag
        h_bar.setValue(h_bar.value() - delta.x())
        v_bar.setValue(v_bar.value() - delta.y())
        
        # Update the start position for the next movement frame
        self.drag_start_pos = event.pos()

    def stop_drag(self, event):
        self.image_canvas.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        
    def recenter_image(self):
        # Simply tell the camera to look at the center of the image item
        self.image_canvas.centerOn(self.image_item)

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
        if self.grid_on:
            self.update_grid()  # the visible area changed

    def on_mouse_wheel(self, event):
        if not self.updating_scaling:
            self.updating_scaling = True

            # Calculate the new zoom value
            delta = event.angleDelta().y() / 120  # Typically, event.angleDelta().y() is a multiple of 120
            new_value = int(np.ceil(self.zoom_spinbox.value() * (1 + delta * 0.1)))  # Adjust zoom step as needed
            new_value = self.clamp_zoom_value(new_value)
            self.zoom_spinbox.setValue(new_value)
            self.zoom_slider.setValue(new_value)

            # Apply the zoom to the scene
            self.apply_scene_zoom()

            self.updating_scaling = False
            
    def reset_zoom(self):
        self.updating_scaling = True
        self.zoom_slider.setValue(100) 
        self.zoom_spinbox.setValue(100) 
        self.apply_scene_zoom() 
        
        # Snap the camera back to the center after resetting the scale
        self.recenter_image()
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
            default_pixel_per_mm = self.data_handler.default_pixel_per_mm  # has to work on original image scaling to account for changes in pixel size
            grid_distance_px = grid_distance_mm * default_pixel_per_mm #* self.data_handler.image_scaling

            # cover the image plus one view size around it (also when zoomed out)
            viewport_size = self.image_canvas.viewport().size()
            zoom = self.image_canvas.transform().m11() or 1
            image_rect = self.image_item.sceneBoundingRect()
            width = image_rect.right() + viewport_size.width() / zoom
            height = image_rect.bottom() + viewport_size.height() / zoom
            width, height = min(width, 500 * grid_distance_px), min(height, 500 * grid_distance_px)  # keep it light

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
            #we have to flip the y coordinate as the image coordinates are flipped in y direction compared to the canvas coordinates
            # new_y = self.data_handler.image_matrix.shape[0] - new_y
            self.current_image_center = [new_x, new_y]

            self.update_image_center()

            #turn off the setting mode
            self.set_image_center_button.setChecked(False)
            self.setting_image_center = False

    def reset_image_center_to_default(self):
        image_matrix = self.data_handler.image_matrix
        if image_matrix is None or self.data_handler.image_matrix_original is None:
            self.data_handler.center_for_hatch = None
            return

        # B15: use the current image (the original is not rotated/cropped)
        self.current_image_center = [(image_matrix.shape[1]-1)/2, (image_matrix.shape[0]-1)/2]
        
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

        self.showing_image_center = not self.showing_image_center
        self.show_image_center_button.setChecked(self.showing_image_center)  # P10.5: icon shows / hides
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
            log.exception("Error drawing center cross")
class NewBlankDialog(QtWidgets.QDialog):
    """Dialog for creating a new blank image with user-defined dimensions."""
    
    def __init__(self, parent, image_controller):
        super().__init__(parent)
        self.image_controller = image_controller
        self.updating_fields = False  # Flag to prevent recursive updates
        
        # Load the UI file
        from pathlib import Path
        import sys
        
        # def resource_path(relative: str) -> Path:
        #     if hasattr(sys, "_MEIPASS"):
        #         return Path(sys._MEIPASS) / relative
        #     return Path(__file__).resolve().parent / relative
        ui_path = get_gui_file_path("NewBlank.ui")
        uic.loadUi(ui_path, self)
        
        # Connect the spinboxes
        self.height_mm_spinbox.valueChanged.connect(self.on_height_mm_changed)
        self.width_mm_spinbox.valueChanged.connect(self.on_width_mm_changed)
        self.pixel_size_spinbox.valueChanged.connect(self.on_pixel_size_changed)
        
        self.height_pixel_spinbox.valueChanged.connect(self.on_height_pixels_changed)
        self.wight_pixel_spinbox.valueChanged.connect(self.on_width_pixels_changed)
        self.pixels_per_mm_spinbox.valueChanged.connect(self.on_pixels_per_mm_changed)
        
        # Connect the create button
        self.create_blank_button.clicked.connect(self.create_blank_image)
        
        # Set initial values
        self.height_mm_spinbox.setValue(50.0)
        self.width_mm_spinbox.setValue(50.0)
        self.pixel_size_spinbox.setValue(0.264)
        self.update_pixel_dimensions()
    
    def on_height_mm_changed(self, value):
        """Update pixel height when height in mm changes."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            if pixels_per_mm > 0:
                pixel_height = int(value * pixels_per_mm)
                self.height_pixel_spinbox.setValue(pixel_height)
        finally:
            self.updating_fields = False
    
    def on_width_mm_changed(self, value):
        """Update pixel width when width in mm changes."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            if pixels_per_mm > 0:
                pixel_width = int(value * pixels_per_mm)
                self.wight_pixel_spinbox.setValue(pixel_width)
        finally:
            self.updating_fields = False
    
    def on_pixel_size_changed(self, value):
        """Update pixels_per_mm and mm dimensions when pixel size in mm changes.
        Keeps pixel dimensions fixed, updates mm dimensions."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            if value > 0:
                # Calculate new pixels_per_mm
                pixels_per_mm = 1.0 / value
                
                # Keep pixels fixed, update mm dimensions accordingly
                height_pixel = self.height_pixel_spinbox.value()
                width_pixel = self.wight_pixel_spinbox.value()
                
                height_mm = height_pixel / pixels_per_mm
                width_mm = width_pixel / pixels_per_mm
                
                # Update spinboxes
                self.height_mm_spinbox.setValue(height_mm)
                self.width_mm_spinbox.setValue(width_mm)
                self.pixels_per_mm_spinbox.setValue(round(pixels_per_mm, 1))
        finally:
            self.updating_fields = False
    
    def on_height_pixels_changed(self, value):
        """Update height in mm when pixel height changes."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            if pixels_per_mm > 0:
                height_mm = value / pixels_per_mm
                self.height_mm_spinbox.setValue(height_mm)
        finally:
            self.updating_fields = False
    
    def on_width_pixels_changed(self, value):
        """Update width in mm when pixel width changes."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            if pixels_per_mm > 0:
                width_mm = value / pixels_per_mm
                self.width_mm_spinbox.setValue(width_mm)
        finally:
            self.updating_fields = False
    
    def on_pixels_per_mm_changed(self, value):
        """Update pixel size and pixel dimensions when pixels_per_mm changes.
        Keeps mm dimensions fixed, recalculates pixel dimensions."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            if value > 0:
                # Update pixel size (reciprocal)
                pixel_size = 1.0 / value
                self.pixel_size_spinbox.setValue(pixel_size)
                
                # Keep mm dimensions fixed, recalculate pixel dimensions
                height_mm = self.height_mm_spinbox.value()
                width_mm = self.width_mm_spinbox.value()
                
                pixel_height = int(height_mm * value)
                pixel_width = int(width_mm * value)
                
                self.height_pixel_spinbox.setValue(pixel_height)
                self.wight_pixel_spinbox.setValue(pixel_width)
        finally:
            self.updating_fields = False
    
    def update_pixel_dimensions(self):
        """Update pixel dimensions based on mm dimensions and pixels_per_mm."""
        if self.updating_fields:
            return
        self.updating_fields = True
        try:
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            if pixels_per_mm > 0:
                height_mm = self.height_mm_spinbox.value()
                width_mm = self.width_mm_spinbox.value()
                
                pixel_height = int(height_mm * pixels_per_mm)
                pixel_width = int(width_mm * pixels_per_mm)
                
                self.height_pixel_spinbox.setValue(pixel_height)
                self.wight_pixel_spinbox.setValue(pixel_width)
        finally:
            self.updating_fields = False
    
    def create_blank_image(self):
        """Create a blank white image with the specified dimensions."""
        try:
            # Get the dimensions
            pixel_width = self.wight_pixel_spinbox.value()
            pixel_height = self.height_pixel_spinbox.value()
            pixels_per_mm = self.pixels_per_mm_spinbox.value()
            
            # Validate dimensions
            if pixel_width < 1 or pixel_height < 1 or pixels_per_mm <= 0:
                QtWidgets.QMessageBox.warning(
                    self, "Invalid Dimensions",
                    "Please ensure all dimensions are valid (positive values)."
                )
                return
            
            # Create a transparent (empty) image
            image_matrix = np.zeros((pixel_height, pixel_width, 4), dtype=np.uint8)
            
            # Create ImgObj and add to list
            img_obj = ImageDocument(image_matrix.copy(), image_matrix.copy(), pixels_per_mm, pixels_per_mm)
            
            # Generate a name for the blank image
            width_mm = self.width_mm_spinbox.value()
            height_mm = self.height_mm_spinbox.value()
            name = f"Blank_{width_mm:.1f}x{height_mm:.1f}mm"
            
            # Add to image list
            self.image_controller.changeing_image = True
            self.image_controller.add_listbox_item(img_obj, name, set_selected=True)
            self.image_controller.changeing_image = False
            
            # Update display
            self.image_controller.set_handler_data(new_image=True)
            self.image_controller.update_dimension_fields()
            
            # Center the image
            self.image_controller.gui.image_canvas.centerOn(self.image_controller.gui.image_item)
            
            # Close the dialog
            self.close()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Error creating blank image: {e}")
            log.exception("Error creating blank image")