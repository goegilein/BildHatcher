"""Mask drawing, editing and lifting (P8.4: moved out of ImageEditing.ImageColorer; P12.4: lift off masks).

MaskTools is a mixin of ImageColorer: the mask tools share the colorer's tool toggles (one active tool at a time),
the canvas event routing and the colour-overlay/imprint system, so they work on the same object.
Masks live in data_handler.masks_list (uint8 0/1 matrices), mask_info (shape + image coordinates) and
mask_overlays (dashed outlines in scene coordinates).
"""
import math

import cv2
import numpy as np
from PIL import Image
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPixmap

from UndoRedo import Action, ImageMatrixAction
from core import image_doc


def _fill_mask_shape(mask_matrix, shape, x_min, y_min, x_max, y_max):
    """Set the pixels of a rectangle / ellipse (inclusive pixel bounds) to 1 (vectorized former per-pixel loops)."""
    height, width = mask_matrix.shape
    # clamp both ends: a negative stop would count from the end of the array
    ys = slice(max(0, y_min), max(0, min(height, y_max + 1)))
    xs = slice(max(0, x_min), max(0, min(width, x_max + 1)))
    if shape == 'rectangle':
        mask_matrix[ys, xs] = 1
        return
    radii_x, radii_y = (x_max - x_min) / 2.0, (y_max - y_min) / 2.0
    if radii_x <= 0 or radii_y <= 0:
        return
    y, x = np.ogrid[ys, xs]
    inside = ((x - (x_min + x_max) / 2.0) / radii_x) ** 2 + ((y - (y_min + y_max) / 2.0) / radii_y) ** 2 <= 1.0
    mask_matrix[ys, xs][inside] = 1


class MaskTools:
    def _init_masks(self, gui):
        """Mask state and mask buttons (called from ImageColorer.__init__)."""
        # Lift off masks (P12.4): mask_info[i]['lift'] holds the floating pixels of a lifted mask
        self._lift_counter = 0

        # Add mask drawing functionality
        self.mask_drawing_on = False
        self.mask_shape_mode = "rectangle"  # Can be "rectangle", "ellipse", or "polygon"
        self.data_handler.masks_list = []  # List of mask matrices
        self.data_handler.mask_info = []  # List storing mask type and coordinates: [{'type': 'rectangle', 'coords': (x1, y1, x2, y2)}, ...]
        self.mask_start_point_scene = None
        self.mask_obj = None
        self.current_mask_overlay_item = None
        self.polygon_points = []  # List of points for polygon drawing
        self.polygon_preview_item = None  # Current polygon preview
        
        # Mask editing functionality
        self.editing_mask_index = -1  # Index of the mask being edited
        self.edit_handles = []  # List of QGraphicsEllipseItem handles for resizing
        self.dragging_handle = None  # Current handle being dragged
        self.mask_edit_mode = False  # Whether we're in mask edit mode

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
        self.delete_all_masks_button.clicked.connect(self.delete_all_masks)
        
        # Button to edit masks
        self.edit_mask_button = gui.edit_mask_button
        self.edit_mask_button.clicked.connect(lambda: self.set_single_toggle_state('mask_edit_mode'))

        #Button to deselect mask 
        self.unselect_mask_button = gui.unselect_mask_button
        self.unselect_mask_button.clicked.connect(self.deselect_mask)

        # Lift button: lifts the selected mask; for a lifted mask it imprints it (its checked state = lifted)
        self.move_masked_area_button = gui.move_masked_area_button
        self.move_masked_area_button.clicked.connect(self.lift_selected_or_imprint)
        # Imprint all lifted masks
        gui.imprint_mask_button.clicked.connect(self.imprint_all_masks)
        
        # List widget to display masks
        self.masks_list_widget = gui.masks_list_widget
        self.masks_list_widget.itemSelectionChanged.connect(self.on_mask_selected)

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
        pen.setCosmetic(True)  # 2 screen pixels at every zoom (P12.5)
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
        _fill_mask_shape(mask_matrix, 'rectangle', x_min, y_min, x_max, y_max)

        # Store the mask and its info
        self.data_handler.masks_list.append(mask_matrix)
        self.data_handler.mask_info.append({
            'type': 'rectangle',
            'coords': (x_min, y_min, x_max, y_max)
        })
        self.add_mask_done()
        
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
        pen.setCosmetic(True)  # 2 screen pixels at every zoom (P12.5)
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
        
        # Fill pixels inside ellipse with ones
        _fill_mask_shape(mask_matrix, 'ellipse', x_min, y_min, x_max, y_max)
        
        # Store the mask and its info
        self.data_handler.masks_list.append(mask_matrix)
        self.data_handler.mask_info.append({
            'type': 'ellipse',
            'coords': (x_min, y_min, x_max, y_max)
        })
        self.add_mask_done()
        
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
        pen.setCosmetic(True)  # 2 screen pixels at every zoom (P12.5)
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
        pen.setCosmetic(True)  # 2 screen pixels at every zoom (P12.5)
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
        self.data_handler.mask_info.append({
            'type': 'polygon',
            'coords': self.polygon_points.copy()
        })
        self.add_mask_done()
        
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

    def add_mask_done(self):
        """A new mask was appended: list it and select it (it is the one the user wants to edit / move next)."""
        self.refresh_mask_outlines()  # exact outline from the pixel coordinates (the drawing preview is rounded)
        self.update_masks_list_widget()
        self.masks_list_widget.setCurrentRow(len(self.data_handler.masks_list) - 1)

    def update_masks_list_widget(self):
        """Update the masks list widget display."""
        self.masks_list_widget.clear()
        for idx, mask in enumerate(self.data_handler.masks_list):
            non_nan_count = np.count_nonzero(mask == 1)
            type = self.data_handler.mask_info[idx]['type']
            item_text = f"{type}-mask {idx + 1} ({non_nan_count} pixels)"
            self.masks_list_widget.addItem(item_text)

    def refresh_mask_outlines(self):
        """Rebuild the (scene coordinate) mask outlines from their image coordinates after the display scale changed."""
        to_scene = lambda x, y: QtCore.QPointF(*self.data_handler.image_to_scene_coords(x, y))
        for overlay, info in zip(self.data_handler.mask_overlays, self.data_handler.mask_info):
            if info['type'] in ('rectangle', 'ellipse'):
                x_min, y_min, x_max, y_max = info['coords']
                overlay.setRect(QtCore.QRectF(to_scene(x_min, y_min), to_scene(x_max + 1, y_max + 1)))  # covers the pixels
            elif info['type'] == 'polygon':
                overlay.setPolygon(QtGui.QPolygonF([to_scene(x, y) for x, y in info['coords']]))
        for index in range(len(self.data_handler.mask_overlays)):
            self._place_frame(index)  # lifted masks: frame at the dragged place
        if self.edit_handles:
            self.clear_edit_handles()
            self.show_edit_handles_for_selected()

    def on_mask_selected(self):
        """Handle mask selection in the list widget."""
        # Clear any existing edit handles
        self.clear_edit_handles()
        
        selected_items = self.masks_list_widget.selectedItems()
        if selected_items:
            index = self.masks_list_widget.row(selected_items[0])
            self.data_handler.active_mask_index = index
            self.editing_mask_index = index
            # Show edit handles if edit mode is enabled
            self.show_edit_handles_for_selected()
        else:
            self.editing_mask_index = -1
        self.update_lift_controls()  # frame colours, lift / imprint buttons

    def show_edit_handles_for_selected(self):
        """Show edit handles for the currently selected mask (if in edit mode)."""
        if not self.mask_edit_mode or self.editing_mask_index < 0 or self.is_lifted(self.editing_mask_index):
            return  # a lifted mask is moved, not reshaped
        
        self.clear_edit_handles()
        
        if self.editing_mask_index < len(self.data_handler.mask_overlays):
            overlay = self.data_handler.mask_overlays[self.editing_mask_index]
            
            if self.editing_mask_index < len(self.data_handler.mask_info):
                mask_info = self.data_handler.mask_info[self.editing_mask_index]
                if mask_info['type'] in ['rectangle', 'ellipse']:
                    self.add_resize_handles(self.editing_mask_index, overlay)
                elif mask_info['type'] == 'polygon':
                    self.add_polygon_handles(self.editing_mask_index, overlay)

    def clear_edit_handles(self):
        """Remove all edit handles from the scene."""
        for handle in self.edit_handles:
            self.gui.image_scene.removeItem(handle)
        self.edit_handles.clear()
        self.dragging_handle = None

    def add_resize_handles(self, mask_index, overlay):
        """Add draggable corner handles to rectangle/ellipse masks."""
        rect = overlay.rect()
        handle_size = 10
        
        # Define handle positions: corners and midpoints
        positions = [
            (rect.left(), rect.top(), 'tl'),      # Top-left
            (rect.right(), rect.top(), 'tr'),     # Top-right
            (rect.left(), rect.bottom(), 'bl'),   # Bottom-left
            (rect.right(), rect.bottom(), 'br'),  # Bottom-right
            (rect.center().x(), rect.top(), 'tm'),   # Top-middle
            (rect.center().x(), rect.bottom(), 'bm'), # Bottom-middle
            (rect.left(), rect.center().y(), 'lm'),  # Left-middle
            (rect.right(), rect.center().y(), 'rm'),  # Right-middle
        ]
        
        for x, y, handle_type in positions:
            handle = QtWidgets.QGraphicsEllipseItem(
                x - handle_size/2, y - handle_size/2, 
                handle_size, handle_size
            )
            handle.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.red))
            handle.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1))
            handle.setZValue(100)  # Above the overlay
            
            # Store metadata
            handle.mask_index = mask_index
            handle.handle_type = handle_type
            
            self.gui.image_scene.addItem(handle)
            self.edit_handles.append(handle)

    def add_polygon_handles(self, mask_index, overlay):
        """Add draggable point handles to polygon masks."""
        if isinstance(overlay, QtWidgets.QGraphicsPolygonItem):
            polygon = overlay.polygon()
            handle_size = 10
            
            for i, point in enumerate(polygon):
                handle = QtWidgets.QGraphicsEllipseItem(
                    point.x() - handle_size/2, point.y() - handle_size/2,
                    handle_size, handle_size
                )
                handle.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.red))
                handle.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1))
                handle.setZValue(100)  # Above the overlay
                
                # Store metadata
                handle.mask_index = mask_index
                handle.point_index = i
                handle.handle_type = 'polygon_point'
                
                self.gui.image_scene.addItem(handle)
                self.edit_handles.append(handle)

    def drag_edit_handle(self, event):
        """Handle dragging of edit handles."""
        if self.dragging_handle is None or self.editing_mask_index < 0:
            return
        
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(x_canvas, y_canvas)
        
        overlay = self.data_handler.mask_overlays[self.editing_mask_index]
        
        # Handle polygon point dragging
        if hasattr(self.dragging_handle, 'point_index'):
            polygon = overlay.polygon()
            polygon[self.dragging_handle.point_index] = QtCore.QPointF(x_scene, y_scene)
            overlay.setPolygon(polygon)
        else:
            # Handle rectangle/ellipse dragging
            rect = overlay.rect()
            handle_type = self.dragging_handle.handle_type
            
            # Update rect based on which handle is being dragged
            if handle_type == 'tl':  # Top-left
                rect.setTopLeft(QtCore.QPointF(x_scene, y_scene))
            elif handle_type == 'tr':  # Top-right
                rect.setTopRight(QtCore.QPointF(x_scene, y_scene))
            elif handle_type == 'bl':  # Bottom-left
                rect.setBottomLeft(QtCore.QPointF(x_scene, y_scene))
            elif handle_type == 'br':  # Bottom-right
                rect.setBottomRight(QtCore.QPointF(x_scene, y_scene))
            elif handle_type == 'tm':  # Top-middle
                rect.setTop(y_scene)
                # center_x = rect.center().x()
                # rect.setLeft(rect.left() + (x_scene - center_x))
                # rect.setRight(rect.right() + (x_scene - center_x))
            elif handle_type == 'bm':  # Bottom-middle
                rect.setBottom(y_scene)
                # center_x = rect.center().x()
                # rect.setLeft(rect.left() + (x_scene - center_x))
                # rect.setRight(rect.right() + (x_scene - center_x))
            elif handle_type == 'lm':  # Left-middle
                rect.setLeft(x_scene)
            elif handle_type == 'rm':  # Right-middle
                rect.setRight(x_scene)
            
            overlay.setRect(rect)
        
        # Move the handle
        handle_size = 10
        self.dragging_handle.setRect(
            x_scene - handle_size/2, y_scene - handle_size/2,
            handle_size, handle_size
        )

    def finish_drag_edit_handle(self, event):
        """Finish dragging and update the mask."""
        if self.dragging_handle is None or self.editing_mask_index < 0:
            self.dragging_handle = None
            return
        
        mask_index = self.editing_mask_index
        overlay = self.data_handler.mask_overlays[mask_index]
        mask_info = self.data_handler.mask_info[mask_index]
        
        x_canvas = event.position().x()
        y_canvas = event.position().y()
        x_img, y_img = self.data_handler.canvas_to_image_coords(x_canvas, y_canvas)
        
        # Update the mask based on type
        if mask_info['type'] in ['rectangle', 'ellipse']:
            self.update_rect_ellipse_mask_from_drag(mask_index, overlay, mask_info)
            # Update handle positions to match the new rect
            self.update_resize_handles_positions(mask_index, overlay)
        elif mask_info['type'] == 'polygon':
            self.update_polygon_mask_from_drag(mask_index, overlay, mask_info)
            # Update handle positions to match the new polygon
            self.update_polygon_handles_positions(mask_index, overlay)
        
        self.dragging_handle = None

    def update_rect_ellipse_mask_from_drag(self, mask_index, overlay, mask_info):
        """Update rectangle/ellipse mask after handle drag."""
        rect = overlay.rect()
        x_min_scene, y_min_scene = rect.left(), rect.top()
        x_max_scene, y_max_scene = rect.right(), rect.bottom()
        
        # Convert scene coordinates to image coordinates
        x_min, y_min = self.data_handler.scene_to_image_coords(x_min_scene, y_min_scene)
        x_max, y_max = self.data_handler.scene_to_image_coords(x_max_scene, y_max_scene)
        
        # Update mask info with image coordinates
        self.data_handler.mask_info[mask_index]['coords'] = (x_min, y_min, x_max, y_max)
        
        # Regenerate mask matrix
        image_matrix = self.data_handler.image_matrix
        height, width = image_matrix.shape[:2]
        mask_matrix = np.zeros((height, width), dtype=image_matrix.dtype)
        
        if mask_info['type'] == 'rectangle':
            _fill_mask_shape(mask_matrix, 'rectangle', x_min, y_min, x_max, y_max)
        else:  # ellipse
            _fill_mask_shape(mask_matrix, 'ellipse', x_min, y_min, x_max, y_max)
        
        self.data_handler.masks_list[mask_index] = mask_matrix
        self.update_masks_list_widget_keep_selection(mask_index)

    def update_polygon_mask_from_drag(self, mask_index, overlay, mask_info):
        """Update polygon mask after vertex drag."""
        if isinstance(overlay, QtWidgets.QGraphicsPolygonItem):
            polygon = overlay.polygon()
            new_points = []
            
            for point in polygon:
                x_img, y_img = self.data_handler.scene_to_image_coords(point.x(), point.y())
                new_points.append((int(x_img), int(y_img)))
            
            # Update mask info
            self.data_handler.mask_info[mask_index]['coords'] = new_points
            
            # Regenerate mask matrix
            image_matrix = self.data_handler.image_matrix
            height, width = image_matrix.shape[:2]
            mask_matrix = np.zeros((height, width), dtype=image_matrix.dtype)
            
            pts = np.array(new_points, dtype=np.int32)
            cv2.fillPoly(mask_matrix, [pts], 1)
            
            self.data_handler.masks_list[mask_index] = mask_matrix
            self.update_masks_list_widget_keep_selection(mask_index)

    def update_masks_list_widget_keep_selection(self, selected_index):
        """Update the masks list widget while keeping a specific mask selected."""
        # Block signals to prevent triggering itemSelectionChanged during update
        self.masks_list_widget.blockSignals(True)
        
        self.masks_list_widget.clear()
        for idx, mask in enumerate(self.data_handler.masks_list):
            non_nan_count = np.count_nonzero(mask == 1)
            item_text = f"Mask {idx + 1} ({non_nan_count} pixels)"
            self.masks_list_widget.addItem(item_text)
        
        # Restore selection
        if selected_index >= 0 and selected_index < self.masks_list_widget.count():
            self.masks_list_widget.setCurrentRow(selected_index)
        
        # Re-enable signals
        self.masks_list_widget.blockSignals(False)

    def update_resize_handles_positions(self, mask_index, overlay):
        """Update positions of resize handles to match the overlay rect."""
        if mask_index >= len(self.edit_handles):
            return
        
        rect = overlay.rect()
        handle_size = 10
        
        positions = [
            (rect.left(), rect.top()),      # Top-left
            (rect.right(), rect.top()),     # Top-right
            (rect.left(), rect.bottom()),   # Bottom-left
            (rect.right(), rect.bottom()),  # Bottom-right
            (rect.center().x(), rect.top()),   # Top-middle
            (rect.center().x(), rect.bottom()), # Bottom-middle
            (rect.left(), rect.center().y()),  # Left-middle
            (rect.right(), rect.center().y()),  # Right-middle
        ]
        
        handle_index = 0
        for handle in self.edit_handles:
            if handle.mask_index == mask_index and hasattr(handle, 'handle_type') and not hasattr(handle, 'point_index'):
                if handle_index < len(positions):
                    x, y = positions[handle_index]
                    handle.setRect(x - handle_size/2, y - handle_size/2, handle_size, handle_size)
                    handle_index += 1

    def update_polygon_handles_positions(self, mask_index, overlay):
        """Update positions of polygon handles to match the overlay polygon."""
        if isinstance(overlay, QtWidgets.QGraphicsPolygonItem):
            polygon = overlay.polygon()
            handle_size = 10
            
            for handle in self.edit_handles:
                if handle.mask_index == mask_index and hasattr(handle, 'point_index'):
                    if handle.point_index < len(polygon):
                        point = polygon[handle.point_index]
                        handle.setRect(point.x() - handle_size/2, point.y() - handle_size/2, handle_size, handle_size)

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
        
        # keep pixels where mask==1, transparent elsewhere
        output_image = np.zeros_like(image_cropped)
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
                if file_path.lower().endswith(".png"):
                    image = Image.fromarray(output_image, mode="RGBA")
                else:
                    image = Image.fromarray(image_doc.composite(output_image), mode="RGB")
                # Add DPI information based on current pixel_per_mm
                dpi = round(self.data_handler.pixel_per_mm * 25.4)
                # Save with DPI metadata
                image.save(file_path, dpi=(dpi, dpi))
                QtWidgets.QMessageBox.information(self.gui, "Success", f"Mask saved successfully to:\n{file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self.gui, "Error Saving Mask", f"Error saving mask: {e}")
    
    def deselect_mask(self):
        """Deselect any selected mask."""
        self.masks_list_widget.clearSelection()
        self.data_handler.active_mask_index = -1
        self.editing_mask_index = -1
        
        self.edit_mask_button.setChecked(False)
        self.clear_edit_handles()
        self.update_lift_controls()

    def delete_selected_mask(self):
        """Delete the currently selected mask."""
        selected_items = self.masks_list_widget.selectedItems()
        if selected_items:
            index = self.masks_list_widget.row(selected_items[0])
            # the indices of the masks behind it shift: no mask stays selected
            self.deselect_mask()
            self._remove_lift_items(index)  # a lifted mask: its pixels simply stay where they are in the image
            self.data_handler.masks_list.pop(index)
            self.gui.image_scene.removeItem(self.data_handler.mask_overlays[index])
            self.data_handler.mask_overlays.pop(index)
            if index < len(self.data_handler.mask_info):
                self.data_handler.mask_info.pop(index)
            self.clear_edit_handles()
            self.update_masks_list_widget()
            self.update_lift_controls()

    def delete_all_masks(self):
        """Clear all masks."""
        reply = QtWidgets.QMessageBox.question(
            self.gui, "Clear All Masks",
            "Are you sure you want to delete all masks?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.reset_masks()

    def reset_masks(self):
        """Remove all masks without asking (also used when the image size changes, B17)."""
        #ensure deselection and edit mode reset first!
        self.deselect_mask()
        self.cancel_mask_drawing()
        #then delete all masks and overlays (lifted ones: nothing was changed in the image yet)
        for index in range(len(self.data_handler.mask_info)):
            self._remove_lift_items(index)
        self.data_handler.masks_list.clear()
        self.data_handler.mask_info.clear()
        self.clear_edit_handles()
        self.update_masks_list_widget()
        for overlay in self.data_handler.mask_overlays:
            if overlay.scene() is not None:
                self.gui.image_scene.removeItem(overlay)
        self.data_handler.mask_overlays.clear()
        self.update_lift_controls()

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
    



    # LIFT OFF MASKS (P12.4)
    # A lifted mask is a floating layer: its pixels are cut out of the image into a movable overlay (drag & drop),
    # the image itself is unchanged until the mask is imprinted (then the old place becomes transparent and the
    # pixels land at the new place; the mask moves along). Lifted masks have an orange frame.
    def is_lifted(self, index):
        return 0 <= index < len(self.data_handler.mask_info) and 'lift' in self.data_handler.mask_info[index]

    def lifted_indices(self):
        """Indices of the lifted masks, in the order they were lifted."""
        found = [i for i in range(len(self.data_handler.mask_info)) if self.is_lifted(i)]
        return sorted(found, key=lambda i: self.data_handler.mask_info[i]['lift']['order'])

    def can_drag_lifted(self):
        """Lifted masks are dragged with the plain mouse – not while a tool (draw, fill, mask drawing ...) is on."""
        return self.active_tool == ""

    def select_mask_at(self, event):
        """P12.5: a click into the image selects the (not lifted) mask under the mouse – the last drawn one when
        masks overlap. Clicks on lifted masks, their handles and text / geometry overlays are theirs."""
        for item in self.gui.image_canvas.items(event.pos()):
            if isinstance(item, (LiftedMaskItem, RotateHandle)) or \
                    item.flags() & QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return
        if self.data_handler.image_matrix is None:
            return
        x, y = self.data_handler.canvas_to_image_coords(event.position().x(), event.position().y())
        for index in range(len(self.data_handler.masks_list) - 1, -1, -1):
            mask = self.data_handler.masks_list[index]
            if not self.is_lifted(index) and 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x] == 1:
                if self.masks_list_widget.currentRow() != index:
                    self.masks_list_widget.setCurrentRow(index)
                return

    def lift_selected_or_imprint(self):
        """The lift button: lift the selected mask, or imprint it if it is lifted already."""
        index = self.editing_mask_index
        if index >= 0:
            if self.is_lifted(index):
                self.imprint_masks([index], "Imprint Mask")
            else:
                self.lift_mask(index)
        self.update_lift_controls()

    def lift_mask(self, index):
        """Cut the masked pixels out into a movable overlay (the image does not change)."""
        if self.is_lifted(index) or self.data_handler.image_matrix is None:
            return
        info = self.data_handler.mask_info[index]
        before = self._mask_snapshot([info])
        mask = self.data_handler.masks_list[index]
        ys, xs = np.nonzero(mask == 1)
        if len(ys) == 0:
            return
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        image = self.data_handler.image_matrix
        crop = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        inside = mask[y0:y1, x0:x1] == 1
        crop[inside] = image[y0:y1, x0:x1][inside]
        self._lift_counter = getattr(self, "_lift_counter", 0) + 1
        self._create_lift_items(index, crop, (int(x0), int(y0)), (0, 0), self._lift_counter, 0.0)
        self._push_mask_action(before, self._mask_snapshot([info]), None, "Lift Mask")
        self.update_lift_controls()

    def imprint_all_masks(self):
        self.imprint_masks(self.lifted_indices(), "Imprint All Masks")

    def imprint_masks(self, indices, description="Imprint Mask"):
        """Put lifted masks back into the image at their current place (in lift order): their old place becomes
        transparent, their pixels are painted where they are now, the masks move along."""
        indices = [i for i in self.lifted_indices() if i in indices]
        if not indices or self.data_handler.image_matrix is None:
            return
        infos = [self.data_handler.mask_info[i] for i in indices]
        before = self._mask_snapshot(infos)
        before_image = self.data_handler.image_matrix.copy()
        image = before_image.copy()
        h, w = image.shape[:2]
        for i in indices:
            info, mask = self.data_handler.mask_info[i], self.data_handler.masks_list[i]
            lift = info['lift']
            qy, qx, sy, sx = self._lift_mapping(lift, mask, (h, w))
            image[mask == 1] = image_doc.TRANSPARENT  # the old place
            pixels = lift['crop'][sy, sx]
            opaque = pixels[:, 3] > 0                  # lifted pixels that are not transparent
            image[qy[opaque], qx[opaque]] = pixels[opaque]
            new_mask = np.zeros_like(mask)              # the mask moves (and turns) along, pixel for pixel
            new_mask[qy, qx] = 1
            self.data_handler.masks_list[i] = new_mask
            self._transform_mask_info(i, lift)
            self._remove_lift_items(i)
        self.data_handler.image_matrix = image
        self.refresh_mask_outlines()
        self.update_masks_list_widget_keep_selection(self.editing_mask_index)
        image_action = self._image_action(before_image, self.data_handler.image_matrix.copy(), description)
        self._push_mask_action(before, self._mask_snapshot(infos), image_action, description)
        self.update_lift_controls()

    def lifted_mask_moved(self, item):
        """A lifted mask is being dragged: its frame follows."""
        for i, info in enumerate(self.data_handler.mask_info):
            if info.get('lift', {}).get('pixels') is item:
                self._place_frame(i)
                return

    def lifted_mask_pressed(self, item):
        """Dragging a lifted mask selects it."""
        for i, info in enumerate(self.data_handler.mask_info):
            if info.get('lift', {}).get('pixels') is item and self.masks_list_widget.currentRow() != i:
                self.masks_list_widget.setCurrentRow(i)
                return

    def lifted_mask_dropped(self, item, start_pos, start_rotation=None):
        """Drag & drop or turning finished: one undo step."""
        for info in self.data_handler.mask_info:
            lift = info.get('lift')
            if lift and lift['pixels'] is item:
                after = self._mask_snapshot([info])
                changes = {'offset': (int(start_pos.x()), int(start_pos.y()))}
                if start_rotation is not None:
                    changes['rotation'] = start_rotation
                before = [(snap[0], snap[1], snap[2], dict(snap[3], **changes), snap[4]) for snap in after]
                self._push_mask_action(before, after, None,
                                       "Rotate Lifted Mask" if start_rotation is not None else "Move Lifted Mask")
                return

    def update_lift_controls(self):
        """Lift button = "imprint mask" while the selected mask is lifted; imprint-all buttons while any is."""
        index = self.editing_mask_index
        button = self.move_masked_area_button
        lifted = self.is_lifted(index)
        button.blockSignals(True)
        button.setChecked(lifted)
        button.blockSignals(False)
        button.setEnabled(index >= 0)
        button.setToolTip("Imprint the lifted mask into the image" if lifted else
                          "Lift off the selected mask: cut it out as a layer you can drag; imprint puts it back")
        any_lifted = bool(self.lifted_indices())
        imprint_all = getattr(self.gui, "imprint_mask_button", None)
        if imprint_all is not None:
            imprint_all.setEnabled(any_lifted)
        self.apply_mask_pens()

    def apply_mask_pens(self):
        """Dashed frames: cyan, the selected one darker; lifted masks orange (the selected one with its rotation
        handle)."""
        for i, overlay in enumerate(self.data_handler.mask_overlays):
            selected = i == self.editing_mask_index
            if self.is_lifted(i):
                self.data_handler.mask_info[i]['lift']['pixels'].show_handle(selected)
            if self.is_lifted(i):
                color = QtGui.QColor(LIFT_SELECTED_COLOR if selected else LIFT_COLOR)
            else:
                color = QtGui.QColor(QtCore.Qt.GlobalColor.darkCyan if selected else QtCore.Qt.GlobalColor.cyan)
            pen = QtGui.QPen(color)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            pen.setWidth(2)
            pen.setCosmetic(True)  # 2 screen pixels at every zoom (P12.5)
            overlay.setPen(pen)

    # --- lift internals ---
    @staticmethod
    def _lift_offset(lift):
        pos = lift['pixels'].pos()
        return int(round(pos.x())), int(round(pos.y()))

    @staticmethod
    def _shifted_coords(info, dx, dy):
        if info['type'] in ('rectangle', 'ellipse'):
            x1, y1, x2, y2 = info['coords']
            return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        return [(px + dx, py + dy) for px, py in info['coords']]

    def _create_lift_items(self, index, crop, origin, offset, order, rotation=0.0):
        info = self.data_handler.mask_info[index]
        mask = self.data_handler.masks_list[index]
        x0, y0 = origin
        h, w = crop.shape[:2]
        # the vacated place, shown as "will become transparent"
        cut = np.zeros((h, w, 4), np.uint8)
        inside = mask[y0:y0 + h, x0:x0 + w] == 1
        cut[inside] = self._checker_rgba(h, w)[inside]
        cutout = QtWidgets.QGraphicsPixmapItem(_pixmap(cut), self.gui.image_item)
        cutout.setOffset(x0, y0)
        cutout.setZValue(11)
        pixels = LiftedMaskItem(_pixmap(crop), self.gui.image_item, self)
        pixels.setOffset(x0, y0)
        pixels.setTransformOriginPoint(QtCore.QPointF(x0 + w / 2, y0 + h / 2))  # turns about the mask centre
        pixels.setPos(*offset)
        pixels.setRotation(rotation)
        info['lift'] = {'crop': crop, 'origin': (x0, y0), 'order': order, 'cutout': cutout, 'pixels': pixels}
        self._place_frame(index)

    def _remove_lift_items(self, index):
        info = self.data_handler.mask_info[index]
        lift = info.pop('lift', None)
        if lift:
            for item in (lift['cutout'], lift['pixels']):
                if item.scene() is not None:
                    item.scene().removeItem(item)
        if index < len(self.data_handler.mask_overlays):
            frame = self.data_handler.mask_overlays[index]
            frame.setPos(0, 0)
            frame.setRotation(0)

    def _place_frame(self, index):
        """Move the dashed frame of a lifted mask by its lift offset (frames are in scene coordinates)."""
        if index >= len(self.data_handler.mask_overlays):
            return
        frame = self.data_handler.mask_overlays[index]
        if not self.is_lifted(index):
            frame.setPos(0, 0)
            frame.setRotation(0)
            return
        pixels = self.data_handler.mask_info[index]['lift']['pixels']
        dx, dy = self._lift_offset(self.data_handler.mask_info[index]['lift'])
        item = self.gui.image_item
        # the frame (scene coordinates) turns about the same mask centre and moves by the same offset
        frame.setTransformOriginPoint(item.mapToScene(pixels.transformOriginPoint()))
        frame.setRotation(pixels.rotation())
        frame.setPos(item.mapToScene(QtCore.QPointF(dx, dy)) - item.mapToScene(QtCore.QPointF(0, 0)))

    @staticmethod
    def _lift_transform(lift):
        """(dx, dy, ox, oy, cos, sin) of a lift: offset, turning centre (image px) and rotation (clockwise)."""
        pixels = lift['pixels']
        dx, dy = MaskTools._lift_offset(lift)
        origin = pixels.transformOriginPoint()
        angle = math.radians(pixels.rotation())
        return dx, dy, origin.x(), origin.y(), math.cos(angle), math.sin(angle)

    def _lift_mapping(self, lift, mask, shape):
        """Image pixels the lifted mask covers now and where they come from (nearest neighbour, so no new
        colours): (dest rows, dest cols, crop rows, crop cols) for every covered pixel of the mask."""
        h_img, w_img = shape
        crop = lift['crop']
        ch, cw = crop.shape[:2]
        x0, y0 = lift['origin']
        dx, dy, ox, oy, cos, sin = self._lift_transform(lift)
        corners = [(x0, y0), (x0 + cw, y0), (x0, y0 + ch), (x0 + cw, y0 + ch)]
        xs = [dx + ox + cos * (x - ox) - sin * (y - oy) for x, y in corners]
        ys = [dy + oy + sin * (x - ox) + cos * (y - oy) for x, y in corners]
        bx0, bx1 = max(0, math.floor(min(xs))), min(w_img, math.ceil(max(xs)))
        by0, by1 = max(0, math.floor(min(ys))), min(h_img, math.ceil(max(ys)))
        if bx0 >= bx1 or by0 >= by1:
            empty = np.zeros(0, int)
            return empty, empty, empty, empty
        qy, qx = np.mgrid[by0:by1, bx0:bx1]
        rx, ry = qx + 0.5 - dx - ox, qy + 0.5 - dy - oy          # destination pixel centre, relative
        sx = np.floor(ox + cos * rx + sin * ry + 1e-9).astype(int) - x0   # turned back into the crop
        sy = np.floor(oy - sin * rx + cos * ry + 1e-9).astype(int) - y0
        ok = (sx >= 0) & (sx < cw) & (sy >= 0) & (sy < ch)
        ok[ok] = mask[(sy + y0)[ok], (sx + x0)[ok]] == 1         # only pixels of the mask itself
        return qy[ok], qx[ok], sy[ok], sx[ok]

    def _transform_mask_info(self, index, lift):
        """Move (and turn) the mask's shape description; a turned rectangle / ellipse becomes a polygon."""
        info = self.data_handler.mask_info[index]
        dx, dy, ox, oy, cos, sin = self._lift_transform(lift)
        if abs(sin) < 1e-9 and cos > 0:  # not turned: keep the shape type, whole pixels
            info['coords'] = self._shifted_coords(info, dx, dy)
            return

        def turn(x, y):
            return (dx + ox + cos * (x - ox) - sin * (y - oy), dy + oy + sin * (x - ox) + cos * (y - oy))
        if info['type'] == 'rectangle':
            x1, y1, x2, y2 = info['coords']
            outline = [(x1, y1), (x2 + 1, y1), (x2 + 1, y2 + 1), (x1, y2 + 1)]
        elif info['type'] == 'ellipse':
            x1, y1, x2, y2 = info['coords']
            cx, cy, rx, ry = (x1 + x2 + 1) / 2, (y1 + y2 + 1) / 2, (x2 - x1 + 1) / 2, (y2 - y1 + 1) / 2
            outline = [(cx + rx * math.cos(t), cy + ry * math.sin(t))
                       for t in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
        else:
            outline = list(info['coords'])
        info['type'] = 'polygon'
        info['coords'] = [tuple(round(v, 2) for v in turn(x, y)) for x, y in outline]
        self._match_overlay_type(index)

    def _match_overlay_type(self, index):
        """The frame item must fit the mask type (a turned rectangle / ellipse is drawn as a polygon)."""
        if index >= len(self.data_handler.mask_overlays):
            return
        wanted = {'rectangle': QtWidgets.QGraphicsRectItem, 'ellipse': QtWidgets.QGraphicsEllipseItem,
                  'polygon': QtWidgets.QGraphicsPolygonItem}[self.data_handler.mask_info[index]['type']]
        old = self.data_handler.mask_overlays[index]
        if type(old) is wanted:
            return
        new = wanted()
        new.setPen(old.pen())
        new.setBrush(QtGui.QBrush())
        if old.scene() is not None:
            old.scene().removeItem(old)
        self.gui.image_scene.addItem(new)
        self.data_handler.mask_overlays[index] = new

    def _mask_snapshot(self, infos):
        """State of some masks for undo: (info, mask matrix, coords, lift or None) – infos by identity, so it
        stays right when other masks are added or deleted in between."""
        snapshot = []
        for info in infos:
            index = next(i for i, other in enumerate(self.data_handler.mask_info) if other is info)
            lift = info.get('lift')
            lift_state = None if lift is None else {'crop': lift['crop'], 'origin': lift['origin'],
                                                     'order': lift['order'], 'offset': self._lift_offset(lift),
                                                     'rotation': lift['pixels'].rotation()}
            coords = info['coords'] if info['type'] != 'polygon' else list(info['coords'])
            snapshot.append((info, self.data_handler.masks_list[index].copy(), coords, lift_state, info['type']))
        return snapshot

    def _restore_mask_snapshot(self, snapshot):
        for info, mask, coords, lift_state, mask_type in snapshot:
            index = next((i for i, other in enumerate(self.data_handler.mask_info) if other is info), None)
            if index is None:  # the mask was deleted meanwhile
                continue
            self._remove_lift_items(index)
            self.data_handler.masks_list[index] = mask.copy()
            info['type'] = mask_type
            info['coords'] = coords if mask_type != 'polygon' else list(coords)
            self._match_overlay_type(index)
            if lift_state is not None:
                self._create_lift_items(index, lift_state['crop'], lift_state['origin'], lift_state['offset'],
                                        lift_state['order'], lift_state['rotation'])
        self.refresh_mask_outlines()
        self.update_masks_list_widget_keep_selection(self.editing_mask_index)
        self.update_lift_controls()

    def _image_action(self, before, after, description):
        controller = getattr(self.undo_manager, "image_controller", None) if self.undo_manager else None
        item = getattr(controller, "active_image_item", None)
        if item is None and hasattr(self.gui, "images_ListWidget"):
            item = self.gui.images_ListWidget.currentItem()
        ppm = self.data_handler.pixel_per_mm
        return ImageMatrixAction(self.data_handler, self.gui, controller, before, after, ppm, ppm,
                                 image_item=item, description=description)

    def _push_mask_action(self, before, after, image_action, description):
        if self.undo_manager:
            self.undo_manager.push_action(MaskLiftAction(self, before, after, image_action, description))


LIFT_COLOR = "#FF6D00"           # lifted masks: bright orange frame
LIFT_SELECTED_COLOR = "#C43C00"  # the selected lifted mask: darker


def _pixmap(rgba):
    h, w = rgba.shape[:2]
    data = np.ascontiguousarray(rgba)
    return QPixmap.fromImage(QImage(data.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy())


class LiftedMaskItem(QtWidgets.QGraphicsPixmapItem):
    """The pixels of a lifted mask: dragged with the mouse (whole image pixels) while no tool is on."""

    def __init__(self, pixmap, parent, owner):
        super().__init__(pixmap, parent)
        self.owner = owner
        self.setZValue(12)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._press_pos = None
        self.handle = RotateHandle(self)

    def show_handle(self, visible):
        self.handle.place()
        self.handle.setVisible(visible)
        self.handle.stem.setVisible(visible)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton or not self.owner.can_drag_lifted():
            event.ignore()
            return
        self._press_pos = self.pos()
        self.owner.lifted_mask_pressed(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._press_pos is not None and self.pos() != self._press_pos:
            self.owner.lifted_mask_dropped(self, self._press_pos)
        self._press_pos = None

    def itemChange(self, change, value):
        Change = QtWidgets.QGraphicsItem.GraphicsItemChange
        if change == Change.ItemPositionChange:
            return QtCore.QPointF(round(value.x()), round(value.y()))
        if change in (Change.ItemPositionHasChanged, Change.ItemRotationHasChanged):
            self.owner.lifted_mask_moved(self)  # the frame follows
        return super().itemChange(change, value)


class RotateHandle(QtWidgets.QGraphicsEllipseItem):
    """P12.5: the handle above a selected lifted mask; dragging it turns the mask (Shift: 15 degree steps).
    A child of the lifted pixels, so it moves and turns with them; constant size on screen."""

    RADIUS = 6

    def __init__(self, lifted):
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, lifted)
        self.lifted = lifted
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setPen(QtGui.QPen(QtGui.QColor("white"), 1.5))
        self.setBrush(QtGui.QColor(LIFT_COLOR))
        self.setZValue(2)
        self.setToolTip("Drag to turn the lifted mask (Shift: 15 degree steps)")
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.stem = QtWidgets.QGraphicsLineItem(lifted)
        pen = QtGui.QPen(QtGui.QColor(LIFT_COLOR), 1.5)
        pen.setCosmetic(True)
        self.stem.setPen(pen)
        self.setVisible(False)
        self.stem.setVisible(False)
        self._start_rotation = None
        self.place()

    def place(self):
        """Above the middle of the mask's top edge (in the lifted item's own, unturned coordinates)."""
        rect = self.lifted.boundingRect()
        gap = max(3.0, rect.height() * 0.15)
        top = QtCore.QPointF(rect.center().x(), rect.top())
        self.setPos(top.x(), top.y() - gap)
        self.stem.setLine(top.x(), top.y(), top.x(), top.y() - gap)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton or not self.lifted.owner.can_drag_lifted():
            event.ignore()
            return
        self._start_rotation = self.lifted.rotation()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._start_rotation is None:
            return
        centre = self.lifted.mapToScene(self.lifted.transformOriginPoint())
        point = event.scenePos()
        angle = math.degrees(math.atan2(point.y() - centre.y(), point.x() - centre.x())) + 90  # handle is on top
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            angle = round(angle / 15) * 15
        self.lifted.setRotation(angle % 360)
        self.lifted.owner.lifted_mask_moved(self.lifted)

    def mouseReleaseEvent(self, event):
        if self._start_rotation is not None and self.lifted.rotation() != self._start_rotation:
            self.lifted.owner.lifted_mask_dropped(self.lifted, self.lifted.pos(), self._start_rotation)
        self._start_rotation = None


class MaskLiftAction(Action):
    """Undo / redo of lifting, moving and imprinting masks (mask state + the image for imprints)."""

    def __init__(self, owner, before, after, image_action=None, description="Lift Mask"):
        super().__init__(description)
        self.owner, self.before, self.after, self.image_action = owner, before, after, image_action

    def undo(self):
        if self.image_action is not None:
            self.image_action.undo()
        self.owner._restore_mask_snapshot(self.before)

    def redo(self):
        if self.image_action is not None:
            self.image_action.redo()
        self.owner._restore_mask_snapshot(self.after)
