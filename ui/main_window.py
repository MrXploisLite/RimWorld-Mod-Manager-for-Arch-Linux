"""
Main Window for RimWorld Mod Manager
The primary application window with all mod management features.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit,
    QGroupBox, QFrame, QTabWidget, QFileDialog, QMessageBox,
    QProgressBar, QStatusBar, QMenuBar, QMenu, QToolBar,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QInputDialog, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon

from config_handler import ConfigHandler
from game_detector import GameDetector, RimWorldInstallation, InstallationType
from mod_parser import ModParser, ModInfo, ModSource
from workshop_downloader import WorkshopDownloader, ModInstaller, DownloadTask, DownloadStatus
from ui.mod_widgets import (
    DraggableModList, ModDetailsPanel, ModListControls, ConflictWarningWidget
)
from ui.workshop_browser import WorkshopBrowser, WorkshopDownloadDialog
from ui.download_manager import DownloadLogWidget, SteamCMDChecker, LiveDownloadWorker


class ScanWorker(QThread):
    """Background worker for scanning mods."""
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)
    
    def __init__(self, paths: list[Path], parser: ModParser, source: ModSource = ModSource.LOCAL):
        super().__init__()
        self.paths = paths
        self.parser = parser
        self.source = source
    
    def run(self):
        all_mods = []
        for path in self.paths:
            self.progress.emit(f"Scanning {path.name}...")
            mods = self.parser.scan_directory(path, self.source)
            all_mods.extend(mods)
        self.finished.emit(all_mods)


class DownloadWorker(QThread):
    """Background worker for downloading workshop mods."""
    progress = pyqtSignal(DownloadTask)
    finished = pyqtSignal(DownloadTask)
    error = pyqtSignal(DownloadTask, str)
    
    def __init__(self, downloader: WorkshopDownloader, workshop_ids: list[str]):
        super().__init__()
        self.downloader = downloader
        self.workshop_ids = workshop_ids
    
    def run(self):
        for wid in self.workshop_ids:
            task = DownloadTask(workshop_id=wid)
            
            # Hook up signals
            def on_progress(t):
                self.progress.emit(t)
            
            self.downloader.on_progress = on_progress
            
            result = self.downloader.download_single(wid)
            
            if result:
                task.status = DownloadStatus.COMPLETE
                task.output_path = result
                self.finished.emit(task)
            else:
                task.status = DownloadStatus.FAILED
                self.error.emit(task, task.error_message or "Download failed")


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
        
        # Workers
        self.scan_worker: Optional[ScanWorker] = None
        self.download_worker: Optional[DownloadWorker] = None
        
        self._setup_ui()
        self._setup_menus()
        self._connect_signals()
        
        # Initial detection
        QTimer.singleShot(100, self._initial_setup)
    
    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("RimWorld Mod Manager")
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
        
        # Search filter
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search mods...")
        self.search_input.textChanged.connect(self._filter_available_mods)
        left_layout.addWidget(self.search_input)
        
        self.available_list = DraggableModList(is_active_list=False)
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
        
        self.active_list = DraggableModList(is_active_list=True)
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
        
        # Placeholder - will be populated when downloader is ready
        self.workshop_browser = None
        self.workshop_placeholder = QLabel(
            "<h3>Select a RimWorld installation first</h3>"
            "<p>The Workshop browser will be available after selecting an installation.</p>"
        )
        self.workshop_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        workshop_layout.addWidget(self.workshop_placeholder)
        
        self.main_tabs.addTab(self.workshop_tab, "🔧 Workshop Browser")
        
        # ===== TAB 3: Download Manager with Live Logs =====
        self.download_tab = QWidget()
        download_layout = QVBoxLayout(self.download_tab)
        download_layout.setContentsMargins(4, 4, 4, 4)
        
        self.download_manager = DownloadLogWidget()
        self.download_manager.download_complete.connect(self._on_downloads_complete)
        download_layout.addWidget(self.download_manager)
        
        self.main_tabs.addTab(self.download_tab, "📥 Downloads")
        
        main_layout.addWidget(self.main_tabs, 1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
    
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
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        workshop_action = QAction("Download Workshop Mods...", self)
        workshop_action.triggered.connect(self._show_workshop_dialog)
        tools_menu.addAction(workshop_action)
        
        paths_action = QAction("Manage Mod Paths...", self)
        paths_action.triggered.connect(self._show_paths_dialog)
        tools_menu.addAction(paths_action)
        
        tools_menu.addSeparator()
        
        rescan_action = QAction("Rescan Mods", self)
        rescan_action.setShortcut("F5")
        rescan_action.triggered.connect(self._scan_mods)
        tools_menu.addAction(rescan_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _connect_signals(self):
        """Connect widget signals."""
        # List selection
        self.available_list.itemSelectionChanged.connect(self._on_available_selection)
        self.active_list.itemSelectionChanged.connect(self._on_active_selection)
        
        # Mod activation/deactivation
        self.available_list.mod_activated.connect(self._activate_mod)
        self.active_list.mod_deactivated.connect(self._deactivate_mod)
        
        # List controls
        self.available_controls.activate_all.connect(self._activate_all)
        self.active_controls.deactivate_all.connect(self._deactivate_all)
        self.active_controls.move_up.connect(self.active_list.move_selected_up)
        self.active_controls.move_down.connect(self.active_list.move_selected_down)
        self.active_controls.move_top.connect(self.active_list.move_selected_to_top)
        self.active_controls.move_bottom.connect(self.active_list.move_selected_to_bottom)
        self.active_controls.auto_sort.connect(self._auto_sort_mods)
        
        # List changes
        self.active_list.mods_changed.connect(self._check_conflicts)
    
    def _initial_setup(self):
        """Perform initial setup after window is shown."""
        self._detect_installations()
    
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
            
            # Set up installer
            mods_folder = self.game_detector.get_mods_folder(install)
            self.installer = ModInstaller(mods_folder)
            
            # Set up downloader
            workshop_path = self.config.get_default_workshop_path()
            self.downloader = WorkshopDownloader(workshop_path)
            
            # Set up workshop browser
            self._setup_workshop_browser()
            
            # Scan mods
            self._scan_mods()
    
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
                self._detect_installations()
                # Select the new installation
                for i in range(self.install_combo.count()):
                    item_install = self.install_combo.itemData(i)
                    if item_install and str(item_install.path) == path:
                        self.install_combo.setCurrentIndex(i)
                        break
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
        
        # Collect paths to scan
        paths_to_scan = []
        
        # Game's Data folder (Core/DLCs)
        data_path = self.current_installation.path / "Data"
        if data_path.exists():
            paths_to_scan.append(data_path)
        
        # Game's Mods folder (get actual mod locations, not symlinks)
        mods_path = self.current_installation.path / "Mods"
        if mods_path.exists():
            for item in mods_path.iterdir():
                if item.is_symlink():
                    target = item.resolve()
                    if target.exists() and target not in paths_to_scan:
                        paths_to_scan.append(target)
                elif item.is_dir():
                    paths_to_scan.append(item)
        
        # Workshop mods
        workshop = self.game_detector.find_workshop_mods_path()
        if workshop and workshop.exists():
            paths_to_scan.append(workshop)
        
        # User-defined mod paths
        for path_str in self.config.config.mod_source_paths:
            path = Path(path_str)
            if path.exists() and path not in paths_to_scan:
                paths_to_scan.append(path)
        
        # Scan directories
        all_mods = []
        
        for path in paths_to_scan:
            # Determine source type
            if path.name == "Data":
                source = ModSource.GAME
                mods = self.mod_parser.scan_directory(path, source)
            elif "workshop" in str(path).lower():
                source = ModSource.WORKSHOP
                mods = self.mod_parser.scan_directory(path, source)
            elif path.parent == mods_path:
                # Individual mod in game's Mods folder
                mod = self.mod_parser.parse_mod(path)
                if mod and mod.is_valid:
                    mods = [mod]
                else:
                    mods = []
            else:
                source = ModSource.LOCAL
                mods = self.mod_parser.scan_directory(path, source)
            
            all_mods.extend(mods)
        
        # Remove duplicates by package_id
        seen = {}
        unique_mods = []
        for mod in all_mods:
            key = mod.package_id.lower()
            if key not in seen:
                seen[key] = mod
                unique_mods.append(mod)
        
        self.all_mods = unique_mods
        
        # Determine active mods (those symlinked in Mods folder)
        active_ids = set()
        if self.installer:
            for target in self.installer.get_installed_mods():
                mod = self.mod_parser.get_mod_by_path(target)
                if mod:
                    active_ids.add(mod.package_id.lower())
        
        # Split into active/inactive
        self.active_mods = []
        self.inactive_mods = []
        
        for mod in self.all_mods:
            if mod.package_id.lower() in active_ids:
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
        self.available_count.setText(f"({self.available_list.count()})")
        self.active_count.setText(f"({self.active_list.count()})")
    
    def _filter_available_mods(self, text: str):
        """Filter available mods by search text."""
        text = text.lower()
        for i in range(self.available_list.count()):
            item = self.available_list.item(i)
            if isinstance(item, DraggableModList):
                continue
            if hasattr(item, 'mod'):
                mod = item.mod
                visible = (
                    text in mod.display_name().lower() or
                    text in mod.package_id.lower() or
                    text in mod.author.lower()
                )
                item.setHidden(not visible)
    
    def _on_available_selection(self):
        """Handle selection in available list."""
        selected = self.available_list.get_selected_mods()
        if selected:
            self.details_panel.show_mod(selected[0])
            self.active_list.clearSelection()
    
    def _on_active_selection(self):
        """Handle selection in active list."""
        selected = self.active_list.get_selected_mods()
        if selected:
            self.details_panel.show_mod(selected[0])
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
    
    def _deactivate_all(self):
        """Deactivate all active mods."""
        mods = self.active_list.get_mods()
        self.active_list.clear_mods()
        for mod in mods:
            mod.is_active = False
            self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
    
    def _check_conflicts(self):
        """Check for conflicts in active mods."""
        active_mods = self.active_list.get_mods()
        
        conflicts = self.mod_parser.find_conflicts(active_mods)
        missing_deps = self.mod_parser.check_dependencies(active_mods)
        incompatibilities = self.mod_parser.check_incompatibilities(active_mods)
        
        self.conflict_warning.set_warnings(conflicts, missing_deps, incompatibilities)
    
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
        if not self.installer:
            QMessageBox.warning(self, "Error", "No installation selected")
            return
        
        active_mods = self.active_list.get_mods()
        
        # Get paths of active mods
        mod_paths = [mod.path for mod in active_mods if mod.path]
        
        # Apply
        self.status_bar.showMessage("Applying mod configuration...")
        
        results = self.installer.install_mods(mod_paths, clear_existing=True)
        
        success = sum(1 for v in results.values() if v)
        failed = len(results) - success
        
        if failed > 0:
            self.status_bar.showMessage(f"Applied {success} mods, {failed} failed")
            QMessageBox.warning(
                self, "Partial Success",
                f"Successfully linked {success} mods.\n{failed} mods failed to link."
            )
        else:
            self.status_bar.showMessage(f"Applied {success} mods successfully")
            QMessageBox.information(
                self, "Success",
                f"Successfully applied {success} mod(s) to the game."
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
        
        # Apply the modlist
        active_ids = set(pid.lower() for pid in data.get("active_mods", []))
        
        # Reorganize mods
        self.available_list.clear_mods()
        self.active_list.clear_mods()
        
        for mod in self.all_mods:
            if mod.package_id.lower() in active_ids:
                mod.is_active = True
                self.active_list.add_mod(mod)
            else:
                mod.is_active = False
                self.available_list.add_mod(mod)
        
        self._update_counts()
        self._check_conflicts()
        self.status_bar.showMessage(f"Loaded modlist: {data.get('name', filepath.stem)}")
    
    def _show_paths_dialog(self):
        """Show the paths management dialog."""
        dialog = PathsDialog(self.config, self)
        if dialog.exec():
            self._scan_mods()
    
    def _setup_workshop_browser(self):
        """Set up the Workshop browser tab."""
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
        
        # Create new workshop browser
        self.workshop_browser = WorkshopBrowser(downloaded_ids, self.workshop_tab)
        self.workshop_browser.download_requested.connect(self._start_workshop_download)
        
        # Add to tab layout
        layout = self.workshop_tab.layout()
        layout.addWidget(self.workshop_browser)
    
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
        
        # Update workshop browser downloaded IDs
        if self.workshop_browser:
            download_path_obj = self.config.get_default_workshop_path()
            if download_path_obj.exists():
                for item in download_path_obj.iterdir():
                    if item.is_dir() and item.name.isdigit():
                        self.workshop_browser.mark_downloaded(item.name)
        
        # Switch to Mod Manager tab to show new mods
        self.main_tabs.setCurrentIndex(0)
        self.status_bar.showMessage("Mod list refreshed with newly downloaded mods!")
    
    def _on_download_progress(self, task: DownloadTask):
        """Handle download progress update."""
        self.status_bar.showMessage(f"Downloading {task.workshop_id}: {task.status.value}")
    
    def _on_download_finished(self, task: DownloadTask):
        """Handle download completion."""
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        self.status_bar.showMessage(f"Downloaded mod {task.workshop_id}")
        
        # Update workshop browser
        if self.workshop_browser:
            self.workshop_browser.mark_downloaded(task.workshop_id)
        
        if self.progress_bar.value() >= self.progress_bar.maximum():
            self.progress_bar.setVisible(False)
            self._scan_mods()  # Rescan to pick up new mods
    
    def _on_download_error(self, task: DownloadTask, error: str):
        """Handle download error."""
        self.status_bar.showMessage(f"Download failed: {error}")
    
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
        """Open a folder in the default file manager."""
        try:
            subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open folder: {e}")
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About RimWorld Mod Manager",
            "<h2>RimWorld Mod Manager</h2>"
            "<p>A universal mod manager for RimWorld on Linux.</p>"
            "<p>Supports:</p>"
            "<ul>"
            "<li>Steam Native Linux</li>"
            "<li>Steam via Proton</li>"
            "<li>Flatpak Steam</li>"
            "<li>Standalone/Wine installations</li>"
            "</ul>"
            "<p>Version 1.0.0</p>"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Save window geometry
        self.config.config.window_width = self.width()
        self.config.config.window_height = self.height()
        self.config.config.window_x = self.x()
        self.config.config.window_y = self.y()
        self.config.config.splitter_sizes = self.main_splitter.sizes()
        self.config.save()
        
        event.accept()
