"""2c: the image list's ImageDocument is the single source of truth for the active image."""
import numpy as np
from PyQt6 import QtWidgets

from core import image_doc
from test_characterization import load_image, make_test_image


def _docs(c):
    lw = c.gui.images_ListWidget
    from PyQt6 import QtCore
    return [lw.item(i).data(QtCore.Qt.ItemDataRole.UserRole) for i in range(lw.count())]


def test_edits_are_stored_in_the_document_and_survive_switching(app_components):
    c = app_components
    load_image(c, make_test_image(), name="a")
    load_image(c, np.zeros((10, 20, 3), np.uint8), name="b")
    doc_a, doc_b = _docs(c)
    assert c.data_handler.active_document is doc_b

    c.gui.images_ListWidget.setCurrentRow(0)
    assert c.data_handler.active_document is doc_a
    edited = c.data_handler.image_matrix.copy()
    edited[0, 0] = (1, 2, 3, 255)
    c.data_handler.image_matrix = edited
    assert doc_a.image_matrix[0, 0].tolist() == [1, 2, 3, 255]  # no extra sync step needed

    c.gui.images_ListWidget.setCurrentRow(1)
    c.gui.images_ListWidget.setCurrentRow(0)
    assert c.data_handler.image_matrix[0, 0].tolist() == [1, 2, 3, 255]
    assert doc_a.original_image_matrix[0, 0].tolist() == [0, 0, 0, 0]  # restore state untouched (white loaded as transparent)


def test_upscale_does_not_modify_the_source_image(app_components, monkeypatch):
    c = app_components
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    source = make_test_image()
    load_image(c, source)
    c.image_controller.upscale_active_image(preserve_palette=True)
    src_doc, up_doc = _docs(c)
    assert np.array_equal(src_doc.image_matrix, image_doc.from_rgb(source))
    assert up_doc.image_matrix.shape == (160, 240, 4)
    assert c.data_handler.active_document is up_doc and up_doc.pixel_per_mm == src_doc.pixel_per_mm * 2


def test_undo_for_a_removed_image_does_not_touch_the_active_one(app_components):
    c = app_components
    load_image(c, make_test_image(), name="a")
    load_image(c, np.zeros((10, 20, 3), np.uint8), name="b")
    c.gui.images_ListWidget.setCurrentRow(0)
    c.image_controller.rot_image_90_clockwise()
    c.gui.images_ListWidget.setCurrentRow(0)
    c.image_controller.remove_image()  # removes "a"
    doc_b = c.data_handler.active_document
    assert doc_b.image_matrix.shape == (10, 20, 4)

    c.data_handler.undo_manager.undo()
    assert c.data_handler.active_document is doc_b
    assert doc_b.image_matrix.shape == (10, 20, 4) and not doc_b.image_matrix[..., :3].any()


def test_undo_rotation(app_components):
    c = app_components
    load_image(c, make_test_image())
    c.image_controller.rot_image_90_clockwise()
    assert c.data_handler.image_matrix.shape == (120, 80, 4)
    c.data_handler.undo_manager.undo()
    assert np.array_equal(c.data_handler.image_matrix, image_doc.from_rgb(make_test_image()))
    assert _docs(c)[0] is c.data_handler.active_document


def test_p69_undo_stack_is_limited_by_memory(app_components):
    from UndoRedo import ImageMatrixAction
    manager = app_components.data_handler.undo_manager
    manager.max_stack_bytes = 10 * 2 * 1_000_000  # room for 10 actions of 2 x 1 MB
    big = np.zeros((1000, 250, 4), np.uint8)  # 1 MB
    for i in range(15):
        manager.push_action(ImageMatrixAction(app_components.data_handler, app_components.gui, None, big, big, 1, 1,
                                              description=str(i)))
    assert [a.description for a in manager.undo_stack] == [str(i) for i in range(5, 15)]


def test_p610_upscale_runs_in_worker_thread(app_components, monkeypatch):
    import threading
    import ImageUpscaling
    threads = []
    original = ImageUpscaling.ImageUpscaler.upscale

    def spy(self, *args, **kwargs):
        threads.append(threading.current_thread() is threading.main_thread())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ImageUpscaling.ImageUpscaler, "upscale", spy)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    load_image(app_components, make_test_image())
    app_components.image_controller.upscale_active_image(preserve_palette=True)
    assert threads == [False]
    assert _docs(app_components)[1].image_matrix.shape == (160, 240, 4)
