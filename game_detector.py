"""
Game Detector for RimModManager
Cross-platform RimWorld installation detection:
- Windows: Steam, GOG, standalone
- macOS: Steam, GOG, standalone
- Linux: Steam native, Proton, Flatpak, Wine, standalone
"""

import logging
import os
import platform
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Module logger
log = logging.getLogger("rimmodmanager.game_detector")


def get_platform() -> str:
    """Get current platform: 'windows', 'macos', or 'linux'."""
    system = platform.system().lower()
    if system == 'darwin':
        return 'macos'
    elif system == 'windows':
        return 'windows'
    else:
        return 'linux'


PLATFORM = get_platform()


class InstallationType(Enum):
    """Types of RimWorld installations."""
    STEAM_NATIVE = "Steam (Native)"
    STEAM_PROTON = "Steam (Proton/Windows)"
    STEAM_WINDOWS = "Steam (Windows)"
    STEAM_MACOS = "Steam (macOS)"
    FLATPAK_STEAM = "Flatpak Steam"
    GOG = "GOG"
    PROTON_STANDALONE = "Standalone (Proton/Wine)"
    STANDALONE = "Standalone"
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
            InstallationType.STEAM_NATIVE: "[Steam]",
            InstallationType.STEAM_PROTON: "[Steam Proton]",
            InstallationType.STEAM_WINDOWS: "[Steam]",
            InstallationType.STEAM_MACOS: "[Steam]",
            InstallationType.FLATPAK_STEAM: "[Flatpak]",
            InstallationType.GOG: "[GOG]",
            InstallationType.PROTON_STANDALONE: "[Standalone]",
            InstallationType.STANDALONE: "[Standalone]",
            InstallationType.CUSTOM: "[Custom]",
            InstallationType.UNKNOWN: "[Unknown]",
        }
        prefix = type_short.get(self.install_type, "")
        return f"{prefix} {self.path}"


class GameDetector:
    """
    Cross-platform RimWorld installation detector.
    Supports Windows, macOS, and Linux.
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
    
    MACOS_MARKERS = [
        "RimWorldMac.app",
        "RimWorld.app",
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
        
        if PLATFORM == 'windows':
            self._detect_windows_steam()
            self._detect_windows_gog()
        elif PLATFORM == 'macos':
            self._detect_macos_steam()
            self._detect_macos_gog()
        else:  # Linux
            self._detect_steam_native()
            self._detect_steam_proton()
            self._detect_flatpak_steam()
        
        # Check custom paths (all platforms)
        self._detect_custom_paths()
        
        # Detect save/config paths for each installation
        for install in self.installations:
            self._detect_save_config_paths(install)
        
        return self.installations
    
    # ==================== WINDOWS ====================
    
    def _detect_windows_steam(self) -> None:
        """Detect Steam installation on Windows."""
        # Get all possible Steam library folders
        steam_paths = self._get_windows_steam_libraries()
        
        for steam_path in steam_paths:
            rimworld_path = steam_path / 'steamapps/common/RimWorld'
            if rimworld_path.exists() and self._is_valid_rimworld(rimworld_path):
                install = RimWorldInstallation(
                    path=rimworld_path,
                    install_type=InstallationType.STEAM_WINDOWS,
                    has_mods_folder=(rimworld_path / "Mods").exists(),
                    has_data_folder=(rimworld_path / "Data").exists(),
                    is_windows_build=True,
                )
                if install not in self.installations:
                    self.installations.append(install)
    
    def _get_windows_steam_libraries(self) -> list[Path]:
        """Get all Steam library folders on Windows."""
        libraries = []
        
        # Default Steam paths
        default_paths = [
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Steam',
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Steam',
            Path('C:/Steam'),
        ]
        
        # Check all drives for Steam and SteamLibrary folders
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = Path(f'{drive}:/')
            if drive_path.exists():
                potential_paths = [
                    drive_path / 'Steam',
                    drive_path / 'SteamLibrary',
                    drive_path / 'Games/Steam',
                    drive_path / 'Games/SteamLibrary',
                    drive_path / 'Program Files/Steam',
                    drive_path / 'Program Files (x86)/Steam',
                ]
                for p in potential_paths:
                    if p.exists() and p not in libraries:
                        libraries.append(p)
        
        # Parse libraryfolders.vdf for additional libraries
        for steam_path in default_paths:
            vdf_path = steam_path / 'steamapps/libraryfolders.vdf'
            if vdf_path.exists():
                try:
                    additional = self._parse_library_folders_vdf(vdf_path)
                    for lib in additional:
                        if lib not in libraries:
                            libraries.append(lib)
                except (OSError, IOError, PermissionError):
                    pass
        
        return libraries
    
    def _detect_windows_gog(self) -> None:
        """Detect GOG installation on Windows."""
        gog_paths = [
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'GOG Galaxy/Games/RimWorld',
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'GOG Galaxy/Games/RimWorld',
        ]
        
        # Check all drives for GOG installations
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = Path(f'{drive}:/')
            if drive_path.exists():
                potential_paths = [
                    drive_path / 'GOG Games/RimWorld',
                    drive_path / 'Games/GOG/RimWorld',
                    drive_path / 'Games/RimWorld',
                    drive_path / 'GOG Galaxy/Games/RimWorld',
                ]
                gog_paths.extend(potential_paths)
        
        for gog_path in gog_paths:
            if gog_path.exists() and self._is_valid_rimworld(gog_path):
                install = RimWorldInstallation(
                    path=gog_path,
                    install_type=InstallationType.GOG,
                    has_mods_folder=(gog_path / "Mods").exists(),
                    has_data_folder=(gog_path / "Data").exists(),
                    is_windows_build=True,
                )
                if install not in self.installations:
                    self.installations.append(install)
    
    # ==================== MACOS ====================
    
    def _detect_macos_steam(self) -> None:
        """Detect Steam installation on macOS."""
        steam_path = Path.home() / 'Library/Application Support/Steam/steamapps/common/RimWorld'
        
        # Check for .app bundle
        app_path = steam_path / 'RimWorldMac.app'
        if not app_path.exists():
            app_path = steam_path
        
        if steam_path.exists() and self._is_valid_rimworld(steam_path):
            install = RimWorldInstallation(
                path=steam_path,
                install_type=InstallationType.STEAM_MACOS,
                has_mods_folder=(steam_path / "Mods").exists(),
                has_data_folder=(steam_path / "Data").exists(),
                is_windows_build=False,
            )
            self.installations.append(install)
    
    def _detect_macos_gog(self) -> None:
        """Detect GOG installation on macOS."""
        gog_paths = [
            Path('/Applications/RimWorld.app'),
            Path.home() / 'Applications/RimWorld.app',
        ]
        
        for gog_path in gog_paths:
            if gog_path.exists():
                # macOS .app bundle - actual game is inside
                contents_path = gog_path / 'Contents/Resources/Data'
                if contents_path.exists():
                    install = RimWorldInstallation(
                        path=gog_path,
                        install_type=InstallationType.GOG,
                        has_mods_folder=(contents_path / "Mods").exists(),
                        has_data_folder=(contents_path / "Data").exists(),
                        is_windows_build=False,
                    )
                    self.installations.append(install)
    
    # ==================== LINUX ====================
    
    def _detect_steam_native(self) -> None:
        """Detect native Linux Steam installation."""
        # Get all Steam library folders
        steam_libraries = self._get_linux_steam_libraries()
        
        for steam_path in steam_libraries:
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
    
    def _get_linux_steam_libraries(self) -> list[Path]:
        """Get all Steam library folders on Linux."""
        libraries = []
        
        # Default Steam paths
        default_paths = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
            Path.home() / ".steam/debian-installation",
            Path("/usr/share/steam"),
            Path("/usr/local/share/steam"),
        ]
        
        for p in default_paths:
            if p.exists() and p not in libraries:
                libraries.append(p)
        
        # Parse libraryfolders.vdf for additional libraries
        for steam_path in default_paths:
            vdf_path = steam_path / 'steamapps/libraryfolders.vdf'
            if vdf_path.exists():
                try:
                    additional = self._parse_library_folders_vdf(vdf_path)
                    for lib in additional:
                        if lib not in libraries:
                            libraries.append(lib)
                except (OSError, IOError, PermissionError):
                    pass
        
        # Check common additional library locations
        common_lib_paths = [
            Path.home() / "Games/SteamLibrary",
            Path.home() / "SteamLibrary",
            Path("/mnt"),
            Path("/media"),
            Path("/run/media"),
        ]
        
        for base_path in common_lib_paths:
            if base_path.exists():
                # Direct SteamLibrary
                if (base_path / "steamapps").exists():
                    if base_path not in libraries:
                        libraries.append(base_path)
                # Check subdirectories (for /mnt, /media, etc.)
                try:
                    for subdir in base_path.iterdir():
                        if subdir.is_dir():
                            steam_lib = subdir / "SteamLibrary"
                            if steam_lib.exists() and steam_lib not in libraries:
                                libraries.append(steam_lib)
                            # Direct steamapps in mount
                            if (subdir / "steamapps").exists() and subdir not in libraries:
                                libraries.append(subdir)
                except PermissionError:
                    pass
        
        return libraries
    
    def _parse_library_folders_vdf(self, vdf_path: Path) -> list[Path]:
        """Parse Steam's libraryfolders.vdf to find additional library paths."""
        libraries = []
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple regex to find path entries
            import re
            # Match "path" followed by the actual path
            pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(pattern, content)
            
            for match in matches:
                lib_path = Path(match)
                if lib_path.exists():
                    libraries.append(lib_path)
        except (OSError, IOError, PermissionError):
            pass
        
        return libraries
    
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
        """Detect save and config paths for an installation - cross-platform."""
        
        # ==================== WINDOWS ====================
        if PLATFORM == 'windows':
            # Windows saves are in %USERPROFILE%/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/
            locallow = os.environ.get('LOCALAPPDATA', '')
            if locallow:
                # LocalLow is actually at same level as Local, not inside it
                locallow_path = Path(locallow).parent / 'LocalLow'
            else:
                locallow_path = Path.home() / 'AppData' / 'LocalLow'
            
            rimworld_data = locallow_path / 'Ludeon Studios' / 'RimWorld by Ludeon Studios'
            if rimworld_data.exists():
                install.save_path = rimworld_data / 'Saves'
                install.config_path = rimworld_data / 'Config'
                return
            
            # Try alternate folder names
            ludeon_path = locallow_path / 'Ludeon Studios'
            if ludeon_path.exists():
                try:
                    for folder in ludeon_path.iterdir():
                        if folder.is_dir() and 'rimworld' in folder.name.lower():
                            install.save_path = folder / 'Saves'
                            install.config_path = folder / 'Config'
                            return
                except PermissionError:
                    pass
            return
        
        # ==================== MACOS ====================
        if PLATFORM == 'macos':
            # macOS saves are in ~/Library/Application Support/RimWorld by Ludeon Studios/
            app_support = Path.home() / 'Library' / 'Application Support'
            
            rimworld_data = app_support / 'RimWorld by Ludeon Studios'
            if rimworld_data.exists():
                install.save_path = rimworld_data / 'Saves'
                install.config_path = rimworld_data / 'Config'
                return
            
            # Try alternate folder names
            try:
                for folder in app_support.iterdir():
                    if folder.is_dir() and 'rimworld' in folder.name.lower():
                        install.save_path = folder / 'Saves'
                        install.config_path = folder / 'Config'
                        return
            except PermissionError:
                pass
            return
        
        # ==================== LINUX ====================
        # For custom/standalone installations, check if there's a proton prefix nearby
        if install.install_type in (InstallationType.CUSTOM, InstallationType.STANDALONE) and not install.proton_prefix:
            # Try to find proton prefix from game path
            # Check if game is in a Wine/Proton prefix structure
            game_path_str = str(install.path)
            if "drive_c" in game_path_str:
                # Extract prefix path (everything before drive_c)
                prefix_idx = game_path_str.find("drive_c")
                if prefix_idx > 0:
                    install.proton_prefix = Path(game_path_str[:prefix_idx])
                    install.is_windows_build = True
        
        # Collect all possible prefixes to check
        prefixes_to_check = []
        
        if install.proton_prefix:
            prefixes_to_check.append(install.proton_prefix)
        
        # For Windows builds, also check ALL Steam compatdata prefixes
        # (game might be standalone but using config from a different Proton prefix)
        if install.is_windows_build:
            steam_paths = [
                Path.home() / ".local/share/Steam",
                Path.home() / ".steam/steam",
                Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
            ]
            
            for steam_path in steam_paths:
                compatdata = steam_path / "steamapps/compatdata"
                if compatdata.exists():
                    try:
                        # Check ALL compatdata folders, not just RimWorld's AppID
                        for appid_folder in compatdata.iterdir():
                            if appid_folder.is_dir():
                                pfx = appid_folder / "pfx"
                                if pfx.exists() and pfx not in prefixes_to_check:
                                    prefixes_to_check.append(pfx)
                    except PermissionError:
                        pass
            
            # Also check common Wine/Lutris/Bottles prefix locations
            wine_prefix_locations = [
                Path.home() / ".wine",
                Path.home() / ".wine32",
                Path.home() / ".wine64",
                Path.home() / ".local/share/lutris/runners/wine",
                Path.home() / ".local/share/lutris/prefixes",
                Path.home() / ".local/share/bottles/bottles",
                Path.home() / ".var/app/com.usebottles.bottles/data/bottles/bottles",
                Path.home() / ".local/share/PlayOnLinux/wineprefix",
                Path.home() / ".PlayOnLinux/wineprefix",
                Path.home() / "Games",  # Common location for game prefixes
            ]
            
            for prefix_base in wine_prefix_locations:
                if not prefix_base.exists():
                    continue
                try:
                    # Check if this is a direct prefix (has drive_c)
                    if (prefix_base / "drive_c").exists():
                        if prefix_base not in prefixes_to_check:
                            prefixes_to_check.append(prefix_base)
                    else:
                        # Search subdirectories for prefixes
                        for subdir in prefix_base.iterdir():
                            if subdir.is_dir():
                                if (subdir / "drive_c").exists():
                                    if subdir not in prefixes_to_check:
                                        prefixes_to_check.append(subdir)
                                elif (subdir / "pfx" / "drive_c").exists():
                                    pfx = subdir / "pfx"
                                    if pfx not in prefixes_to_check:
                                        prefixes_to_check.append(pfx)
                except PermissionError:
                    pass
        
        # Search for config in all prefixes
        for prefix in prefixes_to_check:
            if not prefix or not prefix.exists():
                continue
            
            # Try exact path first
            base = prefix / "drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"
            if base.exists():
                install.save_path = base / "Saves"
                install.config_path = base / "Config"
                if not install.proton_prefix:
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
                            if not install.proton_prefix:
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
                                        if not install.proton_prefix:
                                            install.proton_prefix = prefix
                                        return
                except PermissionError:
                    continue
        
        # Native Linux build - standard Unity path
        if not install.is_windows_build:
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
            Path.home() / ".local/share/lutris/prefixes",
            Path.home() / ".local/share/bottles/bottles",  # Bottles app
            Path.home() / ".var/app/com.usebottles.bottles/data/bottles/bottles",  # Flatpak Bottles
            Path.home() / ".local/share/PlayOnLinux/wineprefix",
            Path.home() / ".PlayOnLinux/wineprefix",
        ]
        
        # Also check ~/Games for standalone installations
        games_folder = Path.home() / "Games"
        if games_folder.exists():
            try:
                for item in games_folder.iterdir():
                    if item.is_dir():
                        # Check if it's a RimWorld folder directly
                        if self._is_valid_rimworld(item):
                            is_windows = self._is_windows_build(item)
                            install = RimWorldInstallation(
                                path=item,
                                install_type=InstallationType.STANDALONE if not is_windows else InstallationType.PROTON_STANDALONE,
                                has_mods_folder=(item / "Mods").exists(),
                                has_data_folder=(item / "Data").exists(),
                                is_windows_build=is_windows,
                            )
                            self._detect_save_config_paths(install)
                            if not any(i.path == item for i in found):
                                found.append(install)
                        # Check if it's a Wine prefix
                        elif (item / "drive_c").exists():
                            wine_prefixes.append(item)
            except PermissionError:
                pass
        
        for prefix_base in wine_prefixes:
            if not prefix_base.exists():
                continue
            
            # Search for RimWorld in Program Files and common game locations
            search_paths = [
                "drive_c/Program Files/RimWorld",
                "drive_c/Program Files (x86)/RimWorld", 
                "drive_c/Games/RimWorld",
                "drive_c/GOG Games/RimWorld",
                "drive_c/Program Files/Steam/steamapps/common/RimWorld",
                "drive_c/Program Files (x86)/Steam/steamapps/common/RimWorld",
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
                        if not any(i.path == rimworld_path for i in found):
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
                                    if not any(i.path == rimworld_path for i in found):
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
