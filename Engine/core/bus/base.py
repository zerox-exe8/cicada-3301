from abc import ABC, abstractmethod
from typing import Callable, Awaitable
from schemas.events import BaseEvent

EventHandler = Callable[[BaseEvent], Awaitable[None]]

class AbstractEventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: BaseEvent) -> None:
        """Publish an event to a specified topic."""
        pass

    @abstractmethod
    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe a handler to listen to a specified topic."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the event bus processing loop."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop and flush all pending events."""
        pass
