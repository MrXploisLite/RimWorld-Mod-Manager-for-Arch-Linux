#!/usr/bin/env python3
"""
Unit tests for game_detector.py
Tests RimWorld installation detection across platforms.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from game_detector import GameDetector, RimWorldInstallation, InstallationType


class TestGameDetector(unittest.TestCase):
    """Tests for GameDetector class."""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.detector = GameDetector()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_mock_rimworld(self, path, windows=False):
        """Create a mock RimWorld installation directory."""
        path.mkdir(parents=True, exist_ok=True)
        
        # Create Data/Core folder (required marker)
        data_core = path / "Data" / "Core"
        data_core.mkdir(parents=True)
        
        # Create Mods folder
        (path / "Mods").mkdir(exist_ok=True)
        
        if windows:
            # Create Windows executable marker
            (path / "RimWorldWin64.exe").touch()
        else:
            # Create Linux binary marker
            (path / "RimWorldLinux").touch()
        
        return path
    
    def test_is_valid_rimworld_with_data_core(self):
        """Test that Data/Core folder is recognized as valid."""
        rimworld_path = self._create_mock_rimworld(self.temp_dir / "RimWorld")
        self.assertTrue(self.detector._is_valid_rimworld(rimworld_path))
    
    def test_is_valid_rimworld_with_windows_exe(self):
        """Test that Windows executable is recognized."""
        rimworld_path = self._create_mock_rimworld(
            self.temp_dir / "RimWorld", windows=True
        )
        self.assertTrue(self.detector._is_valid_rimworld(rimworld_path))
    
    def test_is_valid_rimworld_empty_dir(self):
        """Test that empty directory is not valid."""
        empty_path = self.temp_dir / "Empty"
        empty_path.mkdir()
        self.assertFalse(self.detector._is_valid_rimworld(empty_path))
    
    def test_is_valid_rimworld_nonexistent(self):
        """Test that non-existent path is not valid."""
        fake_path = self.temp_dir / "NonExistent"
        self.assertFalse(self.detector._is_valid_rimworld(fake_path))
    
    def test_is_windows_build_true(self):
        """Test Windows build detection."""
        rimworld_path = self._create_mock_rimworld(
            self.temp_dir / "RimWorld", windows=True
        )
        self.assertTrue(self.detector._is_windows_build(rimworld_path))
    
    def test_is_windows_build_false(self):
        """Test Linux build detection."""
        rimworld_path = self._create_mock_rimworld(
            self.temp_dir / "RimWorld", windows=False
        )
        self.assertFalse(self.detector._is_windows_build(rimworld_path))
    
    def test_custom_paths_detection(self):
        """Test detection of custom installation paths."""
        # Create mock installation
        custom_path = self._create_mock_rimworld(self.temp_dir / "CustomRimWorld")
        
        # Create detector with custom path
        detector = GameDetector(custom_paths=[str(custom_path)])
        detector._detect_custom_paths()
        
        self.assertEqual(len(detector.installations), 1)
        self.assertEqual(detector.installations[0].path, custom_path)
        self.assertEqual(detector.installations[0].install_type, InstallationType.CUSTOM)
    
    def test_custom_paths_invalid_ignored(self):
        """Test that invalid custom paths are ignored."""
        invalid_path = self.temp_dir / "InvalidPath"
        invalid_path.mkdir()  # Empty, not valid RimWorld
        
        detector = GameDetector(custom_paths=[str(invalid_path)])
        detector._detect_custom_paths()
        
        self.assertEqual(len(detector.installations), 0)
    
    def test_duplicate_paths_not_added(self):
        """Test that duplicate paths are not added twice."""
        custom_path = self._create_mock_rimworld(self.temp_dir / "RimWorld")
        
        detector = GameDetector(custom_paths=[str(custom_path)])
        
        # Add first time
        detector._detect_custom_paths()
        self.assertEqual(len(detector.installations), 1)
        
        # Try to add again
        detector._detect_custom_paths()
        self.assertEqual(len(detector.installations), 1)


class TestRimWorldInstallation(unittest.TestCase):
    """Tests for RimWorldInstallation dataclass."""
    
    def test_display_name(self):
        """Test display name generation."""
        install = RimWorldInstallation(
            path=Path("/game/RimWorld"),
            install_type=InstallationType.STEAM_NATIVE
        )
        display = install.display_name()
        
        self.assertIn("[Steam]", display)
        self.assertIn("/game/RimWorld", display)
    
    def test_display_name_proton(self):
        """Test display name for Proton installation."""
        install = RimWorldInstallation(
            path=Path("/game/RimWorld"),
            install_type=InstallationType.STEAM_PROTON
        )
        display = install.display_name()
        
        self.assertIn("[Steam Proton]", display)
    
    def test_str_representation(self):
        """Test string representation."""
        install = RimWorldInstallation(
            path=Path("/game/RimWorld"),
            install_type=InstallationType.GOG
        )
        
        str_repr = str(install)
        self.assertIn("GOG", str_repr)
        self.assertIn("/game/RimWorld", str_repr)


class TestLibraryFoldersVdfParsing(unittest.TestCase):
    """Tests for Steam libraryfolders.vdf parsing."""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.detector = GameDetector()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_parse_library_folders_vdf(self):
        """Test parsing libraryfolders.vdf file."""
        vdf_content = '''
"libraryfolders"
{
    "0"
    {
        "path"      "/home/user/.local/share/Steam"
        "label"     ""
    }
    "1"
    {
        "path"      "/mnt/games/SteamLibrary"
        "label"     ""
    }
}
'''
        vdf_path = self.temp_dir / "libraryfolders.vdf"
        vdf_path.write_text(vdf_content)
        
        # Create the directories so they "exist"
        lib1 = self.temp_dir / "lib1"
        lib2 = self.temp_dir / "lib2"
        lib1.mkdir()
        lib2.mkdir()
        
        # Patch the paths in vdf to use temp dirs
        vdf_content_patched = f'''
"libraryfolders"
{{
    "0"
    {{
        "path"      "{lib1}"
    }}
    "1"
    {{
        "path"      "{lib2}"
    }}
}}
'''
        vdf_path.write_text(vdf_content_patched)
        
        libraries = self.detector._parse_library_folders_vdf(vdf_path)
        
        self.assertEqual(len(libraries), 2)
        self.assertIn(lib1, libraries)
        self.assertIn(lib2, libraries)
    
    def test_parse_library_folders_vdf_nonexistent(self):
        """Test parsing non-existent vdf file."""
        fake_vdf = self.temp_dir / "nonexistent.vdf"
        libraries = self.detector._parse_library_folders_vdf(fake_vdf)
        self.assertEqual(len(libraries), 0)


class TestInstallationType(unittest.TestCase):
    """Tests for InstallationType enum."""
    
    def test_all_types_have_values(self):
        """Test that all installation types have string values."""
        for install_type in InstallationType:
            self.assertIsInstance(install_type.value, str)
            self.assertTrue(len(install_type.value) > 0)
    
    def test_steam_types(self):
        """Test Steam-related installation types."""
        steam_types = [
            InstallationType.STEAM_NATIVE,
            InstallationType.STEAM_PROTON,
            InstallationType.STEAM_WINDOWS,
            InstallationType.STEAM_MACOS,
            InstallationType.FLATPAK_STEAM,
        ]
        for t in steam_types:
            self.assertIn("Steam", t.value)


if __name__ == "__main__":
    unittest.main()
