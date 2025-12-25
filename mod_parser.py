"""
Mod Parser for RimModManager
Parses About/About.xml files and manages mod metadata.
Includes ModsConfig.xml parsing and profile management.
"""

import os
import re
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime

# Module logger
log = logging.getLogger("rimmodmanager.mod_parser")


class ModSource(Enum):
    """Source of the mod."""
    LOCAL = "Local"
    WORKSHOP = "Workshop"
    GAME = "Core/DLC"


@dataclass
class ModInfo:
    """Represents a RimWorld mod's metadata."""
    # Core identifiers
    package_id: str = ""
    name: str = ""
    author: str = ""
    
    # Paths
    path: Path = None
    about_xml_path: Path = None
    
    # Metadata from About.xml
    description: str = ""
    url: str = ""
    supported_versions: list[str] = field(default_factory=list)
    mod_dependencies: list[str] = field(default_factory=list)
    load_before: list[str] = field(default_factory=list)
    load_after: list[str] = field(default_factory=list)
    incompatible_with: list[str] = field(default_factory=list)
    
    # Steam Workshop info
    steam_workshop_id: str = ""
    
    # Source and state
    source: ModSource = ModSource.LOCAL
    is_active: bool = False
    has_preview: bool = False
    preview_path: Optional[Path] = None
    
    # Validity
    is_valid: bool = True
    error_message: str = ""
    
    def __post_init__(self):
        if self.path and not self.about_xml_path:
            self.about_xml_path = self.path / "About" / "About.xml"
    
    def __hash__(self):
        return hash(self.package_id.lower() if self.package_id else str(self.path))
    
    def __eq__(self, other):
        if isinstance(other, ModInfo):
            return self.package_id.lower() == other.package_id.lower()
        return False
    
    def display_name(self) -> str:
        """Get display name for the mod."""
        if self.name:
            return self.name
        if self.path:
            return self.path.name
        return self.package_id or "Unknown Mod"
    
    def get_preview_image(self) -> Optional[Path]:
        """Get path to preview image if exists."""
        if self.preview_path and self.preview_path.exists():
            return self.preview_path
        
        if self.path:
            # Check common preview image locations
            preview_paths = [
                self.path / "About" / "Preview.png",
                self.path / "About" / "preview.png",
                self.path / "Preview.png",
                self.path / "preview.png",
                self.path / "About" / "Preview.jpg",
                self.path / "About" / "preview.jpg",
            ]
            for p in preview_paths:
                if p.exists():
                    self.preview_path = p
                    self.has_preview = True
                    return p
        return None


class ModParser:
    """
    Parses RimWorld mod folders and extracts metadata from About.xml files.
    """
    
    # Core game "mods" that are always present
    CORE_MODS = {
        "ludeon.rimworld": "Core",
        "ludeon.rimworld.royalty": "Royalty",
        "ludeon.rimworld.ideology": "Ideology",
        "ludeon.rimworld.biotech": "Biotech",
        "ludeon.rimworld.anomaly": "Anomaly",
    }
    
    def __init__(self):
        self.mods: dict[str, ModInfo] = {}  # package_id -> ModInfo
        self.mod_paths: dict[Path, ModInfo] = {}  # path -> ModInfo
    
    def parse_mod(self, mod_path: Path) -> Optional[ModInfo]:
        """
        Parse a single mod folder and extract metadata.
        Returns ModInfo or None if invalid.
        """
        if not mod_path.is_dir():
            return None
        
        about_xml = mod_path / "About" / "About.xml"
        
        # Create base mod info
        mod = ModInfo(path=mod_path, about_xml_path=about_xml)
        
        # Check if this is a core mod (from Data folder)
        if mod_path.parent.name == "Data":
            mod.source = ModSource.GAME
        
        # Try to parse About.xml
        if about_xml.exists():
            try:
                mod = self._parse_about_xml(mod, about_xml)
            except (ET.ParseError, OSError, IOError, UnicodeDecodeError) as e:
                mod.is_valid = False
                mod.error_message = f"Failed to parse About.xml: {e}"
                # Try to extract at least the name from folder
                mod.name = mod_path.name
        else:
            # Check for legacy About.xml location
            legacy_xml = mod_path / "about.xml"
            if legacy_xml.exists():
                try:
                    mod = self._parse_about_xml(mod, legacy_xml)
                except (ET.ParseError, OSError, IOError, UnicodeDecodeError) as e:
                    mod.is_valid = False
                    mod.error_message = f"Failed to parse About.xml: {e}"
                    mod.name = mod_path.name
            else:
                mod.is_valid = False
                mod.error_message = "No About.xml found"
                mod.name = mod_path.name
        
        # Check for Steam Workshop ID from folder name or PublishedFileId.txt
        self._detect_workshop_id(mod)
        
        # Check for preview image
        mod.get_preview_image()
        
        # Store in cache
        if mod.package_id:
            self.mods[mod.package_id.lower()] = mod
        self.mod_paths[mod_path] = mod
        
        return mod
    
    def _parse_about_xml(self, mod: ModInfo, xml_path: Path) -> ModInfo:
        """Parse the About.xml file and populate mod info."""
        try:
            # Read file content and handle encoding issues
            with open(xml_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Clean up common XML issues
            content = self._sanitize_xml(content)
            
            root = ET.fromstring(content)
            
            # Package ID (required for modern mods)
            package_id = self._get_text(root, "packageId")
            if not package_id:
                # Try legacy identifier
                package_id = self._get_text(root, "identifier")
            if not package_id:
                # Generate from folder name
                package_id = f"unknown.{mod.path.name.lower().replace(' ', '_')}"
            mod.package_id = package_id
            
            # Name
            mod.name = self._get_text(root, "name") or mod.path.name
            
            # Author(s)
            author = self._get_text(root, "author")
            if not author:
                # Check for authors list
                authors = root.find("authors")
                if authors is not None:
                    author_list = [li.text.strip() for li in authors.findall("li") if li.text]
                    author = ", ".join(author_list)
            mod.author = author or "Unknown"
            
            # Description
            mod.description = self._get_text(root, "description") or ""
            
            # URL
            mod.url = self._get_text(root, "url") or ""
            
            # Supported versions
            mod.supported_versions = self._get_list(root, "supportedVersions")
            if not mod.supported_versions:
                # Legacy single version
                version = self._get_text(root, "targetVersion")
                if version:
                    mod.supported_versions = [version]
            
            # Dependencies
            mod.mod_dependencies = self._get_package_id_list(root, "modDependencies")
            
            # Load order
            mod.load_before = self._get_package_id_list(root, "loadBefore")
            mod.load_after = self._get_package_id_list(root, "loadAfter")
            
            # Incompatibilities
            mod.incompatible_with = self._get_package_id_list(root, "incompatibleWith")
            
            mod.is_valid = True
            
        except ET.ParseError as e:
            mod.is_valid = False
            mod.error_message = f"XML Parse Error: {e}"
            mod.name = mod.path.name
        
        return mod
    
    def _sanitize_xml(self, content: str) -> str:
        """Clean up common XML issues in mod About.xml files."""
        # Remove BOM if present
        if content.startswith('\ufeff'):
            content = content[1:]
        
        # Fix common issues
        # Replace & with &amp; if not already an entity
        content = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', content)
        
        return content
    
    def _get_text(self, root: ET.Element, tag: str) -> str:
        """Get text content of a tag."""
        elem = root.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return ""
    
    def _get_list(self, root: ET.Element, tag: str) -> list[str]:
        """Get list of values from a tag containing <li> elements."""
        result = []
        parent = root.find(tag)
        if parent is not None:
            for li in parent.findall("li"):
                if li.text:
                    result.append(li.text.strip())
        return result
    
    def _get_package_id_list(self, root: ET.Element, tag: str) -> list[str]:
        """Get list of package IDs from a tag, handling nested structures."""
        result = []
        parent = root.find(tag)
        if parent is not None:
            # Direct li elements with text
            for li in parent.findall("li"):
                if li.text and li.text.strip():
                    result.append(li.text.strip())
                else:
                    # Check for packageId child element
                    pkg_id = li.find("packageId")
                    if pkg_id is not None and pkg_id.text:
                        result.append(pkg_id.text.strip())
        return result
    
    def _detect_workshop_id(self, mod: ModInfo) -> None:
        """Detect if mod is from Steam Workshop and extract ID."""
        if mod.path:
            # Check folder name (Workshop mods are numbered folders)
            folder_name = mod.path.name
            if folder_name.isdigit():
                mod.steam_workshop_id = folder_name
                mod.source = ModSource.WORKSHOP
                return
            
            # Check for PublishedFileId.txt
            pub_id_file = mod.path / "About" / "PublishedFileId.txt"
            if pub_id_file.exists():
                try:
                    with open(pub_id_file, 'r', encoding='utf-8') as f:
                        workshop_id = f.read().strip()
                        if workshop_id.isdigit():
                            mod.steam_workshop_id = workshop_id
                            mod.source = ModSource.WORKSHOP
                except (IOError, PermissionError):
                    pass
    
    def scan_directory(self, directory: Path, source: ModSource = ModSource.LOCAL) -> list[ModInfo]:
        """
        Scan a directory for mods and parse all found.
        Returns list of parsed mods.
        """
        mods = []
        
        if not directory.exists() or not directory.is_dir():
            return mods
        
        # Folders to skip (not actual mods)
        SKIP_FOLDERS = {
            'about', 'assemblies', 'defs', 'languages', 'patches', 
            'sounds', 'textures', 'source', 'news', '1.0', '1.1', 
            '1.2', '1.3', '1.4', '1.5', 'common', 'v1.0', 'v1.1',
            'v1.2', 'v1.3', 'v1.4', 'v1.5', 'loadfolders'
        }
        
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    # Skip hidden folders
                    if item.name.startswith('.'):
                        continue
                    
                    # Skip known non-mod folders
                    if item.name.lower() in SKIP_FOLDERS:
                        continue
                    
                    # Check if this looks like a valid mod (has About/About.xml)
                    about_xml = item / "About" / "About.xml"
                    about_xml_lower = item / "About" / "about.xml"
                    legacy_xml = item / "about.xml"
                    
                    if not (about_xml.exists() or about_xml_lower.exists() or legacy_xml.exists()):
                        # Not a valid mod folder, skip
                        continue
                    
                    mod = self.parse_mod(item)
                    if mod and mod.is_valid:
                        if source != ModSource.LOCAL:
                            mod.source = source
                        mods.append(mod)
        except PermissionError:
            pass
        
        return mods
    
    def scan_game_data(self, game_path: Path) -> list[ModInfo]:
        """Scan game's Data folder for core mods/DLCs."""
        data_path = game_path / "Data"
        mods = []
        
        if data_path.exists():
            mods = self.scan_directory(data_path, ModSource.GAME)
        
        return mods
    
    def get_mod_by_id(self, package_id: str) -> Optional[ModInfo]:
        """Get a mod by its package ID."""
        return self.mods.get(package_id.lower())
    
    def get_mod_by_path(self, path: Path) -> Optional[ModInfo]:
        """Get a mod by its path."""
        return self.mod_paths.get(path)
    
    def find_conflicts(self, mod_list: list[ModInfo]) -> dict[str, list[ModInfo]]:
        """
        Find duplicate package IDs in a mod list.
        Returns dict of package_id -> list of conflicting mods.
        """
        conflicts = {}
        seen = {}
        
        for mod in mod_list:
            pkg_id = mod.package_id.lower()
            if pkg_id in seen:
                if pkg_id not in conflicts:
                    conflicts[pkg_id] = [seen[pkg_id]]
                conflicts[pkg_id].append(mod)
            else:
                seen[pkg_id] = mod
        
        return conflicts
    
    def check_dependencies(self, active_mods: list[ModInfo]) -> dict[str, list[str]]:
        """
        Check if all dependencies are satisfied.
        Returns dict of mod_id -> list of missing dependencies.
        """
        active_ids = {m.package_id.lower() for m in active_mods}
        missing = {}
        
        for mod in active_mods:
            mod_missing = []
            for dep in mod.mod_dependencies:
                if dep.lower() not in active_ids:
                    mod_missing.append(dep)
            if mod_missing:
                missing[mod.package_id] = mod_missing
        
        return missing
    
    def check_incompatibilities(self, active_mods: list[ModInfo]) -> list[tuple[ModInfo, ModInfo]]:
        """
        Check for incompatible mods that are both active.
        Returns list of (mod1, mod2) tuples that are incompatible.
        """
        active_ids = {m.package_id.lower(): m for m in active_mods}
        incompatible = []
        checked = set()
        
        for mod in active_mods:
            for incompat_id in mod.incompatible_with:
                key = tuple(sorted([mod.package_id.lower(), incompat_id.lower()]))
                if key not in checked and incompat_id.lower() in active_ids:
                    incompatible.append((mod, active_ids[incompat_id.lower()]))
                    checked.add(key)
        
        return incompatible
    
    def sort_by_load_order(self, mods: list[ModInfo]) -> list[ModInfo]:
        """
        Sort mods respecting loadBefore and loadAfter rules.
        Uses topological sort with Kahn's algorithm.
        """
        from collections import deque
        
        if not mods:
            return []
        
        # Build dependency graph
        mod_dict = {m.package_id.lower(): m for m in mods}
        
        # Calculate in-degrees and adjacency
        in_degree = {m.package_id.lower(): 0 for m in mods}
        graph = {m.package_id.lower(): [] for m in mods}
        
        for mod in mods:
            mod_id = mod.package_id.lower()
            
            # loadAfter means this mod should come after those mods
            for after_id in mod.load_after:
                after_id = after_id.lower()
                if after_id in mod_dict:
                    graph[after_id].append(mod_id)
                    in_degree[mod_id] += 1
            
            # loadBefore means this mod should come before those mods
            for before_id in mod.load_before:
                before_id = before_id.lower()
                if before_id in mod_dict:
                    graph[mod_id].append(before_id)
                    in_degree[before_id] += 1
        
        # Kahn's algorithm with deque for O(1) popleft
        # Sort initial queue once for deterministic order
        queue = deque(sorted([m for m in in_degree if in_degree[m] == 0]))
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(mod_dict[node])
            
            # Collect new nodes with zero in-degree
            new_nodes = []
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    new_nodes.append(neighbor)
            
            # Sort and extend for deterministic order
            if new_nodes:
                new_nodes.sort()
                queue.extend(new_nodes)
        
        # If there's a cycle, return original order for remaining mods
        if len(result) != len(mods):
            remaining = [m for m in mods if m not in result]
            result.extend(remaining)
        
        return result
    
    def clear_cache(self) -> None:
        """Clear the mod cache."""
        self.mods.clear()
        self.mod_paths.clear()


def main():
    """Test the mod parser."""
    import sys
    
    parser = ModParser()
    
    # Test with a path if provided
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
        print(f"Scanning: {test_path}")
        mods = parser.scan_directory(test_path)
        
        print(f"\nFound {len(mods)} mods:")
        for mod in mods:
            print(f"\n  [{mod.source.value}] {mod.display_name()}")
            print(f"    Package ID: {mod.package_id}")
            print(f"    Author: {mod.author}")
            print(f"    Valid: {mod.is_valid}")
            if mod.supported_versions:
                print(f"    Versions: {', '.join(mod.supported_versions)}")
            if mod.steam_workshop_id:
                print(f"    Workshop ID: {mod.steam_workshop_id}")
            if not mod.is_valid:
                print(f"    Error: {mod.error_message}")
    else:
        print("Usage: python mod_parser.py <mods_directory>")
        
        # Demo with common paths
        demo_paths = [
            Path.home() / ".local/share/Steam/steamapps/common/RimWorld/Mods",
            Path.home() / ".local/share/Steam/steamapps/workshop/content/294100",
        ]
        
        for path in demo_paths:
            if path.exists():
                print(f"\nFound mods folder: {path}")
                mods = parser.scan_directory(path)
                print(f"  Contains {len(mods)} mods")


# ==================== MOD PROFILES ====================

@dataclass
class ModProfile:
    """Represents a saved mod profile/configuration."""
    name: str
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    active_mods: list[str] = field(default_factory=list)  # Package IDs in load order
    game_version: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active_mods": self.active_mods,
            "game_version": self.game_version,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModProfile':
        """Create from dictionary."""
        return cls(
            name=data.get("name", "Unnamed"),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            active_mods=data.get("active_mods", []),
            game_version=data.get("game_version", ""),
        )


class ProfileManager:
    """Manages mod profiles - save, load, switch between configurations."""
    
    def __init__(self, profiles_dir: Path):
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profiles: dict[str, ModProfile] = {}
        self._load_all_profiles()
    
    def _load_all_profiles(self) -> None:
        """Load all profiles from disk."""
        self.profiles.clear()
        for file in self.profiles_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                profile = ModProfile.from_dict(data)
                self.profiles[profile.name] = profile
            except (json.JSONDecodeError, IOError) as e:
                log.warning(f"Failed to load profile {file}: {e}")
    
    def save_profile(self, profile: ModProfile) -> bool:
        """Save a profile to disk."""
        profile.updated_at = datetime.now().isoformat()
        
        # Sanitize filename
        safe_name = "".join(c for c in profile.name if c.isalnum() or c in "._- ")
        filepath = self.profiles_dir / f"{safe_name}.json"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2)
            self.profiles[profile.name] = profile
            return True
        except IOError as e:
            log.error(f"Failed to save profile: {e}")
            return False
    
    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        if name not in self.profiles:
            return False
        
        safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
        filepath = self.profiles_dir / f"{safe_name}.json"
        
        try:
            if filepath.exists():
                filepath.unlink()
            del self.profiles[name]
            return True
        except (IOError, KeyError) as e:
            log.error(f"Failed to delete profile: {e}")
            return False
    
    def get_profile(self, name: str) -> Optional[ModProfile]:
        """Get a profile by name."""
        return self.profiles.get(name)
    
    def list_profiles(self) -> list[ModProfile]:
        """List all profiles."""
        return list(self.profiles.values())
    
    def create_profile(self, name: str, active_mods: list[str], 
                       description: str = "", game_version: str = "") -> ModProfile:
        """Create a new profile from current mod list."""
        profile = ModProfile(
            name=name,
            description=description,
            active_mods=active_mods,
            game_version=game_version,
        )
        self.save_profile(profile)
        return profile
    
    def duplicate_profile(self, source_name: str, new_name: str) -> Optional[ModProfile]:
        """Duplicate an existing profile."""
        source = self.get_profile(source_name)
        if not source:
            return None
        
        new_profile = ModProfile(
            name=new_name,
            description=f"Copy of {source_name}",
            active_mods=source.active_mods.copy(),
            game_version=source.game_version,
        )
        self.save_profile(new_profile)
        return new_profile


# ==================== MODS CONFIG PARSER ====================

class ModsConfigParser:
    """
    Parses RimWorld's ModsConfig.xml file.
    Located in the game's config folder.
    """
    
    def __init__(self):
        pass
    
    def find_mods_config(self, config_path: Path) -> Optional[Path]:
        """Find ModsConfig.xml in the config folder."""
        mods_config = config_path / "ModsConfig.xml"
        if mods_config.exists():
            return mods_config
        
        # Try lowercase
        mods_config_lower = config_path / "modsconfig.xml"
        if mods_config_lower.exists():
            return mods_config_lower
        
        return None
    
    def parse_mods_config(self, config_path: Path) -> tuple[list[str], str, list[str]]:
        """
        Parse ModsConfig.xml and return (active_mod_ids, game_version, known_expansions).
        Returns empty values if file not found or invalid.
        """
        mods_config = self.find_mods_config(config_path)
        if not mods_config:
            return [], "", []
        
        try:
            tree = ET.parse(mods_config)
            root = tree.getroot()
            
            # Get game version
            version_elem = root.find("version")
            game_version = version_elem.text.strip() if version_elem is not None and version_elem.text else ""
            
            # Get active mods
            active_mods = []
            active_mods_elem = root.find("activeMods")
            if active_mods_elem is not None:
                for li in active_mods_elem.findall("li"):
                    if li.text:
                        active_mods.append(li.text.strip())
            
            # Get known expansions
            known_expansions = []
            known_expansions_elem = root.find("knownExpansions")
            if known_expansions_elem is not None:
                for li in known_expansions_elem.findall("li"):
                    if li.text:
                        known_expansions.append(li.text.strip())
            
            return active_mods, game_version, known_expansions
            
        except (ET.ParseError, IOError) as e:
            log.error(f"Failed to parse ModsConfig.xml: {e}")
            return [], "", []
    
    def write_mods_config(self, config_path: Path, active_mods: list[str], 
                          game_version: str = "", preserve_existing: bool = True) -> bool:
        """
        Write ModsConfig.xml - RimSort-style implementation.
        DLC/Core are NOT written to activeMods - they're loaded from game Data folder.
        """
        import os
        import shutil
        import xml.dom.minidom as minidom
        
        # DLC package IDs - DO NOT filter these out
        # Game needs all active mods including DLC in activeMods
        # Only knownExpansions is separate (DLCs only, no Core)
        EXCLUDED_IDS = set()  # Don't exclude anything
        
        # knownExpansions - DLCs only (no Core)
        KNOWN_EXPANSIONS = [
            "ludeon.rimworld.royalty", 
            "ludeon.rimworld.ideology",
            "ludeon.rimworld.biotech",
            "ludeon.rimworld.anomaly",
            "ludeon.rimworld.odyssey"
        ]
        
        try:
            config_path.mkdir(parents=True, exist_ok=True)
        except (IOError, PermissionError) as e:
            log.error(f"Failed to create config directory: {e}")
            return False
        
        mods_config = config_path / "ModsConfig.xml"
        backup_path = config_path / "ModsConfig.xml.backup"
        
        # Get existing version
        existing_version = ""
        if preserve_existing and mods_config.exists():
            try:
                tree = ET.parse(mods_config)
                ver = tree.find(".//version")
                if ver is not None and ver.text:
                    existing_version = ver.text.strip()
            except Exception:
                pass
        
        final_version = game_version or existing_version or "1.6.4633 rev1261"
        
        # Filter out DLC/Core, normalize to lowercase, dedupe
        seen = set()
        filtered_mods = []
        for mod_id in active_mods:
            lower = mod_id.lower()
            # Skip DLC and Core - game loads them from Data folder
            if lower in EXCLUDED_IDS:
                log.debug(f"Skipping DLC/Core: {mod_id}")
                continue
            if lower not in seen:
                seen.add(lower)
                filtered_mods.append(lower)
        
        # IMPORTANT: Ensure correct load order
        # 1. Harmony (and other tier-0 mods) must come first
        # 2. Core must come after Harmony but before DLCs
        # 3. DLCs in order: Royalty, Ideology, Biotech, Anomaly, Odyssey
        # 4. Other mods after
        
        CORE_ID = "ludeon.rimworld"
        DLC_ORDER = [
            "ludeon.rimworld.royalty",
            "ludeon.rimworld.ideology", 
            "ludeon.rimworld.biotech",
            "ludeon.rimworld.anomaly",
            "ludeon.rimworld.odyssey"
        ]
        TIER_ZERO = {"brrainz.harmony"}  # Mods that must load before Core
        
        # Separate mods into categories
        tier_zero_mods = [m for m in filtered_mods if m in TIER_ZERO]
        other_mods = [m for m in filtered_mods if m not in TIER_ZERO and m != CORE_ID and m not in DLC_ORDER]
        
        # Check if Core/DLCs were in original list
        has_core = CORE_ID in [m.lower() for m in active_mods]
        active_dlcs = [dlc for dlc in DLC_ORDER if dlc in [m.lower() for m in active_mods]]
        
        # Build final ordered list
        final_mods = []
        final_mods.extend(tier_zero_mods)  # Harmony first
        if has_core:
            final_mods.append(CORE_ID)  # Core second
        final_mods.extend(active_dlcs)  # DLCs in order
        final_mods.extend(other_mods)  # Other mods last
        
        log.info(f"ModsConfig: {len(active_mods)} input -> {len(final_mods)} output mods")
        log.debug(f"ModsConfig final order: {final_mods}")
        
        # Backup existing
        if mods_config.exists():
            try:
                shutil.copy2(mods_config, backup_path)
            except Exception:
                pass
        
        # Build dict structure (RimSort style)
        data = {
            "ModsConfigData": {
                "version": final_version,
                "activeMods": {"li": final_mods},
                "knownExpansions": {"li": KNOWN_EXPANSIONS}
            }
        }
        
        # Convert dict to XML
        def dict_to_xml(d: dict, parent=None):
            if parent is None:
                tag = list(d.keys())[0]
                root = ET.Element(tag)
                dict_to_xml(d[tag], root)
                return root
            
            for key, val in d.items():
                if isinstance(val, dict):
                    if "li" in val and isinstance(val["li"], list):
                        elem = ET.SubElement(parent, key)
                        for item in val["li"]:
                            li = ET.SubElement(elem, "li")
                            li.text = str(item)
                    else:
                        elem = ET.SubElement(parent, key)
                        dict_to_xml(val, elem)
                elif isinstance(val, list):
                    for item in val:
                        elem = ET.SubElement(parent, key)
                        if isinstance(item, dict):
                            dict_to_xml(item, elem)
                        else:
                            elem.text = str(item)
                else:
                    elem = ET.SubElement(parent, key)
                    elem.text = str(val)
            return parent
        
        try:
            root = dict_to_xml(data)
            
            # Pretty print with minidom
            rough = ET.tostring(root, encoding="utf-8")
            reparsed = minidom.parseString(rough)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            
            # Remove extra blank lines
            lines = [line for line in pretty_xml.split('\n') if line.strip()]
            final_xml = '\n'.join(lines)
            
            # Write
            with open(mods_config, 'w', encoding='utf-8') as f:
                f.write(final_xml)
                f.flush()
                os.fsync(f.fileno())
            
            log.info(f"ModsConfig written: {mods_config} ({len(filtered_mods)} mods)")
            
            return True
            
        except Exception as e:
            log.error(f"ModsConfig write failed: {e}", exc_info=True)
            return False


# ==================== MOD BACKUP MANAGER ====================

@dataclass
class ModBackup:
    """Represents a backup of mod configuration."""
    name: str
    timestamp: str
    active_mods: list[str]
    description: str = ""
    auto_backup: bool = False
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "active_mods": self.active_mods,
            "description": self.description,
            "auto_backup": self.auto_backup,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModBackup':
        return cls(
            name=data.get("name", ""),
            timestamp=data.get("timestamp", ""),
            active_mods=data.get("active_mods", []),
            description=data.get("description", ""),
            auto_backup=data.get("auto_backup", False),
        )


class BackupManager:
    """Manages mod configuration backups."""
    
    MAX_AUTO_BACKUPS = 10
    
    def __init__(self, backups_dir: Path):
        self.backups_dir = backups_dir
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.backups: list[ModBackup] = []
        self._load_backups()
    
    def _load_backups(self) -> None:
        """Load backup index."""
        index_file = self.backups_dir / "backups.json"
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.backups = [ModBackup.from_dict(b) for b in data.get("backups", [])]
            except (json.JSONDecodeError, IOError):
                self.backups = []
    
    def _save_index(self) -> None:
        """Save backup index."""
        index_file = self.backups_dir / "backups.json"
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump({"backups": [b.to_dict() for b in self.backups]}, f, indent=2)
        except IOError as e:
            log.error(f"Failed to save backup index: {e}")
    
    def create_backup(self, active_mods: list[str], name: str = "", 
                      description: str = "", auto: bool = False) -> ModBackup:
        """Create a new backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if not name:
            name = f"Backup_{timestamp}"
        
        backup = ModBackup(
            name=name,
            timestamp=timestamp,
            active_mods=active_mods,
            description=description,
            auto_backup=auto,
        )
        
        self.backups.insert(0, backup)
        
        # Cleanup old auto-backups
        if auto:
            self._cleanup_auto_backups()
        
        self._save_index()
        return backup
    
    def _cleanup_auto_backups(self) -> None:
        """Remove old auto-backups beyond limit."""
        auto_backups = [b for b in self.backups if b.auto_backup]
        if len(auto_backups) > self.MAX_AUTO_BACKUPS:
            # Remove oldest auto-backups
            to_remove = auto_backups[self.MAX_AUTO_BACKUPS:]
            for backup in to_remove:
                self.backups.remove(backup)
    
    def restore_backup(self, backup: ModBackup) -> list[str]:
        """Restore a backup - returns the mod list."""
        return backup.active_mods.copy()
    
    def delete_backup(self, backup: ModBackup) -> bool:
        """Delete a backup."""
        if backup in self.backups:
            self.backups.remove(backup)
            self._save_index()
            return True
        return False
    
    def list_backups(self) -> list[ModBackup]:
        """List all backups, newest first."""
        return self.backups.copy()
    
    def get_latest_backup(self) -> Optional[ModBackup]:
        """Get the most recent backup."""
        return self.backups[0] if self.backups else None


if __name__ == "__main__":
    main()


# ==================== MOD UPDATE CHECKER ====================

@dataclass
class ModUpdateInfo:
    """Information about a mod's update status."""
    package_id: str
    workshop_id: str
    name: str
    local_updated: str = ""  # Last modified time of local files
    workshop_updated: str = ""  # Last updated on Workshop
    needs_update: bool = False
    error: str = ""


class ModUpdateChecker:
    """
    Checks for mod updates by comparing local files with Workshop.
    Uses Steam Web API for Workshop info.
    """
    
    STEAM_API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    
    def __init__(self):
        self.update_cache: dict[str, ModUpdateInfo] = {}
    
    def get_local_mod_time(self, mod: 'ModInfo') -> Optional[str]:
        """Get the last modified time of a local mod."""
        if not mod.path or not mod.path.exists():
            return None
        
        try:
            # Check About.xml modification time
            about_xml = mod.path / "About" / "About.xml"
            if about_xml.exists():
                mtime = about_xml.stat().st_mtime
                return datetime.fromtimestamp(mtime).isoformat()
            
            # Fallback to folder mtime
            mtime = mod.path.stat().st_mtime
            return datetime.fromtimestamp(mtime).isoformat()
        except OSError:
            return None
    
    def fetch_workshop_info(self, workshop_ids: list[str]) -> dict[str, dict]:
        """
        Fetch Workshop info for multiple mods using Steam API.
        Returns dict of workshop_id -> info dict.
        """
        import urllib.request
        import urllib.parse
        import urllib.error
        
        if not workshop_ids:
            return {}
        
        results = {}
        
        try:
            # Build POST data
            data = {
                'itemcount': len(workshop_ids),
            }
            for i, wid in enumerate(workshop_ids):
                data[f'publishedfileids[{i}]'] = wid
            
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            
            request = urllib.request.Request(
                self.STEAM_API_URL,
                data=encoded_data,
                headers={'User-Agent': 'RimModManager/1.0'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                import json
                response_data = json.loads(response.read().decode('utf-8'))
            
            # Parse response
            if 'response' in response_data and 'publishedfiledetails' in response_data['response']:
                for item in response_data['response']['publishedfiledetails']:
                    wid = item.get('publishedfileid', '')
                    if wid:
                        results[wid] = {
                            'title': item.get('title', ''),
                            'description': item.get('description', ''),
                            'time_updated': item.get('time_updated', 0),
                            'time_created': item.get('time_created', 0),
                            'file_size': item.get('file_size', 0),
                            'subscriptions': item.get('subscriptions', 0),
                            'favorited': item.get('favorited', 0),
                            'views': item.get('views', 0),
                            'tags': [t.get('tag', '') for t in item.get('tags', [])],
                            'preview_url': item.get('preview_url', ''),
                            'creator': item.get('creator', ''),
                        }
        except urllib.error.URLError as e:
            log.debug(f"Network error fetching Workshop info: {e}")
        except urllib.error.HTTPError as e:
            log.debug(f"HTTP error fetching Workshop info: {e.code}")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.debug(f"Failed to parse Workshop response: {e}")
        except OSError as e:
            log.debug(f"OS error fetching Workshop info: {e}")
        
        return results
    
    def check_updates(self, mods: list['ModInfo']) -> list[ModUpdateInfo]:
        """
        Check for updates for a list of mods.
        Only checks mods with Workshop IDs.
        """
        # Filter mods with workshop IDs
        workshop_mods = [m for m in mods if m.steam_workshop_id]
        
        if not workshop_mods:
            return []
        
        # Fetch workshop info
        workshop_ids = [m.steam_workshop_id for m in workshop_mods]
        workshop_info = self.fetch_workshop_info(workshop_ids)
        
        results = []
        
        for mod in workshop_mods:
            info = ModUpdateInfo(
                package_id=mod.package_id,
                workshop_id=mod.steam_workshop_id,
                name=mod.display_name(),
            )
            
            # Get local time
            local_time = self.get_local_mod_time(mod)
            if local_time:
                info.local_updated = local_time
            
            # Get workshop time
            ws_info = workshop_info.get(mod.steam_workshop_id)
            if ws_info:
                time_updated = ws_info.get('time_updated', 0)
                if time_updated:
                    info.workshop_updated = datetime.fromtimestamp(time_updated).isoformat()
                    
                    # Compare times
                    if local_time:
                        local_dt = datetime.fromisoformat(local_time)
                        workshop_dt = datetime.fromtimestamp(time_updated)
                        info.needs_update = workshop_dt > local_dt
            else:
                info.error = "Could not fetch Workshop info"
            
            results.append(info)
            self.update_cache[mod.steam_workshop_id] = info
        
        return results
    
    def get_cached_info(self, workshop_id: str) -> Optional[ModUpdateInfo]:
        """Get cached update info for a mod."""
        return self.update_cache.get(workshop_id)


# ==================== ENHANCED MOD INFO ====================

@dataclass
class EnhancedModInfo:
    """Extended mod information from Workshop."""
    workshop_id: str
    title: str = ""
    description: str = ""
    author_id: str = ""
    time_created: str = ""
    time_updated: str = ""
    file_size: int = 0
    subscriptions: int = 0
    favorited: int = 0
    views: int = 0
    tags: list[str] = field(default_factory=list)
    preview_url: str = ""
    
    def format_file_size(self) -> str:
        """Format file size in human readable format."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        elif self.file_size < 1024 * 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.file_size / (1024 * 1024 * 1024):.1f} GB"
    
    def format_number(self, num: int) -> str:
        """Format large numbers with K/M suffix."""
        if num < 1000:
            return str(num)
        elif num < 1000000:
            return f"{num / 1000:.1f}K"
        else:
            return f"{num / 1000000:.1f}M"


class EnhancedModInfoFetcher:
    """Fetches enhanced mod information from Steam Workshop."""
    
    STEAM_API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    
    def __init__(self):
        self.cache: dict[str, EnhancedModInfo] = {}
    
    def fetch_info(self, workshop_ids: list[str]) -> dict[str, EnhancedModInfo]:
        """Fetch enhanced info for multiple mods."""
        import urllib.request
        import urllib.parse
        import urllib.error
        
        if not workshop_ids:
            return {}
        
        # Check cache first
        uncached = [wid for wid in workshop_ids if wid not in self.cache]
        
        if uncached:
            try:
                data = {'itemcount': len(uncached)}
                for i, wid in enumerate(uncached):
                    data[f'publishedfileids[{i}]'] = wid
                
                encoded_data = urllib.parse.urlencode(data).encode('utf-8')
                
                request = urllib.request.Request(
                    self.STEAM_API_URL,
                    data=encoded_data,
                    headers={'User-Agent': 'RimModManager/1.0'}
                )
                
                with urllib.request.urlopen(request, timeout=30) as response:
                    import json
                    response_data = json.loads(response.read().decode('utf-8'))
                
                if 'response' in response_data and 'publishedfiledetails' in response_data['response']:
                    for item in response_data['response']['publishedfiledetails']:
                        wid = item.get('publishedfileid', '')
                        if wid:
                            # Safely convert numeric fields (API sometimes returns strings)
                            def safe_int(val, default=0):
                                try:
                                    return int(val) if val else default
                                except (ValueError, TypeError):
                                    return default
                            
                            info = EnhancedModInfo(
                                workshop_id=wid,
                                title=item.get('title', ''),
                                description=item.get('description', ''),
                                author_id=item.get('creator', ''),
                                time_created=datetime.fromtimestamp(item.get('time_created', 0)).isoformat() if item.get('time_created') else '',
                                time_updated=datetime.fromtimestamp(item.get('time_updated', 0)).isoformat() if item.get('time_updated') else '',
                                file_size=safe_int(item.get('file_size', 0)),
                                subscriptions=safe_int(item.get('subscriptions', 0)),
                                favorited=safe_int(item.get('favorited', 0)),
                                views=safe_int(item.get('views', 0)),
                                tags=[t.get('tag', '') for t in item.get('tags', [])],
                                preview_url=item.get('preview_url', ''),
                            )
                            self.cache[wid] = info
            except urllib.error.URLError as e:
                log.debug(f"Network error fetching enhanced mod info: {e}")
            except urllib.error.HTTPError as e:
                log.debug(f"HTTP error fetching enhanced mod info: {e.code}")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                log.debug(f"Failed to parse enhanced mod info response: {e}")
            except OSError as e:
                log.debug(f"OS error fetching enhanced mod info: {e}")
        
        # Return requested items from cache
        return {wid: self.cache[wid] for wid in workshop_ids if wid in self.cache}
    
    def get_cached(self, workshop_id: str) -> Optional[EnhancedModInfo]:
        """Get cached info for a single mod."""
        return self.cache.get(workshop_id)


# ==================== CONFLICT RESOLUTION ASSISTANT ====================

@dataclass
class ConflictInfo:
    """Information about a mod conflict."""
    conflict_type: str  # 'duplicate', 'missing_dep', 'incompatible', 'load_order'
    severity: str  # 'error', 'warning', 'info'
    mod1_id: str
    mod1_name: str
    mod2_id: str = ""
    mod2_name: str = ""
    description: str = ""
    suggestion: str = ""


class ConflictResolver:
    """
    Analyzes mod conflicts and provides resolution suggestions.
    """
    
    def __init__(self, mod_parser: 'ModParser'):
        self.mod_parser = mod_parser
    
    def analyze_conflicts(self, active_mods: list['ModInfo']) -> list[ConflictInfo]:
        """
        Analyze all conflicts in the active mod list.
        Returns list of conflicts with suggestions.
        """
        conflicts = []
        
        # Check for duplicates
        conflicts.extend(self._check_duplicates(active_mods))
        
        # Check for missing dependencies
        conflicts.extend(self._check_missing_deps(active_mods))
        
        # Check for incompatibilities
        conflicts.extend(self._check_incompatibilities(active_mods))
        
        # Check load order issues
        conflicts.extend(self._check_load_order(active_mods))
        
        return conflicts
    
    def _check_duplicates(self, mods: list['ModInfo']) -> list[ConflictInfo]:
        """Check for duplicate package IDs."""
        conflicts = []
        seen = {}
        
        for mod in mods:
            pkg_id = mod.package_id.lower()
            if pkg_id in seen:
                conflicts.append(ConflictInfo(
                    conflict_type='duplicate',
                    severity='error',
                    mod1_id=seen[pkg_id].package_id,
                    mod1_name=seen[pkg_id].display_name(),
                    mod2_id=mod.package_id,
                    mod2_name=mod.display_name(),
                    description=f"Duplicate mod: '{mod.display_name()}' appears twice",
                    suggestion="Remove one of the duplicate mods. Keep the one from Workshop if available."
                ))
            else:
                seen[pkg_id] = mod
        
        return conflicts
    
    def _check_missing_deps(self, mods: list['ModInfo']) -> list[ConflictInfo]:
        """Check for missing dependencies."""
        conflicts = []
        active_ids = {m.package_id.lower() for m in mods}
        
        for mod in mods:
            for dep in mod.mod_dependencies:
                if dep.lower() not in active_ids:
                    # Check if it's a core/DLC dependency
                    is_dlc = dep.lower().startswith('ludeon.rimworld')
                    
                    conflicts.append(ConflictInfo(
                        conflict_type='missing_dep',
                        severity='error' if not is_dlc else 'warning',
                        mod1_id=mod.package_id,
                        mod1_name=mod.display_name(),
                        mod2_id=dep,
                        mod2_name=dep,
                        description=f"'{mod.display_name()}' requires '{dep}' which is not active",
                        suggestion=f"Download and activate '{dep}'" if not is_dlc else f"This mod requires the {dep.split('.')[-1].title()} DLC"
                    ))
        
        return conflicts
    
    def _check_incompatibilities(self, mods: list['ModInfo']) -> list[ConflictInfo]:
        """Check for incompatible mods."""
        conflicts = []
        active_ids = {m.package_id.lower(): m for m in mods}
        checked = set()
        
        for mod in mods:
            for incompat_id in mod.incompatible_with:
                key = tuple(sorted([mod.package_id.lower(), incompat_id.lower()]))
                if key not in checked and incompat_id.lower() in active_ids:
                    other = active_ids[incompat_id.lower()]
                    conflicts.append(ConflictInfo(
                        conflict_type='incompatible',
                        severity='error',
                        mod1_id=mod.package_id,
                        mod1_name=mod.display_name(),
                        mod2_id=other.package_id,
                        mod2_name=other.display_name(),
                        description=f"'{mod.display_name()}' is incompatible with '{other.display_name()}'",
                        suggestion="Deactivate one of these mods. Check mod pages for compatibility patches."
                    ))
                    checked.add(key)
        
        return conflicts
    
    def _check_load_order(self, mods: list['ModInfo']) -> list[ConflictInfo]:
        """Check for load order issues."""
        conflicts = []
        mod_positions = {m.package_id.lower(): i for i, m in enumerate(mods)}
        
        for mod in mods:
            mod_pos = mod_positions[mod.package_id.lower()]
            
            # Check loadAfter - these mods should come before this one
            for after_id in mod.load_after:
                after_id_lower = after_id.lower()
                if after_id_lower in mod_positions:
                    after_pos = mod_positions[after_id_lower]
                    if after_pos > mod_pos:
                        other_name = next((m.display_name() for m in mods if m.package_id.lower() == after_id_lower), after_id)
                        conflicts.append(ConflictInfo(
                            conflict_type='load_order',
                            severity='warning',
                            mod1_id=mod.package_id,
                            mod1_name=mod.display_name(),
                            mod2_id=after_id,
                            mod2_name=other_name,
                            description=f"'{mod.display_name()}' should load after '{other_name}'",
                            suggestion="Use Auto-Sort to fix load order automatically, or move the mod down in the list."
                        ))
            
            # Check loadBefore - these mods should come after this one
            for before_id in mod.load_before:
                before_id_lower = before_id.lower()
                if before_id_lower in mod_positions:
                    before_pos = mod_positions[before_id_lower]
                    if before_pos < mod_pos:
                        other_name = next((m.display_name() for m in mods if m.package_id.lower() == before_id_lower), before_id)
                        conflicts.append(ConflictInfo(
                            conflict_type='load_order',
                            severity='warning',
                            mod1_id=mod.package_id,
                            mod1_name=mod.display_name(),
                            mod2_id=before_id,
                            mod2_name=other_name,
                            description=f"'{mod.display_name()}' should load before '{other_name}'",
                            suggestion="Use Auto-Sort to fix load order automatically, or move the mod up in the list."
                        ))
        
        return conflicts
    
    def get_resolution_steps(self, conflicts: list[ConflictInfo]) -> list[str]:
        """Get ordered list of resolution steps."""
        steps = []
        
        # Group by type
        errors = [c for c in conflicts if c.severity == 'error']
        warnings = [c for c in conflicts if c.severity == 'warning']
        
        if errors:
            steps.append("🔴 Critical Issues (must fix):")
            for c in errors:
                steps.append(f"  • {c.description}")
                steps.append(f"    → {c.suggestion}")
        
        if warnings:
            steps.append("\n🟡 Warnings (recommended to fix):")
            for c in warnings:
                steps.append(f"  • {c.description}")
                steps.append(f"    → {c.suggestion}")
        
        if not conflicts:
            steps.append("✅ No conflicts detected!")
        
        return steps
    
    def auto_fix_load_order(self, mods: list['ModInfo']) -> list['ModInfo']:
        """
        Automatically fix load order issues.
        Returns the sorted mod list.
        """
        return self.mod_parser.sort_by_load_order(mods)
