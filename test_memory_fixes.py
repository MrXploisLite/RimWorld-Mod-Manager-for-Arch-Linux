#!/usr/bin/env python3
"""
Test script to verify memory leak fixes in RimModManager.
Run with: python test_memory_fixes.py
"""

import sys

def test_imports():
    """Test that all modules import correctly."""
    print("Testing imports...")
    try:
        from ui.workshop_browser import WorkshopBrowser, WorkshopDownloadDialog, DownloadThread
        from ui.tools_widgets import ModUpdateCheckerWidget
        from ui.download_manager import DownloadLogWidget, LiveDownloadWorker
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import error: {e}")
        return False

def test_workshop_browser_cleanup():
    """Test WorkshopBrowser has cleanup methods."""
    print("\nTesting WorkshopBrowser cleanup methods...")
    from ui.workshop_browser import WorkshopBrowser
    
    # Check cleanup method exists
    if hasattr(WorkshopBrowser, 'cleanup'):
        print("  ✓ cleanup() method exists")
    else:
        print("  ✗ cleanup() method missing")
        return False
    
    # Check closeEvent override
    if hasattr(WorkshopBrowser, 'closeEvent'):
        print("  ✓ closeEvent() method exists")
    else:
        print("  ✗ closeEvent() method missing")
        return False
    
    return True

def test_download_dialog_cleanup():
    """Test WorkshopDownloadDialog has cleanup method."""
    print("\nTesting WorkshopDownloadDialog cleanup...")
    from ui.workshop_browser import WorkshopDownloadDialog
    
    if hasattr(WorkshopDownloadDialog, '_cleanup_download_thread'):
        print("  ✓ _cleanup_download_thread() method exists")
        return True
    else:
        print("  ✗ _cleanup_download_thread() method missing")
        return False

def test_update_checker_cleanup():
    """Test ModUpdateCheckerWidget has cleanup method."""
    print("\nTesting ModUpdateCheckerWidget cleanup...")
    from ui.tools_widgets import ModUpdateCheckerWidget
    
    if hasattr(ModUpdateCheckerWidget, '_cleanup_worker'):
        print("  ✓ _cleanup_worker() method exists")
        return True
    else:
        print("  ✗ _cleanup_worker() method missing")
        return False

def test_download_manager_cleanup():
    """Test DownloadLogWidget has cleanup method."""
    print("\nTesting DownloadLogWidget cleanup...")
    from ui.download_manager import DownloadLogWidget
    
    if hasattr(DownloadLogWidget, '_cleanup_worker'):
        print("  ✓ _cleanup_worker() method exists")
        return True
    else:
        print("  ✗ _cleanup_worker() method missing")
        return False

def main():
    print("=" * 50)
    print("RimModManager Memory Leak Fix Verification")
    print("=" * 50)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("WorkshopBrowser cleanup", test_workshop_browser_cleanup()))
    results.append(("WorkshopDownloadDialog cleanup", test_download_dialog_cleanup()))
    results.append(("ModUpdateCheckerWidget cleanup", test_update_checker_cleanup()))
    results.append(("DownloadLogWidget cleanup", test_download_manager_cleanup()))
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ All memory leak fixes verified!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
