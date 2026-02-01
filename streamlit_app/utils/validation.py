"""Frontend validation utilities"""
import re
from typing import Tuple

# Constants
MAX_ZIP_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
WARN_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB warning threshold


def validate_zip_file(file_size: int, filename: str) -> Tuple[bool, str]:
    """
    Validate ZIP file before upload
    Returns: (is_valid, message)
    """
    if not filename:
        return False, "No file selected"
    
    if not filename.lower().endswith('.zip'):
        return False, f"Invalid file format. Expected .zip, got: {filename}"
    
    if file_size > MAX_ZIP_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return False, f"File too large: {size_mb:.1f} MB exceeds 100 MB limit"
    
    if file_size == 0:
        return False, "File is empty"
    
    return True, ""


def validate_github_url(url: str) -> Tuple[bool, str]:
    """
    Validate GitHub URL format
    Returns: (is_valid, message)
    """
    if not url:
        return False, "GitHub URL is required"
    
    # GitHub URL pattern
    pattern = r'^https?://(www\.)?github\.com/[\w\-\.]+/[\w\-\.]+(/.*)?$'
    
    if not re.match(pattern, url):
        return False, (
            "Invalid GitHub URL format. Expected format:\n"
            "https://github.com/username/repository"
        )
    
    return True, ""


def get_file_size_warning(file_size: int) -> str:
    """Get warning message for large files"""
    if file_size > WARN_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return f"⚠️ Large file ({size_mb:.1f} MB). Upload may take a moment."
    return ""
