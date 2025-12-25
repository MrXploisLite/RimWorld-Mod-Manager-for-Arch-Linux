#!/usr/bin/env python3
"""
RimModManager
A universal mod manager for RimWorld supporting all platforms.

Author: RimWorld Linux Community
License: MIT
"""

import sys
import os
from pathlib import Path

# Ensure the project directory is in the path
project_dir = Path(__file__).parent.absolute()
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))


def check_dependencies() -> bool:
    """Check if all required dependencies are available."""
    missing = []
    
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        missing.append("PyQt6")
    
    if missing:
        print("Missing required dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall with:")
        print("  pip install PyQt6")
        print("  # or on Arch:")
        print("  sudo pacman -S python-pyqt6")
        return False
    
    return True


def setup_environment():
    """Set up environment variables and paths - cross-platform."""
    import platform
    system = platform.system().lower()
    
    # Suppress Qt portal warnings and WebEngine debug output
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.services=false;qt.webenginecontext.debug=false"
    
    # Suppress JS console errors from web engine
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3"
    
    if system == 'windows':
        # Windows-specific setup
        appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming'))
        config_dir = Path(appdata) / "RimModManager"
        config_dir.mkdir(parents=True, exist_ok=True)
        
    elif system == 'darwin':  # macOS
        # macOS-specific setup
        config_dir = Path.home() / "Library/Application Support/RimModManager"
        config_dir.mkdir(parents=True, exist_ok=True)
        
    else:  # Linux
        # Ensure XDG directories exist
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        config_dir = Path(xdg_config) / "rimmodmanager"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Set Qt environment for better theme integration
        if "QT_QPA_PLATFORMTHEME" not in os.environ:
            # Try to detect KDE/Qt theme
            if os.environ.get("KDE_FULL_SESSION"):
                os.environ["QT_QPA_PLATFORMTHEME"] = "kde"
            elif os.environ.get("DESKTOP_SESSION", "").lower() in ("gnome", "ubuntu"):
                os.environ["QT_QPA_PLATFORMTHEME"] = "gnome"


def main():
    """Main application entry point."""
    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)
    
    # Set up environment
    setup_environment()
    
    # Import after dependency check
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette, QColor
    
    from ui.main_window import MainWindow
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("RimModManager")
    app.setApplicationDisplayName("RimModManager")
    app.setOrganizationName("RimModManager")
    app.setOrganizationDomain("rimmodmanager.app")
    
    # Set up style
    app.setStyle("Fusion")
    
    # Check if system prefers dark mode
    is_dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    
    if is_dark:
        # Apply dark palette
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        # Disabled colors
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        
        app.setPalette(dark_palette)
    
    # Create and show main window
    try:
        window = MainWindow()
        window.show()
    except (OSError, IOError, RuntimeError, ValueError, TypeError) as e:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Startup Error", f"Failed to start application:\n{e}")
        return 1
    
    # Run the application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
