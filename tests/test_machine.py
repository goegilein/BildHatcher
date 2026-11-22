"""P5.1: machine profiles."""
import json

from PyQt6 import QtCore

from core import gcode, machine
from test_characterization import load_image, make_test_image, run_hatching, run_parser

OLD_HEADER_TAIL = [  # hard-coded header lines before 2.0
    "G90 ; Use absolute coordinates",
    "G21 ; Set units to millimeters",
    "M2000 W1 P100 ; Artisan Setting to turn on Enclosure lights 100%",
    "G0 F6000 ; set default feedrate for laser off moves",
    "G1 F6000 ; set default feedrate for laser on moves",
    "",
]
OLD_FOOTER = [
    "; Footer",
    "M5 ; Turn off laser",
    "M9 ; Turn off Air assist",
    "M2000 W2 P0 ; Artisan Setting to turn off Enclosure fan (0%)",
    "M2000 L23 P1 ; Artisan 40W laser. 1 exits half power Moade",
    "; End of G-code",
]


def test_default_profile_reproduces_old_header_and_footer():
    profile = machine.default_profile()
    assert gcode.generate_gcode_header(profile)[-6:] == OLD_HEADER_TAIL
    assert gcode.generate_gcode_footer(profile) == OLD_FOOTER


def test_second_profile_changes_commands_and_mode_options(app_components, tmp_path, monkeypatch):
    c = app_components
    other = {
        "name": "Generic GRBL",
        "header": ["G90", "G21"],
        "footer": ["M5"],
        "laser_modes": {"dynamic": ["M4"]},
        "power_modes": {"default": []},
        "air_assist": {"off": []},
        "enclosure_fan": [],
        "burn_power": " S{power}",
        "rapid_speed": 50,
    }
    (machine.USER_DIR / "grbl.json").write_text(json.dumps(other), encoding="utf-8")
    try:
        c.parser.reload_machine_profiles()
        assert c.gui.machine_profile_combobox.findText("Generic GRBL") >= 0
        c.gui.machine_profile_combobox.setCurrentText("Generic GRBL")
        assert c.data_handler.machine_profile.name == "Generic GRBL"
        assert [c.gui.laser_mode_combobox.itemText(i) for i in range(c.gui.laser_mode_combobox.count())] == ["dynamic"]

        load_image(c, make_test_image())
        run_hatching(c, pattern="FixedMeander", angle=0.0)
        text = run_parser(c, laser_mode="dynamic", power_mode="default", air_assist="off")
        assert "M2000" not in text and "\nM4\n" in text
        burns = [line for line in text.splitlines() if line.startswith("G1") and " S" in line]
        assert burns and all(" P" not in line for line in burns)  # GRBL power format: S only
        block = c.parser.process_listWidget.item(0).data(QtCore.Qt.ItemDataRole.UserRole)
        assert block.machine.name == "Generic GRBL"
    finally:
        (machine.USER_DIR / "grbl.json").unlink()
        c.parser.reload_machine_profiles()
    assert c.data_handler.machine_profile.name == "Snapmaker Artisan 40W"


def test_settings_store_machine_profile(app_components):
    import Settings
    saved = app_components.settings.collect_settings(Settings.HATCHING_SETTINGS)
    assert saved["machine_profile"] == "Snapmaker Artisan 40W"
