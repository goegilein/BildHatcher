"""Masks after testing v2.0: lift off masks (P12.4), selection, imprint, and the Masks / Images section sizes."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

from test_characterization import load_image


def _image():
    """60 x 40 white image with a red block (10..19, 10..19), a blue block (35..44, 10..19) and a green bar
    (x 40..49, y 30..33 – not square, so a turn shows)."""
    img = np.full((40, 60, 3), 255, np.uint8)
    img[10:20, 10:20] = (220, 30, 30)
    img[10:20, 35:45] = (30, 60, 200)
    img[30:34, 40:50] = (40, 160, 60)
    return img


def _mouse(c, kind, x_img, y_img):
    """Mouse event on the centre of image pixel (x_img, y_img)."""
    gui = c.gui
    point = gui.image_canvas.mapFromScene(gui.image_item.mapToScene(QtCore.QPointF(x_img + 0.5, y_img + 0.5)))
    viewport = gui.image_canvas.viewport()
    pos = QtCore.QPointF(point)
    buttons = QtCore.Qt.MouseButton.LeftButton
    return QtGui.QMouseEvent(kind, pos, QtCore.QPointF(viewport.mapToGlobal(pos)), QtCore.Qt.MouseButton.LeftButton,
                             buttons, QtCore.Qt.KeyboardModifier.NoModifier)


def _draw_rect_mask(c, x0, y0, x1, y1):
    """Draw a rectangle mask with the mouse (press, drag, release) like the user."""
    colorer = c.image_colorer
    colorer.mask_drawing_on, colorer.mask_shape_mode = True, "rectangle"
    Type = QtCore.QEvent.Type
    colorer.start_mask_rect(_mouse(c, Type.MouseButtonPress, x0, y0))
    colorer.update_mask_rect_preview(_mouse(c, Type.MouseMove, x1, y1))
    colorer.finish_mask_rect(_mouse(c, Type.MouseButtonRelease, x1, y1))
    colorer.mask_drawing_on = False


def _drag(c, start, end):
    """Drag with the left mouse button on the canvas from image pixel `start` to `end` (real view events)."""
    viewport = c.gui.image_canvas.viewport()
    Type, Button = QtCore.QEvent.Type, QtCore.Qt.MouseButton
    send = QtWidgets.QApplication.sendEvent
    send(viewport, _mouse(c, Type.MouseButtonPress, *start))
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    for point in (middle, end):
        send(viewport, _mouse(c, Type.MouseMove, *point))
    release = _mouse(c, Type.MouseButtonRelease, *end)
    send(viewport, QtGui.QMouseEvent(Type.MouseButtonRelease, release.position(), release.globalPosition(),
                                     Button.LeftButton, Button.NoButton, QtCore.Qt.KeyboardModifier.NoModifier))


def _lift(c, row):
    c.image_colorer.masks_list_widget.setCurrentRow(row)
    c.gui.move_masked_area_button.click()


@pytest.fixture
def masked(app_components):
    c = app_components
    c.gui.resize(1100, 800)
    c.gui.show()
    load_image(c, _image())
    # one image pixel = several screen pixels, so that the simulated clicks hit exact pixels
    view = c.gui.image_canvas
    view.resetTransform()
    view.scale(20, 20)
    QtWidgets.QApplication.processEvents()
    a = view.mapFromScene(c.gui.image_item.mapToScene(QtCore.QPointF(0, 0)))
    b = view.mapFromScene(c.gui.image_item.mapToScene(QtCore.QPointF(10, 0)))
    assert b.x() - a.x() >= 30, "image pixels too small on screen for exact clicks"
    yield c
    c.gui.hide()


def _mask_box(mask):
    ys, xs = np.nonzero(mask == 1)
    return xs.min(), ys.min(), xs.max(), ys.max()




RED, BLUE = (220, 30, 30), (30, 60, 200)


def test_a_new_mask_is_selected(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    assert c.data_handler.active_mask_index == 1
    assert c.image_colorer.masks_list_widget.currentRow() == 1


def test_lifting_a_mask_makes_a_floating_layer(masked):
    c = masked
    colorer, gui = c.image_colorer, c.gui
    _draw_rect_mask(c, 10, 10, 19, 19)
    before = c.data_handler.image_matrix.copy()
    assert not gui.imprint_mask_button.isEnabled() and not gui.move_masked_area_button.isChecked()
    _lift(c, 0)
    assert colorer.is_lifted(0)
    assert gui.move_masked_area_button.isChecked()               # the lift button now imprints
    assert "Imprint" in gui.move_masked_area_button.toolTip()
    assert gui.imprint_mask_button.isEnabled() and gui.actionImprint_Masks.isEnabled()
    assert c.data_handler.mask_overlays[0].pen().color().name().upper() in ("#FF6D00", "#C43C00")  # orange
    image = c.data_handler.image_matrix
    mask = c.data_handler.masks_list[0] == 1
    assert (image[mask][:, 3] == 0).all()                       # its place is free right away (P12.6)
    assert np.array_equal(image[~mask], before[~mask])           # nothing else changed
    assert not c.data_handler.active_color_overlays             # not part of the colour imprint


def test_drag_and_drop_then_imprint_the_mask(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    start = _mask_box(c.data_handler.masks_list[0])
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))                                 # down by 12
    assert c.data_handler.mask_overlays[0].pos().y() > 0          # the frame follows
    c.gui.move_masked_area_button.click()                        # imprint this mask
    image = c.data_handler.image_matrix
    assert not c.image_colorer.is_lifted(0)
    assert tuple(image[27, 15][:3]) == RED and image[27, 15][3] == 255
    assert image[12, 15][3] == 0                                 # the old place became background
    assert _mask_box(c.data_handler.masks_list[0])[:2] == (start[0], start[1] + 12)  # the mask moved along
    assert c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)


def test_masks_lifted_and_moved_alternately(masked):
    """The scenario that failed with the old "move": mask 1, mask 2, mask 1 again – then imprint all."""
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    start_first, start_second = (_mask_box(m) for m in c.data_handler.masks_list)
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))
    _lift(c, 1)
    _drag(c, (40, 15), (40, 27))
    _drag(c, (15, 27), (27, 27))                                 # the first one again (still lifted)
    assert c.data_handler.active_mask_index == 0                 # dragging selects
    c.gui.imprint_mask_button.click()                            # imprint all masks
    image = c.data_handler.image_matrix
    assert tuple(image[27, 27][:3]) == RED and image[27, 27][3] == 255
    assert image[27, 15][3] == 0 and image[15, 15][3] == 0
    assert tuple(image[27, 40][:3]) == BLUE and image[15, 40][3] == 0
    first, second = c.data_handler.masks_list
    assert _mask_box(first)[:2] == (start_first[0] + 12, start_first[1] + 12)
    assert _mask_box(second)[:2] == (start_second[0], start_second[1] + 12)
    assert not c.image_colorer.lifted_indices() and not c.gui.imprint_mask_button.isEnabled()


def test_deleting_a_lifted_mask_imprints_it_first(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))
    c.image_colorer.masks_list_widget.setCurrentRow(0)
    c.image_colorer.delete_selected_mask()
    assert not c.data_handler.masks_list and not c.gui.imprint_mask_button.isEnabled()
    image = c.data_handler.image_matrix
    assert tuple(image[27, 15][:3]) == RED and image[15, 15][3] == 0   # its pixels are not lost
    assert not [i for i in c.gui.image_item.childItems() if type(i).__name__ == "LiftedMaskItem"]


def test_imprinting_onto_the_place_of_a_lifted_mask_keeps_everything(masked):
    """The user's case: mask A is lifted (not imprinted), mask B is moved onto A's old place and imprinted, then
    A is imprinted somewhere else – B must stay complete."""
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)                       # A: red
    _draw_rect_mask(c, 35, 10, 44, 19)                       # B: blue
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))                             # A away (down)
    _lift(c, 1)
    _drag(c, (40, 15), (15, 15))                             # B onto A's old place
    c.gui.move_masked_area_button.click()                    # imprint B
    image = c.data_handler.image_matrix
    assert np.all(image[10:20, 10:20, 3] == 255) and np.all(image[10:20, 10:20, :3] == BLUE)  # B complete
    c.image_colorer.masks_list_widget.setCurrentRow(0)
    c.gui.move_masked_area_button.click()                    # imprint A
    image = c.data_handler.image_matrix
    assert np.all(image[10:20, 10:20, :3] == BLUE) and np.all(image[10:20, 10:20, 3] == 255)  # still complete
    assert tuple(image[27, 15][:3]) == RED


def test_no_drag_while_a_tool_is_on(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _lift(c, 0)
    c.gui.toggle_draw_button.click()                             # draw tool on: the click draws, nothing moves
    _drag(c, (15, 15), (15, 27))
    assert c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)
    c.image_colorer.set_single_toggle_state("")


def test_undo_imprint_drag_and_lift(masked):
    c = masked
    undo = c.image_colorer.undo_manager
    _draw_rect_mask(c, 10, 10, 19, 19)
    original = c.data_handler.image_matrix.copy()
    _lift(c, 0)
    lifted = c.data_handler.image_matrix.copy()                 # with the free place
    _drag(c, (15, 15), (15, 27))
    c.gui.imprint_mask_button.click()
    assert not np.array_equal(c.data_handler.image_matrix, lifted)
    undo.undo()                                                  # imprint undone: lifted at the dragged place
    assert np.array_equal(c.data_handler.image_matrix, lifted)
    assert c.image_colorer.is_lifted(0) and c.data_handler.mask_overlays[0].pos().y() > 0
    undo.undo()                                                  # drag undone
    assert c.image_colorer.is_lifted(0) and c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)
    undo.undo()                                                  # lift undone: the place is filled again
    assert not c.image_colorer.is_lifted(0)
    assert np.array_equal(c.data_handler.image_matrix, original)
    undo.redo()
    undo.redo()
    undo.redo()                                                  # and everything again
    image = c.data_handler.image_matrix
    assert tuple(image[27, 15][:3]) == RED and not c.image_colorer.is_lifted(0)


GREEN = (40, 160, 60)


def _drag_scene(c, start, end):
    """Left-button drag between two scene points (real view events)."""
    view = c.gui.image_canvas
    viewport = view.viewport()
    Type, Button, Mod = QtCore.QEvent.Type, QtCore.Qt.MouseButton, QtCore.Qt.KeyboardModifier.NoModifier

    def event(kind, point, buttons):
        pos = QtCore.QPointF(view.mapFromScene(point))
        return QtGui.QMouseEvent(kind, pos, QtCore.QPointF(viewport.mapToGlobal(pos)), Button.LeftButton, buttons, Mod)
    QtWidgets.QApplication.sendEvent(viewport, event(Type.MouseButtonPress, start, Button.LeftButton))
    QtWidgets.QApplication.sendEvent(viewport, event(Type.MouseMove, end, Button.LeftButton))
    QtWidgets.QApplication.sendEvent(viewport, event(Type.MouseButtonRelease, end, Button.NoButton))


def test_clicking_a_mask_in_the_image_selects_it(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)                            # selected (new)
    _drag(c, (14, 14), (14, 14))                                  # a plain click into mask 1
    assert c.image_colorer.masks_list_widget.currentRow() == 0
    c.gui.toggle_draw_button.click()                              # with a tool on, the click is the tool's
    _drag(c, (40, 14), (40, 14))
    assert c.image_colorer.masks_list_widget.currentRow() == 0
    c.image_colorer.set_single_toggle_state("")


def test_turning_a_lifted_mask_with_its_handle(masked):
    c = masked
    colorer = c.image_colorer
    _draw_rect_mask(c, 40, 30, 49, 33)                            # around the green bar (10 x 4)
    before_lift = c.data_handler.image_matrix.copy()
    _lift(c, 0)
    lift = c.data_handler.mask_info[0]['lift']
    handle = lift['pixels'].handle
    assert handle.isVisible()                                     # selected lifted mask: handle on top
    centre = lift['pixels'].mapToScene(lift['pixels'].transformOriginPoint())
    radius = (handle.scenePos() - centre).manhattanLength()
    _drag_scene(c, handle.scenePos(), centre + QtCore.QPointF(radius, 0))   # handle to the right: 90 degrees
    assert lift['pixels'].rotation() == pytest.approx(90, abs=1)
    lift['pixels'].setRotation(90)                                # exact for the pixel check
    assert c.data_handler.mask_overlays[0].rotation() == 90      # the frame turns along
    original = c.data_handler.image_matrix.copy()                 # (the bar's place is free already)
    c.gui.imprint_mask_button.click()
    image = c.data_handler.image_matrix
    ys, xs = np.nonzero((image[..., 3] == 255) & np.all(image[..., :3] == GREEN, axis=-1))
    assert (xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) == (4, 10)   # the bar stands upright now
    colours = {tuple(p) for p in image.reshape(-1, 4).tolist()}
    assert colours <= {tuple(p) for p in before_lift.reshape(-1, 4).tolist()} | {(0, 0, 0, 0)}  # no new colours
    assert c.data_handler.mask_info[0]['type'] == 'polygon'       # a turned rectangle is a polygon mask
    box = _mask_box(c.data_handler.masks_list[0])
    assert (box[2] - box[0] + 1, box[3] - box[1] + 1) == (4, 10)  # the mask turned with it
    colorer.undo_manager.undo()                                   # back: lifted and turned
    assert np.array_equal(c.data_handler.image_matrix, original)
    assert colorer.is_lifted(0) and c.data_handler.mask_info[0]['type'] == 'rectangle'
    assert c.data_handler.mask_info[0]['lift']['pixels'].rotation() == 90


def test_masks_and_images_sections_have_taller_lists_and_imprint_buttons(app_components):
    gui = app_components.gui
    assert gui.masks_list_widget.minimumHeight() >= 200 and gui.images_ListWidget.minimumHeight() >= 220
    assert gui.imprint_mask_button.property("styleClass") == "ImprintButton"
    assert gui.actionImprint_Masks in gui.toolBar.actions()
    assert gui.imprint_mask_button.parentWidget() is gui.masks_list_widget.parentWidget()
    assert gui.toolbar_colors_label.parentWidget() is gui.toolBar
    load_image(app_components, _image())
    assert gui.toolbar_colors_label.text() == gui.number_of_colors_label.text().split(": ")[1] + " colors"


def test_a_new_mask_outline_lies_exactly_on_its_pixels(masked):
    c = masked
    _draw_rect_mask(c, 40, 30, 49, 33)
    item = c.gui.image_item
    expected = QtCore.QRectF(item.mapToScene(QtCore.QPointF(40, 30)), item.mapToScene(QtCore.QPointF(50, 34)))
    frame = c.data_handler.mask_overlays[0].rect()
    for a, b in ((frame.left(), expected.left()), (frame.top(), expected.top()),
                 (frame.right(), expected.right()), (frame.bottom(), expected.bottom())):
        assert a == pytest.approx(b, abs=1e-6)


def test_lift_and_imprint_all_are_off_at_start(app_components):
    gui = app_components.gui
    assert not gui.imprint_mask_button.isEnabled() and not gui.actionImprint_Masks.isEnabled()
    assert not gui.move_masked_area_button.isEnabled()  # nothing selected
