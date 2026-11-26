"""Atelier style (theme.py, GUI_Files/styles/atelier.qss)."""
from lxml import etree
from PyQt6 import QtGui, QtWidgets

import theme
from PathManager import get_gui_file_path


def test_ui_carries_the_atelier_stylesheet_for_designer():
    """tools/apply_style.py copies the .qss into the .ui; both must stay identical."""
    tree = etree.parse(str(get_gui_file_path("BildHatcher.ui")))
    ui_qss = tree.getroot().find("widget/property[@name='styleSheet']/string").text
    assert ui_qss == theme.render("dark")


def test_legacy_style_is_kept():
    legacy = get_gui_file_path("styles").joinpath("legacy_burgundy.qss").read_text(encoding="utf-8")
    assert "rgb(122,0,28)" in legacy.replace(" ", "")


def test_theme_loads_fonts_and_styles_the_app(qapp):
    assert {"Plus Jakarta Sans", "Space Mono"} <= set(theme.load_fonts())
    assert qapp.styleSheet() == theme.render(theme.MODE)
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


def test_both_palettes_fill_every_token():
    import re
    tokens = set(re.findall(r"@([A-Za-z]+)", theme.template().split("*/", 1)[1]))  # rules after the header
    palettes = theme.palettes()
    assert set(palettes) == {"dark", "light"}
    for mode, palette in palettes.items():
        assert tokens <= set(palette), (mode, tokens - set(palette))
        assert "@" not in theme.render(mode).split("*/", 1)[1], mode


def test_every_ui_pictogram_exists_for_both_modes():
    for name, kind, off, on in theme.ui_icons():
        for file in {off, on} - {None}:
            stem = file.split("/")[-1][:-4]
            assert theme.icon_file(stem, "dark").exists() and theme.icon_file(stem, "light").exists(), stem


def test_bright_mode_switches_style_and_pictograms(app_components, qapp):
    gui = app_components.gui
    action = gui.actionBright_Mode
    assert action in gui.menuModes.actions() and action.isCheckable() and not action.isChecked()
    dark_icon = gui.add_image_button.icon().pixmap(20, 20).toImage()
    try:
        action.setChecked(True)
        assert theme.MODE == "light" and qapp.styleSheet() == theme.render("light")
        light_icon = gui.add_image_button.icon().pixmap(20, 20).toImage()
        assert light_icon != dark_icon
        assert theme.color("surface") == theme.color("surface", "light")
        import Preferences
        assert Preferences.get("theme") == "light"
    finally:
        action.setChecked(False)
    assert theme.MODE == "dark" and qapp.styleSheet() == theme.render("dark")
    assert gui.add_image_button.icon().pixmap(20, 20).toImage() != light_icon  # dark pictograms again


def test_the_app_runs_without_dev_dependencies():
    """Only requirements.txt is needed to run the app: no lxml (dev only) in the modules the app imports."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dev_only = {"lxml", "pytest"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
        names |= {node.module.split(".")[0] for node in ast.walk(tree)
                  if isinstance(node, ast.ImportFrom) and node.module}
        assert not names & dev_only, (path.name, names & dev_only)
    assert theme.ui_icons()  # the .ui is read with the standard library


def test_dropdown_lists_have_an_opaque_background_in_both_modes(app_components):
    """The drop-down list of a combo box inside a panel card was see-through (the card's "transparent children"
    rule reached the popup, which is a child of the combo box)."""
    gui = app_components.gui
    combo = gui.flood_fill_mode_combobox  # in the Color section card
    try:
        for mode in ("dark", "light"):
            theme.set_mode(mode, gui)
            combo.showPopup()
            view = combo.view()
            background = view.palette().color(view.backgroundRole())
            combo.hidePopup()
            assert background.alpha() == 255 and background == theme.color("surface", mode), mode
    finally:
        theme.set_mode("dark", gui)
