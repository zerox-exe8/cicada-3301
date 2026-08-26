"""
Hertz Discord Bot - Custom Exceptions
"""

from discord.ext import commands


class HertzException(commands.CommandError):
    """Base exception class for Hertz Bot."""
    pass


class NotAuthorizedError(HertzException):
    """Raised when user lacks high-level permission."""
    pass


class DatabaseError(HertzException):
    """Raised when database query fails."""
    pass
