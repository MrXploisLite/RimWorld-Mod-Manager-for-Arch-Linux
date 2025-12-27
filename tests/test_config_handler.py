#!/usr/bin/env python3
"""
Unit tests for config_handler.py
Tests configuration save/load and modlist management.
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_handler import ConfigHandler, AppConfig


class TestConfigHandler(unittest.TestCase):
    """Tests for ConfigHandler class."""
    
    def setUp(self):
        """Set up test fixtures with mocked config directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        # Patch _get_config_dir to use temp directory
        self.patcher = patch.object(ConfigHandler, '_get_config_dir', return_value=self.temp_dir)
        self.patcher.start()
        self.config_handler = ConfigHandler()
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_default_config_created(self):
        """Test that default config is created on init."""
        self.assertIsNotNone(self.config_handler.config)
        self.assertIsInstance(self.config_handler.config, AppConfig)
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        # Modify config
        self.config_handler.config.window_width = 1920
        self.config_handler.config.window_height = 1080
        self.config_handler.config.last_installation = "/test/path"
        
        # Save
        self.config_handler.save()
        
        # Create new handler to load (with same patched dir)
        new_handler = ConfigHandler()
        
        self.assertEqual(new_handler.config.window_width, 1920)
        self.assertEqual(new_handler.config.window_height, 1080)
        self.assertEqual(new_handler.config.last_installation, "/test/path")
    
    def test_add_mod_source_path(self):
        """Test adding mod source paths."""
        test_path = str(self.temp_dir / "mods")
        
        result = self.config_handler.add_mod_source_path(test_path)
        
        self.assertTrue(result)
        self.assertIn(test_path, self.config_handler.config.mod_source_paths)
    
    def test_add_duplicate_mod_source_path(self):
        """Test that duplicate paths are not added."""
        test_path = str(self.temp_dir / "mods")
        
        self.config_handler.add_mod_source_path(test_path)
        result = self.config_handler.add_mod_source_path(test_path)
        
        self.assertFalse(result)
        self.assertEqual(
            self.config_handler.config.mod_source_paths.count(test_path), 
            1
        )
    
    def test_remove_mod_source_path(self):
        """Test removing mod source paths."""
        test_path = str(self.temp_dir / "mods")
        self.config_handler.add_mod_source_path(test_path)
        
        result = self.config_handler.remove_mod_source_path(test_path)
        
        self.assertTrue(result)
        self.assertNotIn(test_path, self.config_handler.config.mod_source_paths)


class TestModlistManagement(unittest.TestCase):
    """Tests for modlist save/load functionality."""
    
    def setUp(self):
        """Set up test fixtures with mocked config directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.patcher = patch.object(ConfigHandler, '_get_config_dir', return_value=self.temp_dir)
        self.patcher.start()
        self.config_handler = ConfigHandler()
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_modlist(self):
        """Test saving a modlist."""
        mod_ids = ["mod.one", "mod.two", "mod.three"]
        active_mods = ["mod.one", "mod.two"]
        
        filepath = self.config_handler.save_modlist("test_list", mod_ids, active_mods)
        
        self.assertIsNotNone(filepath)
        self.assertTrue(filepath.exists())
        
        # Verify content
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.assertEqual(data["name"], "test_list")
        self.assertEqual(data["mod_ids"], mod_ids)
        self.assertEqual(data["active_mods"], active_mods)
    
    def test_load_modlist(self):
        """Test loading a modlist."""
        mod_ids = ["mod.one", "mod.two", "mod.three"]
        active_mods = ["mod.one"]
        filepath = self.config_handler.save_modlist("test_list", mod_ids, active_mods)
        
        loaded = self.config_handler.load_modlist(filepath)
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "test_list")
        self.assertEqual(loaded["mod_ids"], mod_ids)
    
    def test_list_modlists(self):
        """Test listing available modlists."""
        # Save some modlists
        self.config_handler.save_modlist("list1", ["mod.a"], ["mod.a"])
        self.config_handler.save_modlist("list2", ["mod.b"], ["mod.b"])
        
        modlists = self.config_handler.list_modlists()
        
        # list_modlists returns list of Path objects
        self.assertEqual(len(modlists), 2)
        names = [p.stem for p in modlists]
        self.assertIn("list1", names)
        self.assertIn("list2", names)


class TestActiveModsPersistence(unittest.TestCase):
    """Tests for per-installation active mods persistence."""
    
    def setUp(self):
        """Set up test fixtures with mocked config directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.patcher = patch.object(ConfigHandler, '_get_config_dir', return_value=self.temp_dir)
        self.patcher.start()
        self.config_handler = ConfigHandler()
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_active_mods(self):
        """Test saving active mods for an installation."""
        install_path = "/game/rimworld"
        mods = ["mod.one", "mod.two"]
        
        self.config_handler.save_active_mods(install_path, mods)
        
        # Verify it's saved
        loaded = self.config_handler.get_active_mods(install_path)
        self.assertEqual(loaded, mods)
    
    def test_load_active_mods_empty(self):
        """Test loading active mods for unknown installation."""
        loaded = self.config_handler.get_active_mods("/unknown/path")
        self.assertEqual(loaded, [])
    
    def test_multiple_installations(self):
        """Test saving mods for multiple installations."""
        install1 = "/game/rimworld1"
        install2 = "/game/rimworld2"
        mods1 = ["mod.a", "mod.b"]
        mods2 = ["mod.x", "mod.y", "mod.z"]
        
        self.config_handler.save_active_mods(install1, mods1)
        self.config_handler.save_active_mods(install2, mods2)
        
        self.assertEqual(self.config_handler.get_active_mods(install1), mods1)
        self.assertEqual(self.config_handler.get_active_mods(install2), mods2)


if __name__ == "__main__":
    unittest.main()
