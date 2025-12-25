"""
Logging configuration for RimModManager.
Provides centralized logging with file and console output.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(config_dir: Path = None, debug: bool = False) -> logging.Logger:
    """
    Set up application logging.
    
    Args:
        config_dir: Directory for log files (optional)
        debug: Enable debug level logging
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("rimmodmanager")
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    
    # Format
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if config_dir provided)
    if config_dir:
        log_dir = config_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Rotate logs - keep last 5
        log_file = log_dir / f"rimmodmanager_{datetime.now().strftime('%Y%m%d')}.log"
        
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            # Clean old logs
            _cleanup_old_logs(log_dir, keep=5)
        except (IOError, PermissionError) as e:
            logger.warning(f"Could not create log file: {e}")
    
    return logger


def _cleanup_old_logs(log_dir: Path, keep: int = 5):
    """Remove old log files, keeping the most recent ones."""
    try:
        log_files = sorted(log_dir.glob("rimmodmanager_*.log"), reverse=True)
        for old_log in log_files[keep:]:
            try:
                old_log.unlink()
            except (IOError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (will be prefixed with 'rimmodmanager.')
        
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"rimmodmanager.{name}")
    return logging.getLogger("rimmodmanager")
