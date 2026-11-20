"""Atelier style (theme.py, GUI_Files/styles/atelier.qss)."""
from lxml import etree
from PyQt6 import QtGui, QtWidgets

import theme
from PathManager import get_gui_file_path


def test_ui_carries_the_atelier_stylesheet_for_designer():
    """tools/apply_style.py copies the .qss into the .ui; both must stay identical."""
    tree = etree.parse(str(get_gui_file_path("BildHatcher.ui")))
    ui_qss = tree.getroot().find("widget/property[@name='styleSheet']/string").text
    assert ui_qss == theme.stylesheet()


def test_legacy_style_is_kept():
    legacy = get_gui_file_path("styles").joinpath("legacy_burgundy.qss").read_text(encoding="utf-8")
    assert "rgb(122,0,28)" in legacy.replace(" ", "")


def test_theme_loads_fonts_and_styles_the_app(qapp):
    assert {"Plus Jakarta Sans", "Space Mono"} <= set(theme.load_fonts())
    assert qapp.styleSheet() == theme.stylesheet()
    assert QtWidgets.QApplication.font().family() == "Plus Jakarta Sans"
    from PyQt6 import QtCore
    for name in ("spin-up", "spin-down", "combo-down", "check"):  # images the stylesheet uses
        assert QtCore.QFile.exists(f"icons:{name}.svg"), name


def test_primary_actions_use_the_gold_button(app_components):
    gui = app_components.gui
    for name in ("hatch_image_button", "create_test_button", "export_button", "automatic_gcode_file_button"):
        assert getattr(gui, name).property("styleClass") == "PrimaryButton"
    for name in ("imprint_color_overlays_button", "imprint_selected_tg_overlays_button", "groupBox_11"):
        assert getattr(gui, name).styleSheet() == ""  # the theme decides
