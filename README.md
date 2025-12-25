# RimWorld Mod Manager for Arch Linux

[![GitHub license](https://img.shields.io/github/license/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/issues)
[![GitHub stars](https://img.shields.io/github/stars/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux)](https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux/stargazers)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Arch Linux](https://img.shields.io/badge/Arch%20Linux-1793D1?logo=arch-linux&logoColor=white)](https://archlinux.org/)

A universal, robust mod manager for RimWorld on Arch Linux and derivatives (CachyOS, Manjaro, EndeavourOS, etc.).

![Screenshot](https://img.shields.io/badge/Status-Active-success)

## ✨ Features

### 🎮 Universal Game Detection
Automatically detects RimWorld installations from:
- ✅ Steam native Linux version
- ✅ Steam Windows version via Proton (including Proton-GE, Proton-CachyOS)
- ✅ Flatpak Steam installations
- ✅ Non-Steam/standalone Windows versions running via Wine/Proton
- ✅ Custom user-defined paths

### 📦 Mod Management
- 🔄 Drag-and-drop load order management
- 🔗 Symlink-based mod activation (non-destructive)
- ➕ Hover buttons for quick activate/deactivate
- 🔍 Search and filter mods
- ⚠️ Mod conflict detection (duplicate packageId)
- 📋 Dependency checking & incompatibility warnings
- 🔀 Auto-sort by load order (loadBefore/loadAfter)
- ▶️ Launch game directly from mod manager

### 🔧 Workshop Integration
- 🌐 **Integrated Workshop Browser** with embedded web view
- 🔥 Browse Most Popular, Recent, Trending mods directly in-app
- ➕ One-click add mods to download queue
- 📁 Parse entire Collections - subscribe all mods at once
- 🚫 Duplicate detection - skip already downloaded mods
- 📝 Batch download from text file or pasted URLs
- 📊 Live download progress with SteamCMD output
- 🔄 Single session batch downloads (efficient!)

### 💾 Save/Config Management
- 🔍 Automatically detects save/config locations for each installation type
- 📂 Quick buttons to open save and config folders
- 💾 Save and load modlists as JSON

## 🚀 Installation

### Prerequisites

**Arch Linux / CachyOS / EndeavourOS:**
```bash
sudo pacman -S python python-pyqt6

# Optional: For integrated Workshop browser (embedded web view)
sudo pacman -S python-pyqt6-webengine
```

**Manjaro:**
```bash
pamac install python python-pyqt6
```

**For Workshop downloads (optional - from AUR):**
```bash
# Using yay
yay -S steamcmd

# Or using paru
paru -S steamcmd

# Or manual installation
git clone https://aur.archlinux.org/steamcmd.git
cd steamcmd
makepkg -si
```

### Install the Mod Manager

1. Clone or download this repository:
```bash
git clone https://github.com/MrXploisLite/RimWorld-Mod-Manager-for-Arch-Linux.git
cd RimWorld-Mod-Manager-for-Arch-Linux
```

2. Run the application:
```bash
python main.py
```

### Create a Desktop Entry (Optional)

Create `~/.local/share/applications/rimworld-mod-manager.desktop`:
```ini
[Desktop Entry]
Name=RimWorld Mod Manager
Comment=Manage RimWorld mods on Linux
Exec=/usr/bin/python /path/to/rimworld-mod-manager/main.py
Icon=application-x-executable
Terminal=false
Type=Application
Categories=Game;Utility;
```

## 📖 Usage Guide

### First Launch

1. The mod manager will automatically scan for RimWorld installations
2. Select your installation from the dropdown
3. Mods will be scanned and displayed in the Available Mods list

### Managing Mods

**Activating Mods:**
- Click the ➕ button that appears when hovering over a mod
- Or double-click a mod in "Available Mods" to activate it
- Or drag mods from Available to Active list
- Or right-click and select "Activate Selected"

**Deactivating Mods:**
- Click the ➖ button that appears when hovering over a mod
- Or double-click a mod in "Active Mods" to deactivate it
- Or drag mods from Active to Available list
- Or right-click and select "Deactivate Selected"

**Changing Load Order:**
- Drag mods up/down in the Active list
- Use the arrow buttons (⬆⬇) to move selected mods
- Use ⬆⬆/⬇⬇ buttons to move to top/bottom
- Click 🔄 **Auto-Sort** to automatically sort by dependencies

**Launching the Game:**
- Click the 🎮 **Play RimWorld** button to launch the game directly

**Applying Changes:**
- Click "Apply Load Order" to apply your mod configuration
- This creates symbolic links in the game's Mods folder

### Adding Mod Sources

Click "Manage Mod Paths..." to add directories containing mods:
- Workshop download folders
- Manually downloaded mod collections
- GitHub cloned mods

### Downloading Workshop Mods

1. Click "Download Workshop Mods"
2. Paste Workshop URLs or mod IDs (one per line)
3. Click "Download"
4. Mods are downloaded to `~/RimWorld_Workshop_Mods/`

**Supported formats:**
```
https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077
steamcommunity.com/workshop/filedetails/?id=818773962
2009463077
```

### Saving/Loading Modlists

- **Save**: Click "Save Modlist" and enter a name
- **Load**: Click "Load Modlist" and select from saved lists
- Modlists are stored in `~/.config/rimworld-mod-manager/modlists/`

## Installation Types Explained

### Steam Native Linux
- Path: `~/.local/share/Steam/steamapps/common/RimWorld/`
- Saves: `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/`
- Uses Linux executable

### Steam Windows via Proton
- Path: `~/.local/share/Steam/steamapps/common/RimWorld/`
- Saves: `~/.local/share/Steam/steamapps/compatdata/294100/pfx/drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/`
- Uses Windows executable via Proton
- Compatible with custom Proton versions (GE, CachyOS, etc.)

### Flatpak Steam
- Path: `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/RimWorld/`
- Saves: Inside Flatpak Proton prefix or native path depending on version
- Detected automatically

### Standalone/Wine
- Custom installation paths
- Add via "Add Custom" button
- Saves typically in Wine prefix: `<prefix>/drive_c/users/<user>/AppData/LocalLow/Ludeon Studios/...`

## 🔧 Troubleshooting

### No installations detected
1. Ensure RimWorld is installed
2. Check Steam library paths
3. Add custom path manually with "Add Custom" button

### SteamCMD not found
SteamCMD is in the AUR, not official repos. Install with:
```bash
yay -S steamcmd
# or
paru -S steamcmd
```

### Mods not appearing after download
1. Click the refresh button or press F5
2. Check that the mod download path is in your mod source paths
3. Verify the mod was downloaded correctly

### Permission errors
Ensure you have write access to:
- The game's Mods folder
- Your mod source directories
- `~/.config/rimworld-mod-manager/`

### Symlinks not working
Some filesystems don't support symlinks. Ensure your game installation is on a Linux filesystem (ext4, btrfs, etc.) not NTFS.

## Configuration

Configuration is stored in `~/.config/rimworld-mod-manager/config.json`:

```json
{
  "last_installation": "/path/to/RimWorld",
  "mod_source_paths": [
    "/home/user/RimWorld_Workshop_Mods",
    "/home/user/MyMods"
  ],
  "custom_game_paths": [],
  "workshop_download_path": "/home/user/RimWorld_Workshop_Mods"
}
```

## Project Structure

```
rimworld-mod-manager/
├── main.py                 # Application entry point
├── config_handler.py       # XDG-compliant configuration
├── game_detector.py        # RimWorld installation detection
├── mod_parser.py           # About.xml parsing
├── workshop_downloader.py  # SteamCMD integration
├── ui/
│   ├── __init__.py
│   ├── main_window.py      # Main application window
│   └── mod_widgets.py      # Custom mod list widgets
└── README.md
```

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

MIT License - See LICENSE file for details.

## Credits

- Built for the RimWorld Linux community
- Uses PyQt6 for the GUI
- SteamCMD for Workshop downloads
