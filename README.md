# RimModManager

[![GitHub license](https://img.shields.io/github/license/MrXploisLite/RimModManager)](https://github.com/MrXploisLite/RimModManager/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/MrXploisLite/RimModManager)](https://github.com/MrXploisLite/RimModManager/issues)
[![GitHub stars](https://img.shields.io/github/stars/MrXploisLite/RimModManager)](https://github.com/MrXploisLite/RimModManager/stargazers)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)

A universal mod manager for RimWorld. Supports Windows, macOS, and Linux.

## ✨ Features

### 🎮 Universal Game Detection
- **Windows**: Steam, GOG, standalone installations
- **macOS**: Steam, GOG, standalone installations
- **Linux**: Steam native, Proton, Flatpak, Wine, standalone

### 📦 Mod Management
- Drag-and-drop load order management
- Symlink-based mod activation (non-destructive)
- Hover buttons for quick activate/deactivate
- Search and filter mods
- Mod conflict & dependency detection
- Auto-sort by load order
- Smart game launcher (detects Steam license vs standalone)

### 🔧 Workshop Integration
- Integrated Workshop Browser with embedded web view
- One-click add mods to download queue
- Parse entire Collections
- Batch downloads with live progress
- Single session SteamCMD downloads

### 💾 Save/Config Management
- Auto-detect save/config locations
- Quick buttons to open folders
- Save and load modlists as JSON

## 🚀 Installation

### Windows
```powershell
# Install Python from https://python.org
pip install PyQt6 PyQt6-WebEngine

# SteamCMD (for Workshop downloads)
# Download from: https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
# Or with Chocolatey: choco install steamcmd
```

### macOS
```bash
# Install Python from https://python.org or Homebrew
pip install PyQt6 PyQt6-WebEngine

# SteamCMD
brew install steamcmd
```

### Linux (Arch / CachyOS / EndeavourOS)
```bash
sudo pacman -S python python-pyqt6 python-pyqt6-webengine

# SteamCMD from AUR
yay -S steamcmd
```

### Linux (Ubuntu / Debian)
```bash
pip install PyQt6 PyQt6-WebEngine
sudo apt install steamcmd
```

### Run
```bash
git clone https://github.com/MrXploisLite/RimModManager.git
cd RimModManager
python main.py
```

## 📖 Usage

1. Launch RimModManager
2. Select your RimWorld installation from dropdown
3. Manage mods with drag-and-drop or hover buttons
4. Click "Apply Load Order" to save changes
5. Click "🎮 Play RimWorld" to launch

### Configuration Locations
- **Windows**: `%APPDATA%/RimModManager/config.json`
- **macOS**: `~/Library/Application Support/RimModManager/config.json`
- **Linux**: `~/.config/rimmodmanager/config.json`

## 🔧 Troubleshooting

### SteamCMD not found
- **Windows**: Download from Steam or use `choco install steamcmd`
- **macOS**: `brew install steamcmd`
- **Linux (Arch)**: `yay -S steamcmd`
- **Linux (Ubuntu)**: `sudo apt install steamcmd`

### No installations detected
Add custom path with "Add Custom" button

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT License
