#!/usr/bin/env python3
"""
Unit tests for mod_presets.py
Tests preset encoding/decoding functionality.
"""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from mod_presets import PresetEncoder, create_preset_code, load_preset_code


class TestPresetEncoder(unittest.TestCase):
    """Tests for PresetEncoder class."""
    
    def test_encode_basic(self):
        """Test basic encoding of package IDs."""
        package_ids = ["mod.one", "mod.two", "mod.three"]
        code = PresetEncoder.encode(package_ids, name="Test")
        
        self.assertTrue(code.startswith("RMM:v1:"))
        self.assertGreater(len(code), 20)
    
    def test_decode_basic(self):
        """Test basic decoding of preset code."""
        package_ids = ["mod.one", "mod.two"]
        code = PresetEncoder.encode(package_ids, name="Test Preset")
        
        preset = PresetEncoder.decode(code)
        
        self.assertIsNotNone(preset)
        self.assertEqual(preset.name, "Test Preset")
        self.assertEqual(preset.package_ids, package_ids)
    
    def test_encode_decode_roundtrip(self):
        """Test that encode/decode preserves data."""
        original_ids = ["brrainz.harmony", "ludeon.rimworld", "test.mod.id"]
        original_workshop = ["123456789", "987654321"]
        
        code = PresetEncoder.encode(
            package_ids=original_ids,
            name="Roundtrip Test",
            workshop_ids=original_workshop,
            description="Test description"
        )
        
        preset = PresetEncoder.decode(code)
        
        self.assertIsNotNone(preset)
        self.assertEqual(preset.package_ids, original_ids)
        self.assertEqual(preset.workshop_ids, original_workshop)
        self.assertEqual(preset.name, "Roundtrip Test")
        self.assertEqual(preset.description, "Test description")
    
    def test_decode_invalid_prefix(self):
        """Test decoding with invalid prefix."""
        preset = PresetEncoder.decode("INVALID:v1:abc123")
        self.assertIsNone(preset)
    
    def test_decode_invalid_format(self):
        """Test decoding with invalid format."""
        preset = PresetEncoder.decode("RMM:invalid")
        self.assertIsNone(preset)
    
    def test_decode_empty_string(self):
        """Test decoding empty string."""
        preset = PresetEncoder.decode("")
        self.assertIsNone(preset)
    
    def test_validate_code_valid(self):
        """Test validation of valid code."""
        code = PresetEncoder.encode(["mod.test"], name="Valid")
        is_valid, message = PresetEncoder.validate_code(code)
        
        self.assertTrue(is_valid)
        self.assertIn("Valid preset", message)
    
    def test_validate_code_invalid(self):
        """Test validation of invalid code."""
        is_valid, message = PresetEncoder.validate_code("not a valid code")
        
        self.assertFalse(is_valid)
        self.assertIn("must start with", message)
    
    def test_validate_code_empty(self):
        """Test validation of empty code."""
        is_valid, message = PresetEncoder.validate_code("")
        
        self.assertFalse(is_valid)
        self.assertEqual(message, "Empty code")
    
    def test_get_code_stats(self):
        """Test getting code statistics."""
        code = PresetEncoder.encode(
            ["mod.a", "mod.b", "mod.c"],
            name="Stats Test",
            workshop_ids=["111", "222"]
        )
        
        stats = PresetEncoder.get_code_stats(code)
        
        self.assertTrue(stats["valid"])
        self.assertEqual(stats["name"], "Stats Test")
        self.assertEqual(stats["mod_count"], 3)
        self.assertEqual(stats["workshop_count"], 2)
    
    def test_get_code_stats_invalid(self):
        """Test getting stats for invalid code."""
        stats = PresetEncoder.get_code_stats("invalid")
        self.assertFalse(stats["valid"])
    
    def test_encode_empty_list(self):
        """Test encoding empty package list."""
        code = PresetEncoder.encode([], name="Empty")
        preset = PresetEncoder.decode(code)
        
        self.assertIsNotNone(preset)
        self.assertEqual(preset.package_ids, [])


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for convenience functions."""
    
    def test_create_preset_code(self):
        """Test create_preset_code function."""
        code = create_preset_code(["mod.test"], name="Convenience Test")
        
        self.assertTrue(code.startswith("RMM:v1:"))
    
    def test_load_preset_code(self):
        """Test load_preset_code function."""
        code = create_preset_code(["mod.test"], name="Load Test")
        preset = load_preset_code(code)
        
        self.assertIsNotNone(preset)
        self.assertEqual(preset.name, "Load Test")


if __name__ == "__main__":
    unittest.main()
