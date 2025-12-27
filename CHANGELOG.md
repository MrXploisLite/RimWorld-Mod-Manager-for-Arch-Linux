# Changelog

All notable changes to RimModManager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-12-27

### Added
- **Dark/Light Theme Toggle**: System/Dark/Light theme options in Settings
- **Auto-Update Checker**: Checks GitHub releases on startup for new versions
- **Screenshots in README**: Collapsible gallery showcasing the UI

### Changed
- **Code Cleanup**: Removed all unused imports and variables
- **Fixed Ambiguous Variables**: Renamed `l` to `line` in mod_importer.py
- **Removed Redundant Imports**: Cleaned up duplicate shutil imports in main_window.py

### Fixed
- All flake8 F401 (unused imports), F841 (unused variables), E741 (ambiguous names) warnings resolved
- All F811 (redefinition) warnings resolved

## [0.1.0] - 2025-12-27

### Added
- **Batch Operations**: Select All, Deselect All, Activate/Deactivate Selected buttons
- **Keyboard Shortcuts**: Ctrl+A (select all), Delete (deactivate), Alt+Up/Down (reorder), etc.
- **AppImage Build**: Portable Linux package (no installation required)
- **CI/CD Pipeline**: Automated testing on Python 3.10, 3.11, 3.12
- **Unit Tests**: 68 tests covering config, parser, game detection, presets, importer
- **Wiki Documentation**: Comprehensive user guide at `docs/WIKI.md`
- **Release Workflow**: Automated builds for Windows (.exe, .zip), Linux (.tar.gz, .deb), macOS (.zip)

### Fixed
- **ModsConfig.xml Corruption**: Now uses RimSort-style format with proper lowercase IDs
- **Proton/Wine Symlink Failure**: Auto-detects Wine/Proton and uses copy mode
- **Workshop Browser Queue**: Auto-clears completed downloads
- **Memory Leaks**: QThread workers now properly cleaned up with `deleteLater()`
- **Undefined DownloadTask**: Removed unused callback methods with undefined type hints

### Changed
- Version now centralized in `main.py` (`__version__`)
- Improved error handling with standardized urllib timeouts
- Removed dead code (unused ScanWorker, DownloadWorker classes)

## [0.0.7] - 2025-12-25 (Pre-release)

### Added
- Initial public release
- Cross-platform RimWorld installation detection
- Drag-and-drop mod load order management
- Steam Workshop downloads via SteamCMD
- Embedded Workshop browser (PyQt6-WebEngine)
- Mod profiles and automatic backups
- Conflict detection and resolution assistant
- Import/export from game's ModsConfig.xml
- Smart game launcher with Wine/Proton support

### Supported Platforms
- Windows (Steam, GOG, standalone)
- macOS (Steam, GOG, standalone)
- Linux (Steam native, Proton, Flatpak, Wine, Lutris, Bottles)

---

## Version History

| Version | Date | Status |
|---------|------|--------|
| 0.2.0 | 2025-12-27 | Current |
| 0.1.0 | 2025-12-27 | Stable |
| 0.0.7 | 2025-12-25 | Pre-release |
