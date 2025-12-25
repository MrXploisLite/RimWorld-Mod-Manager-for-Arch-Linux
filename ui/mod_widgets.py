"""
UI Components for RimModManager
Custom widgets for mod list, drag-drop, and mod details.
"""

from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QScrollArea,
    QAbstractItemView, QMenu, QToolTip, QSizePolicy,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QSize, QRect, QPoint, QEvent
from PyQt6.QtGui import QDrag, QPixmap, QIcon, QPalette, QColor, QAction, QPainter, QBrush, QPen, QFont

from mod_parser import ModInfo, ModSource


class ModListItem(QListWidgetItem):
    """Custom list item for displaying a mod."""
    
    def __init__(self, mod: ModInfo):
        super().__init__()
        self.mod = mod
        self._update_display()
    
    def _update_display(self):
        """Update the display text and styling."""
        # Build display text
        name = self.mod.display_name()
        
        # Add source indicator
        source_icons = {
            ModSource.LOCAL: "📁",
            ModSource.WORKSHOP: "🔧",
            ModSource.GAME: "🎮",
        }
        icon = source_icons.get(self.mod.source, "📦")
        
        self.setText(f"{icon} {name}")
        
        # Set tooltip with more info
        tooltip_parts = [
            f"<b>{name}</b>",
            f"Package ID: {self.mod.package_id}",
            f"Author: {self.mod.author}",
        ]
        
        if self.mod.supported_versions:
            tooltip_parts.append(f"Versions: {', '.join(self.mod.supported_versions)}")
        
        if self.mod.steam_workshop_id:
            tooltip_parts.append(f"Workshop ID: {self.mod.steam_workshop_id}")
        
        if not self.mod.is_valid:
            tooltip_parts.append(f"<font color='red'>Error: {self.mod.error_message}</font>")
        
        tooltip_parts.append("<i>Double-click or click ➕/➖ to activate/deactivate</i>")
        
        self.setToolTip("<br>".join(tooltip_parts))
        
        # Visual styling for invalid mods
        if not self.mod.is_valid:
            self.setForeground(QColor(200, 100, 100))


class HoverButtonDelegate(QStyledItemDelegate):
    """Delegate that draws hover buttons on list items."""
    
    # Button size constants
    BTN_SIZE = 24
    BTN_MARGIN = 4
    
    def __init__(self, parent=None, is_active_list: bool = False):
        super().__init__(parent)
        self.is_active_list = is_active_list
        self._hovered_index = None
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """Paint the item with hover button."""
        # Draw default item
        super().paint(painter, option, index)
        
        # Validate option rect
        if option.rect.width() <= 0 or option.rect.height() <= 0:
            return
        
        # Draw button on hover
        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.save()
            
            # Button area on the right (with margin from edge)
            btn_rect = QRect(
                option.rect.right() - self.BTN_SIZE - self.BTN_MARGIN - 4,  # Extra padding from edge
                option.rect.top() + (option.rect.height() - self.BTN_SIZE) // 2,
                self.BTN_SIZE,
                self.BTN_SIZE
            )
            
            # Draw button background
            if self.is_active_list:
                # Red minus button for active list
                painter.setBrush(QBrush(QColor(180, 60, 60)))
                btn_text = "−"
            else:
                # Green plus button for available list
                painter.setBrush(QBrush(QColor(60, 140, 60)))
                btn_text = "+"
            
            painter.setPen(QPen(QColor(255, 255, 255, 100)))
            painter.drawRoundedRect(btn_rect, 4, 4)
            
            # Draw button text
            painter.setPen(QPen(QColor(255, 255, 255)))
            font = QFont()
            font.setBold(True)
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, btn_text)
            
            painter.restore()
    
    def editorEvent(self, event, model, option, index):
        """Handle mouse events on the button."""
        # Bounds check - ensure index is valid
        if not index.isValid():
            return super().editorEvent(event, model, option, index)
        
        # Validate option rect
        if option.rect.width() <= 0 or option.rect.height() <= 0:
            return super().editorEvent(event, model, option, index)
        
        if event.type() == QEvent.Type.MouseButtonRelease:
            # Calculate button rect locally (not stored as instance variable)
            btn_rect = QRect(
                option.rect.right() - self.BTN_SIZE - self.BTN_MARGIN - 4,
                option.rect.top() + (option.rect.height() - self.BTN_SIZE) // 2,
                self.BTN_SIZE,
                self.BTN_SIZE
            )
            
            if btn_rect.contains(event.pos()):
                # Button was clicked - emit signal through parent
                list_widget = self.parent()
                if list_widget and hasattr(list_widget, '_on_hover_button_clicked'):
                    list_widget._on_hover_button_clicked(index)
                return True
        
        return super().editorEvent(event, model, option, index)


class DraggableModList(QListWidget):
    """
    A list widget that supports drag-drop reordering.
    Used for both active and inactive mod lists.
    Shows hover buttons for quick activate/deactivate.
    """
    
    # Signals
    mods_changed = pyqtSignal()  # Emitted when mods are added/removed/reordered
    mod_activated = pyqtSignal(ModInfo)  # Emitted when a mod is double-clicked
    mod_deactivated = pyqtSignal(ModInfo)  # Emitted when a mod is removed
    
    def __init__(self, parent=None, is_active_list: bool = False):
        super().__init__(parent)
        self.is_active_list = is_active_list
        
        # Enable drag-drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
        # Set custom delegate for hover buttons
        self._delegate = HoverButtonDelegate(self, is_active_list)
        self.setItemDelegate(self._delegate)
        
        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Double-click handler
        self.itemDoubleClicked.connect(self._on_double_click)
    
    def _on_hover_button_clicked(self, index):
        """Handle hover button click."""
        item = self.item(index.row())
        if isinstance(item, ModListItem):
            if self.is_active_list:
                self.mod_deactivated.emit(item.mod)
            else:
                self.mod_activated.emit(item.mod)
    
    def add_mod(self, mod: ModInfo) -> ModListItem:
        """Add a mod to the list."""
        item = ModListItem(mod)
        self.addItem(item)
        return item
    
    def add_mods(self, mods: list[ModInfo]) -> None:
        """Add multiple mods to the list."""
        for mod in mods:
            self.add_mod(mod)
    
    def get_mods(self) -> list[ModInfo]:
        """Get all mods in order."""
        mods = []
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, ModListItem):
                mods.append(item.mod)
        return mods
    
    def get_selected_mods(self) -> list[ModInfo]:
        """Get currently selected mods."""
        mods = []
        for item in self.selectedItems():
            if isinstance(item, ModListItem):
                mods.append(item.mod)
        return mods
    
    def remove_selected(self) -> list[ModInfo]:
        """Remove selected items and return the mods."""
        removed = []
        # Collect rows first, then remove in reverse order to avoid index shifting
        items_to_remove = []
        for item in self.selectedItems():
            if isinstance(item, ModListItem):
                removed.append(item.mod)
            items_to_remove.append((self.row(item), item))
        
        # Sort by row in reverse order and remove
        items_to_remove.sort(key=lambda x: x[0], reverse=True)
        for row, item in items_to_remove:
            self.takeItem(row)
        
        if removed:
            self.mods_changed.emit()
        return removed
    
    def clear_mods(self) -> None:
        """Clear all mods from the list."""
        self.clear()
        self.mods_changed.emit()
    
    def find_mod(self, package_id: str) -> Optional[ModListItem]:
        """Find a mod by package ID."""
        package_id = package_id.lower()
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, ModListItem):
                if item.mod.package_id.lower() == package_id:
                    return item
        return None
    
    def move_selected_up(self) -> None:
        """Move selected items up one position."""
        selected = self.selectedItems()
        if not selected:
            return
        
        rows = sorted([self.row(item) for item in selected])
        if rows[0] == 0:
            return  # Already at top
        
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row - 1, item)
            item.setSelected(True)
        
        self.mods_changed.emit()
    
    def move_selected_down(self) -> None:
        """Move selected items down one position."""
        selected = self.selectedItems()
        if not selected:
            return
        
        rows = sorted([self.row(item) for item in selected], reverse=True)
        if rows[0] == self.count() - 1:
            return  # Already at bottom
        
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row + 1, item)
            item.setSelected(True)
        
        self.mods_changed.emit()
    
    def move_selected_to_top(self) -> None:
        """Move selected items to the top."""
        selected = self.selectedItems()
        if not selected:
            return
        
        rows = sorted([self.row(item) for item in selected], reverse=True)
        for i, row in enumerate(rows):
            item = self.takeItem(row)
            self.insertItem(i, item)
            item.setSelected(True)
        
        self.mods_changed.emit()
    
    def move_selected_to_bottom(self) -> None:
        """Move selected items to the bottom."""
        selected = self.selectedItems()
        if not selected:
            return
        
        # Sort in reverse order of rows
        rows = sorted([self.row(item) for item in selected], reverse=True)
        items = [self.takeItem(row) for row in rows]
        
        for item in reversed(items):
            self.addItem(item)
            item.setSelected(True)
        
        self.mods_changed.emit()
    
    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Handle double-click to activate/deactivate mod."""
        if isinstance(item, ModListItem):
            if self.is_active_list:
                self.mod_deactivated.emit(item.mod)
            else:
                self.mod_activated.emit(item.mod)
    
    def _show_context_menu(self, position) -> None:
        """Show context menu for the list."""
        menu = QMenu(self)
        
        selected = self.selectedItems()
        if selected:
            if self.is_active_list:
                deactivate_action = QAction("Deactivate Selected", self)
                deactivate_action.triggered.connect(lambda: self._context_deactivate())
                menu.addAction(deactivate_action)
            else:
                activate_action = QAction("Activate Selected", self)
                activate_action.triggered.connect(lambda: self._context_activate())
                menu.addAction(activate_action)
            
            menu.addSeparator()
            
            if self.is_active_list:
                move_up = QAction("Move Up", self)
                move_up.triggered.connect(self.move_selected_up)
                menu.addAction(move_up)
                
                move_down = QAction("Move Down", self)
                move_down.triggered.connect(self.move_selected_down)
                menu.addAction(move_down)
                
                move_top = QAction("Move to Top", self)
                move_top.triggered.connect(self.move_selected_to_top)
                menu.addAction(move_top)
                
                move_bottom = QAction("Move to Bottom", self)
                move_bottom.triggered.connect(self.move_selected_to_bottom)
                menu.addAction(move_bottom)
        
        if menu.actions():
            menu.exec(self.mapToGlobal(position))
    
    def _context_activate(self) -> None:
        """Activate selected mods (emit signals for each)."""
        for item in self.selectedItems():
            if isinstance(item, ModListItem):
                self.mod_activated.emit(item.mod)
    
    def _context_deactivate(self) -> None:
        """Deactivate selected mods (emit signals for each)."""
        for item in self.selectedItems():
            if isinstance(item, ModListItem):
                self.mod_deactivated.emit(item.mod)
    
    def dropEvent(self, event):
        """Handle drop event for reordering."""
        super().dropEvent(event)
        self.mods_changed.emit()


class ModDetailsPanel(QFrame):
    """Panel showing details of a selected mod."""
    
    # Signals
    uninstall_requested = pyqtSignal(object)  # ModInfo
    open_folder_requested = pyqtSignal(object)  # ModInfo
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setMinimumWidth(250)
        self._current_mod: Optional[ModInfo] = None
        
        self._setup_ui()
        self.clear()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Preview image
        self.preview_label = QLabel()
        self.preview_label.setFixedHeight(150)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #333; border-radius: 4px;")
        layout.addWidget(self.preview_label)
        
        # Mod name
        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.name_label)
        
        # Author
        self.author_label = QLabel()
        self.author_label.setWordWrap(True)
        layout.addWidget(self.author_label)
        
        # Package ID
        self.package_id_label = QLabel()
        self.package_id_label.setWordWrap(True)
        self.package_id_label.setStyleSheet("color: #888;")
        layout.addWidget(self.package_id_label)
        
        # Versions
        self.versions_label = QLabel()
        self.versions_label.setWordWrap(True)
        layout.addWidget(self.versions_label)
        
        # Source
        self.source_label = QLabel()
        layout.addWidget(self.source_label)
        
        # Description (scrollable)
        self.description_scroll = QScrollArea()
        self.description_scroll.setWidgetResizable(True)
        self.description_scroll.setMinimumHeight(100)
        
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.description_scroll.setWidget(self.description_label)
        layout.addWidget(self.description_scroll, 1)
        
        # Dependencies info
        self.deps_label = QLabel()
        self.deps_label.setWordWrap(True)
        self.deps_label.setStyleSheet("color: #f90;")
        layout.addWidget(self.deps_label)
        
        # Path
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.path_label)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        self.btn_open_folder = QPushButton("📁 Open Folder")
        self.btn_open_folder.setToolTip("Open mod folder in file manager")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        btn_layout.addWidget(self.btn_open_folder)
        
        self.btn_uninstall = QPushButton("🗑️ Uninstall")
        self.btn_uninstall.setToolTip("Delete this mod permanently")
        self.btn_uninstall.setStyleSheet("background-color: #5a2a2a;")
        self.btn_uninstall.clicked.connect(self._on_uninstall)
        btn_layout.addWidget(self.btn_uninstall)
        
        layout.addLayout(btn_layout)
    
    def _on_open_folder(self):
        """Handle open folder button click."""
        if self._current_mod:
            self.open_folder_requested.emit(self._current_mod)
    
    def _on_uninstall(self):
        """Handle uninstall button click."""
        if self._current_mod:
            self.uninstall_requested.emit(self._current_mod)
    
    def show_mod(self, mod: ModInfo) -> None:
        """Display details for a mod."""
        self._current_mod = mod
        
        # Preview image
        preview = mod.get_preview_image()
        if preview and preview.exists():
            pixmap = QPixmap(str(preview))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled)
            else:
                self.preview_label.setText("No Preview")
        else:
            self.preview_label.setText("No Preview")
            self.preview_label.setPixmap(QPixmap())
        
        # Text info
        self.name_label.setText(mod.display_name())
        
        # Author - hide if empty
        if mod.author and mod.author.strip() and mod.author != "Unknown":
            self.author_label.setText(f"by {mod.author}")
            self.author_label.show()
        else:
            self.author_label.hide()
        
        # Package ID - hide if empty
        if mod.package_id and mod.package_id.strip():
            self.package_id_label.setText(f"ID: {mod.package_id}")
            self.package_id_label.show()
        else:
            self.package_id_label.hide()
        
        if mod.supported_versions:
            self.versions_label.setText(f"Versions: {', '.join(mod.supported_versions)}")
            self.versions_label.show()
        else:
            self.versions_label.hide()
        
        self.source_label.setText(f"Source: {mod.source.value}")
        
        # Description
        desc = mod.description or "No description available."
        # Truncate very long descriptions
        if len(desc) > 2000:
            desc = desc[:2000] + "..."
        self.description_label.setText(desc)
        
        # Dependencies
        deps_text = []
        if mod.mod_dependencies:
            deps_text.append(f"Requires: {', '.join(mod.mod_dependencies[:5])}")
        if mod.load_after:
            deps_text.append(f"Load after: {', '.join(mod.load_after[:5])}")
        if mod.load_before:
            deps_text.append(f"Load before: {', '.join(mod.load_before[:5])}")
        
        if deps_text:
            self.deps_label.setText("\n".join(deps_text))
            self.deps_label.show()
        else:
            self.deps_label.hide()
        
        # Path - show the mod folder path, not subfolder
        if mod.path and mod.path.exists():
            # Make sure we're showing the mod root, not About subfolder
            path_str = str(mod.path)
            if path_str.endswith('/About') or path_str.endswith('\\About'):
                path_str = str(mod.path.parent)
            self.path_label.setText(f"📁 {path_str}")
            self.path_label.show()
            self.btn_open_folder.setEnabled(True)
        else:
            self.path_label.hide()
            self.btn_open_folder.setEnabled(False)
        
        # Enable/disable uninstall button based on mod source
        # Don't allow uninstalling core game mods
        if mod.source == ModSource.GAME:
            self.btn_uninstall.setEnabled(False)
            self.btn_uninstall.setToolTip("Cannot uninstall core game files")
        else:
            self.btn_uninstall.setEnabled(mod.path is not None and mod.path.exists())
            self.btn_uninstall.setToolTip("Delete this mod permanently")
    
    def clear(self) -> None:
        """Clear the details panel."""
        self._current_mod = None
        self.preview_label.setText("Select a mod")
        self.preview_label.setPixmap(QPixmap())
        self.name_label.clear()
        self.author_label.clear()
        self.package_id_label.clear()
        self.versions_label.clear()
        self.source_label.clear()
        self.description_label.clear()
        self.deps_label.clear()
        self.path_label.clear()
        self.btn_open_folder.setEnabled(False)
        self.btn_uninstall.setEnabled(False)


class ModListControls(QWidget):
    """Control buttons for a mod list (activate all, move up/down, etc.)."""
    
    activate_all = pyqtSignal()
    deactivate_all = pyqtSignal()
    move_up = pyqtSignal()
    move_down = pyqtSignal()
    move_top = pyqtSignal()
    move_bottom = pyqtSignal()
    auto_sort = pyqtSignal()  # New signal for auto-sort
    
    def __init__(self, is_active_list: bool = False, parent=None):
        super().__init__(parent)
        self.is_active_list = is_active_list
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the control buttons."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        if self.is_active_list:
            # Active list controls
            self.btn_top = QPushButton("⬆⬆")
            self.btn_top.setToolTip("Move to top")
            self.btn_top.setFixedWidth(40)
            self.btn_top.clicked.connect(self.move_top.emit)
            layout.addWidget(self.btn_top)
            
            self.btn_up = QPushButton("⬆")
            self.btn_up.setToolTip("Move up")
            self.btn_up.setFixedWidth(30)
            self.btn_up.clicked.connect(self.move_up.emit)
            layout.addWidget(self.btn_up)
            
            self.btn_down = QPushButton("⬇")
            self.btn_down.setToolTip("Move down")
            self.btn_down.setFixedWidth(30)
            self.btn_down.clicked.connect(self.move_down.emit)
            layout.addWidget(self.btn_down)
            
            self.btn_bottom = QPushButton("⬇⬇")
            self.btn_bottom.setToolTip("Move to bottom")
            self.btn_bottom.setFixedWidth(40)
            self.btn_bottom.clicked.connect(self.move_bottom.emit)
            layout.addWidget(self.btn_bottom)
            
            layout.addStretch()
            
            # Auto-sort button
            self.btn_auto_sort = QPushButton("🔄 Auto-Sort")
            self.btn_auto_sort.setToolTip("Automatically sort mods by dependencies (loadBefore/loadAfter)")
            self.btn_auto_sort.setStyleSheet("background-color: #3a3a5a;")
            self.btn_auto_sort.clicked.connect(self.auto_sort.emit)
            layout.addWidget(self.btn_auto_sort)
            
            self.btn_deactivate_all = QPushButton("Deactivate All")
            self.btn_deactivate_all.clicked.connect(self.deactivate_all.emit)
            layout.addWidget(self.btn_deactivate_all)
        else:
            # Inactive list controls
            self.btn_activate_all = QPushButton("Activate All")
            self.btn_activate_all.clicked.connect(self.activate_all.emit)
            layout.addWidget(self.btn_activate_all)
            
            layout.addStretch()


class ConflictWarningWidget(QFrame):
    """Widget to display mod conflicts and warnings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #442200; border-radius: 4px; padding: 8px;")
        
        self._setup_ui()
        self.hide()
    
    def _setup_ui(self):
        """Set up the warning display."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        self.title_label = QLabel("⚠️ Warnings")
        self.title_label.setStyleSheet("font-weight: bold; color: #ffaa00;")
        layout.addWidget(self.title_label)
        
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #ffcc88;")
        layout.addWidget(self.warnings_label)
    
    def set_warnings(self, conflicts: dict, missing_deps: dict, incompatibilities: list) -> None:
        """Display warnings for conflicts, missing dependencies, and incompatibilities."""
        warnings = []
        
        if conflicts:
            warnings.append("<b>Duplicate Mods:</b>")
            for pkg_id, mods in conflicts.items():
                names = [m.display_name() for m in mods]
                warnings.append(f"  • {pkg_id}: {', '.join(names)}")
        
        if missing_deps:
            warnings.append("<b>Missing Dependencies:</b>")
            for mod_id, deps in list(missing_deps.items())[:5]:  # Limit to 5
                warnings.append(f"  • {mod_id} needs: {', '.join(deps[:3])}")
        
        if incompatibilities:
            warnings.append("<b>Incompatible Mods Active:</b>")
            for mod1, mod2 in incompatibilities[:5]:  # Limit to 5
                warnings.append(f"  • {mod1.display_name()} ⚡ {mod2.display_name()}")
        
        if warnings:
            self.warnings_label.setText("<br>".join(warnings))
            self.show()
        else:
            self.hide()
    
    def clear_warnings(self) -> None:
        """Clear all warnings."""
        self.warnings_label.clear()
        self.hide()
