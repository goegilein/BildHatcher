"""
Undo/Redo management system for BildHatcher.
Implements the Command pattern for image matrix operations and overlay manipulations.
"""

from contextlib import contextmanager
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets


class Action:
    """Base class for all undoable and redoable actions."""

    def __init__(self, description="Action"):
        self.description = description

    def undo(self):
        raise NotImplementedError

    def redo(self):
        raise NotImplementedError


class ImageMatrixAction(Action):
    """
    Action that tracks modifications to the active image matrix and physical resolution.
    Handles rotations, flips, resizing, color adjustments, and cleanup operations.
    """

    def __init__(self, data_handler, gui, image_controller,
                 before_matrix, after_matrix,
                 before_pixel_per_mm, after_pixel_per_mm,
                 image_item=None, description="Image Edit"):
        super().__init__(description)
        self.data_handler = data_handler
        self.gui = gui
        self.image_controller = image_controller
        self.before_matrix = before_matrix.copy() if before_matrix is not None else None
        self.after_matrix = after_matrix.copy() if after_matrix is not None else None
        self.before_pixel_per_mm = before_pixel_per_mm
        self.after_pixel_per_mm = after_pixel_per_mm
        self.image_item = image_item

    def _sync_to_image_item(self, matrix, pixel_per_mm):
        if matrix is None:
            return

        # Ensure correct image item is active if possible
        if self.image_item is not None and hasattr(self.image_controller, "images_ListWidget"):
            list_widget = self.image_controller.images_ListWidget
            try:
                row = list_widget.row(self.image_item)
                if row >= 0 and list_widget.currentItem() != self.image_item:
                    list_widget.setCurrentItem(self.image_item)
                    self.image_controller.active_image_item = self.image_item
            except Exception:
                pass

        # Update the active item's ImgObj
        active_item = getattr(self.image_controller, "active_image_item", None)
        if active_item is not None:
            img_obj = active_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if img_obj is not None:
                img_obj.image_matrix = matrix.copy()
                if pixel_per_mm is not None:
                    img_obj.pixel_per_mm = pixel_per_mm
                active_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)

        if pixel_per_mm is not None:
            self.data_handler.pixel_per_mm = pixel_per_mm

        self.data_handler.image_matrix = matrix.copy()

        # Update dimension spinboxes and canvas view if available
        if self.image_controller and hasattr(self.image_controller, "update_dimension_fields"):
            try:
                self.image_controller.update_dimension_fields()
            except Exception:
                pass

    def undo(self):
        self._sync_to_image_item(self.before_matrix, self.before_pixel_per_mm)

    def redo(self):
        self._sync_to_image_item(self.after_matrix, self.after_pixel_per_mm)


class ColorOverlayAction(Action):
    """
    Action that tracks drawing or manipulation of color overlay items (brush strokes,
    flood fills, moving mask cutouts, etc.) before they are imprinted.
    """

    def __init__(self, items, scene, active_color_overlays_list,
                 description="Color Step",
                 extra_undo=None, extra_redo=None):
        super().__init__(description)
        self.items = list(items) if isinstance(items, (list, tuple)) else [items]
        self.scene = scene
        self.active_color_overlays_list = active_color_overlays_list
        self.parent_items = [item.parentItem() for item in self.items]
        self.extra_undo = extra_undo
        self.extra_redo = extra_redo

    def undo(self):
        for item in reversed(self.items):
            if item in self.active_color_overlays_list:
                self.active_color_overlays_list.remove(item)
            if item.scene() is not None:
                self.scene.removeItem(item)
        if callable(self.extra_undo):
            self.extra_undo()

    def redo(self):
        for item, parent in zip(self.items, self.parent_items):
            if parent is not None:
                item.setParentItem(parent)
            elif item.scene() is None:
                self.scene.addItem(item)
            if item not in self.active_color_overlays_list:
                self.active_color_overlays_list.append(item)
        if callable(self.extra_redo):
            self.extra_redo()


class ImprintColorOverlaysAction(Action):
    """
    Action that tracks imprinting color overlay items into the background pixel matrix.
    Undo restores the previous image matrix and resurrects the overlays on the scene.
    """

    def __init__(self, data_handler, gui, image_controller,
                 before_matrix, after_matrix, imprinted_items,
                 scene, active_color_overlays_list,
                 image_item=None, description="Imprint Color Overlays"):
        super().__init__(description)
        self.data_handler = data_handler
        self.gui = gui
        self.image_controller = image_controller
        self.before_matrix = before_matrix.copy()
        self.after_matrix = after_matrix.copy()
        self.imprinted_items = list(imprinted_items)
        self.parent_items = [item.parentItem() for item in self.imprinted_items]
        self.scene = scene
        self.active_color_overlays_list = active_color_overlays_list
        self.image_item = image_item

    def _sync_matrix(self, matrix):
        if self.image_item is not None and hasattr(self.image_controller, "images_ListWidget"):
            list_widget = self.image_controller.images_ListWidget
            try:
                row = list_widget.row(self.image_item)
                if row >= 0 and list_widget.currentItem() != self.image_item:
                    list_widget.setCurrentItem(self.image_item)
                    self.image_controller.active_image_item = self.image_item
            except Exception:
                pass

        active_item = getattr(self.image_controller, "active_image_item", None)
        if active_item is not None:
            img_obj = active_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if img_obj is not None:
                img_obj.image_matrix = matrix.copy()
                active_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)

        self.data_handler.image_matrix = matrix.copy()

    def undo(self):
        # 1. Restore previous pixel matrix
        self._sync_matrix(self.before_matrix)
        # 2. Re-add the overlay items to scene and active list
        for item, parent in zip(self.imprinted_items, self.parent_items):
            if parent is not None:
                item.setParentItem(parent)
            elif item.scene() is None:
                self.scene.addItem(item)
            if item not in self.active_color_overlays_list:
                self.active_color_overlays_list.append(item)

    def redo(self):
        # 1. Remove overlay items from scene and list
        for item in self.imprinted_items:
            if item in self.active_color_overlays_list:
                self.active_color_overlays_list.remove(item)
            if item.scene() is not None:
                self.scene.removeItem(item)
        # 2. Re-apply imprinted matrix
        self._sync_matrix(self.after_matrix)


class TGAddOverlayAction(Action):
    """Action for adding a Text or Geometry overlay."""

    def __init__(self, overlay_manager, overlay_store, item, description="Add Overlay"):
        super().__init__(description)
        self.overlay_manager = overlay_manager
        self.overlay_store = overlay_store
        self.item = item

    def undo(self):
        self.overlay_store.remove_item(self.item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()

    def redo(self):
        self.overlay_store.add_item(self.item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()


class TGDeleteOverlayAction(Action):
    """Action for deleting one or multiple Text / Geometry overlays."""

    def __init__(self, overlay_manager, overlay_store, items, description="Delete Overlay"):
        super().__init__(description)
        self.overlay_manager = overlay_manager
        self.overlay_store = overlay_store
        self.items = list(items)

    def undo(self):
        for item in self.items:
            self.overlay_store.add_item(item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()

    def redo(self):
        for item in self.items:
            self.overlay_store.remove_item(item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()


class TGTransformOverlayAction(Action):
    """Action for moving, resizing, or altering properties of an overlay."""

    def __init__(self, overlay_manager, item, before_state, after_state, description="Modify Overlay"):
        super().__init__(description)
        self.overlay_manager = overlay_manager
        self.item = item
        self.before_state = before_state
        self.after_state = after_state

    def _apply_state(self, state):
        self.overlay_manager._apply_item_state(self.item, state)
        self.overlay_manager._update_ui_from_selected()
        if hasattr(self.item, "update"):
            self.item.update()

    def undo(self):
        self._apply_state(self.before_state)

    def redo(self):
        self._apply_state(self.after_state)


class TGImprintOverlaysAction(Action):
    """Action for imprinting selected Text / Geometry overlays."""

    def __init__(self, data_handler, gui, image_controller,
                 overlay_manager, overlay_store,
                 before_matrix, after_matrix, imprinted_items,
                 image_item=None, description="Imprint Text & Geometries"):
        super().__init__(description)
        self.data_handler = data_handler
        self.gui = gui
        self.image_controller = image_controller
        self.overlay_manager = overlay_manager
        self.overlay_store = overlay_store
        self.before_matrix = before_matrix.copy()
        self.after_matrix = after_matrix.copy()
        self.imprinted_items = list(imprinted_items)
        self.image_item = image_item

    def _sync_matrix(self, matrix):
        if self.image_item is not None and hasattr(self.image_controller, "images_ListWidget"):
            list_widget = self.image_controller.images_ListWidget
            try:
                row = list_widget.row(self.image_item)
                if row >= 0 and list_widget.currentItem() != self.image_item:
                    list_widget.setCurrentItem(self.image_item)
                    self.image_controller.active_image_item = self.image_item
            except Exception:
                pass

        active_item = getattr(self.image_controller, "active_image_item", None)
        if active_item is not None:
            img_obj = active_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if img_obj is not None:
                img_obj.image_matrix = matrix.copy()
                active_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)

        self.data_handler.image_matrix = matrix.copy()

    def undo(self):
        self._sync_matrix(self.before_matrix)
        for item in self.imprinted_items:
            self.overlay_store.add_item(item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()

    def redo(self):
        for item in self.imprinted_items:
            self.overlay_store.remove_item(item)
        self.overlay_manager._sync_data_handler_lists()
        self.overlay_manager._update_overlay_list()
        self.overlay_manager._update_ui_from_selected()
        self._sync_matrix(self.after_matrix)


class UndoRedoManager(QtCore.QObject):
    """
    Central manager controlling the Undo and Redo stacks.
    Coordinates between ImageControlling, ImageEditing, and TextandGeometries.
    """

    stack_changed = QtCore.pyqtSignal()

    def __init__(self, gui=None, data_handler=None, max_stack_size=50):
        super().__init__()
        self.gui = gui
        self.data_handler = data_handler
        self.image_controller = None
        self.max_stack_size = max_stack_size

        self.undo_stack = []
        self.redo_stack = []
        self.is_undoing_or_redoing = False

        self.menu_undo = None
        self.menu_redo = None
        self.action_undo = None
        self.action_redo = None

    def set_image_controller(self, image_controller):
        self.image_controller = image_controller

    def push_action(self, action: Action):
        """Push a newly executed action onto the undo stack and clear the redo stack."""
        if self.is_undoing_or_redoing:
            return

        self.undo_stack.append(action)
        if len(self.undo_stack) > self.max_stack_size:
            self.undo_stack.pop(0)

        self.redo_stack.clear()
        self.update_ui()
        self.stack_changed.emit()

    def undo(self):
        """Revert the most recent action."""
        if not self.undo_stack or self.is_undoing_or_redoing:
            return False

        action = self.undo_stack.pop()
        self.is_undoing_or_redoing = True
        try:
            action.undo()
        finally:
            self.is_undoing_or_redoing = False

        self.redo_stack.append(action)
        self.update_ui()
        self.stack_changed.emit()
        return True

    def redo(self):
        """Re-apply the most recently undone action."""
        if not self.redo_stack or self.is_undoing_or_redoing:
            return False

        action = self.redo_stack.pop()
        self.is_undoing_or_redoing = True
        try:
            action.redo()
        finally:
            self.is_undoing_or_redoing = False

        self.undo_stack.append(action)
        self.update_ui()
        self.stack_changed.emit()
        return True

    def clear(self):
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.update_ui()
        self.stack_changed.emit()

    @contextmanager
    def record_image_matrix(self, description="Image Edit", target_item=None):
        """
        Convenience context manager that records changes to the active image matrix.
        Usage:
            with undo_manager.record_image_matrix("Rotate 90°"):
                # operations changing data_handler.image_matrix
        """
        if self.is_undoing_or_redoing or self.data_handler is None:
            yield
            return

        before_matrix = self.data_handler.image_matrix.copy() if self.data_handler.image_matrix is not None else None
        before_ppm = self.data_handler.pixel_per_mm
        active_item = target_item
        if active_item is None and self.image_controller is not None:
            active_item = getattr(self.image_controller, "active_image_item", None)

        yield

        after_matrix = self.data_handler.image_matrix.copy() if self.data_handler.image_matrix is not None else None
        after_ppm = self.data_handler.pixel_per_mm

        if before_matrix is not None and after_matrix is not None:
            # Check if matrix shape or content changed or pixel_per_mm changed
            changed = False
            if before_matrix.shape != after_matrix.shape or before_ppm != after_ppm:
                changed = True
            elif not np.array_equal(before_matrix, after_matrix):
                changed = True

            if changed:
                action = ImageMatrixAction(
                    self.data_handler, self.gui, self.image_controller,
                    before_matrix, after_matrix,
                    before_ppm, after_ppm,
                    image_item=active_item,
                    description=description
                )
                self.push_action(action)

    def setup_menus(self, menu_undo: QtWidgets.QMenu, menu_redo: QtWidgets.QMenu):
        """
        Configure the QMenu widgets in the menubar with actions, shortcuts, and click triggers.
        """
        self.menu_undo = menu_undo
        self.menu_redo = menu_redo

        # Create QAction for Undo with Ctrl+Z
        self.action_undo = QtGui.QAction("Undo", self.gui)
        self.action_undo.setShortcut(QtGui.QKeySequence("Ctrl+Z"))
        self.action_undo.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.action_undo.triggered.connect(self.undo)
        if self.gui is not None:
            self.gui.addAction(self.action_undo)
        self.menu_undo.addAction(self.action_undo)

        # Create QAction for Redo with Ctrl+Y
        self.action_redo = QtGui.QAction("Redo", self.gui)
        self.action_redo.setShortcut(QtGui.QKeySequence("Ctrl+Y"))
        self.action_redo.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.action_redo.triggered.connect(self.redo)
        if self.gui is not None:
            self.gui.addAction(self.action_redo)
        self.menu_redo.addAction(self.action_redo)

        # Allow clicking directly on the menubar header to execute undo/redo
        def on_undo_menu_show():
            # If user clicked menu header directly, execute undo and close menu popup
            if self.undo_stack:
                self.menu_undo.hide()
                self.undo()

        def on_redo_menu_show():
            if self.redo_stack:
                self.menu_redo.hide()
                self.redo()

        self.menu_undo.aboutToShow.connect(on_undo_menu_show)
        self.menu_redo.aboutToShow.connect(on_redo_menu_show)

        self.update_ui()

    def update_ui(self):
        """Update enabled states, titles, and action descriptions."""
        can_undo = len(self.undo_stack) > 0
        can_redo = len(self.redo_stack) > 0

        last_undo_desc = self.undo_stack[-1].description if can_undo else ""
        last_redo_desc = self.redo_stack[-1].description if can_redo else ""

        if self.menu_undo is not None:
            self.menu_undo.setEnabled(can_undo)
            if can_undo:
                self.menu_undo.setTitle(f"Undo ({last_undo_desc})")
                self.menu_undo.setToolTip(f"Undo: {last_undo_desc} (Ctrl+Z)")
            else:
                self.menu_undo.setTitle("Undo")
                self.menu_undo.setToolTip("Nothing to undo (Ctrl+Z)")

        if self.action_undo is not None:
            self.action_undo.setEnabled(can_undo)
            self.action_undo.setText(f"Undo {last_undo_desc}" if can_undo else "Undo")

        if self.menu_redo is not None:
            self.menu_redo.setEnabled(can_redo)
            if can_redo:
                self.menu_redo.setTitle(f"Redo ({last_redo_desc})")
                self.menu_redo.setToolTip(f"Redo: {last_redo_desc} (Ctrl+Y)")
            else:
                self.menu_redo.setTitle("Redo")
                self.menu_redo.setToolTip("Nothing to redo (Ctrl+Y)")

        if self.action_redo is not None:
            self.action_redo.setEnabled(can_redo)
            self.action_redo.setText(f"Redo {last_redo_desc}" if can_redo else "Redo")
