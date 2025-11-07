"""
This module contains server-specific classes for middlewares.
"""

from enum import Enum
from typing import Awaitable, Callable, Iterable, overload

from blacksheep.messages import Response


class MiddlewareCategory(Enum):
    INIT = 10  # CORS, security headers, configuration that must happen early
    SESSION = 20  # Session handling
    AUTH = 30  # Authentication
    AUTHZ = 40  # Authorization
    BUSINESS = 50  # User business logic middlewares
    RESPONSE = 60  # Response modification (default headers, etc.)


class CategorizedMiddleware:
    def __init__(
        self,
        middleware,
        category: MiddlewareCategory = MiddlewareCategory.BUSINESS,
        priority: int = 0,
    ):
        self.middleware = middleware
        self.category = category
        self.priority = priority


class MiddlewareList:
    """
    A list-like container for middlewares that supports categorized and
    prioritized insertion.
    """

    def __init__(self):
        self._middlewares: list[CategorizedMiddleware] = []
        self._is_sorted = True
        self._configured = False

    @overload
    def append(self, middleware: Callable[..., Awaitable[Response]]) -> None: ...

    @overload
    def append(
        self,
        middleware: Callable[..., Awaitable[Response]],
        category: MiddlewareCategory,
        priority: int = 0,
    ) -> None: ...

    def append(
        self,
        middleware: Callable[..., Awaitable[Response]],
        category: MiddlewareCategory = MiddlewareCategory.BUSINESS,
        priority: int = 0,
    ) -> None:
        """
        Add a middleware to the application.

        Args:
            middleware: The middleware function
            category: Where in the pipeline to place this middleware (default: BUSINESS)
            priority: Order within the category (lower = earlier, default: 0)
        """
        if self._configured:
            raise RuntimeError("Cannot add middlewares after configuration is complete")

        self._middlewares.append(CategorizedMiddleware(middleware, category, priority))
        self._is_sorted = False

    def insert(
        self, index: int, middleware: Callable[..., Awaitable[Response]]
    ) -> None:
        """Insert middleware at specific index (legacy support)"""
        if self._configured:
            raise RuntimeError("Cannot add middlewares after configuration is complete")

        # Convert to categorized middleware for consistency
        # This method defaults to MiddlewareCategory.INIT for backward compatibility,
        # as in the past insert was the only way to insert middlewares early in the
        # chain.
        self._middlewares.insert(
            index, CategorizedMiddleware(middleware, MiddlewareCategory.INIT, -1)
        )
        self._is_sorted = False

    def extend(self, middlewares) -> None:
        """Extend with multiple middlewares"""
        for middleware in middlewares:
            self.append(middleware)

    def clear(self) -> None:
        """Clear all middlewares"""
        self._middlewares.clear()
        self._is_sorted = True

    def _ensure_sorted(self) -> None:
        """Sort middlewares by category and priority if needed"""
        if not self._is_sorted:
            self._middlewares.sort(key=lambda m: (m.category.value, m.priority))
            self._is_sorted = True

    def _mark_configured(self) -> None:
        """Mark as configured to prevent further modifications"""
        self._configured = True
        self._ensure_sorted()

    def items(self) -> Iterable[CategorizedMiddleware]:
        yield from self._middlewares

    def __iter__(self):
        self._ensure_sorted()
        return iter(m.middleware for m in self._middlewares)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __bool__(self) -> bool:
        return len(self._middlewares) > 0

    def __getitem__(self, index):
        self._ensure_sorted()
        return self._middlewares[index].middleware

    def to_list(self) -> list[Callable[..., Awaitable[Response]]]:
        """Get the sorted list of middleware functions"""
        self._ensure_sorted()
        return [m.middleware for m in self._middlewares]
