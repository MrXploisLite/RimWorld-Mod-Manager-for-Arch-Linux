"""
Tools Widgets for RimModManager
Update checker, conflict resolver, and enhanced mod info UI.
"""

from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QGroupBox, 
    QMessageBox, QProgressBar, QTabWidget, QFrame, 
    QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

from mod_parser import (
    ModInfo, ModUpdateChecker, ModUpdateInfo,
    EnhancedModInfoFetcher, EnhancedModInfo,
    ConflictResolver, ConflictInfo, ModParser
)


class UpdateCheckWorker(QThread):
    """Background worker for checking mod updates."""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(list)  # list of ModUpdateInfo
    error = pyqtSignal(str)
    
    def __init__(self, checker: ModUpdateChecker, mods: list):
        super().__init__()
        self.checker = checker
        self.mods = mods
        self._cancelled = False
    
    def cancel(self):
        """Cancel the update check."""
        self._cancelled = True
    
    def run(self):
        try:
            if not self._cancelled:
                results = self.checker.check_updates(self.mods)
                if not self._cancelled:
                    self.finished.emit(results)
        except (OSError, IOError, ValueError) as e:
            if not self._cancelled:
                self.error.emit(str(e))


class UpdateListItem(QListWidgetItem):
    """List item for mod update info."""
    
    def __init__(self, info: ModUpdateInfo):
        super().__init__()
        self.info = info
        self._update_display()
    
    def _update_display(self):
        if self.info.needs_update:
            icon = "🔄"
            color = QColor("#ffd43b")
        elif self.info.error:
            icon = "❓"
            color = QColor("#888888")
        else:
            icon = "✅"
            color = QColor("#69db7c")
        
        self.setText(f"{icon} {self.info.name}")
        self.setForeground(color)
        
        tooltip = f"<b>{self.info.name}</b><br>"
        tooltip += f"Workshop ID: {self.info.workshop_id}<br>"
        if self.info.local_updated:
            tooltip += f"Local: {self.info.local_updated[:10]}<br>"
        if self.info.workshop_updated:
            tooltip += f"Workshop: {self.info.workshop_updated[:10]}<br>"
        if self.info.needs_update:
            tooltip += "<b style='color: #ffd43b;'>Update available!</b>"
        elif self.info.error:
            tooltip += f"<span style='color: #ff6b6b;'>{self.info.error}</span>"
        else:
            tooltip += "<span style='color: #69db7c;'>Up to date</span>"
        self.setToolTip(tooltip)


class ModUpdateCheckerWidget(QWidget):
    """Widget for checking mod updates."""
    
    update_mod = pyqtSignal(str)  # workshop_id to update
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.checker = ModUpdateChecker()
        self._mods_getter: Optional[Callable[[], list]] = None
        self._worker: Optional[UpdateCheckWorker] = None
        self._setup_ui()
    
    def set_mods_getter(self, getter: Callable[[], list]):
        """Set function to get current mods list."""
        self._mods_getter = getter
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("🔄 Mod Update Checker"))
        header.addStretch()
        
        self.btn_check = QPushButton("Check for Updates")
        self.btn_check.clicked.connect(self._check_updates)
        header.addWidget(self.btn_check)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel(
            "Check if your Workshop mods have updates available.\n"
            "Only mods downloaded from Steam Workshop can be checked."
        )
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_list, 1)
        
        # Summary
        self.summary_frame = QFrame()
        self.summary_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        summary_layout = QVBoxLayout(self.summary_frame)
        
        self.summary_label = QLabel("Click 'Check for Updates' to scan your mods.")
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        
        # Update buttons
        btn_layout = QHBoxLayout()
        self.btn_update_selected = QPushButton("Update Selected")
        self.btn_update_selected.setEnabled(False)
        self.btn_update_selected.clicked.connect(self._update_selected)
        btn_layout.addWidget(self.btn_update_selected)
        
        self.btn_update_all = QPushButton("Update All")
        self.btn_update_all.setEnabled(False)
        self.btn_update_all.clicked.connect(self._update_all)
        btn_layout.addWidget(self.btn_update_all)
        
        btn_layout.addStretch()
        summary_layout.addLayout(btn_layout)
        
        layout.addWidget(self.summary_frame)
    
    def _check_updates(self):
        if not self._mods_getter:
            QMessageBox.warning(self, "Error", "No mods to check")
            return
        
        mods = self._mods_getter()
        if not mods:
            self.status_label.setText("No mods found to check.")
            return
            
        workshop_mods = [m for m in mods if m.steam_workshop_id]
        
        if not workshop_mods:
            self.status_label.setText("No Workshop mods found to check.")
            return
        
        # Cancel any existing worker
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(500)
        
        self.btn_check.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText(f"Checking {len(workshop_mods)} mods...")
        self.results_list.clear()
        
        self._worker = UpdateCheckWorker(self.checker, workshop_mods)
        self._worker.finished.connect(self._on_check_finished)
        self._worker.error.connect(self._on_check_error)
        self._worker.start()
    
    def _on_check_finished(self, results: list):
        self.btn_check.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.results_list.clear()
        
        updates_available = 0
        up_to_date = 0
        errors = 0
        
        for info in results:
            item = UpdateListItem(info)
            self.results_list.addItem(item)
            
            if info.needs_update:
                updates_available += 1
            elif info.error:
                errors += 1
            else:
                up_to_date += 1
        
        self.status_label.setText(f"Checked {len(results)} mods")
        
        summary = f"📊 Results: {updates_available} updates available, {up_to_date} up to date"
        if errors:
            summary += f", {errors} errors"
        self.summary_label.setText(summary)
        
        self.btn_update_all.setEnabled(updates_available > 0)
        self.btn_update_selected.setEnabled(updates_available > 0)
    
    def _on_check_error(self, error: str):
        self.btn_check.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Error", f"Failed to check updates:\n{error}")
    
    def _on_item_double_clicked(self, item: QListWidgetItem):
        if isinstance(item, UpdateListItem) and item.info.needs_update:
            self.update_mod.emit(item.info.workshop_id)
    
    def _update_selected(self):
        selected = self.results_list.currentItem()
        if isinstance(selected, UpdateListItem) and selected.info.needs_update:
            self.update_mod.emit(selected.info.workshop_id)
    
    def _update_all(self):
        ids_to_update = []
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            if isinstance(item, UpdateListItem) and item.info.needs_update:
                ids_to_update.append(item.info.workshop_id)
        
        if ids_to_update:
            reply = QMessageBox.question(
                self, "Update All",
                f"Download updates for {len(ids_to_update)} mods?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                for wid in ids_to_update:
                    self.update_mod.emit(wid)


class ConflictListItem(QListWidgetItem):
    """List item for conflict info."""
    
    def __init__(self, conflict: ConflictInfo):
        super().__init__()
        self.conflict = conflict
        self._update_display()
    
    def _update_display(self):
        if self.conflict.severity == 'error':
            icon = "🔴"
            color = QColor("#ff6b6b")
        elif self.conflict.severity == 'warning':
            icon = "🟡"
            color = QColor("#ffd43b")
        else:
            icon = "🔵"
            color = QColor("#74c0fc")
        
        self.setText(f"{icon} {self.conflict.description}")
        self.setForeground(color)
        
        tooltip = f"<b>{self.conflict.conflict_type.replace('_', ' ').title()}</b><br>"
        tooltip += f"{self.conflict.description}<br><br>"
        tooltip += f"<b>Suggestion:</b> {self.conflict.suggestion}"
        self.setToolTip(tooltip)


class ConflictResolverWidget(QWidget):
    """Widget for analyzing and resolving mod conflicts."""
    
    auto_sort_requested = pyqtSignal()
    deactivate_mod = pyqtSignal(str)  # package_id
    
    def __init__(self, mod_parser: ModParser, parent=None):
        super().__init__(parent)
        self.resolver = ConflictResolver(mod_parser)
        self._mods_getter: Optional[Callable[[], list]] = None
        self._setup_ui()
    
    def set_mods_getter(self, getter: Callable[[], list]):
        self._mods_getter = getter
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("🔧 Conflict Resolution Assistant"))
        header.addStretch()
        
        self.btn_analyze = QPushButton("Analyze Conflicts")
        self.btn_analyze.clicked.connect(self._analyze_conflicts)
        header.addWidget(self.btn_analyze)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel(
            "Analyze your mod list for conflicts, missing dependencies, "
            "and load order issues. Get suggestions for fixing problems."
        )
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Status
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        # Conflicts list
        self.conflicts_list = QListWidget()
        self.conflicts_list.itemClicked.connect(self._on_conflict_selected)
        layout.addWidget(self.conflicts_list, 1)
        
        # Details panel
        details_group = QGroupBox("Details & Suggestion")
        details_layout = QVBoxLayout(details_group)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(120)
        details_layout.addWidget(self.details_text)
        
        layout.addWidget(details_group)
        
        # Actions
        actions_layout = QHBoxLayout()
        
        self.btn_auto_sort = QPushButton("🔄 Auto-Sort Load Order")
        self.btn_auto_sort.setToolTip("Automatically fix load order issues")
        self.btn_auto_sort.clicked.connect(self._auto_sort)
        self.btn_auto_sort.setEnabled(False)
        actions_layout.addWidget(self.btn_auto_sort)
        
        self.btn_deactivate = QPushButton("❌ Deactivate Selected Mod")
        self.btn_deactivate.setToolTip("Deactivate the mod causing the conflict")
        self.btn_deactivate.clicked.connect(self._deactivate_selected)
        self.btn_deactivate.setEnabled(False)
        actions_layout.addWidget(self.btn_deactivate)
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        
        # Summary
        self.summary_label = QLabel("Click 'Analyze Conflicts' to check your mod list.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("padding: 8px; background: #2a2a2a; border-radius: 4px;")
        layout.addWidget(self.summary_label)
    
    def _analyze_conflicts(self):
        if not self._mods_getter:
            return
        
        mods = self._mods_getter()
        if not mods:
            self.status_label.setText("No active mods to analyze.")
            return
        
        self.status_label.setText("Analyzing...")
        QApplication.processEvents()
        
        conflicts = self.resolver.analyze_conflicts(mods)
        
        self.conflicts_list.clear()
        self.details_text.clear()
        
        for conflict in conflicts:
            item = ConflictListItem(conflict)
            self.conflicts_list.addItem(item)
        
        # Count by severity
        errors = sum(1 for c in conflicts if c.severity == 'error')
        warnings = sum(1 for c in conflicts if c.severity == 'warning')
        
        if not conflicts:
            self.status_label.setText("✅ No conflicts found!")
            self.summary_label.setText("Your mod list looks good! No conflicts detected.")
            self.btn_auto_sort.setEnabled(False)
        else:
            self.status_label.setText(f"Found {len(conflicts)} issue(s)")
            
            summary = []
            if errors:
                summary.append(f"🔴 {errors} critical issue(s)")
            if warnings:
                summary.append(f"🟡 {warnings} warning(s)")
            
            self.summary_label.setText(" | ".join(summary))
            
            # Enable auto-sort if there are load order issues
            has_load_order = any(c.conflict_type == 'load_order' for c in conflicts)
            self.btn_auto_sort.setEnabled(has_load_order)
    
    def _on_conflict_selected(self, item: QListWidgetItem):
        if isinstance(item, ConflictListItem):
            conflict = item.conflict
            
            details = f"<h3>{conflict.conflict_type.replace('_', ' ').title()}</h3>"
            details += f"<p><b>Severity:</b> {conflict.severity.upper()}</p>"
            details += f"<p><b>Issue:</b> {conflict.description}</p>"
            details += f"<p><b>Suggestion:</b> {conflict.suggestion}</p>"
            
            if conflict.mod1_id:
                details += f"<p><b>Mod 1:</b> {conflict.mod1_name} ({conflict.mod1_id})</p>"
            if conflict.mod2_id:
                details += f"<p><b>Mod 2:</b> {conflict.mod2_name} ({conflict.mod2_id})</p>"
            
            self.details_text.setHtml(details)
            self.btn_deactivate.setEnabled(True)
    
    def _auto_sort(self):
        self.auto_sort_requested.emit()
        # Re-analyze after sort
        QMessageBox.information(
            self, "Auto-Sort",
            "Load order has been automatically sorted.\n\n"
            "Click 'Analyze Conflicts' again to verify."
        )
    
    def _deactivate_selected(self):
        item = self.conflicts_list.currentItem()
        if isinstance(item, ConflictListItem):
            conflict = item.conflict
            
            # Ask which mod to deactivate
            if conflict.mod2_id:
                reply = QMessageBox.question(
                    self, "Deactivate Mod",
                    f"Which mod do you want to deactivate?\n\n"
                    f"1. {conflict.mod1_name}\n"
                    f"2. {conflict.mod2_name}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.deactivate_mod.emit(conflict.mod1_id)
                else:
                    self.deactivate_mod.emit(conflict.mod2_id)
            else:
                self.deactivate_mod.emit(conflict.mod1_id)


class EnhancedModInfoWidget(QWidget):
    """Widget showing enhanced mod information from Workshop."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fetcher = EnhancedModInfoFetcher()
        self._current_mod: Optional[ModInfo] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        self.header_label = QLabel("📊 Enhanced Mod Info")
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.header_label)
        
        # Content area
        self.content_area = QScrollArea()
        self.content_area.setWidgetResizable(True)
        self.content_area.setFrameStyle(QFrame.Shape.NoFrame)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Placeholder
        self.placeholder = QLabel("Select a Workshop mod to see enhanced information.")
        self.placeholder.setStyleSheet("color: #888;")
        self.placeholder.setWordWrap(True)
        self.content_layout.addWidget(self.placeholder)
        
        # Info labels (hidden initially)
        self.info_frame = QFrame()
        self.info_frame.setVisible(False)
        info_layout = QVBoxLayout(self.info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)
        
        # Stats row
        stats_layout = QHBoxLayout()
        self.subs_label = QLabel()
        stats_layout.addWidget(self.subs_label)
        self.favs_label = QLabel()
        stats_layout.addWidget(self.favs_label)
        self.views_label = QLabel()
        stats_layout.addWidget(self.views_label)
        stats_layout.addStretch()
        info_layout.addLayout(stats_layout)
        
        # Size and dates
        self.size_label = QLabel()
        info_layout.addWidget(self.size_label)
        
        self.dates_label = QLabel()
        self.dates_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.dates_label)
        
        # Tags
        self.tags_label = QLabel()
        self.tags_label.setWordWrap(True)
        info_layout.addWidget(self.tags_label)
        
        # Description
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setMaximumHeight(150)
        info_layout.addWidget(self.desc_text)
        
        self.content_layout.addWidget(self.info_frame)
        self.content_layout.addStretch()
        
        self.content_area.setWidget(self.content_widget)
        layout.addWidget(self.content_area, 1)
        
        # Refresh button
        self.btn_refresh = QPushButton("🔄 Refresh Info")
        self.btn_refresh.clicked.connect(self._refresh_info)
        self.btn_refresh.setEnabled(False)
        layout.addWidget(self.btn_refresh)
    
    def show_mod(self, mod: ModInfo):
        """Show enhanced info for a mod."""
        self._current_mod = mod
        
        if not mod.steam_workshop_id:
            self.placeholder.setText("This mod is not from Steam Workshop.\nEnhanced info is only available for Workshop mods.")
            self.placeholder.setVisible(True)
            self.info_frame.setVisible(False)
            self.btn_refresh.setEnabled(False)
            return
        
        self.btn_refresh.setEnabled(True)
        self._fetch_and_display(mod.steam_workshop_id)
    
    def _refresh_info(self):
        if self._current_mod and self._current_mod.steam_workshop_id:
            # Clear cache for this mod
            wid = self._current_mod.steam_workshop_id
            if wid in self.fetcher.cache:
                del self.fetcher.cache[wid]
            self._fetch_and_display(wid)
    
    def _fetch_and_display(self, workshop_id: str):
        self.placeholder.setText("Loading...")
        self.placeholder.setVisible(True)
        self.info_frame.setVisible(False)
        QApplication.processEvents()
        
        try:
            info_dict = self.fetcher.fetch_info([workshop_id])
        except (OSError, ValueError) as e:
            self.placeholder.setText(f"Failed to fetch Workshop information: {e}")
            return
        
        if workshop_id not in info_dict:
            self.placeholder.setText("Failed to fetch Workshop information.\nThe mod may be private or removed.")
            return
        
        info = info_dict[workshop_id]
        
        self.placeholder.setVisible(False)
        self.info_frame.setVisible(True)
        
        self.title_label.setText(info.title or "Unknown Title")
        
        self.subs_label.setText(f"�  {info.format_number(info.subscriptions)} subs")
        self.favs_label.setText(f"⭐ {info.format_number(info.favorited)} favs")
        self.views_label.setText(f"👁 {info.format_number(info.views)} views")
        
        self.size_label.setText(f"📦 Size: {info.format_file_size()}")
        
        dates = []
        if info.time_created:
            dates.append(f"Created: {info.time_created[:10]}")
        if info.time_updated:
            dates.append(f"Updated: {info.time_updated[:10]}")
        self.dates_label.setText(" | ".join(dates))
        
        if info.tags:
            self.tags_label.setText(f"🏷️ Tags: {', '.join(info.tags)}")
            self.tags_label.setVisible(True)
        else:
            self.tags_label.setVisible(False)
        
        # Clean up description (remove BBCode)
        desc = info.description
        if desc:
            import re
            desc = re.sub(r'\[.*?\]', '', desc)  # Remove BBCode tags
            desc = desc[:500] + "..." if len(desc) > 500 else desc
        self.desc_text.setPlainText(desc or "No description available.")
    
    def clear(self):
        """Clear the display."""
        self._current_mod = None
        self.placeholder.setText("Select a Workshop mod to see enhanced information.")
        self.placeholder.setVisible(True)
        self.info_frame.setVisible(False)
        self.btn_refresh.setEnabled(False)


class ToolsTabWidget(QWidget):
    """Combined tools tab with update checker and conflict resolver."""
    
    update_mods = pyqtSignal(list)  # list of workshop_ids
    auto_sort_requested = pyqtSignal()
    deactivate_mod = pyqtSignal(str)
    
    def __init__(self, mod_parser: ModParser, parent=None):
        super().__init__(parent)
        self.mod_parser = mod_parser
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Sub-tabs
        self.tabs = QTabWidget()
        
        # Update Checker tab
        self.update_checker = ModUpdateCheckerWidget()
        self.update_checker.update_mod.connect(lambda wid: self.update_mods.emit([wid]))
        self.tabs.addTab(self.update_checker, "🔄 Update Checker")
        
        # Conflict Resolver tab
        self.conflict_resolver = ConflictResolverWidget(self.mod_parser)
        self.conflict_resolver.auto_sort_requested.connect(self.auto_sort_requested.emit)
        self.conflict_resolver.deactivate_mod.connect(self.deactivate_mod.emit)
        self.tabs.addTab(self.conflict_resolver, "🔧 Conflict Resolver")
        
        # Enhanced Info tab
        self.enhanced_info = EnhancedModInfoWidget()
        self.tabs.addTab(self.enhanced_info, "📊 Workshop Info")
        
        layout.addWidget(self.tabs)
    
    def set_mods_getter(self, getter: Callable[[], list]):
        """Set function to get current mods."""
        self.update_checker.set_mods_getter(getter)
        self.conflict_resolver.set_mods_getter(getter)
    
    def show_mod_info(self, mod: ModInfo):
        """Show enhanced info for a mod."""
        self.enhanced_info.show_mod(mod)
