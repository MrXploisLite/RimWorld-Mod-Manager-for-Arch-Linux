"""
Main Window for RimModManager
The primary application window with all mod management features.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit,
    QGroupBox, QTabWidget, QFileDialog, QMessageBox,
    QProgressBar, QStatusBar,
    QDialog, QDialogButtonBox, QListWidget,
    QInputDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QColor, QKeySequence, QShortcut

from config_handler import ConfigHandler
from game_detector import GameDetector, RimWorldInstallation, InstallationType
from mod_parser import ModParser, ModInfo, ModSource
from workshop_downloader import WorkshopDownloader, ModInstaller
from ui.mod_widgets import (
    DraggableModList, ModDetailsPanel, ModListControls, ConflictWarningWidget,
    ModSearchFilter
)
from ui.workshop_browser import WorkshopBrowser
from ui.download_manager import DownloadLogWidget, SteamCMDChecker

# Module logger
log = logging.getLogger("rimmodmanager.ui.main_window")


class PathsDialog(QDialog):
    """Dialog for managing mod source paths."""
    
    def __init__(self, config: ConfigHandler, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Manage Mod Source Paths")
        self.setMinimumSize(500, 400)
        
        self._setup_ui()
        self._load_paths()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        label = QLabel("Add directories containing RimWorld mods. "
                      "The mod manager will scan these folders for mods.")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Path list
        self.path_list = QListWidget()
        layout.addWidget(self.path_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("Add Path...")
        self.btn_add.clicked.connect(self._add_path)
        btn_layout.addWidget(self.btn_add)
        
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self._remove_path)
        btn_layout.addWidget(self.btn_remove)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
    
    def _load_paths(self):
        self.path_list.clear()
        for path in self.config.config.mod_source_paths:
            self.path_list.addItem(path)
    
    def _add_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Mod Directory",
            str(Path.home())
        )
        if path:
            if self.config.add_mod_source_path(path):
                self.path_list.addItem(path)
    
    def _remove_path(self):
        current = self.path_list.currentItem()
        if current:
            path = current.text()
            self.config.remove_mod_source_path(path)
            self.path_list.takeItem(self.path_list.row(current))


class WorkshopDialog(QDialog):
    """Dialog for downloading workshop mods."""
    
    download_requested = pyqtSignal(list)  # list of workshop IDs
    
    def __init__(self, downloader: WorkshopDownloader, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        self.setWindowTitle("Download Workshop Mods")
        self.setMinimumSize(500, 400)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Check SteamCMD
        if not self.downloader.is_steamcmd_available():
            warning = QLabel("⚠️ SteamCMD not found!")
            warning.setStyleSheet("color: orange; font-weight: bold;")
            layout.addWidget(warning)
            
            instructions = QLabel(self.downloader.get_install_instructions())
            instructions.setWordWrap(True)
            layout.addWidget(instructions)
            
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            return
        
        # Input section
        input_group = QGroupBox("Workshop URL or Mod ID")
        input_layout = QVBoxLayout(input_group)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "Enter Workshop URLs or Mod IDs (one per line)\n\n"
            "Examples:\n"
            "https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077\n"
            "2009463077\n\n"
            "You can also paste a collection URL or load from file."
        )
        self.input_text.setMinimumHeight(150)
        input_layout.addWidget(self.input_text)
        
        btn_layout = QHBoxLayout()
        
        self.btn_load_file = QPushButton("Load from File...")
        self.btn_load_file.clicked.connect(self._load_from_file)
        btn_layout.addWidget(self.btn_load_file)
        
        self.btn_parse_collection = QPushButton("Parse Collection URL")
        self.btn_parse_collection.clicked.connect(self._parse_collection)
        btn_layout.addWidget(self.btn_parse_collection)
        
        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)
        
        layout.addWidget(input_group)
        
        # Status
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Dialog buttons
        btn_box = QDialogButtonBox()
        self.btn_download = btn_box.addButton("Download", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_download.clicked.connect(self._start_download)
        btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
    
    def _load_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Workshop IDs",
            str(Path.home()),
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            ids = self.downloader.load_ids_from_file(Path(file_path))
            if ids:
                current = self.input_text.toPlainText()
                if current:
                    current += "\n"
                self.input_text.setPlainText(current + "\n".join(ids))
                self.status_label.setText(f"Loaded {len(ids)} mod IDs from file")
    
    def _parse_collection(self):
        text = self.input_text.toPlainText().strip()
        if "steamcommunity.com" in text and "collection" in text.lower():
            self.status_label.setText("Parsing collection...")
            QApplication.processEvents()
            
            ids = self.downloader.parse_collection_page(text)
            if ids:
                self.input_text.setPlainText("\n".join(ids))
                self.status_label.setText(f"Found {len(ids)} mods in collection")
            else:
                self.status_label.setText("Failed to parse collection or no mods found")
        else:
            self.status_label.setText("Please enter a Steam Workshop collection URL")
    
    def _start_download(self):
        text = self.input_text.toPlainText()
        ids = self.downloader.extract_workshop_ids_from_text(text)
        
        if not ids:
            self.status_label.setText("No valid Workshop IDs found")
            return
        
        self.status_label.setText(f"Starting download of {len(ids)} mod(s)...")
        self.download_requested.emit(ids)
        self.accept()


class GameLaunchDialog(QDialog):
    """Dialog for launching game with live detection log."""
    
    def __init__(self, installation: 'RimWorldInstallation', parent=None):
        super().__init__(parent)
        self.installation = installation
        self.setWindowTitle("🎮 Launch RimWorld")
        self.setMinimumSize(500, 350)
        self._setup_ui()
        
        # Start detection after dialog shows
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._start_detection)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("🎮 Launching RimWorld...")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        # Live log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.log_text, 1)
        
        # Status
        self.status_label = QLabel("Detecting...")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
    
    def _log(self, msg: str, color: str = "#d4d4d4"):
        """Add log message."""
        self.log_text.setTextColor(QColor(color))
        self.log_text.append(msg)
        QApplication.processEvents()
    
    def _start_detection(self):
        """Detect and launch game."""
        game_path = self.installation.path
        is_windows = self.installation.is_windows_build
        
        self._log(f"[INFO] Game path: {game_path}", "#74c0fc")
        self._log(f"[INFO] Windows build: {is_windows}", "#74c0fc")
        
        # Find executable based on platform and build type
        import platform
        system = platform.system().lower()
        
        if is_windows:
            executables = [
                game_path / "RimWorldWin64.exe",
                game_path / "RimWorldWin.exe",
            ]
        elif system == 'darwin':
            executables = [
                game_path / "RimWorldMac.app",
                game_path / "RimWorld.app",
                game_path / "RimWorldMac",
                game_path / "RimWorld",
            ]
        else:  # Linux
            executables = [
                game_path / "RimWorldLinux",
                game_path / "RimWorld",
            ]
        
        exe_path = None
        for exe in executables:
            self._log(f"[SCAN] Checking: {exe.name}...")
            if exe.exists():
                exe_path = exe
                self._log(f"[OK] Found: {exe}", "#69db7c")
                break
            else:
                self._log(f"[--] Not found", "#888888")
        
        if not exe_path:
            self._log(f"[ERROR] No executable found!", "#ff6b6b")
            self.status_label.setText("❌ Failed - No executable found")
            return
        
        # Check if Steam owns this game
        self._log(f"\n[SCAN] Checking Steam license...", "#ffd43b")
        has_steam_license = self._check_steam_license()
        
        if has_steam_license:
            self._log(f"[OK] Steam license found - launching via Steam", "#69db7c")
            self._launch_via_steam()
        else:
            self._log(f"[INFO] No Steam license - launching directly (standalone/crack)", "#74c0fc")
            self._launch_direct(exe_path, game_path, is_windows)
    
    def _check_steam_license(self) -> bool:
        """Check if user owns RimWorld on Steam - cross-platform."""
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            # Windows Steam paths
            steam_paths = [
                Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Steam',
                Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Steam',
            ]
        elif system == 'darwin':  # macOS
            steam_paths = [
                Path.home() / 'Library/Application Support/Steam',
            ]
        else:  # Linux
            steam_paths = [
                Path.home() / ".local/share/Steam",
                Path.home() / ".steam/steam",
            ]
        
        for steam_path in steam_paths:
            # Check appmanifest for RimWorld (294100)
            manifest = steam_path / "steamapps/appmanifest_294100.acf"
            if manifest.exists():
                self._log(f"[OK] Found Steam manifest: {manifest.name}", "#69db7c")
                
                # Verify it's actually installed (not just cached)
                try:
                    content = manifest.read_text()
                    if '"StateFlags"' in content and '"4"' in content:
                        self._log(f"[OK] Game is fully installed via Steam", "#69db7c")
                        return True
                except (IOError, OSError):
                    pass
        
        self._log(f"[--] No Steam license/manifest found", "#888888")
        return False
    
    def _find_proton(self) -> Optional[str]:
        """Find Proton executable - checks system proton and Steam proton."""
        # Check for system-installed proton (like proton-cachyos, proton-ge, etc.)
        proton_commands = [
            "proton",           # System proton in PATH
            "proton-cachyos",   # CachyOS proton
            "proton-ge",        # GE-Proton standalone
        ]
        
        for cmd in proton_commands:
            if shutil.which(cmd):
                self._log(f"[SCAN] Found system Proton: {cmd}", "#74c0fc")
                return cmd
        
        # Check common proton installation paths
        proton_paths = [
            Path.home() / ".local/share/Steam/compatibilitytools.d",
            Path.home() / ".steam/steam/compatibilitytools.d",
            Path("/usr/share/steam/compatibilitytools.d"),
        ]
        
        for base_path in proton_paths:
            if base_path.exists():
                try:
                    for proton_dir in base_path.iterdir():
                        if proton_dir.is_dir():
                            proton_bin = proton_dir / "proton"
                            if proton_bin.exists():
                                self._log(f"[SCAN] Found Proton at: {proton_bin}", "#74c0fc")
                                return str(proton_bin)
                except PermissionError:
                    pass
        
        self._log(f"[--] No Proton installation found", "#888888")
        return None
    
    def _launch_via_steam(self):
        """Launch via Steam - cross-platform."""
        import platform
        system = platform.system().lower()
        
        self._log(f"\n[LAUNCH] Starting via Steam...", "#ffd43b")
        
        try:
            if system == 'windows':
                os.startfile("steam://rungameid/294100")
            elif system == 'darwin':  # macOS
                subprocess.Popen(
                    ["open", "steam://rungameid/294100"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:  # Linux
                subprocess.Popen(
                    ["xdg-open", "steam://rungameid/294100"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            self._log(f"[OK] Steam launch command sent!", "#69db7c")
            self.status_label.setText("✅ Launched via Steam!")
        except (OSError, subprocess.SubprocessError) as e:
            self._log(f"[ERROR] {e}", "#ff6b6b")
            self.status_label.setText(f"❌ Failed: {e}")
    
    def _launch_direct(self, exe_path: Path, game_path: Path, is_windows: bool):
        """Launch game directly from folder - cross-platform."""
        import platform
        system = platform.system().lower()
        
        self._log(f"\n[LAUNCH] Starting directly...", "#ffd43b")
        
        try:
            if system == 'windows':
                # On Windows, just run the exe directly
                self._log(f"[INFO] Running Windows executable directly", "#74c0fc")
                subprocess.Popen(
                    [str(exe_path)],
                    cwd=str(game_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self._log(f"[OK] Game started!", "#69db7c")
                self.status_label.setText("✅ Launched!")
                
            elif system == 'darwin':  # macOS
                if is_windows:
                    # Windows build on macOS - need Wine or CrossOver
                    if shutil.which("wine") or shutil.which("wine64"):
                        wine_cmd = shutil.which("wine64") or shutil.which("wine")
                        self._log(f"[INFO] Running Windows build with Wine: {wine_cmd}", "#74c0fc")
                        
                        env = os.environ.copy()
                        if self.installation.proton_prefix:
                            env["WINEPREFIX"] = str(self.installation.proton_prefix)
                            self._log(f"[INFO] WINEPREFIX: {self.installation.proton_prefix}", "#74c0fc")
                        
                        subprocess.Popen(
                            [wine_cmd, str(exe_path)],
                            cwd=str(game_path),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            env=env,
                            start_new_session=True  # Fully detach from parent
                        )
                        self._log(f"[OK] Game started with Wine!", "#69db7c")
                        self._log(f"[TIP] If mods disable when closing this app, enable", "#ffd43b")
                        self._log(f"      Development Mode in RimWorld Options > General", "#ffd43b")
                        self.status_label.setText("✅ Launched with Wine!")
                    else:
                        self._log(f"[ERROR] Wine not found!", "#ff6b6b")
                        self._log(f"[TIP] Install Wine via: brew install --cask wine-stable", "#ffd43b")
                        self.status_label.setText("❌ Wine not installed")
                elif exe_path.suffix == '.app' or '.app' in str(exe_path):
                    # macOS app bundle
                    self._log(f"[INFO] Running macOS app bundle", "#74c0fc")
                    subprocess.Popen(
                        ["open", str(exe_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self._log(f"[OK] Game started!", "#69db7c")
                    self.status_label.setText("✅ Launched!")
                else:
                    # Native macOS binary
                    self._log(f"[INFO] Running native macOS executable", "#74c0fc")
                    subprocess.Popen(
                        [str(exe_path)],
                        cwd=str(game_path),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self._log(f"[OK] Game started!", "#69db7c")
                    self.status_label.setText("✅ Launched!")
                
            else:  # Linux
                if is_windows:
                    # Check for Proton first (better compatibility than wine)
                    proton_cmd = self._find_proton()
                    if proton_cmd:
                        self._log(f"[OK] Found Proton: {proton_cmd}", "#69db7c")
                        self._log(f"[INFO] Launching with Proton...", "#74c0fc")
                        
                        env = os.environ.copy()
                        
                        # Find Steam installation path
                        steam_path = Path.home() / ".local/share/Steam"
                        if not steam_path.exists():
                            steam_path = Path.home() / ".steam/steam"
                        
                        # Set required Proton environment variables
                        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(steam_path)
                        
                        # Set prefix path
                        if self.installation.proton_prefix:
                            compat_data = self.installation.proton_prefix.parent
                            env["STEAM_COMPAT_DATA_PATH"] = str(compat_data)
                            env["WINEPREFIX"] = str(self.installation.proton_prefix)
                            self._log(f"[INFO] Prefix: {self.installation.proton_prefix}", "#74c0fc")
                        else:
                            # Create default prefix path
                            default_prefix = Path.home() / ".proton" / "rimworld"
                            default_prefix.mkdir(parents=True, exist_ok=True)
                            env["STEAM_COMPAT_DATA_PATH"] = str(default_prefix)
                            self._log(f"[INFO] Using default prefix: {default_prefix}", "#74c0fc")
                        
                        # Additional env vars for better compatibility
                        env["PROTON_USE_WINED3D"] = "0"
                        env["PROTON_NO_ESYNC"] = "0"
                        env["PROTON_NO_FSYNC"] = "0"
                        
                        # Get proton directory for wine binary
                        proton_dir = Path(proton_cmd).parent
                        wine_bin = proton_dir / "files" / "bin" / "wine64"
                        if not wine_bin.exists():
                            wine_bin = proton_dir / "files" / "bin" / "wine"
                        
                        if wine_bin.exists():
                            # Use wine binary directly from Proton (more reliable)
                            self._log(f"[INFO] Using Proton's Wine: {wine_bin}", "#74c0fc")
                            subprocess.Popen(
                                [str(wine_bin), str(exe_path)],
                                cwd=str(game_path),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                env=env,
                                start_new_session=True  # Fully detach from parent
                            )
                        else:
                            # Fallback to proton run command
                            subprocess.Popen(
                                [proton_cmd, "run", str(exe_path)],
                                cwd=str(game_path),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                env=env,
                                start_new_session=True  # Fully detach from parent
                            )
                        self._log(f"[OK] Game started with Proton!", "#69db7c")
                        self._log(f"[TIP] If mods disable when closing this app, enable", "#ffd43b")
                        self._log(f"      Development Mode in RimWorld Options > General", "#ffd43b")
                        self.status_label.setText("✅ Launched with Proton!")
                    elif shutil.which("wine"):
                        # Fallback to wine
                        self._log(f"[INFO] Proton not found, using Wine...", "#74c0fc")
                        
                        env = os.environ.copy()
                        if self.installation.proton_prefix:
                            env["WINEPREFIX"] = str(self.installation.proton_prefix)
                            self._log(f"[INFO] WINEPREFIX: {self.installation.proton_prefix}", "#74c0fc")
                        
                        subprocess.Popen(
                            ["wine", str(exe_path)],
                            cwd=str(game_path),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            env=env,
                            start_new_session=True  # Fully detach from parent
                        )
                        self._log(f"[OK] Game started with Wine!", "#69db7c")
                        self._log(f"[TIP] If mods disable when closing this app, enable", "#ffd43b")
                        self._log(f"      Development Mode in RimWorld Options > General", "#ffd43b")
                        self.status_label.setText("✅ Launched with Wine!")
                    else:
                        self._log(f"[ERROR] No Proton or Wine found!", "#ff6b6b")
                        self._log(f"[TIP] Install proton or wine to run Windows games", "#ffd43b")
                        self.status_label.setText("❌ Proton/Wine not installed")
                else:
                    # Native Linux
                    self._log(f"[INFO] Running native Linux executable", "#74c0fc")
                    subprocess.Popen(
                        [str(exe_path)],
                        cwd=str(game_path),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True  # Fully detach from parent
                    )
                    self._log(f"[OK] Game started!", "#69db7c")
                    self.status_label.setText("✅ Launched!")
                
        except (OSError, subprocess.SubprocessError) as e:
            self._log(f"[ERROR] {e}", "#ff6b6b")
            self.status_label.setText(f"❌ Failed: {e}")


class QuickDownloadDialog(QDialog):
    """Dialog for quick downloading mods by URL or ID."""
    
    download_requested = pyqtSignal(list)  # List of workshop IDs
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Download")
        self.setMinimumSize(500, 350)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        info = QLabel(
            "Paste Workshop URLs or IDs below (one per line).\n"
            "Supported formats:\n"
            "• https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890\n"
            "• steamcommunity.com/sharedfiles/filedetails/?id=1234567890\n"
            "• 1234567890 (just the ID)"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)
        
        # Text input
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "Paste URLs or IDs here...\n\n"
            "Example:\n"
            "https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077\n"
            "2009463077\n"
            "1234567890"
        )
        layout.addWidget(self.input_text, 1)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_parse = QPushButton("🔍 Parse && Preview")
        self.btn_parse.clicked.connect(self._parse_input)
        btn_layout.addWidget(self.btn_parse)
        
        btn_layout.addStretch()
        
        self.btn_download = QPushButton("⬇️ Download")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._start_download)
        btn_layout.addWidget(self.btn_download)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
        self.parsed_ids = []
    
    def _parse_input(self):
        """Parse input text and extract workshop IDs."""
        import re
        
        text = self.input_text.toPlainText().strip()
        if not text:
            self.status_label.setText("⚠️ Please enter some URLs or IDs")
            self.status_label.setStyleSheet("color: #ffa500;")
            return
        
        lines = text.split('\n')
        ids = []
        
        # Regex patterns
        url_pattern = re.compile(r'[?&]id=(\d{7,12})')
        id_pattern = re.compile(r'^(\d{7,12})$')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try URL pattern first
            match = url_pattern.search(line)
            if match:
                ids.append(match.group(1))
                continue
            
            # Try plain ID
            match = id_pattern.match(line)
            if match:
                ids.append(match.group(1))
                continue
        
        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for wid in ids:
            if wid not in seen:
                seen.add(wid)
                unique_ids.append(wid)
        
        self.parsed_ids = unique_ids
        
        if unique_ids:
            self.status_label.setText(f"✅ Found {len(unique_ids)} mod(s): {', '.join(unique_ids[:5])}{'...' if len(unique_ids) > 5 else ''}")
            self.status_label.setStyleSheet("color: #69db7c;")
            self.btn_download.setEnabled(True)
        else:
            self.status_label.setText("❌ No valid Workshop IDs found")
            self.status_label.setStyleSheet("color: #ff6b6b;")
            self.btn_download.setEnabled(False)
    
    def _start_download(self):
        """Emit download signal and close."""
        if self.parsed_ids:
            self.download_requested.emit(self.parsed_ids)
            self.accept()


class SettingsDialog(QDialog):
    """Dialog for application settings."""
    
    def __init__(self, config: ConfigHandler, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 400)
        
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Workshop download path
        workshop_group = QGroupBox("Workshop Downloads")
        workshop_layout = QVBoxLayout(workshop_group)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Download Path:"))
        self.workshop_path_edit = QLineEdit()
        self.workshop_path_edit.setPlaceholderText("~/RimWorld_Workshop_Mods")
        path_layout.addWidget(self.workshop_path_edit, 1)
        
        self.btn_browse_workshop = QPushButton("Browse...")
        self.btn_browse_workshop.clicked.connect(self._browse_workshop_path)
        path_layout.addWidget(self.btn_browse_workshop)
        workshop_layout.addLayout(path_layout)
        
        layout.addWidget(workshop_group)
        
        # SteamCMD settings
        steamcmd_group = QGroupBox("SteamCMD")
        steamcmd_layout = QVBoxLayout(steamcmd_group)
        
        steamcmd_path_layout = QHBoxLayout()
        steamcmd_path_layout.addWidget(QLabel("SteamCMD Path:"))
        self.steamcmd_path_edit = QLineEdit()
        self.steamcmd_path_edit.setPlaceholderText("Auto-detect (leave empty)")
        steamcmd_path_layout.addWidget(self.steamcmd_path_edit, 1)
        
        self.btn_browse_steamcmd = QPushButton("Browse...")
        self.btn_browse_steamcmd.clicked.connect(self._browse_steamcmd_path)
        steamcmd_path_layout.addWidget(self.btn_browse_steamcmd)
        steamcmd_layout.addLayout(steamcmd_path_layout)
        
        layout.addWidget(steamcmd_group)
        
        # UI Settings
        ui_group = QGroupBox("User Interface")
        ui_layout = QVBoxLayout(ui_group)
        
        from PyQt6.QtWidgets import QCheckBox
        
        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Dark", "Light"])
        self.theme_combo.setToolTip("Select application theme (requires restart)")
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        ui_layout.addLayout(theme_layout)
        
        self.auto_refresh_check = QCheckBox("Auto-refresh mod list after downloads")
        self.auto_refresh_check.setChecked(True)
        ui_layout.addWidget(self.auto_refresh_check)
        
        self.auto_add_path_check = QCheckBox("Auto-add download path to mod sources")
        self.auto_add_path_check.setChecked(True)
        ui_layout.addWidget(self.auto_add_path_check)
        
        layout.addWidget(ui_group)
        
        # Performance Settings
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf_group)
        
        self.disable_webengine_check = QCheckBox("Disable embedded browser (saves ~150MB RAM)")
        self.disable_webengine_check.setToolTip(
            "Disable the embedded Steam Workshop browser.\n"
            "You can still download mods using Quick Download (Ctrl+D)\n"
            "or by pasting URLs in the Workshop tab."
        )
        perf_layout.addWidget(self.disable_webengine_check)
        
        perf_note = QLabel("<i>Changes take effect after restart</i>")
        perf_note.setStyleSheet("color: #888; font-size: 10px;")
        perf_layout.addWidget(perf_note)
        
        layout.addWidget(perf_group)
        
        # Update Settings
        update_group = QGroupBox("Updates")
        update_layout = QVBoxLayout(update_group)
        
        self.check_updates_startup = QCheckBox("Check for mod updates on startup")
        self.check_updates_startup.setToolTip("Automatically check Workshop mods for updates when the app starts")
        update_layout.addWidget(self.check_updates_startup)
        
        layout.addWidget(update_group)
        
        # Config file location info
        info_group = QGroupBox("Configuration")
        info_layout = QVBoxLayout(info_group)
        
        config_path = str(self.config.config_dir / "config.json")
        info_label = QLabel(f"Config file: <code>{config_path}</code>")
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        
        self.btn_open_config_dir = QPushButton("📂 Open Config Folder")
        self.btn_open_config_dir.clicked.connect(self._open_config_dir)
        info_layout.addWidget(self.btn_open_config_dir)
        
        layout.addWidget(info_group)
        
        layout.addStretch()
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_settings(self):
        """Load current settings into the dialog."""
        self.workshop_path_edit.setText(self.config.config.workshop_download_path)
        self.steamcmd_path_edit.setText(self.config.config.steamcmd_path)
        self.check_updates_startup.setChecked(self.config.config.check_updates_on_startup)
        self.disable_webengine_check.setChecked(self.config.config.disable_webengine)
        
        # Theme
        theme = getattr(self.config.config, 'theme', 'System')
        index = self.theme_combo.findText(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
    
    def _save_settings(self):
        """Save settings and close dialog."""
        self.config.config.workshop_download_path = self.workshop_path_edit.text()
        self.config.config.steamcmd_path = self.steamcmd_path_edit.text()
        self.config.config.check_updates_on_startup = self.check_updates_startup.isChecked()
        self.config.config.disable_webengine = self.disable_webengine_check.isChecked()
        self.config.config.theme = self.theme_combo.currentText()
        self.config.save()
        self.accept()
    
    def _browse_workshop_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Workshop Download Directory",
            str(Path.home())
        )
        if path:
            self.workshop_path_edit.setText(path)
    
    def _browse_steamcmd_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SteamCMD Executable",
            "/usr/bin",
            "Executables (*)"
        )
        if path:
            self.steamcmd_path_edit.setText(path)
    
    def _open_config_dir(self):
        import subprocess
        import platform
        import os
        system = platform.system().lower()
        
        try:
            if system == 'windows':
                os.startfile(str(self.config.config_dir))
            elif system == 'darwin':
                subprocess.run(["open", str(self.config.config_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(self.config.config_dir)], check=False)
        except (OSError, subprocess.SubprocessError):
            pass


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize components
        self.config = ConfigHandler()
        self.game_detector = GameDetector(self.config.config.custom_game_paths)
        self.mod_parser = ModParser()
        self.downloader: Optional[WorkshopDownloader] = None
        self.installer: Optional[ModInstaller] = None
        
        self.current_installation: Optional[RimWorldInstallation] = None
        self.all_mods: list[ModInfo] = []
        self.active_mods: list[ModInfo] = []
        self.inactive_mods: list[ModInfo] = []
        
        self._setup_ui()
        self._setup_menus()
        self._setup_shortcuts()
        self._connect_signals()
        
        # Initial detection
        QTimer.singleShot(100, self._initial_setup)
    
    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("RimModManager")
        self.setMinimumSize(1000, 700)
        
        # Restore window geometry
        if self.config.config.window_width > 0:
            self.resize(self.config.config.window_width, self.config.config.window_height)
        if self.config.config.window_x >= 0:
            self.move(self.config.config.window_x, self.config.config.window_y)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Top bar - Installation selector
        top_bar = QHBoxLayout()
        
        top_bar.addWidget(QLabel("Installation:"))
        self.install_combo = QComboBox()
        self.install_combo.setMinimumWidth(400)
        self.install_combo.currentIndexChanged.connect(self._on_installation_changed)
        top_bar.addWidget(self.install_combo, 1)
        
        self.btn_refresh_installs = QPushButton("🔄 Detect")
        self.btn_refresh_installs.setToolTip("Re-scan for RimWorld installations")
        self.btn_refresh_installs.clicked.connect(self._detect_installations)
        top_bar.addWidget(self.btn_refresh_installs)
        
        self.btn_add_install = QPushButton("➕ Add Custom")
        self.btn_add_install.clicked.connect(self._add_custom_installation)
        top_bar.addWidget(self.btn_add_install)
        
        main_layout.addLayout(top_bar)
        
        # Quick actions bar
        actions_bar = QHBoxLayout()
        
        self.btn_open_saves = QPushButton("📁 Open Saves")
        self.btn_open_saves.clicked.connect(self._open_saves_folder)
        actions_bar.addWidget(self.btn_open_saves)
        
        self.btn_open_config = QPushButton("⚙️ Open Config")
        self.btn_open_config.clicked.connect(self._open_config_folder)
        actions_bar.addWidget(self.btn_open_config)
        
        self.btn_open_mods = QPushButton("📦 Open Mods Folder")
        self.btn_open_mods.clicked.connect(self._open_mods_folder)
        actions_bar.addWidget(self.btn_open_mods)
        
        actions_bar.addStretch()
        
        # Play button
        self.btn_play = QPushButton("🎮 Play RimWorld")
        self.btn_play.setStyleSheet("background-color: #2a6a2a; font-weight: bold; padding: 6px 16px;")
        self.btn_play.setToolTip("Launch RimWorld")
        self.btn_play.clicked.connect(self._launch_game)
        actions_bar.addWidget(self.btn_play)
        
        self.btn_workshop = QPushButton("🔧 Download Workshop Mods")
        self.btn_workshop.clicked.connect(self._show_workshop_dialog)
        actions_bar.addWidget(self.btn_workshop)
        
        main_layout.addLayout(actions_bar)
        
        # Main tab widget
        self.main_tabs = QTabWidget()
        
        # ===== TAB 1: Mod Manager =====
        mod_manager_tab = QWidget()
        mod_manager_layout = QVBoxLayout(mod_manager_tab)
        mod_manager_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main splitter with three panels
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Available mods
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("📦 Available Mods"))
        left_header.addStretch()
        self.available_count = QLabel("(0)")
        left_header.addWidget(self.available_count)
        left_layout.addLayout(left_header)
        
        # Search filter widget
        self.available_search_filter = ModSearchFilter()
        left_layout.addWidget(self.available_search_filter)
        
        self.available_list = DraggableModList(is_active_list=False)
        self.available_list.set_search_filter(self.available_search_filter)
        left_layout.addWidget(self.available_list)
        
        self.available_controls = ModListControls(is_active_list=False)
        left_layout.addWidget(self.available_controls)
        
        self.btn_manage_paths = QPushButton("📁 Manage Mod Paths...")
        self.btn_manage_paths.clicked.connect(self._show_paths_dialog)
        left_layout.addWidget(self.btn_manage_paths)
        
        self.main_splitter.addWidget(left_panel)
        
        # Center panel - Active mods (load order)
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        center_header = QHBoxLayout()
        center_header.addWidget(QLabel("✅ Active Mods (Load Order)"))
        center_header.addStretch()
        self.active_count = QLabel("(0)")
        center_header.addWidget(self.active_count)
        center_layout.addLayout(center_header)
        
        # Search filter for active mods
        self.active_search_filter = ModSearchFilter()
        center_layout.addWidget(self.active_search_filter)
        
        self.active_list = DraggableModList(is_active_list=True)
        self.active_list.set_search_filter(self.active_search_filter)
        center_layout.addWidget(self.active_list)
        
        self.active_controls = ModListControls(is_active_list=True)
        center_layout.addWidget(self.active_controls)
        
        # Warning panel
        self.conflict_warning = ConflictWarningWidget()
        center_layout.addWidget(self.conflict_warning)
        
        # Apply/save buttons
        apply_layout = QHBoxLayout()
        
        self.btn_apply = QPushButton("✓ Apply Load Order")
        self.btn_apply.setStyleSheet("background-color: #2a5a2a; font-weight: bold;")
        self.btn_apply.clicked.connect(self._apply_mods)
        apply_layout.addWidget(self.btn_apply)
        
        self.btn_save_list = QPushButton("💾 Save Modlist")
        self.btn_save_list.clicked.connect(self._save_modlist)
        apply_layout.addWidget(self.btn_save_list)
        
        self.btn_load_list = QPushButton("📂 Load Modlist")
        self.btn_load_list.clicked.connect(self._load_modlist)
        apply_layout.addWidget(self.btn_load_list)
        
        center_layout.addLayout(apply_layout)
        
        self.main_splitter.addWidget(center_panel)
        
        # Right panel - Mod details
        self.details_panel = ModDetailsPanel()
        self.main_splitter.addWidget(self.details_panel)
        
        # Set splitter sizes
        if self.config.config.splitter_sizes:
            self.main_splitter.setSizes(self.config.config.splitter_sizes)
        else:
            self.main_splitter.setSizes([300, 500, 250])
        
        mod_manager_layout.addWidget(self.main_splitter, 1)
        
        self.main_tabs.addTab(mod_manager_tab, "📦 Mod Manager")
        
        # ===== TAB 2: Workshop Browser =====
        self.workshop_tab = QWidget()
        workshop_layout = QVBoxLayout(self.workshop_tab)
        workshop_layout.setContentsMargins(0, 0, 0, 0)
        
        # Placeholder - will be populated when tab is first clicked (lazy loading)
        self.workshop_browser = None
        self._workshop_initialized = False
        self.workshop_placeholder = QLabel(
            "<h3>🔧 Workshop Browser</h3>"
            "<p>Click this tab to load the Steam Workshop browser.</p>"
            "<p><i>WebEngine is loaded on-demand to save memory.</i></p>"
        )
        self.workshop_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        workshop_layout.addWidget(self.workshop_placeholder)
        
        self.main_tabs.addTab(self.workshop_tab, "🔧 Workshop Browser")
        
        # Connect tab change signal for lazy loading
        self.main_tabs.currentChanged.connect(self._on_tab_changed)
        
        # ===== TAB 3: Download Manager with Live Logs =====
        self.download_tab = QWidget()
        download_layout = QVBoxLayout(self.download_tab)
        download_layout.setContentsMargins(4, 4, 4, 4)
        
        self.download_manager = DownloadLogWidget()
        self.download_manager.download_complete.connect(self._on_downloads_complete)
        download_layout.addWidget(self.download_manager)
        
        self.main_tabs.addTab(self.download_tab, "📥 Downloads")
        
        # ===== TAB 4: Profiles & Backups =====
        from ui.profiles_manager import ProfilesManagerWidget
        self.profiles_widget = ProfilesManagerWidget(self.config.config_dir)
        self.profiles_widget.profile_loaded.connect(self._on_profile_loaded)
        self.main_tabs.addTab(self.profiles_widget, "📋 Profiles")
        
        # ===== TAB 5: Tools (Update Checker, Conflict Resolver) =====
        from ui.tools_widgets import ToolsTabWidget
        self.tools_widget = ToolsTabWidget(self.mod_parser)
        self.tools_widget.update_mods.connect(self._start_workshop_download)
        self.tools_widget.auto_sort_requested.connect(self._auto_sort_mods)
        self.tools_widget.deactivate_mod.connect(self._deactivate_mod_by_id)
        self.main_tabs.addTab(self.tools_widget, "🔧 Tools")
        
        main_layout.addWidget(self.main_tabs, 1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Mod count labels in status bar
        self.status_total_label = QLabel("Total: 0")
        self.status_active_label = QLabel("Active: 0")
        self.status_inactive_label = QLabel("Inactive: 0")
        self.status_bar.addPermanentWidget(self.status_total_label)
        self.status_bar.addPermanentWidget(self.status_active_label)
        self.status_bar.addPermanentWidget(self.status_inactive_label)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.status_bar.showMessage("Ready")
    
    def _setup_menus(self):
        """Set up the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        save_action = QAction("Save Modlist...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_modlist)
        file_menu.addAction(save_action)
        
        load_action = QAction("Load Modlist...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_modlist)
        file_menu.addAction(load_action)
        
        import_action = QAction("Import from RimPy/RimSort...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self._import_modlist)
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        
        # Quick Download - paste URLs/IDs directly
        quick_download_action = QAction("⬇️ Quick Download...", self)
        quick_download_action.setShortcut("Ctrl+D")
        quick_download_action.triggered.connect(self._show_quick_download)
        file_menu.addAction(quick_download_action)
        
        file_menu.addSeparator()
        
        # Export modlist as text
        export_text_action = QAction("Export Modlist as Text...", self)
        export_text_action.setShortcut("Ctrl+Shift+E")
        export_text_action.triggered.connect(self._export_modlist_text)
        file_menu.addAction(export_text_action)
        
        file_menu.addSeparator()
        
        # Preset sharing
        export_preset_action = QAction("📤 Export as Shareable Code...", self)
        export_preset_action.setShortcut("Ctrl+Shift+C")
        export_preset_action.triggered.connect(self._export_preset_code)
        file_menu.addAction(export_preset_action)
        
        import_preset_action = QAction("📥 Import from Code...", self)
        import_preset_action.setShortcut("Ctrl+Shift+V")
        import_preset_action.triggered.connect(self._import_preset_code)
        file_menu.addAction(import_preset_action)
        
        file_menu.addSeparator()
        
        # Save/Export current config
        export_config_action = QAction("Export Config...", self)
        export_config_action.triggered.connect(self._export_config)
        file_menu.addAction(export_config_action)
        
        import_config_action = QAction("Import Config...", self)
        import_config_action.triggered.connect(self._import_config)
        file_menu.addAction(import_config_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        search_action = QAction("Search Mods", self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(self._focus_search)
        edit_menu.addAction(search_action)
        
        edit_menu.addSeparator()
        
        settings_action = QAction("Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        workshop_action = QAction("Download Workshop Mods...", self)
        workshop_action.triggered.connect(self._show_workshop_dialog)
        tools_menu.addAction(workshop_action)
        
        paths_action = QAction("Manage Mod Paths...", self)
        paths_action.triggered.connect(self._show_paths_dialog)
        tools_menu.addAction(paths_action)
        
        install_info_action = QAction("Installation Info...", self)
        install_info_action.triggered.connect(self._show_installation_info)
        tools_menu.addAction(install_info_action)
        
        tools_menu.addSeparator()
        
        rescan_action = QAction("Rescan Mods", self)
        rescan_action.setShortcut("F5")
        rescan_action.triggered.connect(self._scan_mods)
        tools_menu.addAction(rescan_action)
        
        tools_menu.addSeparator()
        
        auto_sort_action = QAction("Auto-Sort by Dependencies", self)
        auto_sort_action.setShortcut("Ctrl+Shift+S")
        auto_sort_action.triggered.connect(self._auto_sort_mods)
        tools_menu.addAction(auto_sort_action)
        
        apply_action = QAction("Apply Load Order", self)
        apply_action.setShortcut("Ctrl+Return")
        apply_action.triggered.connect(self._apply_mods)
        tools_menu.addAction(apply_action)
        
        tools_menu.addSeparator()
        
        graph_action = QAction("🔗 Dependency Graph...", self)
        graph_action.setShortcut("Ctrl+G")
        graph_action.triggered.connect(self._show_dependency_graph)
        tools_menu.addAction(graph_action)
        
        # Compatibility Database submenu
        compat_menu = tools_menu.addMenu("📚 Community Rules")
        
        download_rules_action = QAction("Download/Update Rules...", self)
        download_rules_action.triggered.connect(self._download_community_rules)
        compat_menu.addAction(download_rules_action)
        
        check_rules_action = QAction("Check Load Order...", self)
        check_rules_action.triggered.connect(self._check_community_rules)
        compat_menu.addAction(check_rules_action)
        
        sort_rules_action = QAction("Sort by Community Rules", self)
        sort_rules_action.triggered.connect(self._sort_by_community_rules)
        compat_menu.addAction(sort_rules_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        help_menu.addSeparator()
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts."""
        # Select all in focused list (Ctrl+A)
        select_all = QShortcut(QKeySequence("Ctrl+A"), self)
        select_all.activated.connect(self._shortcut_select_all)
        
        # Deselect all (Escape)
        deselect = QShortcut(QKeySequence("Escape"), self)
        deselect.activated.connect(self._shortcut_deselect)
        
        # Delete/Deactivate selected (Delete)
        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self._shortcut_delete)
        
        # Activate selected (Enter when in available list)
        enter_shortcut = QShortcut(QKeySequence("Return"), self)
        enter_shortcut.activated.connect(self._shortcut_activate)
        
        # Move up (Alt+Up)
        move_up = QShortcut(QKeySequence("Alt+Up"), self)
        move_up.activated.connect(self.active_list.move_selected_up)
        
        # Move down (Alt+Down)
        move_down = QShortcut(QKeySequence("Alt+Down"), self)
        move_down.activated.connect(self.active_list.move_selected_down)
        
        # Move to top (Alt+Home)
        move_top = QShortcut(QKeySequence("Alt+Home"), self)
        move_top.activated.connect(self.active_list.move_selected_to_top)
        
        # Move to bottom (Alt+End)
        move_bottom = QShortcut(QKeySequence("Alt+End"), self)
        move_bottom.activated.connect(self.active_list.move_selected_to_bottom)
    
    def _shortcut_select_all(self):
        """Select all items in the focused list."""
        if self.available_list.hasFocus():
            self.available_list.selectAll()
        elif self.active_list.hasFocus():
            self.active_list.selectAll()
    
    def _shortcut_deselect(self):
        """Deselect all items."""
        self.available_list.clearSelection()
        self.active_list.clearSelection()
    
    def _shortcut_delete(self):
        """Deactivate selected mods from active list."""
        if self.active_list.hasFocus() or self.active_list.selectedItems():
            self._deactivate_selected()
    
    def _shortcut_activate(self):
        """Activate selected mods from available list."""
        if self.available_list.hasFocus() or self.available_list.selectedItems():
            self._activate_selected()
    
    def _connect_signals(self):
        """Connect widget signals."""
        # List selection
        self.available_list.itemSelectionChanged.connect(self._on_available_selection)
        self.active_list.itemSelectionChanged.connect(self._on_active_selection)
        
        # Mod activation/deactivation
        self.available_list.mod_activated.connect(self._activate_mod)
        self.active_list.mod_deactivated.connect(self._deactivate_mod)
        
        # Uninstall selected mods
        self.available_list.uninstall_selected.connect(self._uninstall_selected_mods)
        self.active_list.uninstall_selected.connect(self._uninstall_selected_mods)
        
        # List controls
        self.available_controls.activate_all.connect(self._activate_all)
        self.active_controls.deactivate_all.connect(self._deactivate_all)
        self.active_controls.move_up.connect(self.active_list.move_selected_up)
        self.active_controls.move_down.connect(self.active_list.move_selected_down)
        self.active_controls.move_top.connect(self.active_list.move_selected_to_top)
        self.active_controls.move_bottom.connect(self.active_list.move_selected_to_bottom)
        self.active_controls.auto_sort.connect(self._auto_sort_mods)
        
        # Batch selection controls
        self.available_controls.select_all.connect(self.available_list.selectAll)
        self.available_controls.deselect_all.connect(self.available_list.clearSelection)
        self.available_controls.activate_selected.connect(self._activate_selected)
        self.active_controls.select_all.connect(self.active_list.selectAll)
        self.active_controls.deselect_all.connect(self.active_list.clearSelection)
        self.active_controls.deactivate_selected.connect(self._deactivate_selected)
        
        # List changes
        self.active_list.mods_changed.connect(self._check_conflicts)
        
        # Details panel actions
        self.details_panel.uninstall_requested.connect(self._uninstall_mod)
        self.details_panel.open_folder_requested.connect(self._open_mod_folder)
    
    def _on_tab_changed(self, index: int):
        """Handle tab change - lazy load Workshop browser."""
        # Workshop tab is index 1
        if index == 1 and not self._workshop_initialized:
            self._lazy_init_workshop_browser()
    
    def _lazy_init_workshop_browser(self):
        """Lazy initialize the Workshop browser (saves ~100-200MB RAM on startup)."""
        if self._workshop_initialized:
            return
        
        self._workshop_initialized = True
        self.status_bar.showMessage("Loading Workshop browser...")
        QApplication.processEvents()
        
        # Initialize the workshop browser
        self._init_workshop_browser()
        
        self.status_bar.showMessage("Workshop browser ready")
    
    def _initial_setup(self):
        """Perform initial setup after window is shown."""
        self._detect_installations()
        
        # Check for app updates in background
        QTimer.singleShot(2000, self._check_app_updates)
    
    def _check_app_updates(self):
        """Check for application updates from GitHub."""
        try:
            import urllib.request
            import json
            from main import __version__
            
            url = "https://api.github.com/repos/MrXploisLite/RimModManager/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'RimModManager'})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get('tag_name', '').lstrip('v')
                
                if latest_version and latest_version != __version__:
                    self.status_bar.showMessage(
                        f"🆕 Update available: v{latest_version} (current: v{__version__})"
                    )
        except Exception:
            pass  # Silently fail - not critical
    
    def _detect_installations(self):
        """Detect RimWorld installations."""
        self.status_bar.showMessage("Detecting RimWorld installations...")
        self.install_combo.clear()
        
        # Update custom paths from config
        self.game_detector.custom_paths = self.config.config.custom_game_paths
        
        # Detect all installations
        installations = self.game_detector.detect_all()
        
        # Also scan Wine prefixes
        self.game_detector.scan_wine_prefixes()
        
        installations = self.game_detector.installations
        
        if not installations:
            self.install_combo.addItem("No RimWorld installations found")
            self.status_bar.showMessage("No RimWorld installations detected")
            return
        
        # Populate combo box
        for install in installations:
            self.install_combo.addItem(install.display_name(), install)
        
        # Try to restore last selection
        last_path = self.config.config.last_installation
        if last_path:
            for i in range(self.install_combo.count()):
                install = self.install_combo.itemData(i)
                if install and str(install.path) == last_path:
                    self.install_combo.setCurrentIndex(i)
                    break
        
        self.status_bar.showMessage(f"Found {len(installations)} installation(s)")
    
    def _on_installation_changed(self, index: int):
        """Handle installation selection change."""
        install = self.install_combo.itemData(index)
        if isinstance(install, RimWorldInstallation):
            self.current_installation = install
            self.config.set("last_installation", str(install.path))
            
            # Check for config path override
            override_path = self.config.get_config_path_override(str(install.path))
            if override_path:
                install.config_path = Path(override_path)
                log.info(f"Using config path override: {override_path}")
            
            # Set up installer - for standalone games, we download directly to Mods folder
            # so no symlink/copy is needed. Just update ModsConfig.xml.
            mods_folder = self.game_detector.get_mods_folder(install)
            
            # For standalone/custom games, default download path to game's Mods folder
            # This simplifies everything - no copy/symlink needed!
            if install.install_type in (InstallationType.CUSTOM, InstallationType.STANDALONE, 
                                        InstallationType.PROTON_STANDALONE, InstallationType.GOG):
                # Set download path to game's Mods folder if not already set
                current_download_path = self.config.config.workshop_download_path
                if not current_download_path or not Path(current_download_path).exists():
                    self.config.config.workshop_download_path = str(mods_folder)
                    self.config.save()
                    log.info(f"Auto-set download path to game's Mods folder: {mods_folder}")
            
            # Use copy mode for Proton/Wine (Windows builds on Linux) - symlinks don't work
            # But if downloading directly to Mods folder, copy is not needed anyway
            use_copy = install.is_windows_build and install.proton_prefix is not None
            self.installer = ModInstaller(mods_folder, use_copy=use_copy)
            if use_copy:
                log.info(f"ModInstaller using copy mode for Proton/Wine compatibility")
            
            # Set up downloader - use game's Mods folder as default for standalone
            download_path = self.config.get_default_workshop_path()
            
            # If download path is game's Mods folder, log it
            if Path(download_path).resolve() == mods_folder.resolve():
                log.info(f"Downloading mods directly to game's Mods folder (no copy needed)")
            
            self.downloader = WorkshopDownloader(download_path)
            
            # Set up workshop browser
            self._setup_workshop_browser()
            
            # Set up profiles widget with config path and mod getter
            if install.config_path:
                self.profiles_widget.set_config_path(install.config_path)
            self.profiles_widget.set_current_mods_getter(self._get_active_mod_ids)
            
            # Set up tools widget with mod getter
            self.tools_widget.set_mods_getter(self._get_all_active_mods)
            
            # Scan mods
            self._scan_mods()
            
            # Check for updates on startup if enabled
            if self.config.config.check_updates_on_startup:
                QTimer.singleShot(2000, self._check_updates_on_startup)
    
    def _add_custom_installation(self):
        """Add a custom game installation path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select RimWorld Installation Folder",
            str(Path.home())
        )
        if path:
            install = self.game_detector.add_custom_path(path)
            if install:
                self.config.add_custom_game_path(path)
                
                # For Windows builds without detected config, ask for Proton prefix
                if install.is_windows_build and not install.config_path:
                    reply = QMessageBox.question(
                        self, "Proton/Wine Prefix",
                        "This appears to be a Windows build.\n\n"
                        "Would you like to specify a Proton/Wine prefix folder?\n"
                        "This is needed to find/save the game's config (ModsConfig.xml).\n\n"
                        "The prefix folder typically contains a 'drive_c' subfolder.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        prefix_path = QFileDialog.getExistingDirectory(
                            self, "Select Proton/Wine Prefix Folder",
                            str(Path.home() / ".local/share/Steam/steamapps/compatdata")
                        )
                        if prefix_path:
                            prefix = Path(prefix_path)
                            # If user selected a compatdata folder, look for pfx subfolder
                            if (prefix / "pfx").exists():
                                prefix = prefix / "pfx"
                            install.proton_prefix = prefix
                            # Re-detect config paths with the new prefix
                            self.game_detector._detect_save_config_paths(install)
                            if install.config_path:
                                log.debug(f"Config path found: {install.config_path}")
                            else:
                                log.debug(f"Config path still not found after setting prefix")
                
                self._detect_installations()
                # Select the new installation
                for i in range(self.install_combo.count()):
                    item_install = self.install_combo.itemData(i)
                    if item_install and str(item_install.path) == path:
                        self.install_combo.setCurrentIndex(i)
                        break
                
                # Show info about detected paths
                info_msg = f"Installation added: {path}\n\n"
                if install.config_path:
                    info_msg += f"✅ Config path: {install.config_path}\n"
                else:
                    info_msg += "⚠️ Config path not detected\n"
                if install.save_path:
                    info_msg += f"✅ Save path: {install.save_path}\n"
                else:
                    info_msg += "⚠️ Save path not detected\n"
                if install.proton_prefix:
                    info_msg += f"✅ Proton prefix: {install.proton_prefix}\n"
                
                if not install.config_path:
                    info_msg += (
                        "\n⚠️ Without a config path, ModsConfig.xml cannot be updated.\n"
                        "Run the game once to create the config folder, then re-add this installation."
                    )
                
                QMessageBox.information(self, "Installation Added", info_msg)
            else:
                QMessageBox.warning(
                    self, "Invalid Installation",
                    f"The selected folder does not appear to be a valid RimWorld installation:\n{path}"
                )
    
    def _scan_mods(self):
        """Scan all mod directories."""
        if not self.current_installation:
            return
        
        self.status_bar.showMessage("Scanning mods...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        
        # Clear current lists
        self.available_list.clear_mods()
        self.active_list.clear_mods()
        self.mod_parser.clear_cache()
        
        game_mods_path = self.current_installation.path / "Mods"
        download_path = Path(self.config.config.workshop_download_path) if self.config.config.workshop_download_path else None
        
        # Check if we're in "direct mode" (download to game's Mods folder)
        direct_mode = download_path and download_path.resolve() == game_mods_path.resolve()
        
        # Collect paths to scan
        paths_to_scan = []
        
        # 1. Game's Data folder (Core/DLCs) - always first
        data_path = self.current_installation.path / "Data"
        if data_path.exists():
            paths_to_scan.append(data_path)
        
        # 2. Game's Mods folder - primary source for mods
        if game_mods_path.exists():
            paths_to_scan.append(game_mods_path)
        
        # 3. If NOT in direct mode, also scan external sources
        if not direct_mode:
            # Workshop mods (Steam)
            workshop = self.game_detector.find_workshop_mods_path()
            if workshop and workshop.exists() and workshop.resolve() != game_mods_path.resolve():
                paths_to_scan.append(workshop)
            
            # User-defined mod paths
            for path_str in self.config.config.mod_source_paths:
                path = Path(path_str)
                if path.exists() and path.resolve() != game_mods_path.resolve():
                    if path not in paths_to_scan:
                        paths_to_scan.append(path)
        
        # Scan directories
        all_mods = []
        
        for path in paths_to_scan:
            # Determine source type
            if path.name == "Data":
                source = ModSource.GAME
            elif path.resolve() == game_mods_path.resolve():
                source = ModSource.LOCAL  # Mods in game folder
            elif "workshop" in str(path).lower():
                source = ModSource.WORKSHOP
            else:
                source = ModSource.LOCAL
            
            mods = self.mod_parser.scan_directory(path, source)
            all_mods.extend(mods)
        
        # Remove duplicates by package_id - FIRST occurrence wins
        seen = {}
        unique_mods = []
        for mod in all_mods:
            key = mod.package_id.lower()
            if key not in seen:
                seen[key] = mod
                unique_mods.append(mod)
        
        self.all_mods = unique_mods
        
        # Determine active mods - first try from saved config, then fall back to symlinks
        active_ids = set()
        saved_active_ids = []
        
        if self.current_installation:
            saved_active_ids = self.config.get_active_mods(str(self.current_installation.path))
        
        # Deduplicate saved_active_ids (case-insensitive, preserve order)
        if saved_active_ids:
            seen = set()
            deduped = []
            for pid in saved_active_ids:
                pid_lower = pid.lower()
                if pid_lower not in seen:
                    seen.add(pid_lower)
                    deduped.append(pid)
            saved_active_ids = deduped
            active_ids = seen
        elif self.installer:
            # Fall back to reading symlinks (for first run or migration)
            for target in self.installer.get_installed_mods():
                mod = self.mod_parser.get_mod_by_path(target)
                if mod:
                    active_ids.add(mod.package_id.lower())
        
        # Split into active/inactive
        self.active_mods = []
        self.inactive_mods = []
        
        # Build a map for ordering
        mod_by_id = {mod.package_id.lower(): mod for mod in self.all_mods}
        
        # If we have saved order, use it (already deduplicated)
        seen_active = set()
        if saved_active_ids:
            for pid in saved_active_ids:
                pid_lower = pid.lower()
                mod = mod_by_id.get(pid_lower)
                if mod and pid_lower not in seen_active:
                    seen_active.add(pid_lower)
                    mod.is_active = True
                    self.active_mods.append(mod)
        
        # Add any remaining mods
        for mod in self.all_mods:
            mod_lower = mod.package_id.lower()
            if mod_lower in active_ids:
                if mod_lower not in seen_active:
                    seen_active.add(mod_lower)
                    mod.is_active = True
                    self.active_mods.append(mod)
            else:
                mod.is_active = False
                self.inactive_mods.append(mod)
        
        # Sort inactive by name
        self.inactive_mods.sort(key=lambda m: m.display_name().lower())
        
        # Populate lists
        self.available_list.add_mods(self.inactive_mods)
        self.active_list.add_mods(self.active_mods)
        
        # Update counts
        self._update_counts()
        self._check_conflicts()
        
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Found {len(self.all_mods)} mods")
    
    def _update_counts(self):
        """Update mod count labels."""
        available = self.available_list.count()
        active = self.active_list.count()
        total = len(self.all_mods)
        
        self.available_count.setText(f"({available})")
        self.active_count.setText(f"({active})")
        
        # Update status bar counts
        self.status_total_label.setText(f"Total: {total}")
        self.status_active_label.setText(f"Active: {active}")
        self.status_inactive_label.setText(f"Inactive: {available}")
    
    def _filter_available_mods(self, text: str):
        """Legacy filter method - now handled by ModSearchFilter widget."""
        # Filtering is now handled by ModSearchFilter connected to DraggableModList
        pass
    
    def _focus_search(self):
        """Focus the search input box."""
        self.main_tabs.setCurrentIndex(0)  # Switch to Mod Manager tab
        self.available_search_filter.search_input.setFocus()
        self.available_search_filter.search_input.selectAll()
    
    def _on_available_selection(self):
        """Handle selection in available list."""
        selected = self.available_list.get_selected_mods()
        if selected:
            self.details_panel.show_mod(selected[0])
            # Don't call show_mod_info here - it causes freeze due to HTTP request
            # User can view Workshop info in the Tools tab manually
            self.active_list.clearSelection()
    
    def _on_active_selection(self):
        """Handle selection in active list."""
        selected = self.active_list.get_selected_mods()
        if selected:
            self.details_panel.show_mod(selected[0])
            # Don't call show_mod_info here - it causes freeze due to HTTP request
            self.available_list.clearSelection()
    
    def _activate_mod(self, mod: ModInfo):
        """Move a mod from available to active."""
        # Remove from available list
        item = self.available_list.find_mod(mod.package_id)
        if item:
            row = self.available_list.row(item)
            self.available_list.takeItem(row)
        
        # Add to active list
        mod.is_active = True
        self.active_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
    
    def _deactivate_mod(self, mod: ModInfo):
        """Move a mod from active to available."""
        # Remove from active list
        item = self.active_list.find_mod(mod.package_id)
        if item:
            row = self.active_list.row(item)
            self.active_list.takeItem(row)
        
        # Add to available list (sorted position)
        mod.is_active = False
        self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
    
    def _activate_all(self):
        """Activate all available mods."""
        mods = self.available_list.get_mods()
        self.available_list.clear_mods()
        for mod in mods:
            mod.is_active = True
            self.active_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
    
    def _activate_selected(self):
        """Activate selected mods from available list."""
        selected = self.available_list.get_selected_mods()
        if not selected:
            self.status_bar.showMessage("No mods selected")
            return
        
        for mod in selected:
            self.available_list.remove_mod(mod)
            mod.is_active = True
            self.active_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(f"Activated {len(selected)} mods")
    
    def _deactivate_all(self):
        """Deactivate all active mods."""
        mods = self.active_list.get_mods()
        self.active_list.clear_mods()
        for mod in mods:
            mod.is_active = False
            self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
    
    def _deactivate_selected(self):
        """Deactivate selected mods from active list."""
        selected = self.active_list.get_selected_mods()
        if not selected:
            self.status_bar.showMessage("No mods selected")
            return
        
        for mod in selected:
            self.active_list.remove_mod(mod)
            mod.is_active = False
            self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(f"Deactivated {len(selected)} mods")
    
    def _check_conflicts(self):
        """Check for conflicts in active mods."""
        active_mods = self.active_list.get_mods()
        
        conflicts = self.mod_parser.find_conflicts(active_mods)
        missing_deps = self.mod_parser.check_dependencies(active_mods)
        incompatibilities = self.mod_parser.check_incompatibilities(active_mods)
        
        self.conflict_warning.set_warnings(conflicts, missing_deps, incompatibilities)
    
    def _get_active_mod_ids(self) -> list[str]:
        """Get list of active mod package IDs in load order."""
        active_mods = self.active_list.get_mods()
        return [mod.package_id for mod in active_mods]
    
    def _get_all_active_mods(self) -> list:
        """Get list of active ModInfo objects."""
        return self.active_list.get_mods()
    
    def _check_updates_on_startup(self):
        """Check for mod updates on startup (if enabled)."""
        workshop_mods = [m for m in self.all_mods if m.steam_workshop_id]
        if not workshop_mods:
            return
        
        log.info(f"Checking updates for {len(workshop_mods)} Workshop mods on startup...")
        self.status_bar.showMessage(f"Checking for mod updates...")
        
        # Switch to Tools tab and trigger update check
        self.main_tabs.setCurrentIndex(4)  # Tools tab
        if hasattr(self.tools_widget, 'update_checker'):
            self.tools_widget.update_checker._check_updates()
    
    def _deactivate_mod_by_id(self, package_id: str):
        """Deactivate a mod by its package ID."""
        mods = self.active_list.get_mods()
        for mod in mods:
            if mod.package_id.lower() == package_id.lower():
                self._deactivate_mod(mod)
                self.status_bar.showMessage(f"Deactivated: {mod.display_name()}")
                return
        self.status_bar.showMessage(f"Mod not found: {package_id}")
    
    def _uninstall_mod(self, mod):
        """Uninstall (delete) a mod permanently."""
        from mod_parser import ModSource
        
        if not mod or not mod.path:
            return
        
        # Don't allow uninstalling core game mods
        if mod.source == ModSource.GAME:
            QMessageBox.warning(
                self, "Cannot Uninstall",
                "Cannot uninstall core game files."
            )
            return
        
        # Confirm deletion
        reply = QMessageBox.warning(
            self, "Uninstall Mod",
            f"Are you sure you want to permanently delete this mod?\n\n"
            f"Name: {mod.display_name()}\n"
            f"Path: {mod.path}\n\n"
            f"This action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Store package_id before any modifications
            mod_package_id = mod.package_id.lower()
            mod_name = mod.display_name()
            
            # First deactivate if active
            if mod.is_active:
                self._deactivate_mod(mod)
            
            # Remove from available list
            item = self.available_list.find_mod(mod.package_id)
            if item:
                row = self.available_list.row(item)
                self.available_list.takeItem(row)
            
            # Delete the mod folder
            if mod.path.exists():
                shutil.rmtree(mod.path)
            
            # Remove from all_mods list (create new list to avoid modification during iteration)
            self.all_mods = [m for m in self.all_mods if m.package_id.lower() != mod_package_id]
            
            # Clear details panel
            self.details_panel.clear()
            
            self._update_counts()
            self.status_bar.showMessage(f"Uninstalled: {mod_name}")
            
            QMessageBox.information(
                self, "Mod Uninstalled",
                f"Successfully uninstalled '{mod_name}'."
            )
            
        except PermissionError:
            QMessageBox.critical(
                self, "Uninstall Failed",
                f"Permission denied. Cannot delete:\n{mod.path}\n\n"
                "Try running the application with elevated permissions."
            )
        except (OSError, IOError) as e:
            QMessageBox.critical(
                self, "Uninstall Failed",
                f"Failed to uninstall mod:\n{e}"
            )
    
    def _uninstall_selected_mods(self, mods: list):
        """Uninstall multiple selected mods."""
        from mod_parser import ModSource
        
        if not mods:
            return
        
        # Filter out core game mods
        uninstallable = [m for m in mods if m.source != ModSource.GAME and m.path and m.path.exists()]
        skipped = len(mods) - len(uninstallable)
        
        if not uninstallable:
            QMessageBox.warning(
                self, "Cannot Uninstall",
                "None of the selected mods can be uninstalled.\n"
                "Core game files cannot be removed."
            )
            return
        
        # Build confirmation message
        mod_names = [m.display_name() for m in uninstallable[:10]]
        if len(uninstallable) > 10:
            mod_names.append(f"... and {len(uninstallable) - 10} more")
        
        msg = f"Are you sure you want to permanently delete {len(uninstallable)} mod(s)?\n\n"
        msg += "\n".join(f"• {name}" for name in mod_names)
        if skipped > 0:
            msg += f"\n\n({skipped} core game mod(s) will be skipped)"
        msg += "\n\nThis action cannot be undone!"
        
        reply = QMessageBox.warning(
            self, "Uninstall Mods",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Uninstall mods
        success_count = 0
        failed = []
        
        for mod in uninstallable:
            try:
                # Remove from active list if present
                self.active_list.remove_mod(mod)
                
                # Remove from available list
                self.available_list.remove_mod(mod)
                
                # Delete the folder
                if mod.path.exists():
                    shutil.rmtree(mod.path)
                
                # Remove from all_mods
                self.all_mods = [m for m in self.all_mods if m.package_id.lower() != mod.package_id.lower()]
                
                success_count += 1
                
            except (PermissionError, OSError, IOError) as e:
                failed.append((mod.display_name(), str(e)))
        
        self._update_counts()
        self._check_conflicts()
        
        # Show result
        if failed:
            failed_msg = "\n".join(f"• {name}: {err}" for name, err in failed[:5])
            if len(failed) > 5:
                failed_msg += f"\n... and {len(failed) - 5} more"
            QMessageBox.warning(
                self, "Uninstall Partially Failed",
                f"Successfully uninstalled {success_count} mod(s).\n"
                f"Failed to uninstall {len(failed)} mod(s):\n\n{failed_msg}"
            )
        else:
            self.status_bar.showMessage(f"Uninstalled {success_count} mod(s)")
            QMessageBox.information(
                self, "Mods Uninstalled",
                f"Successfully uninstalled {success_count} mod(s)."
            )
    
    def _open_mod_folder(self, mod):
        """Open the mod's folder in file manager."""
        if not mod or not mod.path:
            return
        
        if mod.path.exists():
            self._open_folder(mod.path)
        else:
            QMessageBox.warning(
                self, "Folder Not Found",
                f"Mod folder does not exist:\n{mod.path}"
            )
    
    def _on_profile_loaded(self, mod_ids: list[str]):
        """Handle profile/backup loaded - update mod lists."""
        if not mod_ids:
            return
        
        # Create auto-backup before loading profile
        current_ids = self._get_active_mod_ids()
        if current_ids:
            self.profiles_widget.create_auto_backup(current_ids, "Before loading profile")
        
        # Build mod lookup
        mod_by_id = {mod.package_id.lower(): mod for mod in self.all_mods}
        active_ids_set = set(pid.lower() for pid in mod_ids)
        
        # Clear current lists
        self.available_list.clear_mods()
        self.active_list.clear_mods()
        
        # Add active mods in profile order
        for pid in mod_ids:
            mod = mod_by_id.get(pid.lower())
            if mod:
                mod.is_active = True
                self.active_list.add_mod(mod)
        
        # Add remaining mods to available list
        for mod in self.all_mods:
            if mod.package_id.lower() not in active_ids_set:
                mod.is_active = False
                self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(f"Loaded profile with {len(mod_ids)} mods")
    
    def _auto_sort_mods(self):
        """Automatically sort active mods by dependencies."""
        active_mods = self.active_list.get_mods()
        
        if not active_mods:
            return
        
        self.status_bar.showMessage("Auto-sorting mods by dependencies...")
        
        # Use the mod parser's topological sort
        sorted_mods = self.mod_parser.sort_by_load_order(active_mods)
        
        # Clear and repopulate the active list
        self.active_list.clear_mods()
        for mod in sorted_mods:
            self.active_list.add_mod(mod)
        
        self._check_conflicts()
        self.status_bar.showMessage(f"Sorted {len(sorted_mods)} mods by load order")
    
    def _apply_mods(self):
        """Apply the current mod configuration to the game."""
        if not self.current_installation:
            QMessageBox.warning(self, "Error", "No installation selected")
            return
        
        active_mods = self.active_list.get_mods()
        
        # Create auto-backup before applying
        active_ids = [mod.package_id for mod in active_mods]
        self.profiles_widget.create_auto_backup(active_ids, "Before applying mods")
        
        # Check if we need to copy mods or if they're already in game's Mods folder
        game_mods_folder = self.current_installation.path / "Mods"
        download_path = Path(self.config.config.workshop_download_path) if self.config.config.workshop_download_path else None
        
        # If download path is game's Mods folder, no copy needed - just update ModsConfig.xml
        direct_mode = download_path and download_path.resolve() == game_mods_folder.resolve()
        
        mods_copied = 0
        mods_skipped = 0
        mods_failed = 0
        
        if not direct_mode and self.installer:
            # Traditional mode: copy/symlink mods from external folder to game's Mods folder
            self.status_bar.showMessage("Applying mod configuration...")
            
            # Get paths of active mods (exclude Core/DLC - they're already in Data folder)
            mod_paths = []
            skipped_mods = []
            for mod in active_mods:
                if mod.source == ModSource.GAME:
                    continue  # Skip Core/DLC
                if not mod.path:
                    skipped_mods.append(f"{mod.display_name()} (no path)")
                    continue
                if not mod.path.exists():
                    skipped_mods.append(f"{mod.display_name()} (path not found)")
                    continue
                mod_paths.append(mod.path)
            
            if skipped_mods:
                log.warning(f"Skipped mods without valid paths: {skipped_mods}")
            
            # Apply symlinks/copy
            results = self.installer.install_mods(mod_paths, clear_existing=True)
            
            mods_copied = sum(1 for v in results.values() if v)
            mods_failed = len(results) - mods_copied
            mods_skipped = len(skipped_mods)
            
            if mods_failed > 0:
                failed_paths = [str(p) for p, v in results.items() if not v]
                log.error(f"Failed to install mods: {failed_paths}")
        else:
            # Direct mode: mods are already in game's Mods folder, just update ModsConfig.xml
            self.status_bar.showMessage("Updating mod configuration...")
            log.info("Direct mode: mods already in game folder, just updating ModsConfig.xml")
        
        # Save active mods to config (by package_id in load order)
        config_written = False
        config_warning = ""
        
        if self.current_installation:
            self.config.save_active_mods(str(self.current_installation.path), active_ids)
            
            # Write to game's ModsConfig.xml
            if self.current_installation.config_path:
                from mod_parser import ModsConfigParser
                config_parser = ModsConfigParser()
                config_written = config_parser.write_mods_config(
                    self.current_installation.config_path, 
                    active_ids
                )
                if not config_written:
                    config_warning = (
                        f"Failed to write ModsConfig.xml to:\n"
                        f"{self.current_installation.config_path}\n\n"
                        "You may need to manually export via Profiles > Game Sync tab."
                    )
            else:
                config_warning = (
                    "Could not detect game's config folder.\n"
                    "ModsConfig.xml was NOT updated.\n\n"
                    "Please use Tools > Installation Info to set the config path."
                )
        
        # Show result
        if direct_mode:
            # Direct mode - simpler message
            if config_written:
                self.status_bar.showMessage(f"Mod configuration saved ({len(active_ids)} mods)")
                QMessageBox.information(
                    self, "Success",
                    f"Mod configuration updated!\n\n"
                    f"{len(active_ids)} mod(s) enabled in ModsConfig.xml.\n"
                    f"Mods are already in game folder - no copying needed."
                )
            elif config_warning:
                self.status_bar.showMessage("Config update failed")
                QMessageBox.warning(self, "Warning", config_warning)
        else:
            # Traditional mode - show copy results
            if mods_failed > 0 or mods_skipped > 0:
                self.status_bar.showMessage(f"Applied {mods_copied} mods, {mods_failed} failed, {mods_skipped} skipped")
                msg = f"Successfully linked {mods_copied} mods."
                if mods_failed > 0:
                    msg += f"\n{mods_failed} mods failed to link."
                if mods_skipped > 0:
                    msg += f"\n{mods_skipped} mods skipped (no valid path)."
                if config_warning:
                    msg += f"\n\n⚠️ {config_warning}"
                QMessageBox.warning(self, "Partial Success", msg)
            else:
                if config_written:
                    self.status_bar.showMessage(f"Applied {mods_copied} mods successfully")
                    QMessageBox.information(
                        self, "Success",
                        f"Successfully applied {mods_copied} mod(s) to the game.\n"
                        f"ModsConfig.xml has been updated."
                    )
                elif config_warning:
                    self.status_bar.showMessage(f"Applied {mods_copied} mods (config warning)")
                    QMessageBox.warning(
                        self, "Mods Linked",
                        f"Successfully linked {mods_copied} mod(s).\n\n⚠️ {config_warning}"
                    )
    
    def _save_modlist(self):
        """Save current mod list to file."""
        name, ok = QInputDialog.getText(
            self, "Save Modlist",
            "Enter a name for this modlist:"
        )
        if ok and name:
            active_mods = self.active_list.get_mods()
            mod_ids = [m.package_id for m in self.all_mods]
            active_ids = [m.package_id for m in active_mods]
            
            filepath = self.config.save_modlist(name, mod_ids, active_ids)
            self.status_bar.showMessage(f"Saved modlist to {filepath}")
    
    def _load_modlist(self):
        """Load a mod list from file."""
        modlists = self.config.list_modlists()
        
        if not modlists:
            # Open file dialog
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Load Modlist",
                str(self.config.modlists_dir),
                "JSON Files (*.json);;All Files (*)"
            )
            if not filepath:
                return
            filepath = Path(filepath)
        else:
            # Show selection dialog
            names = [p.stem for p in modlists]
            name, ok = QInputDialog.getItem(
                self, "Load Modlist",
                "Select a modlist:",
                names, 0, False
            )
            if not ok:
                return
            filepath = self.config.modlists_dir / f"{name}.json"
        
        data = self.config.load_modlist(filepath)
        if not data:
            QMessageBox.warning(self, "Error", "Failed to load modlist")
            return
        
        # Apply the modlist - preserve saved order
        active_ids_list = data.get("active_mods", [])
        active_ids_set = set(pid.lower() for pid in active_ids_list)
        
        # Build mod lookup
        mod_by_id = {mod.package_id.lower(): mod for mod in self.all_mods}
        
        # Reorganize mods
        self.available_list.clear_mods()
        self.active_list.clear_mods()
        
        # Add active mods in saved order
        for pid in active_ids_list:
            mod = mod_by_id.get(pid.lower())
            if mod:
                mod.is_active = True
                self.active_list.add_mod(mod)
        
        # Add remaining mods to available list
        for mod in self.all_mods:
            if mod.package_id.lower() not in active_ids_set:
                mod.is_active = False
                self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(f"Loaded modlist: {data.get('name', filepath.stem)}")
    
    def _import_modlist(self):
        """Import modlist from RimPy, RimSort, or other formats."""
        from mod_importer import ModImporter
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Modlist",
            str(Path.home()),
            "All Supported (*.json *.xml *.txt *.rml);;JSON Files (*.json);;XML Files (*.xml);;Text Files (*.txt *.rml);;All Files (*)"
        )
        if not filepath:
            return
        
        filepath = Path(filepath)
        importer = ModImporter()
        result = importer.import_file(filepath)
        
        if not result.success:
            error_msg = "\n".join(result.errors) if result.errors else "Unknown error"
            QMessageBox.warning(self, "Import Failed", f"Failed to import modlist:\n\n{error_msg}")
            return
        
        # Show import summary
        summary = f"<b>Format:</b> {result.format_detected.value}<br>"
        summary += f"<b>Package IDs:</b> {len(result.package_ids)}<br>"
        summary += f"<b>Workshop IDs:</b> {len(result.workshop_ids)}<br>"
        
        if result.warnings:
            summary += f"<br><b>Warnings:</b><br>"
            for w in result.warnings[:5]:
                summary += f"• {w}<br>"
            if len(result.warnings) > 5:
                summary += f"• ... and {len(result.warnings) - 5} more<br>"
        
        # Ask user how to apply
        msg = QMessageBox(self)
        msg.setWindowTitle("Import Modlist")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(f"Successfully parsed modlist from:<br><code>{filepath.name}</code><br><br>{summary}")
        msg.setInformativeText("How would you like to apply this modlist?")
        
        btn_replace = msg.addButton("Replace Current", QMessageBox.ButtonRole.AcceptRole)
        btn_merge = msg.addButton("Merge (Add Missing)", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        
        msg.exec()
        clicked = msg.clickedButton()
        
        if clicked == btn_replace:
            self._apply_imported_modlist(result, replace=True)
        elif clicked == btn_merge:
            self._apply_imported_modlist(result, replace=False)
        # Cancel does nothing
    
    def _apply_imported_modlist(self, result, replace: bool = True):
        """Apply imported modlist to current mod lists."""
        # Build mod lookup
        mod_by_id = {mod.package_id.lower(): mod for mod in self.all_mods}
        
        if replace:
            # Clear current active mods
            self.available_list.clear_mods()
            self.active_list.clear_mods()
            
            active_ids_set = set(pid.lower() for pid in result.package_ids)
            
            # Add active mods in imported order
            found_count = 0
            missing_ids = []
            for pid in result.package_ids:
                mod = mod_by_id.get(pid.lower())
                if mod:
                    mod.is_active = True
                    self.active_list.add_mod(mod)
                    found_count += 1
                else:
                    missing_ids.append(pid)
            
            # Add remaining mods to available list
            for mod in self.all_mods:
                if mod.package_id.lower() not in active_ids_set:
                    mod.is_active = False
                    self.available_list.add_mod(mod)
            
            status_msg = f"Imported {found_count} mods"
            if missing_ids:
                status_msg += f" ({len(missing_ids)} not found)"
                log.warning(f"Missing mods from import: {missing_ids[:10]}")
        else:
            # Merge - add missing mods to active list
            current_active = {mod.package_id.lower() for mod in self.active_list.get_all_mods()}
            added_count = 0
            
            for pid in result.package_ids:
                pid_lower = pid.lower()
                if pid_lower not in current_active:
                    mod = mod_by_id.get(pid_lower)
                    if mod:
                        # Remove from available, add to active
                        self.available_list.remove_mod(mod)
                        mod.is_active = True
                        self.active_list.add_mod(mod)
                        added_count += 1
            
            status_msg = f"Added {added_count} mods from import"
        
        # Handle workshop IDs - offer to download
        if result.workshop_ids:
            reply = QMessageBox.question(
                self, "Download Workshop Mods?",
                f"The imported modlist contains {len(result.workshop_ids)} Workshop IDs.\n\n"
                "Would you like to add them to the download queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Add to workshop browser queue if available
                if hasattr(self, 'workshop_browser') and self.workshop_browser:
                    for wid in result.workshop_ids:
                        self.workshop_browser.browser._add_to_queue(wid)
                    self.main_tabs.setCurrentIndex(1)  # Switch to Workshop tab
                    status_msg += f", {len(result.workshop_ids)} added to download queue"
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(status_msg)
    
    def _show_paths_dialog(self):
        """Show the paths management dialog."""
        dialog = PathsDialog(self.config, self)
        if dialog.exec():
            self._scan_mods()
    
    def _show_installation_info(self):
        """Show information about the current installation and allow setting Proton prefix."""
        if not self.current_installation:
            QMessageBox.warning(self, "No Installation", "No installation selected.")
            return
        
        install = self.current_installation
        
        # Check for config path override
        override_path = self.config.get_config_path_override(str(install.path))
        
        # Build info text
        info = f"<b>Installation Path:</b><br><code>{install.path}</code><br><br>"
        info += f"<b>Type:</b> {install.install_type.value}<br>"
        info += f"<b>Windows Build:</b> {'Yes' if install.is_windows_build else 'No'}<br><br>"
        
        if install.config_path:
            if override_path:
                info += f"<b>Config Path:</b> ✅ (Override)<br><code>{install.config_path}</code><br><br>"
            else:
                info += f"<b>Config Path:</b> ✅<br><code>{install.config_path}</code><br><br>"
        else:
            info += "<b>Config Path:</b> ⚠️ Not detected<br><br>"
        
        if install.save_path:
            info += f"<b>Save Path:</b> ✅<br><code>{install.save_path}</code><br><br>"
        else:
            info += "<b>Save Path:</b> ⚠️ Not detected<br><br>"
        
        if install.proton_prefix:
            info += f"<b>Proton/Wine Prefix:</b> ✅<br><code>{install.proton_prefix}</code><br><br>"
        elif install.is_windows_build:
            info += "<b>Proton/Wine Prefix:</b> ⚠️ Not set<br><br>"
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Installation Info")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(info)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info_label)
        
        # Buttons for setting paths
        btn_layout = QVBoxLayout()
        
        # Set Config Path Override button (always show for troubleshooting)
        btn_set_config = QPushButton("📁 Set Config Path Override...")
        btn_set_config.setToolTip(
            "Manually set where ModsConfig.xml should be written.\n"
            "Use this if auto-detection finds the wrong path."
        )
        def set_config_override():
            start_path = str(install.config_path) if install.config_path else str(Path.home())
            
            config_path = QFileDialog.getExistingDirectory(
                dialog, "Select Config Folder (contains ModsConfig.xml)", start_path
            )
            if config_path:
                self.config.set_config_path_override(str(install.path), config_path)
                install.config_path = Path(config_path)
                # Update profiles widget
                self.profiles_widget.set_config_path(install.config_path)
                dialog.accept()
                QMessageBox.information(
                    self, "Config Path Set",
                    f"Config path override saved:\n{config_path}\n\n"
                    "ModsConfig.xml will now be written to this location."
                )
                # Show updated info
                self._show_installation_info()
        
        btn_set_config.clicked.connect(set_config_override)
        btn_layout.addWidget(btn_set_config)
        
        # Clear override button if one exists
        if override_path:
            btn_clear_override = QPushButton("🗑️ Clear Config Path Override")
            def clear_override():
                self.config.set_config_path_override(str(install.path), "")
                # Re-detect paths
                self.game_detector._detect_save_config_paths(install)
                if install.config_path:
                    self.profiles_widget.set_config_path(install.config_path)
                dialog.accept()
                self._show_installation_info()
            btn_clear_override.clicked.connect(clear_override)
            btn_layout.addWidget(btn_clear_override)
        
        # Add button to set Proton prefix for Windows builds
        if install.is_windows_build:
            btn_set_prefix = QPushButton("🍷 Set Proton/Wine Prefix...")
            def set_prefix():
                start_path = str(Path.home() / ".local/share/Steam/steamapps/compatdata")
                if install.proton_prefix:
                    start_path = str(install.proton_prefix.parent)
                
                prefix_path = QFileDialog.getExistingDirectory(
                    dialog, "Select Proton/Wine Prefix Folder", start_path
                )
                if prefix_path:
                    prefix = Path(prefix_path)
                    # If user selected a compatdata folder, look for pfx subfolder
                    if (prefix / "pfx").exists():
                        prefix = prefix / "pfx"
                    install.proton_prefix = prefix
                    # Re-detect config paths
                    self.game_detector._detect_save_config_paths(install)
                    # Update profiles widget
                    if install.config_path:
                        self.profiles_widget.set_config_path(install.config_path)
                    dialog.accept()
                    # Show updated info
                    self._show_installation_info()
            
            btn_set_prefix.clicked.connect(set_prefix)
            btn_layout.addWidget(btn_set_prefix)
        
        layout.addLayout(btn_layout)
        
        # Warning if no config path
        if not install.config_path:
            warning = QLabel(
                "<br><b style='color: orange;'>⚠️ Warning:</b> Without a config path, "
                "ModsConfig.xml cannot be updated and the game won't load your mods.<br><br>"
                "<b>Solution:</b> Click 'Set Config Path Override' above and select the folder "
                "containing your game's ModsConfig.xml file.<br><br>"
                "Common locations:<br>"
                "• Proton: ~/.local/share/Steam/steamapps/compatdata/[APPID]/pfx/drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config<br>"
                "• Wine: ~/.wine/drive_c/users/[USER]/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config"
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("font-size: 11px;")
            layout.addWidget(warning)
        
        # Tip for Wine/Proton users about mod disabling
        if install.is_windows_build:
            tip = QLabel(
                "<br><b style='color: #74c0fc;'>💡 Tip:</b> If mods become disabled when you close "
                "this app while the game is running, RimWorld's built-in 'disable mods on crash' "
                "feature may be triggering.<br><br>"
                "<b>Fix:</b> In RimWorld, go to <b>Options → General</b> and enable "
                "<b>Development Mode</b>. This disables the auto-disable feature."
            )
            tip.setWordWrap(True)
            tip.setStyleSheet("font-size: 11px;")
            layout.addWidget(tip)
        
        layout.addStretch()
        
        # Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        
        dialog.exec()
    
    def _show_dependency_graph(self):
        """Show the mod dependency/conflict graph visualization."""
        from ui.graph_view import ConflictGraphDialog
        
        # Get all mods (both active and available)
        all_mods = self.all_mods
        
        if not all_mods:
            QMessageBox.information(
                self, "No Mods",
                "No mods loaded. Scan mods first."
            )
            return
        
        dialog = ConflictGraphDialog(all_mods, self)
        dialog.mod_selected.connect(self._select_mod_by_id)
        dialog.exec()
    
    def _select_mod_by_id(self, mod_id: str):
        """Select a mod in the lists by its package ID."""
        # Try to find in active list first
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            mod = item.data(Qt.ItemDataRole.UserRole)
            if mod and mod.package_id.lower() == mod_id.lower():
                self.active_list.setCurrentItem(item)
                self._on_mod_selected(item)
                return
        
        # Try available list
        for i in range(self.available_list.count()):
            item = self.available_list.item(i)
            mod = item.data(Qt.ItemDataRole.UserRole)
            if mod and mod.package_id.lower() == mod_id.lower():
                self.available_list.setCurrentItem(item)
                self._on_mod_selected(item)
                return
    
    def _get_compatibility_db(self):
        """Get or create compatibility database instance."""
        if not hasattr(self, '_compat_db'):
            from compatibility_db import CompatibilityDatabase
            self._compat_db = CompatibilityDatabase(self.config.config_dir)
        return self._compat_db
    
    def _download_community_rules(self):
        """Download/update community rules database."""
        db = self._get_compatibility_db()
        
        self.status_bar.showMessage("Downloading community rules...")
        QApplication.processEvents()
        
        if db.download():
            stats = db.get_stats()
            QMessageBox.information(
                self, "Success",
                f"Downloaded {stats['rule_count']} community rules!\n\n"
                f"Use 'Check Load Order' to find issues or\n"
                f"'Sort by Community Rules' to auto-sort."
            )
            self.status_bar.showMessage(f"Community rules: {stats['rule_count']} rules loaded")
        else:
            # Try loading from cache
            if db.load_from_cache():
                QMessageBox.warning(
                    self, "Network Error",
                    f"Failed to download fresh rules.\n"
                    f"Using cached version ({db.rule_count} rules)."
                )
            else:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to download community rules.\n"
                    "Check your internet connection."
                )
    
    def _check_community_rules(self):
        """Check current load order against community rules."""
        db = self._get_compatibility_db()
        
        # Ensure rules are loaded
        if not db.is_loaded:
            if db.is_cache_valid():
                db.load_from_cache()
            else:
                reply = QMessageBox.question(
                    self, "Download Rules?",
                    "Community rules not loaded.\nDownload now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    if not db.download():
                        QMessageBox.critical(self, "Error", "Failed to download rules.")
                        return
                else:
                    return
        
        # Get current active mod order
        active_mods = self.active_list.get_mods()
        if not active_mods:
            QMessageBox.information(self, "No Mods", "No active mods to check.")
            return
        
        mod_order = [m.package_id for m in active_mods]
        issues = db.get_load_order_issues(mod_order)
        
        if not issues:
            QMessageBox.information(
                self, "All Good! ✅",
                f"No load order issues found!\n\n"
                f"Checked {len(mod_order)} mods against {db.rule_count} rules."
            )
            return
        
        # Show issues dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"⚠️ Load Order Issues ({len(issues)})")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel(f"Found {len(issues)} potential issues:"))
        
        issues_list = QListWidget()
        for issue in issues:
            icon = "🔴" if issue["severity"] == "error" else "🟡"
            issues_list.addItem(f"{icon} {issue['message']}")
        layout.addWidget(issues_list, 1)
        
        btn_layout = QHBoxLayout()
        btn_auto_fix = QPushButton("Auto-Sort by Rules")
        btn_auto_fix.clicked.connect(lambda: (dialog.accept(), self._sort_by_community_rules()))
        btn_layout.addWidget(btn_auto_fix)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _sort_by_community_rules(self):
        """Sort active mods using community rules."""
        db = self._get_compatibility_db()
        
        # Ensure rules are loaded
        if not db.is_loaded:
            if db.is_cache_valid():
                db.load_from_cache()
            elif not db.download():
                QMessageBox.critical(self, "Error", "Failed to load community rules.")
                return
        
        active_mods = self.active_list.get_mods()
        if not active_mods:
            QMessageBox.information(self, "No Mods", "No active mods to sort.")
            return
        
        # Get current order
        mod_ids = [m.package_id for m in active_mods]
        
        # Get suggested order
        sorted_ids = db.suggest_sort_order(mod_ids)
        
        # Build lookup
        mod_by_id = {m.package_id.lower(): m for m in active_mods}
        
        # Reorder
        sorted_mods = []
        for pid in sorted_ids:
            mod = mod_by_id.get(pid.lower())
            if mod:
                sorted_mods.append(mod)
        
        # Update list
        self.active_list.clear()
        for mod in sorted_mods:
            self.active_list.add_mod(mod)
        
        self.status_bar.showMessage(f"Sorted {len(sorted_mods)} mods by community rules")
        QMessageBox.information(
            self, "Sorted! ✅",
            f"Sorted {len(sorted_mods)} mods using community rules.\n\n"
            f"Review the order and click 'Apply' when ready."
        )
    
    def _setup_workshop_browser(self):
        """Set up the Workshop browser tab - only updates if already initialized (lazy loading)."""
        if not self.downloader:
            return
        
        # If workshop browser not yet initialized (lazy loading), just return
        # It will be initialized when user clicks the Workshop tab
        if not self._workshop_initialized:
            return
        
        # Update downloaded IDs for existing browser
        self._init_workshop_browser()
    
    def _init_workshop_browser(self):
        """Initialize or reinitialize the Workshop browser."""
        if not self.downloader:
            return
        
        # Get already downloaded mod IDs
        downloaded_ids = set()
        workshop_path = self.config.get_default_workshop_path()
        if workshop_path.exists():
            for item in workshop_path.iterdir():
                if item.is_dir() and item.name.isdigit():
                    downloaded_ids.add(item.name)
        
        # Remove placeholder if exists
        if self.workshop_placeholder:
            self.workshop_placeholder.setParent(None)
            self.workshop_placeholder = None
        
        # Remove old browser if exists
        if self.workshop_browser:
            self.workshop_browser.setParent(None)
        
        # Check if WebEngine is disabled in settings (saves ~150MB RAM)
        disable_webengine = self.config.config.disable_webengine
        
        # Create new workshop browser (pass disable flag)
        self.workshop_browser = WorkshopBrowser(
            downloaded_ids, 
            parent=self.workshop_tab,
            disable_webengine=disable_webengine
        )
        self.workshop_browser.download_requested.connect(self._start_workshop_download)
        
        # Add to tab layout
        layout = self.workshop_tab.layout()
        layout.addWidget(self.workshop_browser)
    
    def _show_quick_download(self):
        """Show quick download dialog for pasting URLs/IDs directly."""
        dialog = QuickDownloadDialog(self)
        dialog.download_requested.connect(self._start_workshop_download)
        dialog.exec()
    
    def _show_workshop_dialog(self):
        """Show the workshop download dialog - now switches to Workshop tab."""
        # Switch to Workshop tab
        self.main_tabs.setCurrentIndex(1)
        
        # Focus the URL input if browser is available
        if self.workshop_browser:
            self.workshop_browser.url_input.setFocus()
    
    def _start_workshop_download(self, workshop_ids: list[str]):
        """Start downloading workshop mods with live logging."""
        if not workshop_ids:
            return
        
        # Check SteamCMD availability
        steamcmd_path = SteamCMDChecker.find_steamcmd()
        if not steamcmd_path:
            QMessageBox.warning(
                self, "SteamCMD Not Found",
                f"SteamCMD is required to download mods.\n\n"
                f"Install with:\n{SteamCMDChecker.get_install_command()}"
            )
            return
        
        # Switch to Downloads tab
        self.main_tabs.setCurrentIndex(2)
        
        # Get download path
        download_path = self.config.get_default_workshop_path()
        
        # Start downloads with live logging
        self.download_manager.start_downloads(steamcmd_path, workshop_ids, download_path)
        self.status_bar.showMessage(f"Downloading {len(workshop_ids)} mod(s)...")
    
    def _on_downloads_complete(self, download_path: str):
        """Handle all downloads complete - auto refresh mods and add path."""
        self.status_bar.showMessage("Downloads complete! Refreshing mod list...")
        
        # Auto-add download path to mod source paths if not already there
        if download_path and download_path not in self.config.config.mod_source_paths:
            self.config.add_mod_source_path(download_path)
            self.status_bar.showMessage(f"Added {download_path} to mod sources")
        
        # Auto-refresh the mod list
        self._scan_mods()
        
        # Update workshop browser - refresh downloaded IDs from disk and clear completed
        if self.workshop_browser:
            download_path_obj = self.config.get_default_workshop_path()
            self.workshop_browser.refresh_downloaded_ids(download_path_obj)
            self.workshop_browser.clear_completed()
        
        # Switch to Mod Manager tab to show new mods
        self.main_tabs.setCurrentIndex(0)
        self.status_bar.showMessage("Mod list refreshed with newly downloaded mods!")
    

    
    def _open_saves_folder(self):
        """Open the saves folder in file manager."""
        if self.current_installation and self.current_installation.save_path:
            path = self.current_installation.save_path
            if path.exists():
                self._open_folder(path)
            else:
                QMessageBox.information(self, "Info", f"Save folder not found:\n{path}")
        else:
            QMessageBox.information(self, "Info", "Save path not detected for this installation.")
    
    def _open_config_folder(self):
        """Open the config folder in file manager."""
        if self.current_installation and self.current_installation.config_path:
            path = self.current_installation.config_path
            if path.exists():
                self._open_folder(path)
            else:
                QMessageBox.information(self, "Info", f"Config folder not found:\n{path}")
        else:
            QMessageBox.information(self, "Info", "Config path not detected for this installation.")
    
    def _open_mods_folder(self):
        """Open the mods folder in file manager."""
        if self.current_installation:
            path = self.current_installation.path / "Mods"
            if path.exists():
                self._open_folder(path)
            else:
                path.mkdir(parents=True, exist_ok=True)
                self._open_folder(path)
    
    def _open_folder(self, path: Path):
        """Open a folder in the default file manager - cross-platform."""
        import platform
        system = platform.system().lower()
        
        try:
            if system == 'windows':
                os.startfile(str(path))
            elif system == 'darwin':  # macOS
                subprocess.run(["open", str(path)], check=False)
            else:  # Linux
                subprocess.run(["xdg-open", str(path)], check=False)
        except (OSError, FileNotFoundError, subprocess.SubprocessError) as e:
            QMessageBox.warning(self, "Error", f"Failed to open folder: {e}")
    
    def _launch_game(self):
        """Launch RimWorld with smart detection."""
        if not self.current_installation:
            QMessageBox.warning(self, "Error", "No installation selected")
            return
        
        # Show launch dialog with live log
        dialog = GameLaunchDialog(self.current_installation, self)
        dialog.exec()
    
    def _show_about(self):
        """Show about dialog."""
        from main import __version__
        QMessageBox.about(
            self,
            "About RimModManager",
            "<h2>RimModManager</h2>"
            "<p>A universal mod manager for RimWorld.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Cross-platform: Windows, macOS, Linux</li>"
            "<li>Drag-and-drop mod load order management</li>"
            "<li>Workshop downloads via SteamCMD (batch mode)</li>"
            "<li>Auto-sort mods by dependencies</li>"
            "<li>Mod profiles &amp; automatic backups</li>"
            "<li>Conflict detection &amp; resolution assistant</li>"
            "<li>Import/export from game's ModsConfig.xml</li>"
            "<li>Smart game launcher with Wine/Proton support</li>"
            "</ul>"
            "<p><b>Supported Installations:</b></p>"
            "<ul>"
            "<li>Steam (Native, Proton, Flatpak)</li>"
            "<li>GOG</li>"
            "<li>Standalone/Wine/Lutris/Bottles</li>"
            "</ul>"
            f"<p>Version {__version__}</p>"
        )
    
    def _show_shortcuts(self):
        """Show keyboard shortcuts dialog."""
        shortcuts_text = """
<h3>Keyboard Shortcuts</h3>
<table style="border-collapse: collapse;">
<tr><th colspan="2" style="text-align:left; padding-top:10px;">File Operations</th></tr>
<tr><td><b>Ctrl+S</b></td><td>Save modlist</td></tr>
<tr><td><b>Ctrl+O</b></td><td>Load modlist</td></tr>
<tr><td><b>Ctrl+I</b></td><td>Import from RimPy/RimSort</td></tr>
<tr><td><b>Ctrl+D</b></td><td>Quick Download (paste URLs)</td></tr>
<tr><td><b>Ctrl+Shift+E</b></td><td>Export modlist as text</td></tr>
<tr><td><b>Ctrl+Shift+C</b></td><td>Export as shareable code</td></tr>
<tr><td><b>Ctrl+Shift+V</b></td><td>Import from code</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>Quit application</td></tr>

<tr><th colspan="2" style="text-align:left; padding-top:10px;">Selection</th></tr>
<tr><td><b>Ctrl+A</b></td><td>Select all in focused list</td></tr>
<tr><td><b>Escape</b></td><td>Deselect all</td></tr>
<tr><td><b>Return</b></td><td>Activate selected (available list)</td></tr>
<tr><td><b>Delete</b></td><td>Deactivate selected (active list)</td></tr>

<tr><th colspan="2" style="text-align:left; padding-top:10px;">Load Order</th></tr>
<tr><td><b>Alt+Up</b></td><td>Move selected up</td></tr>
<tr><td><b>Alt+Down</b></td><td>Move selected down</td></tr>
<tr><td><b>Alt+Home</b></td><td>Move to top</td></tr>
<tr><td><b>Alt+End</b></td><td>Move to bottom</td></tr>

<tr><th colspan="2" style="text-align:left; padding-top:10px;">Navigation</th></tr>
<tr><td><b>Ctrl+F</b></td><td>Focus search box</td></tr>
<tr><td><b>Ctrl+,</b></td><td>Open settings</td></tr>
<tr><td><b>F1</b></td><td>Show this help</td></tr>
<tr><td><b>F5</b></td><td>Rescan mods</td></tr>

<tr><th colspan="2" style="text-align:left; padding-top:10px;">Tools</th></tr>
<tr><td><b>Ctrl+Shift+S</b></td><td>Auto-sort by dependencies</td></tr>
<tr><td><b>Ctrl+Return</b></td><td>Apply load order</td></tr>
<tr><td><b>Ctrl+G</b></td><td>Show dependency graph</td></tr>
</table>

<p style="margin-top:15px; color:#888;">
<b>Tip:</b> Hover over mods to see ➕/➖ buttons for quick activation.
</p>
"""
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)
    
    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.status_bar.showMessage("Settings saved")
            # Refresh downloader with new settings
            if self.downloader:
                workshop_path = self.config.get_default_workshop_path()
                self.downloader.download_path = workshop_path
                if self.config.config.steamcmd_path:
                    self.downloader.steamcmd_path = self.config.config.steamcmd_path
    
    def _export_config(self):
        """Export current configuration to a file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Configuration",
            str(Path.home() / "rimmodmanager-config.json"),
            "JSON Files (*.json)"
        )
        if filepath:
            import json
            
            # Copy current config
            try:
                config_data = {
                    "last_installation": self.config.config.last_installation,
                    "mod_source_paths": self.config.config.mod_source_paths,
                    "custom_game_paths": self.config.config.custom_game_paths,
                    "workshop_download_path": self.config.config.workshop_download_path,
                    "steamcmd_path": self.config.config.steamcmd_path,
                }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2)
                
                self.status_bar.showMessage(f"Config exported to {filepath}")
                QMessageBox.information(self, "Export Successful", f"Configuration exported to:\n{filepath}")
            except (OSError, IOError, TypeError, ValueError) as e:
                QMessageBox.warning(self, "Export Failed", f"Failed to export config:\n{e}")
    
    def _export_modlist_text(self):
        """Export active modlist as shareable text."""
        active_mods = self.active_list.get_mods()
        
        if not active_mods:
            QMessageBox.information(self, "No Mods", "No active mods to export.")
            return
        
        # Build text content
        from main import __version__
        lines = [
            "# RimWorld Modlist",
            f"# Generated by RimModManager v{__version__}",
            f"# Total mods: {len(active_mods)}",
            "",
            "## Load Order:",
            ""
        ]
        
        for i, mod in enumerate(active_mods, 1):
            lines.append(f"{i:3}. {mod.display_name()} [{mod.package_id}]")
            if mod.steam_workshop_id:
                lines.append(f"     Workshop: https://steamcommunity.com/sharedfiles/filedetails/?id={mod.steam_workshop_id}")
        
        lines.extend([
            "",
            "## Workshop IDs (for batch download):",
            ""
        ])
        
        workshop_ids = [mod.steam_workshop_id for mod in active_mods if mod.steam_workshop_id]
        if workshop_ids:
            lines.extend(workshop_ids)
        else:
            lines.append("(No Workshop mods)")
        
        text_content = "\n".join(lines)
        
        # Ask user what to do
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Export Modlist")
        dialog.setText(f"Export {len(active_mods)} mods as text?")
        dialog.setInformativeText("Choose how to export:")
        
        save_btn = dialog.addButton("Save to File", QMessageBox.ButtonRole.AcceptRole)
        copy_btn = dialog.addButton("Copy to Clipboard", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        
        dialog.exec()
        
        clicked = dialog.clickedButton()
        
        if clicked == save_btn:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Save Modlist",
                str(Path.home() / "rimworld-modlist.txt"),
                "Text Files (*.txt);;Markdown Files (*.md)"
            )
            if filepath:
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(text_content)
                    self.status_bar.showMessage(f"Modlist exported to {filepath}")
                    QMessageBox.information(self, "Success", f"Modlist saved to:\n{filepath}")
                except (OSError, IOError) as e:
                    QMessageBox.warning(self, "Error", f"Failed to save file:\n{e}")
        
        elif clicked == copy_btn:
            clipboard = QApplication.clipboard()
            clipboard.setText(text_content)
            self.status_bar.showMessage("Modlist copied to clipboard!")
    
    def _export_preset_code(self):
        """Export active modlist as a shareable preset code."""
        from mod_presets import PresetEncoder
        
        active_mods = self.active_list.get_mods()
        
        if not active_mods:
            QMessageBox.information(self, "No Mods", "No active mods to export.")
            return
        
        # Get preset name
        name, ok = QInputDialog.getText(
            self, "Export Preset",
            "Enter a name for this preset:",
            text="My Modlist"
        )
        if not ok or not name:
            return
        
        # Build data
        package_ids = [mod.package_id for mod in active_mods]
        workshop_ids = [mod.steam_workshop_id for mod in active_mods if mod.steam_workshop_id]
        
        try:
            code = PresetEncoder.encode(
                package_ids=package_ids,
                name=name,
                workshop_ids=workshop_ids,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Error", f"Failed to create preset code:\n{e}")
            return
        
        # Show result dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("📤 Preset Code")
        dialog.setMinimumSize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        info = QLabel(f"<b>{name}</b><br>{len(package_ids)} mods, {len(workshop_ids)} Workshop IDs<br>Code length: {len(code)} characters")
        layout.addWidget(info)
        
        code_edit = QTextEdit()
        code_edit.setPlainText(code)
        code_edit.setReadOnly(True)
        code_edit.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(code_edit)
        
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(code, "Preset code copied!"))
        btn_layout.addWidget(copy_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _import_preset_code(self):
        """Import modlist from a shareable preset code."""
        from mod_presets import PresetEncoder
        
        # Get code from user
        dialog = QDialog(self)
        dialog.setWindowTitle("📥 Import Preset Code")
        dialog.setMinimumSize(500, 250)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Paste the preset code below:"))
        
        code_edit = QTextEdit()
        code_edit.setPlaceholderText("RMM:v1:...")
        code_edit.setStyleSheet("font-family: monospace;")
        layout.addWidget(code_edit)
        
        btn_layout = QHBoxLayout()
        
        import_btn = QPushButton("Import")
        cancel_btn = QPushButton("Cancel")
        
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        cancel_btn.clicked.connect(dialog.reject)
        
        result = {"code": None}
        
        def on_import():
            result["code"] = code_edit.toPlainText().strip()
            dialog.accept()
        
        import_btn.clicked.connect(on_import)
        
        if dialog.exec() != QDialog.DialogCode.Accepted or not result["code"]:
            return
        
        code = result["code"]
        
        # Decode preset
        preset = PresetEncoder.decode(code)
        if not preset:
            QMessageBox.warning(self, "Invalid Code", "Failed to decode preset code.\n\nMake sure you copied the entire code starting with 'RMM:'")
            return
        
        # Show summary and ask how to apply
        summary = f"<b>Name:</b> {preset.name}<br>"
        summary += f"<b>Mods:</b> {len(preset.package_ids)}<br>"
        summary += f"<b>Workshop IDs:</b> {len(preset.workshop_ids)}<br>"
        if preset.created_at:
            summary += f"<b>Created:</b> {preset.created_at}<br>"
        if preset.author:
            summary += f"<b>Author:</b> {preset.author}<br>"
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Import Preset")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(f"Preset decoded successfully!<br><br>{summary}")
        msg.setInformativeText("How would you like to apply this preset?")
        
        btn_replace = msg.addButton("Replace Current", QMessageBox.ButtonRole.AcceptRole)
        btn_merge = msg.addButton("Merge (Add Missing)", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        
        msg.exec()
        clicked = msg.clickedButton()
        
        if clicked == btn_replace:
            self._apply_preset(preset, replace=True)
        elif clicked == btn_merge:
            self._apply_preset(preset, replace=False)
    
    def _apply_preset(self, preset, replace: bool = True):
        """Apply a decoded preset to the mod lists."""
        # Build mod lookup
        mod_by_id = {mod.package_id.lower(): mod for mod in self.all_mods}
        
        if replace:
            self.available_list.clear_mods()
            self.active_list.clear_mods()
            
            active_ids_set = set(pid.lower() for pid in preset.package_ids)
            
            found_count = 0
            for pid in preset.package_ids:
                mod = mod_by_id.get(pid.lower())
                if mod:
                    mod.is_active = True
                    self.active_list.add_mod(mod)
                    found_count += 1
            
            for mod in self.all_mods:
                if mod.package_id.lower() not in active_ids_set:
                    mod.is_active = False
                    self.available_list.add_mod(mod)
            
            status_msg = f"Applied preset '{preset.name}': {found_count} mods"
        else:
            current_active = {mod.package_id.lower() for mod in self.active_list.get_all_mods()}
            added_count = 0
            
            for pid in preset.package_ids:
                pid_lower = pid.lower()
                if pid_lower not in current_active:
                    mod = mod_by_id.get(pid_lower)
                    if mod:
                        self.available_list.remove_mod(mod)
                        mod.is_active = True
                        self.active_list.add_mod(mod)
                        added_count += 1
            
            status_msg = f"Merged preset '{preset.name}': added {added_count} mods"
        
        # Handle workshop IDs
        if preset.workshop_ids:
            reply = QMessageBox.question(
                self, "Download Workshop Mods?",
                f"The preset contains {len(preset.workshop_ids)} Workshop IDs.\n\nAdd to download queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if hasattr(self, 'workshop_browser') and self.workshop_browser:
                    for wid in preset.workshop_ids:
                        self.workshop_browser.browser._add_to_queue(wid)
                    self.main_tabs.setCurrentIndex(1)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(status_msg)
    
    def _copy_to_clipboard(self, text: str, message: str = "Copied!"):
        """Copy text to clipboard and show status message."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_bar.showMessage(message)
    
    def _import_config(self):
        """Import configuration from a file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Configuration",
            str(Path.home()),
            "JSON Files (*.json)"
        )
        if filepath:
            import json
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Apply imported settings
                if "mod_source_paths" in config_data:
                    self.config.config.mod_source_paths = config_data["mod_source_paths"]
                if "custom_game_paths" in config_data:
                    self.config.config.custom_game_paths = config_data["custom_game_paths"]
                if "workshop_download_path" in config_data:
                    self.config.config.workshop_download_path = config_data["workshop_download_path"]
                if "steamcmd_path" in config_data:
                    self.config.config.steamcmd_path = config_data["steamcmd_path"]
                
                self.config.save()
                
                self.status_bar.showMessage("Config imported successfully")
                QMessageBox.information(
                    self, "Import Successful", 
                    "Configuration imported successfully.\n\nPlease restart the application for all changes to take effect."
                )
                
                # Refresh installations
                self._detect_installations()
                
            except (OSError, IOError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                QMessageBox.warning(self, "Import Failed", f"Failed to import config:\n{e}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Clean up download manager worker if still running
        if hasattr(self, 'download_manager') and self.download_manager:
            if self.download_manager.is_downloading():
                self.download_manager._cancel_downloads()
        
        # Save window geometry
        self.config.config.window_width = self.width()
        self.config.config.window_height = self.height()
        self.config.config.window_x = self.x()
        self.config.config.window_y = self.y()
        self.config.config.splitter_sizes = self.main_splitter.sizes()
        self.config.save()
        
        # Note: Game processes launched with start_new_session=True are fully
        # independent and will continue running after this app closes.
        # We do NOT modify ModsConfig.xml on close - that would break the game.
        
        event.accept()
        event.accept()
