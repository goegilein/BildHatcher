"""P12.14: hatch precision default, hatch settings from a database colour, database window height."""
from PyQt6 import QtCore, QtWidgets

from HelperClasses import DBColorPalette

PARAMS = [
    {"color_name": "Red", "color_rgb": "220,30,30", "hatch_pattern": "Spiral", "hatch_angle": 30.0,
     "hatch_distance": 120, "laser_power": 50, "speed": 1000},
    {"color_name": "Blue", "color_rgb": "30,60,200", "hatch_pattern": "Radial", "hatch_angle": 75.0,
     "hatch_distance": 250, "laser_power": 70, "speed": 800},
]


class _Profiles:
    def __init__(self, palette):
        self.palette = palette

    def require(self):
        return self.palette


def _answer_dialog(row, accept=True):
    """Pick `row` in the open colour dialog and confirm (or cancel) as soon as it shows."""
    def act():
        dialog = QtWidgets.QApplication.activeModalWidget()
        if dialog is None:
            QtCore.QTimer.singleShot(20, act)
            return
        colors = dialog.findChild(QtWidgets.QListWidget, "db_color_list")
        colors.setCurrentRow(row)
        buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
        role = QtWidgets.QDialogButtonBox.StandardButton.Ok if accept else QtWidgets.QDialogButtonBox.StandardButton.Cancel
        buttons.button(role).click()
    QtCore.QTimer.singleShot(20, act)


def test_default_precision_and_the_new_button(app_components):
    gui = app_components.gui
    assert gui.hatch_precision_spinbox.value() == 0.01
    assert not hasattr(gui, "hatch_progress_label")
    button = gui.load_db_hatch_settings_button
    assert not button.icon().isNull() and "color profile" in button.toolTip()


def test_settings_of_a_database_colour_are_taken_over(app_components):
    c = app_components
    gui = c.gui
    profiles = _Profiles(DBColorPalette(PARAMS, {}))
    _answer_dialog(1)
    chosen = c.image_hatcher.load_settings_from_profile(profiles)
    assert chosen["color_name"] == "Blue"
    assert gui.hatch_pattern_combobox.currentText() == "Radial"
    assert gui.hatch_angle_spinbox.value() == 75.0
    assert gui.hatch_dist_mode_combobox.currentText() == "Fixed" and gui.hatch_dist_min_spinbox.value() == 250
    before = gui.hatch_pattern_combobox.currentText()
    _answer_dialog(0, accept=False)                          # cancel: nothing changes
    assert c.image_hatcher.load_settings_from_profile(profiles) is None
    assert gui.hatch_pattern_combobox.currentText() == before


def test_database_window_opens_as_low_as_possible(app_components):
    settings = app_components.settings
    settings.open_color_database()
    window = settings.editor_window
    QtWidgets.QApplication.processEvents()
    assert window.height() <= window.minimumSizeHint().height() + 2
    window.close()
