import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


class VersionManager:
    """Manage version numbers for the executable."""
    
    def __init__(self, version_file="version.json"):
        self.version_file = Path(version_file)
        self.version_data = self._load_version()
    
    def _load_version(self):
        """Load version from file or create default."""
        if self.version_file.exists():
            try:
                with open(self.version_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading version file: {e}")
                return {"major": 1, "minor": 0, "patch": 0}
        else:
            return {"major": 1, "minor": 0, "patch": 0}
    
    def _save_version(self):
        """Save version to file."""
        with open(self.version_file, 'w') as f:
            json.dump(self.version_data, f, indent=2)
    
    def get_version_string(self):
        """Get version as string (e.g., '1.0.0')."""
        return f"{self.version_data['major']}.{self.version_data['minor']}.{self.version_data['patch']}"
    
    def bump_patch(self):
        """Increment patch version (1.0.0 -> 1.0.1)."""
        self.version_data['patch'] += 1
        self._save_version()
        return self.get_version_string()
    
    def bump_minor(self):
        """Increment minor version and reset patch (1.0.5 -> 1.1.0)."""
        self.version_data['minor'] += 1
        self.version_data['patch'] = 0
        self._save_version()
        return self.get_version_string()
    
    def bump_major(self):
        """Increment major version and reset minor/patch (1.5.3 -> 2.0.0)."""
        self.version_data['major'] += 1
        self.version_data['minor'] = 0
        self.version_data['patch'] = 0
        self._save_version()
        return self.get_version_string()


# Get version for build
version_manager = VersionManager()
VERSION_STRING = version_manager.get_version_string()

# Project configuration
PROJECT_NAME = "BildHatcher"
MAIN_FILE = "main.py"
ICON_FILE = "icon.ico"  # Optional: add your icon file path
OUTPUT_DIR = "dist"

def build_executable():
    """Build the executable using PyInstaller with versioning."""
    
    exe_name = f"{PROJECT_NAME}_v{VERSION_STRING}"
    
    print(f"Building {PROJECT_NAME} v{VERSION_STRING}...")
    print(f"Output: {exe_name}.exe")
    
    # PyInstaller command - use correct argument names
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", exe_name,
        "--onefile",
        "--windowed",
        "--add-data", "GUI_files;GUI_files",  # Include GUI files
        "--add-data", "settings;settings",    # Include settings
        "--add-data", "libraries;libraries",  # Include libraries
        # "--add-data", "Drivers;Drivers",      # Include drivers
        "--distpath", OUTPUT_DIR,
        "--workpath", "build",   # ← FIXED HERE
    ]
    
    # Add icon if it exists
    icon_path = Path(ICON_FILE)
    if icon_path.exists():
        pyinstaller_cmd.extend(["--icon", ICON_FILE])
        print(f"Including icon: {ICON_FILE}")
    else:
        print(f"Note: Icon file '{ICON_FILE}' not found. Building without custom icon...")
    
    # Add main file
    pyinstaller_cmd.append(MAIN_FILE)
    
    try:
        # Run PyInstaller
        print(f"Running: {' '.join(pyinstaller_cmd)}\n")
        result = subprocess.run(pyinstaller_cmd, check=True)
        
        if result.returncode == 0:
            exe_path = Path(OUTPUT_DIR) / f"{exe_name}.exe"
            print(f"\n✓ Build successful!")
            print(f"✓ Executable: {exe_path}")
            print(f"✓ Version: {VERSION_STRING}")
        else:
            print(f"\n✗ Build failed with return code {result.returncode}")
            sys.exit(1)
            
    except FileNotFoundError:
        print("Error: PyInstaller not found. Install it with: pip install pyinstaller")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: Build failed with error:\n{e}")
        sys.exit(1)

if __name__ == "__main__":
    build_executable()