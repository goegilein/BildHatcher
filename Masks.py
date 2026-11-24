"""Mask drawing, editing and moving (P8.4: moved out of ImageEditing.ImageColorer).

MaskTools is a mixin of ImageColorer: the mask tools share the colorer's tool toggles (one active tool at a time),
the canvas event routing and the colour-overlay/imprint system, so they work on the same object.
Masks live in data_handler.masks_list (uint8 0/1 matrices), mask_info (shape + image coordinates) and
mask_overlays (dashed outlines in scene coordinates).
"""
import cv2
import numpy as np
from PIL import Image
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPixmap

from UndoRedo import ColorOverlayAction
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
        # Mask Moving functionality
        self.move_mask_on = False
        self.detached_mask_index = -1  # Tracks which mask is currently floating
        self.moving_mask_item = None
        self.white_cutout_item = None
        
        self.mask_drag_start_canvas = None
        self.moving_item_start_pos = None
        self.mask_boundary_start_pos = None

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

        #Button to move masked area
        self.move_masked_area_button = gui.move_masked_area_button
        self.move_masked_area_button.clicked.connect(lambda: self.set_single_toggle_state('move_mask_on'))
        
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
            
            # Update overlay colors: selected mask in red, others in cyan
            for i, overlay in enumerate(self.data_handler.mask_overlays):
                pen = QtGui.QPen()
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                pen.setWidth(2)
                
                if i == index:
                    pen.setColor(QtCore.Qt.GlobalColor.darkCyan)  # Selected mask in red
                else:
                    pen.setColor(QtCore.Qt.GlobalColor.cyan)  # Other masks in cyan
                
                overlay.setPen(pen)
            
            # Show edit handles if edit mode is enabled
            self.show_edit_handles_for_selected()
        else:
            self.editing_mask_index = -1

        #ensure to reset mask moving
        self.disable_move_mask_mode()

    def show_edit_handles_for_selected(self):
        """Show edit handles for the currently selected mask (if in edit mode)."""
        if not self.mask_edit_mode or self.editing_mask_index < 0:
            return
        
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
        # Update overlay colors to all cyan
        for overlay in self.data_handler.mask_overlays:
            pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            pen.setWidth(2)
            overlay.setPen(pen)
        
        self.clear_edit_handles()

    def delete_selected_mask(self):
        """Delete the currently selected mask."""
        selected_items = self.masks_list_widget.selectedItems()
        if selected_items:
            index = self.masks_list_widget.row(selected_items[0])
            # the indices of the masks behind it shift: no mask stays selected
            self.deselect_mask()
            self._mask_removed(index)
            self.data_handler.masks_list.pop(index)
            self.gui.image_scene.removeItem(self.data_handler.mask_overlays[index])
            self.data_handler.mask_overlays.pop(index)
            if index < len(self.data_handler.mask_info):
                self.data_handler.mask_info.pop(index)
            self.clear_edit_handles()
            self.update_masks_list_widget()

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
        #then delete all masks and overlays
        self._forget_detached_mask()
        self.data_handler.masks_list.clear()
        self.data_handler.mask_info.clear()
        self.clear_edit_handles()
        self.update_masks_list_widget()
        for overlay in self.data_handler.mask_overlays:
            if overlay.scene() is not None:
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
    



    #MOVE MASK FUNCTIONALITY
    def _forget_detached_mask(self):
        """The moved mask is gone: its moved pixels stay pending (imprint still works), only the mask is not
        tracked any more."""
        self.detached_mask_index = -1
        self.moving_mask_item = None
        self.white_cutout_item = None

    def _mask_removed(self, index):
        """Keep the move tracking consistent when mask `index` is deleted (bug: imprint failed afterwards)."""
        if self.detached_mask_index == index:
            self._forget_detached_mask()
        elif self.detached_mask_index > index:
            self.detached_mask_index -= 1

    def _extract_mask_for_moving(self, mask_index):
        """Creates the overlays and hands them over to the existing imprint system."""
        mask = self.data_handler.masks_list[mask_index]
        # P12.3: the pixels as they are now, pending moves / colour edits included (not the unimprinted image –
        # moving a mask a second time after another one must take its already moved pixels)
        image = self.pending_image_rgba()
        h, w = mask.shape
        
        # 1. Create the cutout: the vacated area becomes transparent on imprint
        temp_white_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        temp_white_rgba[mask == 1] = self._checker_rgba(h, w)[mask == 1]
        white_img = QImage(temp_white_rgba.data, w, h, QImage.Format.Format_RGBA8888)
        self.white_cutout_item = QtWidgets.QGraphicsPixmapItem(QPixmap.fromImage(white_img.copy()), self.gui.image_item)
        self.white_cutout_item.setZValue(11)
        self.white_cutout_item.erases = True

        # 2. Create the Moving Pixels
        temp_moving_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        temp_moving_rgba[mask == 1] = image[mask == 1]
        moving_img = QImage(temp_moving_rgba.data, w, h, QImage.Format.Format_RGBA8888)
        self.moving_mask_item = QtWidgets.QGraphicsPixmapItem(QPixmap.fromImage(moving_img.copy()), self.gui.image_item)
        self.moving_mask_item.setZValue(12) 
        
        # 3. Add to your existing undo/imprint stack! 
        # (This automatically triggers your imprint button visibility if you have it linked to this list)
        self.data_handler.active_color_overlays.append(self.white_cutout_item)
        self.data_handler.active_color_overlays.append(self.moving_mask_item)
        
        self.detached_mask_index = mask_index

        if self.undo_manager:
            def undo_mask_move():
                if self.detached_mask_index >= 0 and self.detached_mask_index < len(self.data_handler.mask_overlays):
                    self.data_handler.mask_overlays[self.detached_mask_index].setPos(0, 0)
                self.detached_mask_index = -1
                self.moving_mask_item = None
                self.white_cutout_item = None

            action = ColorOverlayAction(
                [self.white_cutout_item, self.moving_mask_item],
                self.gui.image_scene,
                self.data_handler.active_color_overlays,
                description="Move Mask",
                extra_undo=undo_mask_move
            )
            self.undo_manager.push_action(action)

    def on_move_mask_press(self, event):
        """Prepares for dragging. Detaches mask if it hasn't been detached yet."""
        idx = self.data_handler.active_mask_index
        if idx < 0:
            return 
            
        if self.detached_mask_index != idx:
            # another mask was moved before and not imprinted yet: move its mask geometry along now (its pixels
            # stay pending), otherwise it would be lost when this mask is detached
            self.update_logical_mask_matrices()
            self._extract_mask_for_moving(idx)
        
        # Record starting coordinates for smooth delta calculation
        self.mask_drag_start_canvas = event.pos()
        self.moving_item_start_pos = self.moving_mask_item.pos()
        self.mask_boundary_start_pos = self.data_handler.mask_overlays[idx].pos()

    def on_move_mask_drag(self, event):
        """Updates the visual position of the pixel overlay and dashed boundary."""
        idx = self.data_handler.active_mask_index
        if idx < 0:
            return 
        if self.moving_mask_item is None or self.detached_mask_index < 0:
            return
            
        idx = self.detached_mask_index
        start_x = self.mask_drag_start_canvas.x()
        start_y = self.mask_drag_start_canvas.y()
        curr_x = event.position().x()
        curr_y = event.position().y()
        
        # Calculate Image-space delta (for the Pixmap)
        start_img = self.data_handler.canvas_to_image_coords(start_x, start_y)
        curr_img = self.data_handler.canvas_to_image_coords(curr_x, curr_y)
        dx_img = curr_img[0] - start_img[0]
        dy_img = curr_img[1] - start_img[1]
        
        # Calculate Scene-space delta (for the dashed boundary)
        start_scene = self.data_handler.canvas_to_scene_coords(start_x, start_y)
        curr_scene = self.data_handler.canvas_to_scene_coords(curr_x, curr_y)
        dx_scene = curr_scene[0] - start_scene[0]
        dy_scene = curr_scene[1] - start_scene[1]
        
        # Move items
        self.moving_mask_item.setPos(self.moving_item_start_pos.x() + dx_img, self.moving_item_start_pos.y() + dy_img)
        self.data_handler.mask_overlays[idx].setPos(self.mask_boundary_start_pos.x() + dx_scene, self.mask_boundary_start_pos.y() + dy_scene)

    def on_move_mask_release(self, event):
        """Clears drag variables. Items stay exactly where left."""
        self.mask_drag_start_canvas = None
        self.moving_item_start_pos = None
        self.mask_boundary_start_pos = None

    def update_logical_mask_matrices(self):
        """Shifts the logical mask array to match the visual item before imprinting."""
        if self.detached_mask_index < 0 or self.moving_mask_item is None:
            return
            
        idx = self.detached_mask_index
        dx_img = int(self.moving_mask_item.pos().x())
        dy_img = int(self.moving_mask_item.pos().y())
        
        if dx_img != 0 or dy_img != 0:
            mask = self.data_handler.masks_list[idx]
            h, w = mask.shape
            
            # Calculate new valid coordinates
            y, x = np.where(mask == 1)
            ny, nx = y + dy_img, x + dx_img
            valid = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)

            # Generate and save new mask array
            new_mask = np.zeros_like(mask)
            new_mask[ny[valid], nx[valid]] = 1
            self.data_handler.masks_list[idx] = new_mask

            # Update internal mask_info coordinate tracking
            info = self.data_handler.mask_info[idx]
            if info['type'] in ['rectangle', 'ellipse']:
                x1, y1, x2, y2 = info['coords']
                info['coords'] = (x1 + dx_img, y1 + dy_img, x2 + dx_img, y2 + dy_img)
            elif info['type'] == 'polygon':
                info['coords'] = [(px + dx_img, py + dy_img) for px, py in info['coords']]
                
            # Permanently translate the dashed boundary overlay's geometry so its pos can be reset to 0,0
            boundary_item = self.data_handler.mask_overlays[idx]
            dx_scene = boundary_item.pos().x()
            dy_scene = boundary_item.pos().y()
            boundary_item.setPos(0, 0)
            if isinstance(boundary_item, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsEllipseItem)):
                boundary_item.setRect(boundary_item.rect().translated(dx_scene, dy_scene))
            elif isinstance(boundary_item, QtWidgets.QGraphicsPolygonItem):
                boundary_item.setPolygon(boundary_item.polygon().translated(dx_scene, dy_scene))

        # Reset state tracking
        self.detached_mask_index = -1
        self.moving_mask_item = None
        self.white_cutout_item = None
    
    def disable_move_mask_mode(self):
        #disable move mask mode and reset state
        self.move_masked_area_button.setChecked(False)
        self.move_mask_on = False
        self._notify_state()
