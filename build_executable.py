import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Version configuration
VERSION_MAJOR = 1
VERSION_MINOR = 0
VERSION_PATCH = 1
VERSION_STRING = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"

# Project configuration
PROJECT_NAME = "BildHatcher"
MAIN_FILE = "main.py"
ICON_FILE = "icon.ico"  # Optional: add your icon file path
OUTPUT_DIR = "dist"

def build_executable():
    """Build the executable using PyInstaller with versioning."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exe_name = f"{PROJECT_NAME}_v{VERSION_STRING}_{timestamp}"
    
    print(f"Building {PROJECT_NAME} v{VERSION_STRING}...")
    print(f"Output: {exe_name}.exe")
    
    # PyInstaller command - use correct argument names
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", exe_name,
        "--onefile",
        "--windowed",
        "--add-data", "BildHatcher.ui;.",
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