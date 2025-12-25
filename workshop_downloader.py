"""
Workshop Downloader for RimModManager
SteamCMD integration for downloading Workshop mods anonymously.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum
import threading
import queue


class DownloadStatus(Enum):
    """Download status states."""
    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    EXTRACTING = "Extracting"
    COMPLETE = "Complete"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class DownloadTask:
    """Represents a download task."""
    workshop_id: str
    name: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: int = 0
    error_message: str = ""
    output_path: Optional[Path] = None


class WorkshopDownloader:
    """
    Downloads RimWorld mods from Steam Workshop using SteamCMD.
    Supports anonymous downloads for public mods.
    """
    
    RIMWORLD_APPID = "294100"
    WORKSHOP_URL_PATTERNS = [
        r'steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)',
        r'steamcommunity\.com/workshop/filedetails/\?id=(\d+)',
        r'^(\d{7,12})$'  # Workshop IDs can be 7-12 digits$',  # Just the ID
    ]
    
    def __init__(self, download_path: Path = None, steamcmd_path: str = ""):
        self.download_path = download_path or Path.home() / "RimWorld_Workshop_Mods"
        self.steamcmd_path = steamcmd_path or self._find_steamcmd()
        self.download_queue: queue.Queue[DownloadTask] = queue.Queue()
        self.current_task: Optional[DownloadTask] = None
        self.is_downloading = False
        self._worker_thread: Optional[threading.Thread] = None
        self._cancel_flag = False
        
        # Callbacks
        self.on_progress: Optional[Callable[[DownloadTask], None]] = None
        self.on_complete: Optional[Callable[[DownloadTask], None]] = None
        self.on_error: Optional[Callable[[DownloadTask, str], None]] = None
    
    def _find_steamcmd(self) -> str:
        """Find SteamCMD executable - cross-platform."""
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            paths_to_check = [
                "steamcmd.exe",
                str(Path.home() / "steamcmd/steamcmd.exe"),
                "C:/steamcmd/steamcmd.exe",
                "C:/Program Files/steamcmd/steamcmd.exe",
                "C:/Program Files (x86)/steamcmd/steamcmd.exe",
            ]
        elif system == 'darwin':  # macOS
            paths_to_check = [
                "steamcmd",
                "/usr/local/bin/steamcmd",
                "/opt/homebrew/bin/steamcmd",
                str(Path.home() / "steamcmd/steamcmd.sh"),
                str(Path.home() / "Library/Application Support/Steam/steamcmd/steamcmd.sh"),
            ]
        else:  # Linux
            paths_to_check = [
                "steamcmd",  # In PATH
                "/usr/bin/steamcmd",
                "/usr/games/steamcmd",
                str(Path.home() / "steamcmd/steamcmd.sh"),
                str(Path.home() / ".local/share/Steam/steamcmd/steamcmd.sh"),
                str(Path.home() / ".steam/steam/steamcmd/steamcmd.sh"),
            ]
        
        for path in paths_to_check:
            if shutil.which(path):
                return path
            if Path(path).exists():
                return path
        
        return ""
    
    def is_steamcmd_available(self) -> bool:
        """Check if SteamCMD is available."""
        if not self.steamcmd_path:
            self.steamcmd_path = self._find_steamcmd()
        
        if not self.steamcmd_path:
            return False
        
        # Verify it's executable
        try:
            result = subprocess.run(
                [self.steamcmd_path, "+quit"],
                capture_output=True,
                timeout=30
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
            return False
    
    def get_install_instructions(self) -> str:
        """Get installation instructions for SteamCMD - cross-platform."""
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            return """
SteamCMD is required to download Workshop mods.

Windows Installation:
1. Download from: https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
2. Extract to C:\\steamcmd\\
3. Run steamcmd.exe once to complete setup
4. Restart this application

Or use Chocolatey:
    choco install steamcmd
"""
        elif system == 'darwin':  # macOS
            return """
SteamCMD is required to download Workshop mods.

macOS Installation (using Homebrew):
    brew install steamcmd

If you don't have Homebrew:
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install steamcmd

After installation, restart this application.
"""
        else:  # Linux
            return """
SteamCMD is required to download Workshop mods.

Arch Linux / CachyOS / EndeavourOS (AUR):
    yay -S steamcmd
    # or: paru -S steamcmd

Ubuntu / Debian:
    sudo apt install steamcmd

Fedora:
    sudo dnf install steamcmd

Manual installation (Arch):
    git clone https://aur.archlinux.org/steamcmd.git
    cd steamcmd
    makepkg -si

After installation, restart this application.
"""
    
    def extract_workshop_id(self, input_str: str) -> Optional[str]:
        """
        Extract Workshop ID from URL or direct ID input.
        Returns the ID or None if invalid.
        """
        input_str = input_str.strip()
        
        for pattern in self.WORKSHOP_URL_PATTERNS:
            match = re.search(pattern, input_str)
            if match:
                return match.group(1)
        
        return None
    
    def extract_workshop_ids_from_text(self, text: str) -> list[str]:
        """
        Extract multiple Workshop IDs from text (URLs, IDs, one per line).
        """
        ids = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Try to extract ID
            workshop_id = self.extract_workshop_id(line)
            if workshop_id and workshop_id not in ids:
                ids.append(workshop_id)
        
        return ids
    
    def add_to_queue(self, workshop_id: str, name: str = "") -> DownloadTask:
        """Add a mod to the download queue."""
        task = DownloadTask(
            workshop_id=workshop_id,
            name=name or f"Workshop Mod {workshop_id}"
        )
        self.download_queue.put(task)
        return task
    
    def add_batch_to_queue(self, workshop_ids: list[str]) -> list[DownloadTask]:
        """Add multiple mods to the download queue."""
        tasks = []
        for wid in workshop_ids:
            task = self.add_to_queue(wid)
            tasks.append(task)
        return tasks
    
    def start_downloads(self) -> None:
        """Start processing the download queue."""
        if self.is_downloading:
            return
        
        self._cancel_flag = False
        self._worker_thread = threading.Thread(target=self._download_worker, daemon=True)
        self._worker_thread.start()
    
    def cancel_downloads(self) -> None:
        """Cancel all pending downloads."""
        self._cancel_flag = True
        # Clear the queue
        while not self.download_queue.empty():
            try:
                task = self.download_queue.get_nowait()
                task.status = DownloadStatus.CANCELLED
            except queue.Empty:
                break
    
    def _download_worker(self) -> None:
        """Worker thread for processing downloads."""
        self.is_downloading = True
        
        while not self.download_queue.empty() and not self._cancel_flag:
            try:
                task = self.download_queue.get(timeout=1)
                self.current_task = task
                self._download_mod(task)
                self.download_queue.task_done()
            except queue.Empty:
                break
            except (OSError, IOError, subprocess.SubprocessError) as e:
                if self.current_task:
                    self.current_task.status = DownloadStatus.FAILED
                    self.current_task.error_message = str(e)
                    if self.on_error:
                        self.on_error(self.current_task, str(e))
        
        self.is_downloading = False
        self.current_task = None
    
    def _download_mod(self, task: DownloadTask) -> bool:
        """
        Download a single mod using SteamCMD.
        Returns True if successful.
        """
        task.status = DownloadStatus.DOWNLOADING
        if self.on_progress:
            self.on_progress(task)
        
        # Ensure download directory exists
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # Create temp directory for SteamCMD download
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Build SteamCMD command
            cmd = [
                self.steamcmd_path,
                "+force_install_dir", str(temp_path),
                "+login", "anonymous",
                "+workshop_download_item", self.RIMWORLD_APPID, task.workshop_id,
                "+quit"
            ]
            
            try:
                # Run SteamCMD
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # Monitor output for progress
                output_lines = []
                for line in process.stdout:
                    output_lines.append(line)
                    
                    # Parse progress if possible
                    if "Downloading" in line:
                        task.progress = 25
                    elif "downloading" in line.lower():
                        # Try to extract percentage
                        match = re.search(r'(\d+)%', line)
                        if match:
                            task.progress = int(match.group(1))
                    elif "Success" in line:
                        task.progress = 100
                    
                    if self.on_progress:
                        self.on_progress(task)
                    
                    if self._cancel_flag:
                        process.terminate()
                        task.status = DownloadStatus.CANCELLED
                        return False
                
                process.wait()
                
                if process.returncode != 0:
                    task.status = DownloadStatus.FAILED
                    task.error_message = "SteamCMD returned error. Check if mod ID is valid."
                    if self.on_error:
                        self.on_error(task, task.error_message)
                    return False
                
                # Find downloaded mod
                workshop_content = temp_path / "steamapps/workshop/content" / self.RIMWORLD_APPID / task.workshop_id
                
                if not workshop_content.exists():
                    task.status = DownloadStatus.FAILED
                    task.error_message = "Download completed but mod folder not found."
                    if self.on_error:
                        self.on_error(task, task.error_message)
                    return False
                
                # Move to final destination
                task.status = DownloadStatus.EXTRACTING
                if self.on_progress:
                    self.on_progress(task)
                
                final_path = self.download_path / task.workshop_id
                
                # Remove existing if present
                if final_path.exists():
                    shutil.rmtree(final_path)
                
                # Move downloaded mod
                shutil.move(str(workshop_content), str(final_path))
                
                task.output_path = final_path
                task.status = DownloadStatus.COMPLETE
                task.progress = 100
                
                if self.on_complete:
                    self.on_complete(task)
                
                return True
                
            except subprocess.TimeoutExpired:
                task.status = DownloadStatus.FAILED
                task.error_message = "Download timed out."
                if self.on_error:
                    self.on_error(task, task.error_message)
                return False
            except (OSError, IOError, subprocess.SubprocessError) as e:
                task.status = DownloadStatus.FAILED
                task.error_message = str(e)
                if self.on_error:
                    self.on_error(task, task.error_message)
                return False
    
    def download_single(self, workshop_id: str) -> Optional[Path]:
        """
        Download a single mod synchronously.
        Returns the path to the downloaded mod or None if failed.
        """
        task = DownloadTask(workshop_id=workshop_id)
        success = self._download_mod(task)
        return task.output_path if success else None
    
    def parse_collection_page(self, collection_url: str) -> list[str]:
        """
        Parse a Steam Workshop collection page to extract mod IDs.
        Requires internet access.
        """
        try:
            import urllib.request
            import urllib.error
            
            # Fetch the collection page
            request = urllib.request.Request(
                collection_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                html = response.read().decode('utf-8', errors='replace')
            
            # Extract mod IDs from the collection page
            # Workshop items are usually in sharedfiles/filedetails/?id=XXXXX links
            pattern = r'sharedfiles/filedetails/\?id=(\d+)'
            matches = re.findall(pattern, html)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_ids = []
            for mid in matches:
                if mid not in seen:
                    seen.add(mid)
                    unique_ids.append(mid)
            
            return unique_ids
            
        except urllib.error.URLError as e:
            print(f"Network error parsing collection: {e}")
            return []
        except urllib.error.HTTPError as e:
            print(f"HTTP error parsing collection: {e.code}")
            return []
        except (OSError, ValueError) as e:
            print(f"Failed to parse collection: {e}")
            return []
    
    def load_ids_from_file(self, file_path: Path) -> list[str]:
        """Load workshop IDs from a text file (one per line)."""
        ids = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            ids = self.extract_workshop_ids_from_text(content)
        except (IOError, PermissionError) as e:
            print(f"Failed to read file: {e}")
        
        return ids
    
    def get_queue_status(self) -> dict:
        """Get current download queue status."""
        return {
            "is_downloading": self.is_downloading,
            "queue_size": self.download_queue.qsize(),
            "current_task": self.current_task,
        }


class ModInstaller:
    """
    Handles installing/activating mods via symlinks.
    """
    
    def __init__(self, game_mods_path: Path):
        self.game_mods_path = game_mods_path
    
    def clear_symlinks(self) -> int:
        """
        Remove all symbolic links from the game's Mods folder.
        Returns the number of links removed.
        """
        removed = 0
        
        if not self.game_mods_path.exists():
            return 0
        
        for item in self.game_mods_path.iterdir():
            if item.is_symlink():
                try:
                    item.unlink()
                    removed += 1
                except (OSError, PermissionError) as e:
                    print(f"Failed to remove symlink {item}: {e}")
        
        return removed
    
    def create_symlink(self, source_path: Path, link_name: str = None) -> bool:
        """
        Create a symbolic link in the game's Mods folder.
        On Windows, falls back to directory junction if symlink fails.
        Returns True if successful.
        """
        import platform
        
        if not source_path.exists():
            return False
        
        link_name = link_name or source_path.name
        link_path = self.game_mods_path / link_name
        
        # Remove existing link/folder with same name
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_symlink():
                link_path.unlink()
            else:
                # Don't remove actual folders
                return False
        
        try:
            link_path.symlink_to(source_path)
            return True
        except (OSError, PermissionError) as e:
            # On Windows, symlinks require admin or Developer Mode
            # Fall back to directory junction (mklink /J) which doesn't require elevation
            if platform.system().lower() == 'windows':
                try:
                    import subprocess
                    # Use mklink /J for directory junction (no admin required)
                    result = subprocess.run(
                        ['cmd', '/c', 'mklink', '/J', str(link_path), str(source_path)],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        return True
                    print(f"Failed to create junction: {result.stderr}")
                except (subprocess.SubprocessError, FileNotFoundError, OSError) as je:
                    print(f"Failed to create junction: {je}")
            
            print(f"Failed to create symlink: {e}")
            return False
    
    def install_mods(self, mod_paths: list[Path], clear_existing: bool = True) -> dict[Path, bool]:
        """
        Install multiple mods by creating symlinks.
        Returns dict of path -> success status.
        """
        results = {}
        
        # Ensure mods folder exists
        self.game_mods_path.mkdir(parents=True, exist_ok=True)
        
        # Clear existing symlinks if requested
        if clear_existing:
            self.clear_symlinks()
        
        for mod_path in mod_paths:
            results[mod_path] = self.create_symlink(mod_path)
        
        return results
    
    def get_installed_mods(self) -> list[Path]:
        """Get list of currently installed (symlinked) mods."""
        mods = []
        
        if not self.game_mods_path.exists():
            return mods
        
        for item in self.game_mods_path.iterdir():
            if item.is_symlink():
                # Get the actual target
                target = item.resolve()
                if target.exists():
                    mods.append(target)
        
        return mods
    
    def get_symlink_targets(self) -> dict[str, Path]:
        """Get mapping of symlink names to their targets."""
        targets = {}
        
        if not self.game_mods_path.exists():
            return targets
        
        for item in self.game_mods_path.iterdir():
            if item.is_symlink():
                try:
                    targets[item.name] = item.resolve()
                except OSError:
                    pass
        
        return targets


def main():
    """Test the workshop downloader."""
    import sys
    
    downloader = WorkshopDownloader()
    
    print("RimWorld Workshop Downloader")
    print("=" * 40)
    
    # Check SteamCMD
    if downloader.is_steamcmd_available():
        print(f"SteamCMD found: {downloader.steamcmd_path}")
    else:
        print("SteamCMD not found!")
        print(downloader.get_install_instructions())
        return
    
    # Test URL parsing
    test_urls = [
        "https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077",
        "steamcommunity.com/workshop/filedetails/?id=818773962",
        "2009463077",
    ]
    
    print("\nTesting URL parsing:")
    for url in test_urls:
        result = downloader.extract_workshop_id(url)
        print(f"  {url[:50]}... -> {result}")
    
    # If argument provided, try to download
    if len(sys.argv) > 1:
        workshop_id = downloader.extract_workshop_id(sys.argv[1])
        if workshop_id:
            print(f"\nDownloading mod {workshop_id}...")
            
            def on_progress(task):
                print(f"  Status: {task.status.value} ({task.progress}%)")
            
            downloader.on_progress = on_progress
            result = downloader.download_single(workshop_id)
            
            if result:
                print(f"Downloaded to: {result}")
            else:
                print("Download failed!")
        else:
            print(f"Invalid workshop ID/URL: {sys.argv[1]}")


if __name__ == "__main__":
    main()
