"""
Workshop Browser for RimWorld Mod Manager
Integrated Steam Workshop browser with subscription and download features.
"""

import re
import json
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
    QSplitter, QFrame, QMessageBox, QGroupBox, QCheckBox,
    QTabWidget, QTextEdit, QScrollArea, QToolBar, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QThread, QTimer
from PyQt6.QtGui import QAction, QIcon

# Try to import WebEngine, fallback gracefully if not available
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None


@dataclass
class WorkshopItem:
    """Represents a Workshop mod item."""
    workshop_id: str
    name: str = ""
    author: str = ""
    description: str = ""
    thumbnail_url: str = ""
    subscribed: bool = False
    downloaded: bool = False
    is_collection: bool = False
    collection_items: list[str] = field(default_factory=list)


class DownloadQueueItem(QListWidgetItem):
    """List item for download queue."""
    
    def __init__(self, item: WorkshopItem):
        super().__init__()
        self.workshop_item = item
        self.update_display()
    
    def update_display(self, status: str = "Pending"):
        icon = "📦" if not self.workshop_item.is_collection else "📁"
        name = self.workshop_item.name or self.workshop_item.workshop_id
        self.setText(f"{icon} {name} - {status}")


class WorkshopBrowser(QWidget):
    """
    Integrated Steam Workshop browser widget.
    Allows browsing, subscribing, and downloading mods directly.
    """
    
    # Signals
    mod_added = pyqtSignal(str, str)  # workshop_id, name
    download_requested = pyqtSignal(list)  # list of workshop_ids
    
    WORKSHOP_URL = "https://steamcommunity.com/app/294100/workshop/"
    WORKSHOP_BROWSE_URL = "https://steamcommunity.com/workshop/browse/?appid=294100"
    
    def __init__(self, downloaded_ids: set[str] = None, parent=None):
        super().__init__(parent)
        self.downloaded_ids = downloaded_ids or set()
        self.queue: list[WorkshopItem] = []
        self.queue_ids: set[str] = set()
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the browser UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - Browser or URL input
        browser_widget = QWidget()
        browser_layout = QVBoxLayout(browser_widget)
        browser_layout.setContentsMargins(4, 4, 4, 4)
        
        # Navigation toolbar
        nav_bar = QHBoxLayout()
        
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedWidth(30)
        self.btn_back.setToolTip("Go back")
        nav_bar.addWidget(self.btn_back)
        
        self.btn_forward = QPushButton("→")
        self.btn_forward.setFixedWidth(30)
        self.btn_forward.setToolTip("Go forward")
        nav_bar.addWidget(self.btn_forward)
        
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedWidth(30)
        self.btn_refresh.setToolTip("Refresh")
        nav_bar.addWidget(self.btn_refresh)
        
        self.btn_home = QPushButton("🏠")
        self.btn_home.setFixedWidth(30)
        self.btn_home.setToolTip("Workshop home")
        nav_bar.addWidget(self.btn_home)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Workshop URL or Mod ID...")
        nav_bar.addWidget(self.url_input, 1)
        
        self.btn_add = QPushButton("➕ Add to Queue")
        self.btn_add.clicked.connect(self._add_current_to_queue)
        nav_bar.addWidget(self.btn_add)
        
        browser_layout.addLayout(nav_bar)
        
        # Web view or fallback
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView()
            self.web_view.setUrl(QUrl(self.WORKSHOP_URL))
            browser_layout.addWidget(self.web_view, 1)
            
            # Connect navigation
            self.btn_back.clicked.connect(self.web_view.back)
            self.btn_forward.clicked.connect(self.web_view.forward)
            self.btn_refresh.clicked.connect(self.web_view.reload)
            self.btn_home.clicked.connect(lambda: self.web_view.setUrl(QUrl(self.WORKSHOP_URL)))
            self.web_view.urlChanged.connect(self._on_url_changed)
            self.url_input.returnPressed.connect(self._navigate_to_url)
        else:
            # Fallback - no web engine
            self.web_view = None
            fallback = QLabel(
                "<h3>Web Browser Not Available</h3>"
                "<p>PyQt6-WebEngine is not installed.</p>"
                "<p>Install with: <code>sudo pacman -S python-pyqt6-webengine</code></p>"
                "<p>You can still paste Workshop URLs or mod IDs above and add them to the queue.</p>"
                f"<p><a href='{self.WORKSHOP_URL}'>Open Workshop in Browser</a></p>"
            )
            fallback.setOpenExternalLinks(True)
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            browser_layout.addWidget(fallback, 1)
            
            self.btn_back.setEnabled(False)
            self.btn_forward.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            self.btn_home.setEnabled(False)
            self.url_input.returnPressed.connect(self._add_current_to_queue)
        
        # Quick links
        links_layout = QHBoxLayout()
        
        btn_popular = QPushButton("🔥 Most Popular")
        btn_popular.clicked.connect(lambda: self._open_url(
            "https://steamcommunity.com/workshop/browse/?appid=294100&browsesort=toprated"
        ))
        links_layout.addWidget(btn_popular)
        
        btn_recent = QPushButton("🆕 Most Recent")
        btn_recent.clicked.connect(lambda: self._open_url(
            "https://steamcommunity.com/workshop/browse/?appid=294100&browsesort=mostrecent"
        ))
        links_layout.addWidget(btn_recent)
        
        btn_trending = QPushButton("📈 Trending")
        btn_trending.clicked.connect(lambda: self._open_url(
            "https://steamcommunity.com/workshop/browse/?appid=294100&browsesort=trend"
        ))
        links_layout.addWidget(btn_trending)
        
        btn_collections = QPushButton("📁 Collections")
        btn_collections.clicked.connect(lambda: self._open_url(
            "https://steamcommunity.com/workshop/browse/?appid=294100&section=collections"
        ))
        links_layout.addWidget(btn_collections)
        
        links_layout.addStretch()
        browser_layout.addLayout(links_layout)
        
        splitter.addWidget(browser_widget)
        
        # Right side - Queue
        queue_widget = QWidget()
        queue_widget.setMaximumWidth(350)
        queue_widget.setMinimumWidth(250)
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(4, 4, 4, 4)
        
        # Queue header
        queue_header = QHBoxLayout()
        queue_header.addWidget(QLabel("📥 Download Queue"))
        queue_header.addStretch()
        self.queue_count = QLabel("(0)")
        queue_header.addWidget(self.queue_count)
        queue_layout.addLayout(queue_header)
        
        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        queue_layout.addWidget(self.queue_list, 1)
        
        # Queue controls
        queue_controls = QHBoxLayout()
        
        self.btn_remove = QPushButton("🗑️ Remove")
        self.btn_remove.clicked.connect(self._remove_selected)
        queue_controls.addWidget(self.btn_remove)
        
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_queue)
        queue_controls.addWidget(self.btn_clear)
        
        queue_layout.addLayout(queue_controls)
        
        # Duplicate warning
        self.dup_check = QCheckBox("Skip already downloaded mods")
        self.dup_check.setChecked(True)
        queue_layout.addWidget(self.dup_check)
        
        # Batch input
        batch_group = QGroupBox("Batch Add (IDs/URLs)")
        batch_layout = QVBoxLayout(batch_group)
        
        self.batch_input = QTextEdit()
        self.batch_input.setMaximumHeight(80)
        self.batch_input.setPlaceholderText("Paste multiple mod IDs or URLs here (one per line)")
        batch_layout.addWidget(self.batch_input)
        
        batch_btns = QHBoxLayout()
        self.btn_add_batch = QPushButton("Add All")
        self.btn_add_batch.clicked.connect(self._add_batch)
        batch_btns.addWidget(self.btn_add_batch)
        
        self.btn_parse_collection = QPushButton("Parse Collection")
        self.btn_parse_collection.clicked.connect(self._parse_collection)
        batch_btns.addWidget(self.btn_parse_collection)
        
        batch_layout.addLayout(batch_btns)
        queue_layout.addWidget(batch_group)
        
        # Download button
        self.btn_download = QPushButton("⬇️ Download All")
        self.btn_download.setStyleSheet("background-color: #2a5a2a; font-weight: bold; padding: 8px;")
        self.btn_download.clicked.connect(self._start_download)
        queue_layout.addWidget(self.btn_download)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        queue_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888;")
        queue_layout.addWidget(self.status_label)
        
        splitter.addWidget(queue_widget)
        
        # Set splitter sizes
        splitter.setSizes([700, 300])
        
        layout.addWidget(splitter)
    
    def _open_url(self, url: str):
        """Navigate to a URL."""
        if self.web_view:
            self.web_view.setUrl(QUrl(url))
        else:
            import webbrowser
            webbrowser.open(url)
    
    def _on_url_changed(self, url: QUrl):
        """Handle URL change in web view."""
        self.url_input.setText(url.toString())
        
        # Auto-detect if on a mod page
        url_str = url.toString()
        if "filedetails" in url_str and "id=" in url_str:
            self.btn_add.setStyleSheet("background-color: #2a5a2a;")
            self.btn_add.setText("➕ Add This Mod")
        elif "collection" in url_str.lower():
            self.btn_add.setStyleSheet("background-color: #5a5a2a;")
            self.btn_add.setText("📁 Add Collection")
        else:
            self.btn_add.setStyleSheet("")
            self.btn_add.setText("➕ Add to Queue")
    
    def _navigate_to_url(self):
        """Navigate to URL from input."""
        url = self.url_input.text().strip()
        if not url:
            return
        
        # Check if it's just an ID
        if url.isdigit():
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={url}"
        elif not url.startswith("http"):
            url = f"https://{url}"
        
        if self.web_view:
            self.web_view.setUrl(QUrl(url))
    
    def _add_current_to_queue(self):
        """Add current page/URL to download queue."""
        url = self.url_input.text().strip()
        if not url:
            return
        
        # Extract workshop ID(s)
        workshop_id = self._extract_workshop_id(url)
        if workshop_id:
            self._add_to_queue(workshop_id)
        else:
            self.status_label.setText("Could not find mod ID in URL")
    
    def _extract_workshop_id(self, url: str) -> Optional[str]:
        """Extract workshop ID from URL or direct input."""
        patterns = [
            r'steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)',
            r'steamcommunity\.com/workshop/filedetails/\?id=(\d+)',
            r'\?id=(\d+)',
            r'^(\d{9,12})$',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None$',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _add_to_queue(self, workshop_id: str, name: str = ""):
        """Add a mod to the download queue."""
        # Check for duplicates
        if workshop_id in self.queue_ids:
            self.status_label.setText(f"Mod {workshop_id} already in queue")
            return False
        
        # Check if already downloaded
        if self.dup_check.isChecked() and workshop_id in self.downloaded_ids:
            self.status_label.setText(f"Mod {workshop_id} already downloaded (skipped)")
            return False
        
        item = WorkshopItem(
            workshop_id=workshop_id,
            name=name or f"Workshop Mod {workshop_id}"
        )
        
        self.queue.append(item)
        self.queue_ids.add(workshop_id)
        
        list_item = DownloadQueueItem(item)
        self.queue_list.addItem(list_item)
        
        self._update_queue_count()
        self.status_label.setText(f"Added {workshop_id} to queue")
        self.mod_added.emit(workshop_id, name)
        
        return True
    
    def _add_batch(self):
        """Add multiple mods from batch input."""
        text = self.batch_input.toPlainText()
        lines = text.strip().split('\n')
        
        added = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            workshop_id = self._extract_workshop_id(line)
            if workshop_id and self._add_to_queue(workshop_id):
                added += 1
        
        self.batch_input.clear()
        self.status_label.setText(f"Added {added} mod(s) to queue")
    
    def _parse_collection(self):
        """Parse a Steam collection page for mod IDs."""
        url = self.url_input.text().strip()
        if not url:
            url = self.batch_input.toPlainText().strip()
        
        if "collection" not in url.lower() and "steamcommunity" not in url:
            self.status_label.setText("Please enter a collection URL")
            return
        
        self.status_label.setText("Parsing collection...")
        
        try:
            import urllib.request
            
            request = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                html = response.read().decode('utf-8', errors='replace')
            
            # Extract mod IDs
            pattern = r'sharedfiles/filedetails/\?id=(\d+)'
            matches = re.findall(pattern, html)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_ids = []
            for mid in matches:
                if mid not in seen:
                    seen.add(mid)
                    unique_ids.append(mid)
            
            if unique_ids:
                added = 0
                for wid in unique_ids:
                    if self._add_to_queue(wid):
                        added += 1
                self.status_label.setText(f"Added {added} mods from collection ({len(unique_ids)} total)")
            else:
                self.status_label.setText("No mods found in collection")
                
        except Exception as e:
            self.status_label.setText(f"Failed to parse collection: {e}")
    
    def _remove_selected(self):
        """Remove selected items from queue."""
        for item in self.queue_list.selectedItems():
            if isinstance(item, DownloadQueueItem):
                self.queue_ids.discard(item.workshop_item.workshop_id)
                self.queue = [q for q in self.queue if q.workshop_id != item.workshop_item.workshop_id]
            self.queue_list.takeItem(self.queue_list.row(item))
        
        self._update_queue_count()
    
    def _clear_queue(self):
        """Clear the entire queue."""
        self.queue.clear()
        self.queue_ids.clear()
        self.queue_list.clear()
        self._update_queue_count()
        self.status_label.setText("Queue cleared")
    
    def _update_queue_count(self):
        """Update the queue count display."""
        count = len(self.queue)
        self.queue_count.setText(f"({count})")
        self.btn_download.setEnabled(count > 0)
        self.btn_download.setText(f"⬇️ Download All ({count})")
    
    def _start_download(self):
        """Start downloading all queued mods."""
        if not self.queue:
            return
        
        workshop_ids = [item.workshop_id for item in self.queue]
        self.download_requested.emit(workshop_ids)
    
    def set_downloaded_ids(self, ids: set[str]):
        """Update the set of already-downloaded mod IDs."""
        self.downloaded_ids = ids
    
    def mark_downloaded(self, workshop_id: str):
        """Mark a mod as downloaded."""
        self.downloaded_ids.add(workshop_id)
        
        # Update queue display
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if isinstance(item, DownloadQueueItem):
                if item.workshop_item.workshop_id == workshop_id:
                    item.update_display("✓ Downloaded")
    
    def show_progress(self, current: int, total: int, status: str = ""):
        """Show download progress."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if status:
            self.status_label.setText(status)
    
    def hide_progress(self):
        """Hide progress bar."""
        self.progress_bar.setVisible(False)
    
    def get_queue_ids(self) -> list[str]:
        """Get list of workshop IDs in queue."""
        return [item.workshop_id for item in self.queue]


class WorkshopDownloadDialog(QWidget):
    """
    Standalone dialog/widget for Workshop downloads.
    Can be used as a tab or separate window.
    """
    
    download_complete = pyqtSignal()
    
    def __init__(self, downloader, downloaded_ids: set[str] = None, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Check steamcmd availability
        if not downloader.is_steamcmd_available():
            warning = QLabel(
                "<h3>⚠️ SteamCMD Not Found</h3>"
                f"<pre>{downloader.get_install_instructions()}</pre>"
            )
            warning.setWordWrap(True)
            layout.addWidget(warning)
            return
        
        # Workshop browser
        self.browser = WorkshopBrowser(downloaded_ids, self)
        self.browser.download_requested.connect(self._start_downloads)
        layout.addWidget(self.browser)
    
    def _start_downloads(self, workshop_ids: list[str]):
        """Start downloading mods."""
        if not workshop_ids:
            return
        
        self.browser.show_progress(0, len(workshop_ids), "Starting downloads...")
        
        # Download in thread
        self._download_thread = DownloadThread(self.downloader, workshop_ids)
        self._download_thread.progress.connect(self._on_progress)
        self._download_thread.finished.connect(self._on_finished)
        self._download_thread.start()
    
    def _on_progress(self, current: int, total: int, workshop_id: str, status: str):
        """Handle download progress."""
        self.browser.show_progress(current, total, f"{status}: {workshop_id}")
        if status == "Complete":
            self.browser.mark_downloaded(workshop_id)
    
    def _on_finished(self, success: int, failed: int):
        """Handle download completion."""
        self.browser.hide_progress()
        self.browser.status_label.setText(f"Downloaded {success} mod(s), {failed} failed")
        self.download_complete.emit()


class DownloadThread(QThread):
    """Background thread for downloading mods."""
    
    progress = pyqtSignal(int, int, str, str)  # current, total, workshop_id, status
    finished = pyqtSignal(int, int)  # success, failed
    
    def __init__(self, downloader, workshop_ids: list[str]):
        super().__init__()
        self.downloader = downloader
        self.workshop_ids = workshop_ids
    
    def run(self):
        success = 0
        failed = 0
        total = len(self.workshop_ids)
        
        for i, wid in enumerate(self.workshop_ids):
            self.progress.emit(i, total, wid, "Downloading")
            
            result = self.downloader.download_single(wid)
            
            if result:
                success += 1
                self.progress.emit(i + 1, total, wid, "Complete")
            else:
                failed += 1
                self.progress.emit(i + 1, total, wid, "Failed")
        
        self.finished.emit(success, failed)
