"""
Configuration Handler for RimModManager
Cross-platform configuration storage.
- Windows: %APPDATA%/RimModManager/
- macOS: ~/Library/Application Support/RimModManager/
- Linux: ~/.config/rimmodmanager/
"""

import json
import os
import sys
import platform
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


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


@dataclass
class AppConfig:
    """Application configuration data class."""
    # Last selected game installation path
    last_installation: str = ""
    
    # Custom mod source directories (user can add multiple)
    mod_source_paths: list[str] = field(default_factory=list)
    
    # Custom game installation paths (user-defined)
    custom_game_paths: list[str] = field(default_factory=list)
    
    # Last used modlist file path
    last_modlist_path: str = ""
    
    # Window geometry
    window_width: int = 1200
    window_height: int = 800
    window_x: int = -1
    window_y: int = -1
    
    # SteamCMD path (if not in PATH)
    steamcmd_path: str = ""
    
    # Workshop download directory
    workshop_download_path: str = ""
    
    # Remember splitter positions
    splitter_sizes: list[int] = field(default_factory=lambda: [300, 600, 300])
    
    # Dark mode preference (None = system, True = dark, False = light)
    dark_mode: Optional[bool] = None
    
    # Active mods list (package IDs in load order) - per installation
    active_mods: dict[str, list[str]] = field(default_factory=dict)


class ConfigHandler:
    """
    Handles loading, saving, and accessing application configuration.
    Cross-platform config directory support.
    """
    
    CONFIG_DIR_NAME = "RimModManager" if PLATFORM == 'windows' else "rimmodmanager"
    CONFIG_FILE_NAME = "config.json"
    MODLISTS_DIR_NAME = "modlists"
    
    def __init__(self):
        self._config_dir = self._get_config_dir()
        self._config_file = self._config_dir / self.CONFIG_FILE_NAME
        self._modlists_dir = self._config_dir / self.MODLISTS_DIR_NAME
        self._config: AppConfig = AppConfig()
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Load existing config
        self.load()
    
    def _get_config_dir(self) -> Path:
        """Get platform-specific config directory."""
        if PLATFORM == 'windows':
            # Windows: %APPDATA%/RimModManager/
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / self.CONFIG_DIR_NAME
            return Path.home() / 'AppData' / 'Roaming' / self.CONFIG_DIR_NAME
        
        elif PLATFORM == 'macos':
            # macOS: ~/Library/Application Support/RimModManager/
            return Path.home() / 'Library' / 'Application Support' / self.CONFIG_DIR_NAME
        
        else:
            # Linux: XDG config directory
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
            if xdg_config_home:
                base = Path(xdg_config_home)
            else:
                base = Path.home() / ".config"
            return base / self.CONFIG_DIR_NAME
    
    def _ensure_directories(self) -> None:
        """Create config directories if they don't exist."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._modlists_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def config_dir(self) -> Path:
        """Return the configuration directory path."""
        return self._config_dir
    
    @property
    def modlists_dir(self) -> Path:
        """Return the modlists directory path."""
        return self._modlists_dir
    
    @property
    def config(self) -> AppConfig:
        """Return the current configuration."""
        return self._config
    
    def load(self) -> bool:
        """
        Load configuration from file.
        Returns True if loaded successfully, False otherwise.
        """
        if not self._config_file.exists():
            return False
        
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate data is a dict
            if not isinstance(data, dict):
                print("Warning: Config file is not a valid JSON object")
                return False
            
            # Update config with loaded values, keeping defaults for missing keys
            for key, value in data.items():
                if hasattr(self._config, key):
                    # Type validation for critical fields
                    if key == 'mod_source_paths' and not isinstance(value, list):
                        continue
                    if key == 'custom_game_paths' and not isinstance(value, list):
                        continue
                    if key == 'active_mods' and not isinstance(value, dict):
                        continue
                    setattr(self._config, key, value)
            
            return True
        except (json.JSONDecodeError, IOError, PermissionError, TypeError) as e:
            print(f"Warning: Failed to load config: {e}")
            return False
    
    def save(self) -> bool:
        """
        Save configuration to file using atomic write.
        Returns True if saved successfully, False otherwise.
        """
        import tempfile
        
        try:
            # Write to temp file first, then atomic rename
            fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix='config_',
                dir=self._config_dir
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(asdict(self._config), f, indent=2)
                
                # Atomic rename (works on POSIX, best-effort on Windows)
                temp_file = Path(temp_path)
                temp_file.replace(self._config_file)
                return True
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except (IOError, PermissionError, OSError) as e:
            print(f"Error: Failed to save config: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return getattr(self._config, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and save."""
        if hasattr(self._config, key):
            setattr(self._config, key, value)
            self.save()
    
    def add_mod_source_path(self, path: str) -> bool:
        """Add a mod source directory if not already present."""
        if path and path not in self._config.mod_source_paths:
            self._config.mod_source_paths.append(path)
            self.save()
            return True
        return False
    
    def remove_mod_source_path(self, path: str) -> bool:
        """Remove a mod source directory."""
        if path in self._config.mod_source_paths:
            self._config.mod_source_paths.remove(path)
            self.save()
            return True
        return False
    
    def add_custom_game_path(self, path: str) -> bool:
        """Add a custom game installation path."""
        if path and path not in self._config.custom_game_paths:
            self._config.custom_game_paths.append(path)
            self.save()
            return True
        return False
    
    def remove_custom_game_path(self, path: str) -> bool:
        """Remove a custom game installation path."""
        if path in self._config.custom_game_paths:
            self._config.custom_game_paths.remove(path)
            self.save()
            return True
        return False
    
    def get_default_workshop_path(self) -> Path:
        """Get default path for workshop downloads."""
        if self._config.workshop_download_path:
            return Path(self._config.workshop_download_path)
        
        # Default to a directory in user's home
        default = Path.home() / "RimWorld_Workshop_Mods"
        return default
    
    def save_modlist(self, name: str, mod_ids: list[str], active_mods: list[str]) -> Path:
        """
        Save a modlist to the modlists directory.
        Returns the path to the saved file.
        """
        import tempfile
        
        modlist_data = {
            "name": name,
            "mod_ids": mod_ids,
            "active_mods": active_mods
        }
        
        # Sanitize filename - prevent path traversal
        safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
        safe_name = safe_name.replace("..", "_")  # Prevent path traversal
        if not safe_name:
            safe_name = "unnamed_modlist"
        filename = f"{safe_name}.json"
        filepath = self._modlists_dir / filename
        
        # Atomic write
        try:
            fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix='modlist_',
                dir=self._modlists_dir
            )
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(modlist_data, f, indent=2)
            
            Path(temp_path).replace(filepath)
        except Exception:
            try:
                os.unlink(temp_path)
            except (OSError, NameError):
                pass
            raise
        
        return filepath
    
    def load_modlist(self, filepath: Path) -> Optional[dict]:
        """Load a modlist from file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Failed to load modlist: {e}")
            return None
    
    def list_modlists(self) -> list[Path]:
        """List all saved modlists."""
        return list(self._modlists_dir.glob("*.json"))
    
    def save_active_mods(self, installation_path: str, mod_ids: list[str]) -> None:
        """
        Save active mods list for a specific installation.
        
        Args:
            installation_path: Path to the RimWorld installation
            mod_ids: List of package IDs in load order
        """
        self._config.active_mods[installation_path] = mod_ids
        self.save()
    
    def get_active_mods(self, installation_path: str) -> list[str]:
        """
        Get saved active mods list for a specific installation.
        
        Args:
            installation_path: Path to the RimWorld installation
            
        Returns:
            List of package IDs in load order, or empty list if none saved
        """
        return self._config.active_mods.get(installation_path, [])
