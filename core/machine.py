"""Machine profiles: everything that is specific to a laser machine (REVISION_PLAN.md P5.1).

A profile is a JSON file (see machine_profiles/snapmaker_artisan_40w.json). The bundled profiles are copied to
the user folder ~/Documents/BildHatcher/machine_profiles on first use; users add or edit profiles there.

Fields:
  name                      shown in the UI
  header, footer            G-code lines at the start/end of a file; "{feedrate}" is replaced
  laser_modes, power_modes, air_assist
                            option name -> G-code lines (the option names fill the UI drop-downs)
  enclosure_fan             lines with "{fan}" (percent); [] if the machine has none
  burn_power                appended to a G1 move when the power changes; "{power}" = percent, "{s}" = 0-255
  feedrate                  default feed in mm/min for the header
  rapid_speed               mm/s of the lead-in travel moves of the drive post-processing
  acceleration              mm/s^2, sets the lead-in/lead-out length of the drive post-processing
  over_drive_fit            [a, b, c, n] of the over-drive length a + (b - a) / (1 + (speed / c)^n) in mm
  cylinder_laser_distance   mm the workpiece surface may move away from the focus when wrapping around a cylinder
"""
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PathManager import USER_DIR as APP_USER_DIR, get_base_dir

log = logging.getLogger(__name__)

BUNDLED_DIR = get_base_dir() / "machine_profiles"
USER_DIR = APP_USER_DIR / "machine_profiles"


@dataclass
class MachineProfile:
    name: str
    header: list = field(default_factory=list)
    footer: list = field(default_factory=list)
    laser_modes: dict = field(default_factory=dict)
    power_modes: dict = field(default_factory=dict)
    air_assist: dict = field(default_factory=dict)
    enclosure_fan: list = field(default_factory=list)
    burn_power: str = " S{s}"
    feedrate: float = 6000
    rapid_speed: float = 100
    acceleration: float = 3000
    over_drive_fit: list = field(default_factory=lambda: [0.24484, 0.10634, 27.3937, 5.82549])
    cylinder_laser_distance: float = 17
    path: Path = None

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            log.warning("%s: unknown keys %s ignored", path, sorted(unknown))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__}, path=Path(path))

    def option_lines(self, kind, option):
        """G-code lines of option `option` for kind 'laser_modes' / 'power_modes' / 'air_assist'."""
        options = getattr(self, kind)
        if option not in options:
            log.error("Machine %r has no %s option %r", self.name, kind, option)
            return []
        return list(options[option])


def load_profiles(user_dir=USER_DIR, bundled_dir=BUNDLED_DIR):
    """All profiles by name (user profiles override bundled ones with the same name), sorted by name."""
    try:
        user_dir.mkdir(parents=True, exist_ok=True)
        for bundled in bundled_dir.glob("*.json"):
            if not (user_dir / bundled.name).exists():
                shutil.copy2(bundled, user_dir / bundled.name)
    except OSError as e:
        log.warning("Could not prepare %s: %s", user_dir, e)
    profiles = {}
    for directory in (bundled_dir, user_dir):
        for path in sorted(Path(directory).glob("*.json")):
            try:
                profile = MachineProfile.load(path)
                profiles[profile.name] = profile
            except Exception as e:
                log.error("Could not load machine profile %s: %s", path, e)
    return dict(sorted(profiles.items()))


def default_profile():
    """The bundled default profile (used where no profile was chosen, e.g. in tests)."""
    return MachineProfile.load(BUNDLED_DIR / "snapmaker_artisan_40w.json")
