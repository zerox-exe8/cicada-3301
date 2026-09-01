"""
Kyro Discord Bot - Custom Exceptions
"""

from discord.ext import commands


class KyroException(commands.CommandError):
    """Base exception class for Kyro Bot."""
    pass


class NotAuthorizedError(KyroException):
    """Raised when user lacks high-level permission."""
    pass


class DatabaseError(KyroException):
    """Raised when database query fails."""
    pass
