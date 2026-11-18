"""P10: prints the minimum width of every panel section, measured in a real (off-screen positioned) window.

Used by tests/test_layout.py; the offscreen test platform has no real fonts.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["BILDHATCHER_USER_DIR"] = tempfile.mkdtemp()

from PyQt6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication(sys.argv)
import main  # noqa: E402

gui = main.create_main_window()
c = main.create_components(gui)
panel = main.MainLayout.build(gui, c)
gui.move(-4000, -4000)
gui.show()
result = {}
for label, section in panel.sections.items():
    panel.select_group(panel.group_of[label])
    panel.section_buttons[label].setChecked(True)
    app.processEvents()
    result[label] = section.minimumSizeHint().width()
gui.close()
print(json.dumps(result))
