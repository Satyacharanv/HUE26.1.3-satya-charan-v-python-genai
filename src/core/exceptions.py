"""Custom exception classes"""
from fastapi import HTTPException, status


class MacadException(HTTPException):
    """Base exception for maCAD system"""
    pass


class InvalidFileException(MacadException):
    """Raised when file validation fails"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class FileTooLargeException(InvalidFileException):
    """Raised when uploaded file exceeds size limit"""
    pass


class CorruptedFileException(InvalidFileException):
    """Raised when file is corrupted or invalid"""
    pass


class UnsupportedFileTypeException(InvalidFileException):
    """Raised when file type is not supported"""
    pass


class EmptyRepositoryException(InvalidFileException):
    """Raised when repository contains no recognizable code"""
    pass


class GitHubAccessException(MacadException):
    """Raised when GitHub repository cannot be accessed"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class ProjectNotFoundException(MacadException):
    """Raised when project is not found"""
    def __init__(self, project_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )


class UnauthorizedException(MacadException):
    """Raised when user is not authorized"""
    def __init__(self, detail: str = "Not authorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail
        )


class ForbiddenException(MacadException):
    """Raised when user lacks required permissions"""
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )
