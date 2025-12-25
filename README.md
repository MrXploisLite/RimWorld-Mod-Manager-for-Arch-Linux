# RimModManager

[![GitHub license](https://img.shields.io/github/license/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/issues)
[![GitHub stars](https://img.shields.io/github/stars/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/stargazers)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)

A universal mod manager for RimWorld. Currently supports Linux (Arch-based distros), with cross-platform support coming soon.

## ✨ Features

### 🎮 Universal Game Detection
- Steam native Linux version
- Steam Windows version via Proton
- Flatpak Steam installations
- Standalone Windows versions via Wine
- Custom user-defined paths

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

### Arch Linux / CachyOS / EndeavourOS
```bash
sudo pacman -S python python-pyqt6 python-pyqt6-webengine

# For Workshop downloads (AUR)
yay -S steamcmd
```

### Run
```bash
git clone https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux.git
cd RimWorld-Mod-Manager-for-Arch-Linux
python main.py
```

### Desktop Entry (Optional)
Create `~/.local/share/applications/rimmodmanager.desktop`:
```ini
[Desktop Entry]
Name=RimModManager
Comment=Universal RimWorld Mod Manager
Exec=/usr/bin/python /path/to/rimmodmanager/main.py
Icon=application-x-executable
Terminal=false
Type=Application
Categories=Game;Utility;
```

## 📖 Usage

1. Launch RimModManager
2. Select your RimWorld installation from dropdown
3. Manage mods with drag-and-drop or hover buttons
4. Click "Apply Load Order" to save changes
5. Click "🎮 Play RimWorld" to launch

### Configuration
Config stored in `~/.config/rimmodmanager/config.json`

## 🔧 Troubleshooting

### SteamCMD not found
```bash
yay -S steamcmd
```

### No installations detected
Add custom path with "Add Custom" button

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT License
