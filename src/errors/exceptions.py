"""
Cicada 3301 Discord Bot - Custom Exceptions
"""

from discord.ext import commands


class CicadaException(commands.CommandError):
    """Base exception class for Cicada 3301 Bot."""
    pass


class NotAuthorizedError(CicadaException):
    """Raised when user lacks high-level permission."""
    pass


class DatabaseError(CicadaException):
    """Raised when database query fails."""
    pass
