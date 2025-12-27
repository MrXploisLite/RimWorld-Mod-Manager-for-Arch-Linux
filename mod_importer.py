"""
Mod Importer for RimModManager
Import modlists from RimPy, RimSort, and other formats.
"""

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger("rimmodmanager.mod_importer")


class ImportFormat(Enum):
    """Supported import formats."""
    UNKNOWN = "Unknown"
    RIMSORT_JSON = "RimSort JSON"
    RIMPY_XML = "RimPy XML"
    MODSCONFIG_XML = "ModsConfig.xml"
    PLAIN_TEXT = "Plain Text (Package IDs)"
    WORKSHOP_IDS = "Workshop IDs"
    RMM_JSON = "RimModManager JSON"


@dataclass
class ImportResult:
    """Result of import operation."""
    success: bool
    format_detected: ImportFormat
    package_ids: list[str]  # Ordered list of package IDs
    workshop_ids: list[str]  # Workshop IDs found (for downloading)
    mod_names: dict[str, str]  # package_id -> name mapping
    errors: list[str]
    warnings: list[str]


class ModImporter:
    """Import modlists from various formats."""
    
    def __init__(self):
        pass
    
    def detect_format(self, file_path: Path) -> ImportFormat:
        """Auto-detect the format of a modlist file."""
        if not file_path.exists():
            return ImportFormat.UNKNOWN
        
        suffix = file_path.suffix.lower()
        name = file_path.name.lower()
        
        # Check by filename
        if name == "modsconfig.xml":
            return ImportFormat.MODSCONFIG_XML
        
        # Check by extension
        if suffix == ".json":
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # RimSort format detection
                if isinstance(data, dict):
                    if "mods" in data or "active_mods" in data:
                        return ImportFormat.RIMSORT_JSON
                    if "package_ids" in data or "modlist" in data:
                        return ImportFormat.RMM_JSON
                
                # List of strings
                if isinstance(data, list):
                    return ImportFormat.RMM_JSON
                    
            except (json.JSONDecodeError, IOError):
                pass
            return ImportFormat.RMM_JSON
        
        if suffix == ".xml":
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                
                # ModsConfig.xml format
                if root.tag == "ModsConfigData":
                    return ImportFormat.MODSCONFIG_XML
                
                # RimPy format
                if root.tag in ("ModList", "modlist", "RimPyModList"):
                    return ImportFormat.RIMPY_XML
                    
            except ET.ParseError:
                pass
            return ImportFormat.RIMPY_XML
        
        if suffix in (".txt", ".list", ".rml"):
            # Check content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                if lines:
                    # All numeric = workshop IDs
                    if all(line.isdigit() for line in lines[:10]):
                        return ImportFormat.WORKSHOP_IDS
                    # Contains dots = package IDs
                    if any('.' in line for line in lines[:10]):
                        return ImportFormat.PLAIN_TEXT
                        
            except IOError:
                pass
            return ImportFormat.PLAIN_TEXT
        
        return ImportFormat.UNKNOWN
    
    def import_file(self, file_path: Path) -> ImportResult:
        """Import a modlist file, auto-detecting format."""
        format_type = self.detect_format(file_path)
        
        if format_type == ImportFormat.UNKNOWN:
            return ImportResult(
                success=False,
                format_detected=format_type,
                package_ids=[],
                workshop_ids=[],
                mod_names={},
                errors=[f"Unknown file format: {file_path.suffix}"],
                warnings=[]
            )
        
        try:
            if format_type == ImportFormat.RIMSORT_JSON:
                return self._import_rimsort_json(file_path)
            elif format_type == ImportFormat.RIMPY_XML:
                return self._import_rimpy_xml(file_path)
            elif format_type == ImportFormat.MODSCONFIG_XML:
                return self._import_modsconfig_xml(file_path)
            elif format_type == ImportFormat.PLAIN_TEXT:
                return self._import_plain_text(file_path)
            elif format_type == ImportFormat.WORKSHOP_IDS:
                return self._import_workshop_ids(file_path)
            elif format_type == ImportFormat.RMM_JSON:
                return self._import_rmm_json(file_path)
            else:
                return ImportResult(
                    success=False,
                    format_detected=format_type,
                    package_ids=[],
                    workshop_ids=[],
                    mod_names={},
                    errors=[f"Unsupported format: {format_type.value}"],
                    warnings=[]
                )
        except Exception as e:
            log.exception(f"Error importing {file_path}")
            return ImportResult(
                success=False,
                format_detected=format_type,
                package_ids=[],
                workshop_ids=[],
                mod_names={},
                errors=[f"Import error: {str(e)}"],
                warnings=[]
            )
    
    def _import_rimsort_json(self, file_path: Path) -> ImportResult:
        """Import RimSort JSON modlist."""
        errors = []
        warnings = []
        package_ids = []
        workshop_ids = []
        mod_names = {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # RimSort can have different structures
            mods_data = None
            
            if isinstance(data, dict):
                # Try different keys RimSort might use
                for key in ["mods", "active_mods", "activeMods", "mod_list", "modList"]:
                    if key in data:
                        mods_data = data[key]
                        break
                
                # Get name if available
                if "name" in data:
                    log.info(f"Importing RimSort modlist: {data['name']}")
            
            if isinstance(data, list):
                mods_data = data
            
            if not mods_data:
                errors.append("No mod list found in JSON file")
                return ImportResult(False, ImportFormat.RIMSORT_JSON, [], [], {}, errors, warnings)
            
            for item in mods_data:
                if isinstance(item, str):
                    # Simple string - could be package ID or workshop ID
                    if item.isdigit() and len(item) >= 7:
                        workshop_ids.append(item)
                    else:
                        package_ids.append(item.lower())
                elif isinstance(item, dict):
                    # Object with metadata
                    pkg_id = item.get("packageId") or item.get("package_id") or item.get("id", "")
                    if pkg_id:
                        package_ids.append(pkg_id.lower())
                    
                    name = item.get("name") or item.get("displayName", "")
                    if name and pkg_id:
                        mod_names[pkg_id.lower()] = name
                    
                    wid = item.get("workshopId") or item.get("workshop_id") or item.get("steamId", "")
                    if wid and str(wid).isdigit():
                        workshop_ids.append(str(wid))
            
            if not package_ids and not workshop_ids:
                errors.append("No valid mods found in file")
                return ImportResult(False, ImportFormat.RIMSORT_JSON, [], [], {}, errors, warnings)
            
            log.info(f"Imported {len(package_ids)} package IDs, {len(workshop_ids)} workshop IDs from RimSort")
            
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {e}")
            return ImportResult(False, ImportFormat.RIMSORT_JSON, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.RIMSORT_JSON,
            package_ids=package_ids,
            workshop_ids=workshop_ids,
            mod_names=mod_names,
            errors=errors,
            warnings=warnings
        )
    
    def _import_rimpy_xml(self, file_path: Path) -> ImportResult:
        """Import RimPy XML modlist."""
        errors = []
        warnings = []
        package_ids = []
        workshop_ids = []
        mod_names = {}
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Find mod entries - RimPy uses various structures
            for mod_elem in root.iter():
                if mod_elem.tag.lower() in ("mod", "li", "item", "entry"):
                    # Check for package ID
                    pkg_id = None
                    name = None
                    wid = None
                    
                    # Direct text content
                    if mod_elem.text and mod_elem.text.strip():
                        text = mod_elem.text.strip()
                        if '.' in text:
                            pkg_id = text
                        elif text.isdigit():
                            wid = text
                    
                    # Child elements
                    for child in mod_elem:
                        tag = child.tag.lower()
                        text = child.text.strip() if child.text else ""
                        
                        if tag in ("packageid", "package_id", "id"):
                            pkg_id = text
                        elif tag in ("name", "displayname", "title"):
                            name = text
                        elif tag in ("workshopid", "workshop_id", "steamid", "publishedfileid"):
                            wid = text
                    
                    # Attributes
                    pkg_id = pkg_id or mod_elem.get("packageId") or mod_elem.get("id")
                    name = name or mod_elem.get("name")
                    wid = wid or mod_elem.get("workshopId") or mod_elem.get("steamId")
                    
                    if pkg_id:
                        package_ids.append(pkg_id.lower())
                        if name:
                            mod_names[pkg_id.lower()] = name
                    
                    if wid and wid.isdigit():
                        workshop_ids.append(wid)
            
            # Also check for activeMods section (ModsConfig style)
            active_mods = root.find("activeMods")
            if active_mods is not None:
                for li in active_mods.findall("li"):
                    if li.text and li.text.strip():
                        pkg_id = li.text.strip().lower()
                        if pkg_id not in package_ids:
                            package_ids.append(pkg_id)
            
            if not package_ids and not workshop_ids:
                errors.append("No valid mods found in XML file")
                return ImportResult(False, ImportFormat.RIMPY_XML, [], [], {}, errors, warnings)
            
            log.info(f"Imported {len(package_ids)} package IDs from RimPy XML")
            
        except ET.ParseError as e:
            errors.append(f"Invalid XML: {e}")
            return ImportResult(False, ImportFormat.RIMPY_XML, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.RIMPY_XML,
            package_ids=package_ids,
            workshop_ids=workshop_ids,
            mod_names=mod_names,
            errors=errors,
            warnings=warnings
        )
    
    def _import_modsconfig_xml(self, file_path: Path) -> ImportResult:
        """Import game's ModsConfig.xml."""
        errors = []
        warnings = []
        package_ids = []
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            active_mods = root.find("activeMods")
            if active_mods is None:
                errors.append("No activeMods section found")
                return ImportResult(False, ImportFormat.MODSCONFIG_XML, [], [], {}, errors, warnings)
            
            for li in active_mods.findall("li"):
                if li.text and li.text.strip():
                    package_ids.append(li.text.strip().lower())
            
            if not package_ids:
                warnings.append("No active mods found in ModsConfig.xml")
            
            log.info(f"Imported {len(package_ids)} package IDs from ModsConfig.xml")
            
        except ET.ParseError as e:
            errors.append(f"Invalid XML: {e}")
            return ImportResult(False, ImportFormat.MODSCONFIG_XML, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.MODSCONFIG_XML,
            package_ids=package_ids,
            workshop_ids=[],
            mod_names={},
            errors=errors,
            warnings=warnings
        )
    
    def _import_plain_text(self, file_path: Path) -> ImportResult:
        """Import plain text list of package IDs."""
        errors = []
        warnings = []
        package_ids = []
        workshop_ids = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for line in content.split('\n'):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#') or line.startswith('//'):
                    continue
                
                # Remove inline comments
                if '#' in line:
                    line = line.split('#')[0].strip()
                
                # Check if it's a workshop ID
                if line.isdigit() and len(line) >= 7:
                    workshop_ids.append(line)
                elif '.' in line or line.startswith("ludeon."):
                    # Looks like a package ID
                    package_ids.append(line.lower())
                else:
                    # Could be a mod name or invalid
                    warnings.append(f"Skipped unrecognized line: {line[:50]}")
            
            if not package_ids and not workshop_ids:
                errors.append("No valid package IDs or workshop IDs found")
                return ImportResult(False, ImportFormat.PLAIN_TEXT, [], [], {}, errors, warnings)
            
            log.info(f"Imported {len(package_ids)} package IDs, {len(workshop_ids)} workshop IDs from text")
            
        except IOError as e:
            errors.append(f"Failed to read file: {e}")
            return ImportResult(False, ImportFormat.PLAIN_TEXT, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.PLAIN_TEXT,
            package_ids=package_ids,
            workshop_ids=workshop_ids,
            mod_names={},
            errors=errors,
            warnings=warnings
        )
    
    def _import_workshop_ids(self, file_path: Path) -> ImportResult:
        """Import list of workshop IDs."""
        errors = []
        warnings = []
        workshop_ids = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for line in content.split('\n'):
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                # Extract workshop ID from URL if present
                if "steamcommunity.com" in line:
                    import re
                    match = re.search(r'id=(\d+)', line)
                    if match:
                        workshop_ids.append(match.group(1))
                        continue
                
                if line.isdigit() and len(line) >= 7:
                    workshop_ids.append(line)
                else:
                    warnings.append(f"Skipped invalid workshop ID: {line[:30]}")
            
            if not workshop_ids:
                errors.append("No valid workshop IDs found")
                return ImportResult(False, ImportFormat.WORKSHOP_IDS, [], [], {}, errors, warnings)
            
            log.info(f"Imported {len(workshop_ids)} workshop IDs")
            
        except IOError as e:
            errors.append(f"Failed to read file: {e}")
            return ImportResult(False, ImportFormat.WORKSHOP_IDS, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.WORKSHOP_IDS,
            package_ids=[],
            workshop_ids=workshop_ids,
            mod_names={},
            errors=errors,
            warnings=warnings
        )
    
    def _import_rmm_json(self, file_path: Path) -> ImportResult:
        """Import RimModManager's own JSON format."""
        errors = []
        warnings = []
        package_ids = []
        workshop_ids = []
        mod_names = {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle list format
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        package_ids.append(item.lower())
                    elif isinstance(item, dict):
                        pkg_id = item.get("package_id", "")
                        if pkg_id:
                            package_ids.append(pkg_id.lower())
                            if "name" in item:
                                mod_names[pkg_id.lower()] = item["name"]
            
            # Handle dict format
            elif isinstance(data, dict):
                # Our format
                if "package_ids" in data:
                    package_ids = [p.lower() for p in data["package_ids"]]
                if "modlist" in data:
                    for item in data["modlist"]:
                        if isinstance(item, str):
                            package_ids.append(item.lower())
                        elif isinstance(item, dict):
                            pkg_id = item.get("package_id", "")
                            if pkg_id:
                                package_ids.append(pkg_id.lower())
                if "workshop_ids" in data:
                    workshop_ids = data["workshop_ids"]
                if "mod_names" in data:
                    mod_names = {k.lower(): v for k, v in data["mod_names"].items()}
            
            if not package_ids and not workshop_ids:
                errors.append("No valid mods found in JSON")
                return ImportResult(False, ImportFormat.RMM_JSON, [], [], {}, errors, warnings)
            
            log.info(f"Imported {len(package_ids)} package IDs from RMM JSON")
            
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {e}")
            return ImportResult(False, ImportFormat.RMM_JSON, [], [], {}, errors, warnings)
        
        return ImportResult(
            success=True,
            format_detected=ImportFormat.RMM_JSON,
            package_ids=package_ids,
            workshop_ids=workshop_ids,
            mod_names=mod_names,
            errors=errors,
            warnings=warnings
        )
    
    def import_from_text(self, text: str) -> ImportResult:
        """Import from pasted text content."""
        errors = []
        warnings = []
        package_ids = []
        workshop_ids = []
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line or line.startswith('#'):
                continue
            
            # Workshop URL
            if "steamcommunity.com" in line:
                import re
                match = re.search(r'id=(\d+)', line)
                if match:
                    workshop_ids.append(match.group(1))
                continue
            
            # Workshop ID
            if line.isdigit() and len(line) >= 7:
                workshop_ids.append(line)
                continue
            
            # Package ID
            if '.' in line:
                package_ids.append(line.lower())
                continue
            
            warnings.append(f"Skipped: {line[:40]}")
        
        success = bool(package_ids or workshop_ids)
        
        return ImportResult(
            success=success,
            format_detected=ImportFormat.PLAIN_TEXT,
            package_ids=package_ids,
            workshop_ids=workshop_ids,
            mod_names={},
            errors=errors if not success else [],
            warnings=warnings
        )
