"""
Cicada 3301 Discord Bot - Abstract Database Interface
Defines standard CRUD contracts for database backends (SQLite, PostgreSQL, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDatabase(ABC):
    """Abstract base class for all database drivers."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection pool."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close database connection pool."""
        pass

    @abstractmethod
    async def execute(self, query: str, *args: Any) -> None:
        """Execute an insert/update/delete query."""
        pass

    @abstractmethod
    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch a single record as a dictionary."""
        pass

    @abstractmethod
    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch all matching records as a list of dictionaries."""
        pass

    @abstractmethod
    async def initialize_tables(self) -> None:
        """Create necessary default tables on bot boot."""
        pass
