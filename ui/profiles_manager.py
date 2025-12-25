"""
Profiles Manager UI for RimModManager
Handles mod profiles, backups, and import/export from game.
"""

from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QLineEdit, QTextEdit, QGroupBox, QMessageBox, QInputDialog,
    QTabWidget, QFrame, QSplitter, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from mod_parser import ModProfile, ProfileManager, BackupManager, ModsConfigParser, ModBackup


class ProfileListItem(QListWidgetItem):
    """List item for a mod profile."""
    
    def __init__(self, profile: ModProfile):
        super().__init__()
        self.profile = profile
        self._update_display()
    
    def _update_display(self):
        mod_count = len(self.profile.active_mods)
        self.setText(f"📋 {self.profile.name} ({mod_count} mods)")
        
        # Tooltip with details
        tooltip = f"<b>{self.profile.name}</b><br>"
        if self.profile.description:
            tooltip += f"{self.profile.description}<br>"
        tooltip += f"Mods: {mod_count}<br>"
        tooltip += f"Created: {self.profile.created_at[:10] if self.profile.created_at else 'Unknown'}"
        self.setToolTip(tooltip)


class BackupListItem(QListWidgetItem):
    """List item for a backup."""
    
    def __init__(self, backup: ModBackup):
        super().__init__()
        self.backup = backup
        self._update_display()
    
    def _update_display(self):
        icon = "🔄" if self.backup.auto_backup else "💾"
        mod_count = len(self.backup.active_mods)
        
        # Format timestamp
        try:
            dt = datetime.strptime(self.backup.timestamp, "%Y%m%d_%H%M%S")
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            time_str = self.backup.timestamp
        
        self.setText(f"{icon} {self.backup.name} - {time_str} ({mod_count} mods)")
        
        tooltip = f"<b>{self.backup.name}</b><br>"
        if self.backup.description:
            tooltip += f"{self.backup.description}<br>"
        tooltip += f"Mods: {mod_count}<br>"
        tooltip += f"Auto-backup: {'Yes' if self.backup.auto_backup else 'No'}"
        self.setToolTip(tooltip)


class ProfileDialog(QDialog):
    """Dialog for creating/editing a profile."""
    
    def __init__(self, profile: ModProfile = None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle("Edit Profile" if profile else "New Profile")
        self.setMinimumSize(400, 300)
        self._setup_ui()
        
        if profile:
            self._load_profile()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Mod Profile")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Description
        layout.addWidget(QLabel("Description:"))
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Optional description for this profile...")
        self.desc_input.setMaximumHeight(100)
        layout.addWidget(self.desc_input)
        
        # Info
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #888;")
        layout.addWidget(self.info_label)
        
        layout.addStretch()
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_profile(self):
        self.name_input.setText(self.profile.name)
        self.desc_input.setPlainText(self.profile.description)
        self.info_label.setText(
            f"Created: {self.profile.created_at[:10] if self.profile.created_at else 'Unknown'}\n"
            f"Mods: {len(self.profile.active_mods)}"
        )
    
    def get_data(self) -> tuple[str, str]:
        """Return (name, description)."""
        return self.name_input.text().strip(), self.desc_input.toPlainText().strip()


class ProfilesTab(QWidget):
    """Tab widget for managing mod profiles."""
    
    # Signals
    profile_loaded = pyqtSignal(list)  # Emits list of package IDs to load
    profile_saved = pyqtSignal(str)    # Emits profile name
    
    def __init__(self, profiles_dir: Path, parent=None):
        super().__init__(parent)
        self.profile_manager = ProfileManager(profiles_dir)
        self._current_mods_getter: Optional[Callable[[], list[str]]] = None
        self._setup_ui()
        self._refresh_list()
    
    def set_current_mods_getter(self, getter: Callable[[], list[str]]):
        """Set function to get current active mod IDs."""
        self._current_mods_getter = getter
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("📋 Mod Profiles"))
        header.addStretch()
        
        self.btn_new = QPushButton("➕ New Profile")
        self.btn_new.clicked.connect(self._create_profile)
        header.addWidget(self.btn_new)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel("Save and switch between different mod configurations quickly.")
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Profile list
        self.profile_list = QListWidget()
        self.profile_list.itemDoubleClicked.connect(self._load_profile)
        layout.addWidget(self.profile_list, 1)
        
        # Actions
        actions = QHBoxLayout()
        
        self.btn_load = QPushButton("📂 Load")
        self.btn_load.setToolTip("Load selected profile")
        self.btn_load.clicked.connect(self._load_selected)
        actions.addWidget(self.btn_load)
        
        self.btn_save = QPushButton("💾 Save Current")
        self.btn_save.setToolTip("Save current mods to selected profile")
        self.btn_save.clicked.connect(self._save_to_selected)
        actions.addWidget(self.btn_save)
        
        self.btn_edit = QPushButton("✏️ Edit")
        self.btn_edit.clicked.connect(self._edit_profile)
        actions.addWidget(self.btn_edit)
        
        self.btn_duplicate = QPushButton("📋 Duplicate")
        self.btn_duplicate.clicked.connect(self._duplicate_profile)
        actions.addWidget(self.btn_duplicate)
        
        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.clicked.connect(self._delete_profile)
        actions.addWidget(self.btn_delete)
        
        layout.addLayout(actions)
    
    def _refresh_list(self):
        """Refresh the profile list."""
        self.profile_list.clear()
        for profile in self.profile_manager.list_profiles():
            item = ProfileListItem(profile)
            self.profile_list.addItem(item)
    
    def _get_selected_profile(self) -> Optional[ModProfile]:
        """Get currently selected profile."""
        item = self.profile_list.currentItem()
        if isinstance(item, ProfileListItem):
            return item.profile
        return None
    
    def _create_profile(self):
        """Create a new profile from current mods."""
        if not self._current_mods_getter:
            QMessageBox.warning(self, "Error", "Cannot get current mod list")
            return
        
        dialog = ProfileDialog(parent=self)
        if dialog.exec():
            name, desc = dialog.get_data()
            if not name:
                QMessageBox.warning(self, "Error", "Profile name is required")
                return
            
            current_mods = self._current_mods_getter()
            profile = self.profile_manager.create_profile(name, current_mods, desc)
            self._refresh_list()
            self.profile_saved.emit(name)
            QMessageBox.information(self, "Success", f"Profile '{name}' created with {len(current_mods)} mods")
    
    def _load_profile(self, item: QListWidgetItem = None):
        """Load a profile."""
        profile = self._get_selected_profile()
        if not profile:
            return
        
        reply = QMessageBox.question(
            self, "Load Profile",
            f"Load profile '{profile.name}'?\n\nThis will replace your current mod list with {len(profile.active_mods)} mods.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.profile_loaded.emit(profile.active_mods)
    
    def _load_selected(self):
        """Load the selected profile."""
        self._load_profile()
    
    def _save_to_selected(self):
        """Save current mods to selected profile."""
        profile = self._get_selected_profile()
        if not profile:
            QMessageBox.warning(self, "Error", "Select a profile first")
            return
        
        if not self._current_mods_getter:
            return
        
        reply = QMessageBox.question(
            self, "Update Profile",
            f"Update profile '{profile.name}' with current mod list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            profile.active_mods = self._current_mods_getter()
            self.profile_manager.save_profile(profile)
            self._refresh_list()
            self.profile_saved.emit(profile.name)
    
    def _edit_profile(self):
        """Edit selected profile."""
        profile = self._get_selected_profile()
        if not profile:
            return
        
        dialog = ProfileDialog(profile, self)
        if dialog.exec():
            name, desc = dialog.get_data()
            if name:
                # If name changed, delete old and create new
                if name != profile.name:
                    self.profile_manager.delete_profile(profile.name)
                    profile.name = name
                profile.description = desc
                self.profile_manager.save_profile(profile)
                self._refresh_list()
    
    def _duplicate_profile(self):
        """Duplicate selected profile."""
        profile = self._get_selected_profile()
        if not profile:
            return
        
        name, ok = QInputDialog.getText(
            self, "Duplicate Profile",
            "Name for the copy:",
            text=f"{profile.name} (copy)"
        )
        
        if ok and name:
            new_profile = self.profile_manager.duplicate_profile(profile.name, name)
            if new_profile:
                self._refresh_list()
    
    def _delete_profile(self):
        """Delete selected profile."""
        profile = self._get_selected_profile()
        if not profile:
            return
        
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{profile.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.profile_manager.delete_profile(profile.name)
            self._refresh_list()


class BackupsTab(QWidget):
    """Tab widget for managing backups."""
    
    backup_restored = pyqtSignal(list)  # Emits list of package IDs
    
    def __init__(self, backups_dir: Path, parent=None):
        super().__init__(parent)
        self.backup_manager = BackupManager(backups_dir)
        self._current_mods_getter: Optional[Callable[[], list[str]]] = None
        self._setup_ui()
        self._refresh_list()
    
    def set_current_mods_getter(self, getter: Callable[[], list[str]]):
        self._current_mods_getter = getter
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("💾 Backups"))
        header.addStretch()
        
        self.btn_backup = QPushButton("➕ Create Backup")
        self.btn_backup.clicked.connect(self._create_backup)
        header.addWidget(self.btn_backup)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel("Backups are created automatically before major changes. You can also create manual backups.")
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Backup list
        self.backup_list = QListWidget()
        self.backup_list.itemDoubleClicked.connect(self._restore_backup)
        layout.addWidget(self.backup_list, 1)
        
        # Actions
        actions = QHBoxLayout()
        
        self.btn_restore = QPushButton("🔄 Restore")
        self.btn_restore.clicked.connect(self._restore_selected)
        actions.addWidget(self.btn_restore)
        
        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.clicked.connect(self._delete_backup)
        actions.addWidget(self.btn_delete)
        
        actions.addStretch()
        layout.addLayout(actions)
    
    def _refresh_list(self):
        self.backup_list.clear()
        for backup in self.backup_manager.list_backups():
            item = BackupListItem(backup)
            self.backup_list.addItem(item)
    
    def _get_selected_backup(self) -> Optional[ModBackup]:
        item = self.backup_list.currentItem()
        if isinstance(item, BackupListItem):
            return item.backup
        return None
    
    def create_auto_backup(self, mods: list[str], description: str = ""):
        """Create an automatic backup (called before major changes)."""
        self.backup_manager.create_backup(mods, description=description, auto=True)
        self._refresh_list()
    
    def _create_backup(self):
        if not self._current_mods_getter:
            return
        
        name, ok = QInputDialog.getText(
            self, "Create Backup",
            "Backup name (optional):"
        )
        
        if ok:
            mods = self._current_mods_getter()
            self.backup_manager.create_backup(mods, name=name or "", description="Manual backup")
            self._refresh_list()
            QMessageBox.information(self, "Success", f"Backup created with {len(mods)} mods")
    
    def _restore_backup(self, item: QListWidgetItem = None):
        backup = self._get_selected_backup()
        if not backup:
            return
        
        reply = QMessageBox.question(
            self, "Restore Backup",
            f"Restore backup '{backup.name}'?\n\nThis will replace your current mod list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            mods = self.backup_manager.restore_backup(backup)
            self.backup_restored.emit(mods)
    
    def _restore_selected(self):
        self._restore_backup()
    
    def _delete_backup(self):
        backup = self._get_selected_backup()
        if not backup:
            return
        
        reply = QMessageBox.question(
            self, "Delete Backup",
            f"Delete backup '{backup.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.backup_manager.delete_backup(backup)
            self._refresh_list()


class ImportExportTab(QWidget):
    """Tab for importing/exporting from game's ModsConfig.xml."""
    
    mods_imported = pyqtSignal(list, str)  # (mod_ids, game_version)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_parser = ModsConfigParser()
        self._config_path: Optional[Path] = None
        self._current_mods_getter: Optional[Callable[[], list[str]]] = None
        self._setup_ui()
    
    def set_config_path(self, path: Path):
        """Set the game's config path."""
        self._config_path = path
        self._update_status()
    
    def set_current_mods_getter(self, getter: Callable[[], list[str]]):
        self._current_mods_getter = getter
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        layout.addWidget(QLabel("🔄 Import/Export from Game"))
        
        # Description
        desc = QLabel(
            "Sync your mod list with RimWorld's ModsConfig.xml.\n"
            "Import to load the game's current mod list, or export to apply your changes to the game."
        )
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Status
        self.status_frame = QFrame()
        self.status_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(self.status_frame)
        
        self.status_label = QLabel("Config path not set")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.game_info_label = QLabel("")
        self.game_info_label.setStyleSheet("color: #888;")
        status_layout.addWidget(self.game_info_label)
        
        layout.addWidget(self.status_frame)
        
        # Actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        # Import
        import_layout = QHBoxLayout()
        self.btn_import = QPushButton("📥 Import from Game")
        self.btn_import.setToolTip("Load mod list from RimWorld's ModsConfig.xml")
        self.btn_import.clicked.connect(self._import_from_game)
        import_layout.addWidget(self.btn_import)
        
        import_layout.addWidget(QLabel("Load the game's current mod configuration"))
        import_layout.addStretch()
        actions_layout.addLayout(import_layout)
        
        # Export
        export_layout = QHBoxLayout()
        self.btn_export = QPushButton("📤 Export to Game")
        self.btn_export.setToolTip("Write current mod list to RimWorld's ModsConfig.xml")
        self.btn_export.clicked.connect(self._export_to_game)
        export_layout.addWidget(self.btn_export)
        
        export_layout.addWidget(QLabel("Apply your mod list to the game"))
        export_layout.addStretch()
        actions_layout.addLayout(export_layout)
        
        layout.addWidget(actions_group)
        
        # Warning
        warning = QLabel(
            "⚠️ Exporting will modify the game's ModsConfig.xml file.\n"
            "A backup will be created automatically."
        )
        warning.setStyleSheet("color: #f90;")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        
        layout.addStretch()
    
    def _update_status(self):
        if not self._config_path:
            self.status_label.setText("❌ Config path not set")
            self.game_info_label.setText("Select a game installation first")
            self.btn_import.setEnabled(False)
            self.btn_export.setEnabled(False)
            return
        
        mods_config = self.config_parser.find_mods_config(self._config_path)
        if mods_config:
            active_mods, version, _ = self.config_parser.parse_mods_config(self._config_path)
            self.status_label.setText(f"✅ ModsConfig.xml found")
            self.game_info_label.setText(
                f"Path: {mods_config}\n"
                f"Game version: {version or 'Unknown'}\n"
                f"Active mods: {len(active_mods)}"
            )
            self.btn_import.setEnabled(True)
            self.btn_export.setEnabled(True)
        else:
            self.status_label.setText("❌ ModsConfig.xml not found")
            self.game_info_label.setText(f"Expected at: {self._config_path / 'ModsConfig.xml'}")
            self.btn_import.setEnabled(False)
            self.btn_export.setEnabled(True)  # Can still create new one
    
    def _import_from_game(self):
        if not self._config_path:
            return
        
        active_mods, version, _ = self.config_parser.parse_mods_config(self._config_path)
        
        if not active_mods:
            QMessageBox.warning(self, "Import Failed", "No mods found in ModsConfig.xml")
            return
        
        reply = QMessageBox.question(
            self, "Import from Game",
            f"Import {len(active_mods)} mods from the game?\n\n"
            f"Game version: {version or 'Unknown'}\n\n"
            "This will replace your current mod list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.mods_imported.emit(active_mods, version)
            QMessageBox.information(self, "Success", f"Imported {len(active_mods)} mods from game")
    
    def _export_to_game(self):
        if not self._config_path or not self._current_mods_getter:
            return
        
        current_mods = self._current_mods_getter()
        
        if not current_mods:
            QMessageBox.warning(self, "Export Failed", "No active mods to export")
            return
        
        reply = QMessageBox.question(
            self, "Export to Game",
            f"Export {len(current_mods)} mods to the game's ModsConfig.xml?\n\n"
            "A backup will be created automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success = self.config_parser.write_mods_config(self._config_path, current_mods)
            if success:
                QMessageBox.information(
                    self, "Success", 
                    f"Exported {len(current_mods)} mods to game.\n\n"
                    "The game will use this mod list on next launch."
                )
                self._update_status()
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to write ModsConfig.xml")


class ProfilesManagerWidget(QWidget):
    """Main widget combining profiles, backups, and import/export."""
    
    profile_loaded = pyqtSignal(list)
    
    def __init__(self, config_dir: Path, parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab widget
        self.tabs = QTabWidget()
        
        # Profiles tab
        self.profiles_tab = ProfilesTab(self.config_dir / "profiles")
        self.profiles_tab.profile_loaded.connect(self.profile_loaded.emit)
        self.tabs.addTab(self.profiles_tab, "📋 Profiles")
        
        # Backups tab
        self.backups_tab = BackupsTab(self.config_dir / "backups")
        self.backups_tab.backup_restored.connect(self.profile_loaded.emit)
        self.tabs.addTab(self.backups_tab, "💾 Backups")
        
        # Import/Export tab
        self.import_export_tab = ImportExportTab()
        self.import_export_tab.mods_imported.connect(lambda mods, ver: self.profile_loaded.emit(mods))
        self.tabs.addTab(self.import_export_tab, "🔄 Game Sync")
        
        layout.addWidget(self.tabs)
    
    def set_current_mods_getter(self, getter):
        """Set the function to get current active mod IDs."""
        self.profiles_tab.set_current_mods_getter(getter)
        self.backups_tab.set_current_mods_getter(getter)
        self.import_export_tab.set_current_mods_getter(getter)
    
    def set_config_path(self, path: Path):
        """Set the game's config path for import/export."""
        self.import_export_tab.set_config_path(path)
    
    def create_auto_backup(self, mods: list[str], description: str = ""):
        """Create an automatic backup."""
        self.backups_tab.create_auto_backup(mods, description)
