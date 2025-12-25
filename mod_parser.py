"""
Mod Parser for RimModManager
Parses About/About.xml files and manages mod metadata.
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


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
            except Exception as e:
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
                except Exception as e:
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
                    with open(pub_id_file, 'r') as f:
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


if __name__ == "__main__":
    main()
