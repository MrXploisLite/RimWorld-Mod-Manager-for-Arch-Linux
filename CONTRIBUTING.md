# Contributing to RimModManager

First off, thanks for taking the time to contribute! 🎉

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates.

When creating a bug report, include:
- Your Linux distribution and version
- Python version (`python --version`)
- PyQt6 version (`pip show PyQt6`)
- RimWorld installation type (Steam Native, Proton, Flatpak, etc.)
- Steps to reproduce the issue
- Expected vs actual behavior
- Screenshots if applicable

### Suggesting Features

Feature requests are welcome! Please:
- Check if the feature has already been requested
- Describe the feature and its use case
- Explain why it would be useful to most users

### Pull Requests

1. Fork the repo and create your branch from `main`
2. Follow the existing code style
3. Test your changes thoroughly
4. Update documentation if needed
5. Write a clear PR description

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/RimWorld-Mod-Manager-for-Arch-Linux.git
cd RimWorld-Mod-Manager-for-Arch-Linux

# Install dependencies
sudo pacman -S python python-pyqt6 python-pyqt6-webengine

# Run the application
python main.py
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Write docstrings for classes and functions
- Keep functions focused and small

## Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Keep the first line under 72 characters
- Reference issues when applicable

## Questions?

Feel free to open an issue with the "question" label.
