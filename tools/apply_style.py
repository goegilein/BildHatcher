"""Copy a stylesheet from GUI_Files/styles into the root of GUI_Files/BildHatcher.ui (so Qt Designer shows it).

    python tools/apply_style.py             # atelier (the app's style)
    python tools/apply_style.py legacy_burgundy

Edit the .qss file, not the stylesheet in Designer – this script overwrites it.
"""
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "GUI_Files" / "BildHatcher.ui"


def apply(name="atelier"):
    qss = (ROOT / "GUI_Files" / "styles" / f"{name}.qss").read_text(encoding="utf-8")
    tree = etree.parse(str(UI))
    window = tree.getroot().find("widget")
    prop = window.find("property[@name='styleSheet']")
    prop.find("string").text = qss
    text = etree.tostring(tree, xml_declaration=True, encoding="UTF-8").decode("utf-8")
    UI.write_text(text.replace("<?xml version='1.0' encoding='UTF-8'?>", '<?xml version="1.0" encoding="UTF-8"?>')
                  + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    print(f"{name}.qss -> {UI.name}")


if __name__ == "__main__":
    apply(*(sys.argv[1:] or ["atelier"]))
