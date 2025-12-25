"""
Download Manager with Live Logging for RimModManager
Provides real-time SteamCMD output and download progress.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QProgressBar, QGroupBox, QFrame,
    QSplitter, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QTextCursor, QColor


class DownloadStatus(Enum):
    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    EXTRACTING = "Extracting"
    COMPLETE = "Complete"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class DownloadItem:
    """A single download item."""
    workshop_id: str
    name: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: int = 0
    error: str = ""


class SteamCMDChecker:
    """Utility to check and help install SteamCMD - cross-platform."""
    
    @staticmethod
    def get_platform() -> str:
        """Get current platform."""
        import platform
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'windows':
            return 'windows'
        return 'linux'
    
    @staticmethod
    def find_steamcmd() -> Optional[str]:
        """Find SteamCMD executable - cross-platform."""
        plat = SteamCMDChecker.get_platform()
        
        if plat == 'windows':
            paths = [
                "steamcmd.exe",
                str(Path.home() / "steamcmd/steamcmd.exe"),
                "C:/steamcmd/steamcmd.exe",
                "C:/Program Files/steamcmd/steamcmd.exe",
                "C:/Program Files (x86)/steamcmd/steamcmd.exe",
            ]
        elif plat == 'macos':
            paths = [
                "steamcmd",
                "/usr/local/bin/steamcmd",
                "/opt/homebrew/bin/steamcmd",
                str(Path.home() / "steamcmd/steamcmd.sh"),
                str(Path.home() / "Library/Application Support/Steam/steamcmd/steamcmd.sh"),
            ]
        else:  # Linux
            paths = [
                "steamcmd",
                "/usr/bin/steamcmd",
                "/usr/games/steamcmd",
                str(Path.home() / "steamcmd/steamcmd.sh"),
                str(Path.home() / ".local/share/Steam/steamcmd/steamcmd.sh"),
            ]
        
        for path in paths:
            if shutil.which(path):
                return path
            if Path(path).exists():
                return path
        return None
    
    @staticmethod
    def is_available() -> bool:
        """Check if SteamCMD is available."""
        return SteamCMDChecker.find_steamcmd() is not None
    
    @staticmethod
    def get_install_command() -> str:
        """Get the install command for the current system."""
        plat = SteamCMDChecker.get_platform()
        
        if plat == 'windows':
            return (
                "Download from: https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip\n"
                "Extract to C:\\steamcmd\\ and run steamcmd.exe"
            )
        elif plat == 'macos':
            if shutil.which("brew"):
                return "brew install steamcmd"
            return (
                "Install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n"
                "Then: brew install steamcmd"
            )
        else:  # Linux
            # Check for AUR helpers
            if shutil.which("yay"):
                return "yay -S steamcmd"
            elif shutil.which("paru"):
                return "paru -S steamcmd"
            elif shutil.which("pamac"):
                return "pamac build steamcmd"
            elif shutil.which("apt"):
                return "sudo apt install steamcmd"
            elif shutil.which("dnf"):
                return "sudo dnf install steamcmd"
            else:
                return "git clone https://aur.archlinux.org/steamcmd.git && cd steamcmd && makepkg -si"


def get_mod_name_from_path(mod_path: Path) -> str:
    """Extract mod name from About.xml in the mod folder."""
    about_xml = mod_path / "About" / "About.xml"
    if not about_xml.exists():
        about_xml = mod_path / "About" / "about.xml"
    
    if about_xml.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(about_xml)
            root = tree.getroot()
            name_elem = root.find("name")
            if name_elem is not None and name_elem.text:
                return name_elem.text.strip()
        except (ET.ParseError, OSError, IOError):
            pass
    
    return mod_path.name


class LiveDownloadWorker(QThread):
    """
    Download worker with live output streaming.
    Uses batch download mode - single SteamCMD session for all mods.
    """
    
    # Signals
    log_output = pyqtSignal(str)  # Real-time log line
    item_started = pyqtSignal(str)  # workshop_id
    item_progress = pyqtSignal(str, int)  # workshop_id, progress %
    item_complete = pyqtSignal(str, str, str)  # workshop_id, output_path, mod_name
    item_failed = pyqtSignal(str, str)  # workshop_id, error
    all_complete = pyqtSignal(int, int)  # success_count, fail_count
    
    RIMWORLD_APPID = "294100"
    
    def __init__(self, steamcmd_path: str, workshop_ids: list[str], download_path: Path):
        super().__init__()
        self.steamcmd_path = steamcmd_path
        self.workshop_ids = workshop_ids
        self.download_path = download_path
        self._cancelled = False
        self._process = None
    
    def cancel(self):
        """Cancel the download."""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except (OSError, ProcessLookupError):
                pass
    
    def run(self):
        success = 0
        failed = 0
        skipped = 0
        
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # Check which mods already exist
        ids_to_download = []
        for wid in self.workshop_ids:
            existing_path = self.download_path / wid
            if existing_path.exists() and self._is_valid_mod(existing_path):
                # Mod already exists, skip download
                mod_name = get_mod_name_from_path(existing_path)
                self.log_output.emit(f"[SKIP] Mod {wid} already exists: {mod_name}")
                self.item_complete.emit(wid, str(existing_path), mod_name)
                skipped += 1
            else:
                ids_to_download.append(wid)
        
        if not ids_to_download:
            self.log_output.emit(f"\n[INFO] All {len(self.workshop_ids)} mod(s) already downloaded!")
            self.all_complete.emit(skipped, 0)
            return
        
        # Use batch download - single SteamCMD session for remaining mods
        self.log_output.emit(f"\n[INFO] Starting batch download of {len(ids_to_download)} mod(s)")
        if skipped > 0:
            self.log_output.emit(f"[INFO] Skipped {skipped} already downloaded mod(s)")
        self.log_output.emit(f"[INFO] Using single SteamCMD session for efficiency\n")
        
        results = self._download_batch(ids_to_download)
        
        for wid, result_path in results.items():
            if result_path:
                mod_name = get_mod_name_from_path(result_path)
                success += 1
                self.item_complete.emit(wid, str(result_path), mod_name)
                self.log_output.emit(f"[SUCCESS] {mod_name} ({wid}) -> {result_path}")
            else:
                failed += 1
                self.item_failed.emit(wid, "Download failed")
        
        self.all_complete.emit(success + skipped, failed)
    
    def _is_valid_mod(self, mod_path: Path) -> bool:
        """Check if a mod folder is valid (has About.xml)."""
        about_xml = mod_path / "About" / "About.xml"
        if about_xml.exists():
            return True
        # Try lowercase
        about_xml_lower = mod_path / "About" / "about.xml"
        return about_xml_lower.exists()
    
    def _download_batch(self, workshop_ids: list[str]) -> dict[str, Optional[Path]]:
        """Download multiple mods in a single SteamCMD session."""
        results = {wid: None for wid in workshop_ids}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Build batch command - login once, download all
            cmd = [
                self.steamcmd_path,
                "+force_install_dir", str(temp_path),
                "+login", "anonymous",
            ]
            
            # Add all workshop items to download
            for wid in workshop_ids:
                cmd.extend(["+workshop_download_item", self.RIMWORLD_APPID, wid])
                self.item_started.emit(wid)
            
            cmd.append("+quit")
            
            self.log_output.emit(f"{'='*50}")
            self.log_output.emit(f"[BATCH] Downloading {len(workshop_ids)} mods in single session")
            self.log_output.emit(f"{'='*50}\n")
            
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                current_wid = None
                logged_in = False
                
                # Stream output with filtering
                if self._process.stdout:
                    for line in self._process.stdout:
                        line = line.rstrip()
                        if not line:
                            continue
                    
                        # Filter out noisy/repetitive lines
                        skip_patterns = [
                            "Redirecting stderr",
                            "Logging directory",
                            "UpdateUI: skip",
                            "Steam Console Client",
                            "type 'quit'",
                            "[0m",  # ANSI codes
                            "CProcessWorkItem",
                            "Work Item",
                            "d3ddriverquery",
                        ]
                    
                        should_skip = any(p in line for p in skip_patterns)
                    
                        # Clean ANSI codes
                        clean_line = re.sub(r'\[0m', '', line).strip()
                    
                        if not clean_line or should_skip:
                            continue
                    
                        # Detect login success (only show once)
                        if "Connecting anonymously" in clean_line and not logged_in:
                            self.log_output.emit("[SESSION] Connecting to Steam...")
                            continue
                        elif "Waiting for user info" in clean_line and not logged_in:
                            logged_in = True
                            self.log_output.emit("[SESSION] Connected to Steam (session will be reused)")
                            continue
                        elif logged_in and ("Connecting anonymously" in clean_line or "Waiting for" in clean_line):
                            # Skip repeated connection messages
                            continue
                    
                        # Detect which mod is being downloaded
                        download_match = re.search(r'Downloading item (\d+)', clean_line)
                        if download_match:
                            current_wid = download_match.group(1)
                            self.log_output.emit(f"\n[DOWNLOAD] Mod {current_wid}...")
                            self.item_progress.emit(current_wid, 10)
                            continue
                    
                        # Detect success
                        success_match = re.search(r'Success.*Downloaded item (\d+)', clean_line)
                        if success_match:
                            wid = success_match.group(1)
                            self.item_progress.emit(wid, 100)
                            self.log_output.emit(f"[OK] Mod {wid} downloaded")
                            continue
                    
                        # Show other relevant output
                        if "Loading Steam API" in clean_line:
                            self.log_output.emit("[SESSION] Loading Steam API...")
                        elif "Unloading Steam API" in clean_line:
                            self.log_output.emit("[SESSION] Finishing up...")
                        elif "ERROR" in clean_line.upper() or "FAILED" in clean_line.upper():
                            self.log_output.emit(f"[ERROR] {clean_line}")
                        elif "%" in clean_line:
                            # Progress percentage
                            self.log_output.emit(f"  {clean_line}")
                    
                        if self._cancelled:
                            self._process.terminate()
                            return results
                
                self._process.wait()
                
                if self._process.returncode != 0:
                    self.log_output.emit(f"\n[WARNING] SteamCMD exited with code {self._process.returncode}")
                
                # Move downloaded mods to final location
                self.log_output.emit(f"\n[INFO] Moving mods to {self.download_path}...")
                
                workshop_content_base = temp_path / "steamapps/workshop/content" / self.RIMWORLD_APPID
                
                for wid in workshop_ids:
                    workshop_content = workshop_content_base / wid
                    
                    if workshop_content.exists():
                        final_path = self.download_path / wid
                        if final_path.exists():
                            shutil.rmtree(final_path)
                        
                        shutil.move(str(workshop_content), str(final_path))
                        results[wid] = final_path
                    else:
                        self.log_output.emit(f"[WARNING] Mod {wid} folder not found after download")
                
            except (OSError, IOError, subprocess.SubprocessError) as e:
                self.log_output.emit(f"[EXCEPTION] {e}")
        
        return results


class DownloadLogWidget(QWidget):
    """
    Widget showing live download progress and logs.
    """
    
    download_complete = pyqtSignal(str)  # Emits download path for auto-add
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._worker: Optional[LiveDownloadWorker] = None
        self._items: dict[str, DownloadItem] = {}
        self._download_path: Optional[Path] = None
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QHBoxLayout()
        self.title_label = QLabel("📥 Download Manager")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header.addWidget(self.title_label)
        header.addStretch()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888;")
        header.addWidget(self.status_label)
        layout.addLayout(header)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Splitter for queue and log
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Download queue
        queue_group = QGroupBox("Download Queue")
        queue_layout = QVBoxLayout(queue_group)
        queue_layout.setContentsMargins(4, 4, 4, 4)
        
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(150)
        queue_layout.addWidget(self.queue_list)
        
        splitter.addWidget(queue_group)
        
        # Live log
        log_group = QGroupBox("Live Log (SteamCMD Output)")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("monospace", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        splitter.addWidget(log_group)
        splitter.setSizes([150, 300])
        
        layout.addWidget(splitter, 1)
        
        # Controls
        controls = QHBoxLayout()
        
        self.btn_cancel = QPushButton("❌ Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_downloads)
        controls.addWidget(self.btn_cancel)
        
        self.btn_clear = QPushButton("🗑️ Clear Log")
        self.btn_clear.clicked.connect(self._clear_log)
        controls.addWidget(self.btn_clear)
        
        controls.addStretch()
        
        self.btn_close = QPushButton("✓ Done")
        self.btn_close.clicked.connect(self._emit_complete)
        controls.addWidget(self.btn_close)
        
        layout.addLayout(controls)
    
    def _emit_complete(self):
        """Emit complete signal with download path."""
        path = str(self._download_path) if self._download_path else ""
        self.download_complete.emit(path)
    
    def start_downloads(self, steamcmd_path: str, workshop_ids: list[str], download_path: Path):
        """Start downloading mods with live logging."""
        if self._worker and self._worker.isRunning():
            return
        
        self._download_path = download_path
        
        # Clear previous state
        self.queue_list.clear()
        self._items.clear()
        self.log_text.clear()
        
        self._log_info("Fetching mod names from Steam Workshop...")
        
        # Fetch mod names from Steam API
        mod_names = self._fetch_mod_names(workshop_ids)
        
        # Add items to queue
        for wid in workshop_ids:
            name = mod_names.get(wid, f"Workshop Mod {wid}")
            item = DownloadItem(workshop_id=wid, name=name)
            self._items[wid] = item
            
            # Check if already exists
            existing_path = download_path / wid
            if existing_path.exists():
                # Try to get name from local About.xml
                local_name = get_mod_name_from_path(existing_path)
                if local_name and local_name != wid:
                    name = local_name
                    item.name = name
                list_item = QListWidgetItem(f"✓ {name} - Already downloaded")
                list_item.setForeground(QColor("#888888"))
            else:
                list_item = QListWidgetItem(f"⏳ {name} - Pending")
            
            list_item.setData(Qt.ItemDataRole.UserRole, wid)
            self.queue_list.addItem(list_item)
        
        # Setup progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(workshop_ids))
        self.progress_bar.setValue(0)
        
        self.status_label.setText(f"Downloading 0/{len(workshop_ids)}...")
        self.btn_cancel.setEnabled(True)
        
        # Start worker
        self._worker = LiveDownloadWorker(steamcmd_path, workshop_ids, download_path)
        self._worker.log_output.connect(self._on_log)
        self._worker.item_started.connect(self._on_item_started)
        self._worker.item_progress.connect(self._on_item_progress)
        self._worker.item_complete.connect(self._on_item_complete)
        self._worker.item_failed.connect(self._on_item_failed)
        self._worker.all_complete.connect(self._on_all_complete)
        self._worker.finished.connect(self._cleanup_worker)  # Clean up when done
        self._worker.start()
        
        self._log_info("Download manager started...")
    
    def _cleanup_worker(self):
        """Clean up finished worker to prevent memory leak."""
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
    
    def _fetch_mod_names(self, workshop_ids: list[str]) -> dict[str, str]:
        """Fetch mod names from Steam Workshop API."""
        import urllib.request
        import urllib.parse
        import json
        
        names = {}
        
        try:
            # Steam API endpoint
            url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            
            # Build POST data
            data = {"itemcount": len(workshop_ids)}
            for i, wid in enumerate(workshop_ids):
                data[f"publishedfileids[{i}]"] = wid
            
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            
            request = urllib.request.Request(url, data=encoded_data, method='POST')
            request.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            if 'response' in result and 'publishedfiledetails' in result['response']:
                for item in result['response']['publishedfiledetails']:
                    wid = item.get('publishedfileid', '')
                    title = item.get('title', '')
                    if wid and title:
                        names[wid] = title
            
            self._log_info(f"Fetched {len(names)} mod names from Steam")
            
        except Exception as e:
            self._log_info(f"Could not fetch mod names: {e}")
        
        return names
    
    def _on_log(self, line: str):
        """Handle log output."""
        # Color code the output
        if "[ERROR]" in line or "[EXCEPTION]" in line or "[FAILED]" in line or "[WARNING]" in line:
            self.log_text.setTextColor(QColor("#ff6b6b"))
        elif "[SUCCESS]" in line or "[OK]" in line:
            self.log_text.setTextColor(QColor("#69db7c"))
        elif "[SESSION]" in line or "[BATCH]" in line or "[INFO]" in line:
            self.log_text.setTextColor(QColor("#74c0fc"))
        elif "[DOWNLOAD]" in line:
            self.log_text.setTextColor(QColor("#ffd43b"))
        elif line.startswith("="):
            self.log_text.setTextColor(QColor("#ffd43b"))
        else:
            self.log_text.setTextColor(QColor("#d4d4d4"))
        
        self.log_text.append(line)
        
        # Auto-scroll
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
    
    def _log_info(self, msg: str):
        """Log an info message."""
        self.log_text.setTextColor(QColor("#74c0fc"))
        self.log_text.append(f"[INFO] {msg}")
    
    def _on_item_started(self, workshop_id: str):
        """Handle item download started."""
        item = self._items.get(workshop_id)
        name = item.name if item else f"Mod {workshop_id}"
        self._update_queue_item(workshop_id, "⬇️", f"{name} - Queued...")
    
    def _on_item_progress(self, workshop_id: str, progress: int):
        """Handle item progress."""
        item = self._items.get(workshop_id)
        name = item.name if item else f"Mod {workshop_id}"
        self._update_queue_item(workshop_id, "⬇️", f"{name} - {progress}%")
    
    def _on_item_complete(self, workshop_id: str, path: str, mod_name: str):
        """Handle item complete with mod name."""
        # Update item with actual mod name
        if workshop_id in self._items:
            self._items[workshop_id].name = mod_name
        
        self._update_queue_item(workshop_id, "✅", f"{mod_name}")
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        
        done = self.progress_bar.value()
        total = self.progress_bar.maximum()
        self.status_label.setText(f"Downloaded {done}/{total}...")
    
    def _on_item_failed(self, workshop_id: str, error: str):
        """Handle item failed."""
        self._update_queue_item(workshop_id, "❌", f"Failed: {error}")
        self.progress_bar.setValue(self.progress_bar.value() + 1)
    
    def _on_all_complete(self, success: int, failed: int):
        """Handle all downloads complete."""
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        self.status_label.setText(f"Complete: {success} succeeded, {failed} failed")
        self._log_info(f"All downloads complete: {success} succeeded, {failed} failed")
        
        if success > 0:
            self._log_info(f"Mods saved to: {self._download_path}")
            self._log_info("Click 'Done' to refresh mod list and auto-add download path.")
    
    def _update_queue_item(self, workshop_id: str, icon: str, status: str):
        """Update a queue item's display."""
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == workshop_id:
                item.setText(f"{icon} {status}")
                break
    
    def _cancel_downloads(self):
        """Cancel current downloads."""
        if self._worker:
            self._worker.cancel()
            self._log_info("Cancelling downloads...")
    
    def _clear_log(self):
        """Clear the log."""
        self.log_text.clear()
    
    def is_downloading(self) -> bool:
        """Check if downloads are in progress."""
        return self._worker is not None and self._worker.isRunning()


class SteamCMDSetupWidget(QWidget):
    """
    Widget to help users install SteamCMD.
    """
    
    setup_complete = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Warning
        warning = QLabel(
            "<h2>⚠️ SteamCMD Not Found</h2>"
            "<p>SteamCMD is required to download mods from Steam Workshop.</p>"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        
        # Install command
        cmd = SteamCMDChecker.get_install_command()
        cmd_label = QLabel(f"<p>Install with:</p><pre>{cmd}</pre>")
        cmd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(cmd_label)
        
        # Manual instructions
        manual = QLabel(
            "<p><b>Manual steps:</b></p>"
            "<ol>"
            "<li>Open a terminal</li>"
            "<li>Run the command above</li>"
            "<li>Wait for installation to complete</li>"
            "<li>Click 'Check Again' below</li>"
            "</ol>"
        )
        manual.setWordWrap(True)
        layout.addWidget(manual)
        
        # Log area for auto-install attempt
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setVisible(False)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log_text)
        
        layout.addStretch()
        
        # Buttons
        buttons = QHBoxLayout()
        
        self.btn_check = QPushButton("🔄 Check Again")
        self.btn_check.clicked.connect(self._check_steamcmd)
        buttons.addWidget(self.btn_check)
        
        buttons.addStretch()
        layout.addLayout(buttons)
    
    def _check_steamcmd(self):
        """Check if SteamCMD is now available."""
        if SteamCMDChecker.is_available():
            self.setup_complete.emit()
        else:
            self.log_text.setVisible(True)
            self.log_text.append("SteamCMD not found. Please install it using the command above.")
