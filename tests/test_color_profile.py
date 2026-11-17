"""P8.5: one application-wide colour-database profile."""
import json

import numpy as np
import pytest

import ColorProfile
from Database.database_main import DatabaseManager


def _some_profile_ids():
    db = DatabaseManager()  # copy of the bundled database in the test user folder
    try:
        for laser in db.get_lasers():
            for material in db.get_all_materials():
                for mtype in db.get_material_types_for_material(material["id"]):
                    if db.get_parameters(db.get_or_create_palette(laser["id"], mtype["id"])):
                        return laser["id"], material["id"], mtype["id"]
    finally:
        db.close()
    pytest.skip("bundled database has no profile with colours")


def test_profile_is_used_everywhere_and_remembered(app_components, monkeypatch):
    c = app_components
    ids = _some_profile_ids()
    palette = ColorProfile.palette_from_payload(ColorProfile.load_profile(*ids))
    c.color_profiles.set_profile(palette)

    name = ColorProfile.profile_name(palette)
    assert c.color_profiles.action.text() == f"Color Profile: {name}"
    assert c.gui.selected_laser_label.text().strip("<b> /") == palette.identifiers["laser"]["name"]
    assert palette.identifiers["laser"]["name"] in c.gui.recolor_from_database_button.toolTip()
    saved = json.loads(ColorProfile.PREFERENCES_FILE.read_text())["color_profile"]
    assert (saved["laser_id"], saved["material_id"], saved["type_id"]) == ids

    # a new session restores it without asking
    monkeypatch.setattr(ColorProfile, "choose_profile_dialog", lambda *a: pytest.fail("must not ask"))
    restored = ColorProfile.ColorProfileController(c.data_handler, c.gui)
    assert ColorProfile.profile_name(c.data_handler.color_profile) == name
    assert restored.action.text() == f"Color Profile: {name}"


def test_recolor_uses_the_active_profile_without_dialog(app_components, monkeypatch):
    from core import image_doc
    from test_characterization import load_image, make_test_image
    c = app_components
    c.color_profiles.set_profile(ColorProfile.palette_from_payload(ColorProfile.load_profile(*_some_profile_ids())))
    monkeypatch.setattr(ColorProfile, "choose_profile_dialog", lambda *a: pytest.fail("must not ask"))
    load_image(c, image_doc.from_rgb(make_test_image()))
    c.image_colorer.recolor_color_from_db()
    c.image_colorer.imprint_color_overlays()
    allowed = {tuple(int(v) for v in p["color_rgb"].split(",")) for p in c.data_handler.color_profile.color_palette}
    img = c.data_handler.image_matrix
    assert {tuple(int(v) for v in px) for px in img[img[..., 3] > 0][:, :3]} <= allowed
