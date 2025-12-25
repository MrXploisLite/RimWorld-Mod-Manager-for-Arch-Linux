"""
Game Detector for RimModManager
Detects all RimWorld installations on Linux including:
- Steam native Linux version
- Steam Windows version via Proton
- Non-Steam/cracked versions via Wine/Proton
- Flatpak Steam installations
- Custom user-defined paths
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class InstallationType(Enum):
    """Types of RimWorld installations."""
    STEAM_NATIVE = "Steam (Native Linux)"
    STEAM_PROTON = "Steam (Proton/Windows)"
    FLATPAK_STEAM = "Flatpak Steam"
    PROTON_STANDALONE = "Standalone (Proton/Wine)"
    CUSTOM = "Custom Installation"
    UNKNOWN = "Unknown"


@dataclass
class RimWorldInstallation:
    """Represents a detected RimWorld installation."""
    path: Path
    install_type: InstallationType
    version: str = ""
    has_mods_folder: bool = False
    has_data_folder: bool = False
    is_windows_build: bool = False
    proton_prefix: Optional[Path] = None
    save_path: Optional[Path] = None
    config_path: Optional[Path] = None
    
    def __str__(self) -> str:
        return f"{self.install_type.value}: {self.path}"
    
    def display_name(self) -> str:
        """Generate a user-friendly display name."""
        type_short = {
            InstallationType.STEAM_NATIVE: "[Steam Native]",
            InstallationType.STEAM_PROTON: "[Steam Proton]",
            InstallationType.FLATPAK_STEAM: "[Flatpak]",
            InstallationType.PROTON_STANDALONE: "[Standalone]",
            InstallationType.CUSTOM: "[Custom]",
            InstallationType.UNKNOWN: "[Unknown]",
        }
        prefix = type_short.get(self.install_type, "")
        return f"{prefix} {self.path}"


class GameDetector:
    """
    Detects RimWorld installations across various Linux setups.
    Supports Steam native, Proton, Flatpak, Wine, and custom installations.
    """
    
    # RimWorld Steam AppID
    RIMWORLD_APPID = "294100"
    
    # Common RimWorld executable/data markers
    WINDOWS_MARKERS = [
        "RimWorldWin64.exe",
        "RimWorldWin64_Data",
        "RimWorldWin.exe",
        "RimWorldWin_Data",
    ]
    
    LINUX_MARKERS = [
        "RimWorldLinux",
        "RimWorld",  # Could be Linux binary
    ]
    
    DATA_FOLDER_MARKERS = [
        "Data",  # Contains Core game data
        "Mods",  # Mods folder
    ]
    
    def __init__(self, custom_paths: list[str] = None):
        self.custom_paths = custom_paths or []
        self.installations: list[RimWorldInstallation] = []
    
    def detect_all(self) -> list[RimWorldInstallation]:
        """
        Detect all RimWorld installations.
        Returns a list of found installations.
        """
        self.installations = []
        
        # 1. Check standard Steam installation
        self._detect_steam_native()
        
        # 2. Check Proton prefixes for Windows version
        self._detect_steam_proton()
        
        # 3. Check Flatpak Steam
        self._detect_flatpak_steam()
        
        # 4. Check custom paths
        self._detect_custom_paths()
        
        # 5. Detect save/config paths for each installation
        for install in self.installations:
            self._detect_save_config_paths(install)
        
        return self.installations
    
    def _detect_steam_native(self) -> None:
        """Detect native Linux Steam installation."""
        steam_paths = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
            Path.home() / ".steam/debian-installation",
        ]
        
        for steam_path in steam_paths:
            rimworld_path = steam_path / "steamapps/common/RimWorld"
            if rimworld_path.exists() and self._is_valid_rimworld(rimworld_path):
                is_windows = self._is_windows_build(rimworld_path)
                install = RimWorldInstallation(
                    path=rimworld_path,
                    install_type=InstallationType.STEAM_PROTON if is_windows else InstallationType.STEAM_NATIVE,
                    has_mods_folder=(rimworld_path / "Mods").exists(),
                    has_data_folder=(rimworld_path / "Data").exists(),
                    is_windows_build=is_windows,
                )
                if install not in self.installations:
                    self.installations.append(install)
                
                # If Windows build via Proton, find the prefix
                if is_windows:
                    prefix = self._find_proton_prefix(steam_path)
                    if prefix:
                        install.proton_prefix = prefix
    
    def _detect_steam_proton(self) -> None:
        """Detect RimWorld in Proton compatibility data."""
        steam_paths = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
        ]
        
        for steam_path in steam_paths:
            compatdata_path = steam_path / "steamapps/compatdata" / self.RIMWORLD_APPID
            if compatdata_path.exists():
                # The game files are usually in the common folder, but check prefix for saves
                prefix_path = compatdata_path / "pfx"
                if prefix_path.exists():
                    # Check if there's a game installed in common
                    rimworld_common = steam_path / "steamapps/common/RimWorld"
                    if rimworld_common.exists():
                        # Already detected in native check, but update prefix
                        for install in self.installations:
                            if install.path == rimworld_common:
                                install.proton_prefix = prefix_path
                                break
    
    def _detect_flatpak_steam(self) -> None:
        """Detect Flatpak Steam installation."""
        flatpak_steam_path = Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
        
        if flatpak_steam_path.exists():
            rimworld_path = flatpak_steam_path / "steamapps/common/RimWorld"
            if rimworld_path.exists() and self._is_valid_rimworld(rimworld_path):
                is_windows = self._is_windows_build(rimworld_path)
                
                # Find Flatpak Proton prefix
                prefix = None
                compatdata = flatpak_steam_path / "steamapps/compatdata" / self.RIMWORLD_APPID / "pfx"
                if compatdata.exists():
                    prefix = compatdata
                
                install = RimWorldInstallation(
                    path=rimworld_path,
                    install_type=InstallationType.FLATPAK_STEAM,
                    has_mods_folder=(rimworld_path / "Mods").exists(),
                    has_data_folder=(rimworld_path / "Data").exists(),
                    is_windows_build=is_windows,
                    proton_prefix=prefix,
                )
                self.installations.append(install)
    
    def _detect_custom_paths(self) -> None:
        """Detect installations in user-defined custom paths."""
        for path_str in self.custom_paths:
            path = Path(path_str)
            if path.exists() and self._is_valid_rimworld(path):
                is_windows = self._is_windows_build(path)
                install = RimWorldInstallation(
                    path=path,
                    install_type=InstallationType.CUSTOM,
                    has_mods_folder=(path / "Mods").exists(),
                    has_data_folder=(path / "Data").exists(),
                    is_windows_build=is_windows,
                )
                # Check if already detected
                if not any(i.path == path for i in self.installations):
                    self.installations.append(install)
    
    def _is_valid_rimworld(self, path: Path) -> bool:
        """
        Check if a path contains a valid RimWorld installation.
        Looks for game executables or data folders.
        """
        if not path.is_dir():
            return False
        
        # Check for Windows markers
        for marker in self.WINDOWS_MARKERS:
            if (path / marker).exists():
                return True
        
        # Check for Linux markers
        for marker in self.LINUX_MARKERS:
            marker_path = path / marker
            if marker_path.exists() and marker_path.is_file():
                return True
        
        # Check for Data folder (always present in valid installation)
        data_path = path / "Data"
        if data_path.exists() and (data_path / "Core").exists():
            return True
        
        return False
    
    def _is_windows_build(self, path: Path) -> bool:
        """Check if the installation is a Windows build."""
        for marker in self.WINDOWS_MARKERS:
            if (path / marker).exists():
                return True
        return False
    
    def _find_proton_prefix(self, steam_path: Path) -> Optional[Path]:
        """Find Proton prefix for RimWorld."""
        compatdata = steam_path / "steamapps/compatdata" / self.RIMWORLD_APPID / "pfx"
        if compatdata.exists():
            return compatdata
        return None
    
    def _detect_save_config_paths(self, install: RimWorldInstallation) -> None:
        """Detect save and config paths for an installation."""
        # For custom installations, check if there's a proton prefix nearby
        if install.install_type == InstallationType.CUSTOM and not install.proton_prefix:
            # Try to find proton prefix from game path
            # Check if game is in a Wine/Proton prefix structure
            game_path_str = str(install.path)
            if "drive_c" in game_path_str:
                # Extract prefix path (everything before drive_c)
                prefix_idx = game_path_str.find("drive_c")
                if prefix_idx > 0:
                    install.proton_prefix = Path(game_path_str[:prefix_idx])
                    install.is_windows_build = True
        
        if install.is_windows_build:
            # Windows build - check multiple possible prefix locations
            prefixes_to_check = []
            
            if install.proton_prefix:
                prefixes_to_check.append(install.proton_prefix)
            
            # Also check Steam compatdata
            steam_paths = [
                Path.home() / ".local/share/Steam",
                Path.home() / ".steam/steam",
            ]
            for steam_path in steam_paths:
                compatdata = steam_path / "steamapps/compatdata" / self.RIMWORLD_APPID / "pfx"
                if compatdata.exists():
                    prefixes_to_check.append(compatdata)
            
            # Search patterns for config/save folders
            search_patterns = [
                "drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios",
                "drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios",
            ]
            
            for prefix in prefixes_to_check:
                if not prefix or not prefix.exists():
                    continue
                    
                # Try exact path first
                base = prefix / "drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"
                if base.exists():
                    install.save_path = base / "Saves"
                    install.config_path = base / "Config"
                    install.proton_prefix = prefix
                    return
                
                # Try to find folder with rimworld in name
                alt_base = prefix / "drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios"
                if alt_base.exists():
                    try:
                        for folder in alt_base.iterdir():
                            if folder.is_dir() and "rimworld" in folder.name.lower():
                                install.save_path = folder / "Saves"
                                install.config_path = folder / "Config"
                                install.proton_prefix = prefix
                                return
                    except PermissionError:
                        continue
                
                # Try other user folders (not just steamuser)
                users_path = prefix / "drive_c/users"
                if users_path.exists():
                    try:
                        for user_folder in users_path.iterdir():
                            if user_folder.is_dir() and user_folder.name not in ("Public", "Default"):
                                ludeon_path = user_folder / "AppData/LocalLow/Ludeon Studios"
                                if ludeon_path.exists():
                                    for folder in ludeon_path.iterdir():
                                        if folder.is_dir() and "rimworld" in folder.name.lower():
                                            install.save_path = folder / "Saves"
                                            install.config_path = folder / "Config"
                                            install.proton_prefix = prefix
                                            return
                    except PermissionError:
                        continue
        
        # Native Linux build - standard Unity path
        native_paths = [
            Path.home() / ".config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios",
            Path.home() / ".config/unity3d/Ludeon Studios",
        ]
        
        for native_base in native_paths:
            if native_base.exists():
                if native_base.name == "RimWorld by Ludeon Studios":
                    install.save_path = native_base / "Saves"
                    install.config_path = native_base / "Config"
                    return
                else:
                    # Search for rimworld folder
                    try:
                        for folder in native_base.iterdir():
                            if folder.is_dir() and "rimworld" in folder.name.lower():
                                install.save_path = folder / "Saves"
                                install.config_path = folder / "Config"
                                return
                    except PermissionError:
                        continue
    
    def add_custom_path(self, path: str) -> Optional[RimWorldInstallation]:
        """
        Add and detect a custom installation path.
        Returns the installation if valid, None otherwise.
        """
        if path not in self.custom_paths:
            self.custom_paths.append(path)
        
        path_obj = Path(path)
        if path_obj.exists() and self._is_valid_rimworld(path_obj):
            is_windows = self._is_windows_build(path_obj)
            install = RimWorldInstallation(
                path=path_obj,
                install_type=InstallationType.CUSTOM,
                has_mods_folder=(path_obj / "Mods").exists(),
                has_data_folder=(path_obj / "Data").exists(),
                is_windows_build=is_windows,
            )
            self._detect_save_config_paths(install)
            
            if not any(i.path == path_obj for i in self.installations):
                self.installations.append(install)
            
            return install
        return None
    
    def find_workshop_mods_path(self, steam_path: Path = None) -> Optional[Path]:
        """Find the Steam Workshop mods folder for RimWorld."""
        if steam_path is None:
            steam_path = Path.home() / ".local/share/Steam"
        
        workshop_path = steam_path / "steamapps/workshop/content" / self.RIMWORLD_APPID
        if workshop_path.exists():
            return workshop_path
        
        # Try Flatpak
        flatpak_workshop = Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/workshop/content" / self.RIMWORLD_APPID
        if flatpak_workshop.exists():
            return flatpak_workshop
        
        return None
    
    def scan_wine_prefixes(self) -> list[RimWorldInstallation]:
        """
        Scan common Wine prefix locations for RimWorld installations.
        Used for non-Steam Wine/Proton setups.
        """
        found = []
        
        # Common Wine prefix locations
        wine_prefixes = [
            Path.home() / ".wine",
            Path.home() / ".wine32",
            Path.home() / ".wine64",
            Path.home() / "Games",  # Lutris default
            Path.home() / ".local/share/lutris/runners/wine",
            Path.home() / ".local/share/bottles",  # Bottles app
        ]
        
        for prefix_base in wine_prefixes:
            if not prefix_base.exists():
                continue
            
            # Search for RimWorld in Program Files
            search_paths = [
                "drive_c/Program Files/RimWorld",
                "drive_c/Program Files (x86)/RimWorld", 
                "drive_c/Games/RimWorld",
                "drive_c/GOG Games/RimWorld",
            ]
            
            # If this is a prefix directory, search directly
            if (prefix_base / "drive_c").exists():
                for search in search_paths:
                    rimworld_path = prefix_base / search
                    if rimworld_path.exists() and self._is_valid_rimworld(rimworld_path):
                        install = RimWorldInstallation(
                            path=rimworld_path,
                            install_type=InstallationType.PROTON_STANDALONE,
                            has_mods_folder=(rimworld_path / "Mods").exists(),
                            has_data_folder=(rimworld_path / "Data").exists(),
                            is_windows_build=True,
                            proton_prefix=prefix_base,
                        )
                        self._detect_save_config_paths(install)
                        found.append(install)
            else:
                # Search subdirectories (multiple prefixes)
                try:
                    for subdir in prefix_base.iterdir():
                        if subdir.is_dir() and (subdir / "drive_c").exists():
                            for search in search_paths:
                                rimworld_path = subdir / search
                                if rimworld_path.exists() and self._is_valid_rimworld(rimworld_path):
                                    install = RimWorldInstallation(
                                        path=rimworld_path,
                                        install_type=InstallationType.PROTON_STANDALONE,
                                        has_mods_folder=(rimworld_path / "Mods").exists(),
                                        has_data_folder=(rimworld_path / "Data").exists(),
                                        is_windows_build=True,
                                        proton_prefix=subdir,
                                    )
                                    self._detect_save_config_paths(install)
                                    found.append(install)
                except PermissionError:
                    continue
        
        # Add found installations to main list
        for install in found:
            if not any(i.path == install.path for i in self.installations):
                self.installations.append(install)
        
        return found
    
    def get_mods_folder(self, installation: RimWorldInstallation) -> Path:
        """Get the Mods folder path for an installation."""
        mods_path = installation.path / "Mods"
        if not mods_path.exists():
            mods_path.mkdir(parents=True, exist_ok=True)
        return mods_path
    
    def refresh(self) -> list[RimWorldInstallation]:
        """Re-scan for all installations."""
        return self.detect_all()


def main():
    """Test the game detector."""
    detector = GameDetector()
    installations = detector.detect_all()
    
    print("=" * 60)
    print("RimWorld Installation Detector")
    print("=" * 60)
    
    if not installations:
        print("No RimWorld installations found.")
        print("\nSearched locations:")
        print("  - ~/.local/share/Steam/steamapps/common/RimWorld")
        print("  - ~/.steam/steam/steamapps/common/RimWorld")
        print("  - ~/.var/app/com.valvesoftware.Steam/... (Flatpak)")
    else:
        for i, install in enumerate(installations, 1):
            print(f"\n[{i}] {install.install_type.value}")
            print(f"    Path: {install.path}")
            print(f"    Windows Build: {install.is_windows_build}")
            print(f"    Has Mods Folder: {install.has_mods_folder}")
            print(f"    Has Data Folder: {install.has_data_folder}")
            if install.proton_prefix:
                print(f"    Proton Prefix: {install.proton_prefix}")
            if install.save_path:
                print(f"    Save Path: {install.save_path}")
            if install.config_path:
                print(f"    Config Path: {install.config_path}")
    
    # Also scan Wine prefixes
    print("\n" + "=" * 60)
    print("Scanning Wine prefixes...")
    wine_installs = detector.scan_wine_prefixes()
    if wine_installs:
        print(f"Found {len(wine_installs)} Wine/Proton installation(s)")
        for install in wine_installs:
            print(f"  - {install.path}")
    
    # Check for Workshop mods
    workshop = detector.find_workshop_mods_path()
    if workshop:
        print(f"\nWorkshop Mods Path: {workshop}")


if __name__ == "__main__":
    main()
