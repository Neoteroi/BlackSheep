import pytest

from blacksheep.messages import Response
from blacksheep.middlewares import (
    CategorizedMiddleware,
    MiddlewareCategory,
    MiddlewareList,
)


# Test fixtures
async def middleware_a() -> Response: ...


async def middleware_b() -> Response: ...


async def middleware_c() -> Response: ...


async def middleware_d() -> Response: ...


async def middleware_e() -> Response: ...


class TestMiddlewareList:
    def test_init(self):
        """Test MiddlewareList initialization"""
        ml = MiddlewareList()
        assert len(ml) == 0
        assert not ml
        assert ml._is_sorted is True
        assert ml._configured is False

    def test_append_default_category(self):
        """Test appending middleware with default category"""
        ml = MiddlewareList()
        ml.append(middleware_a)

        assert len(ml) == 1
        assert ml[0] is middleware_a

        # Check internal structure
        categorized = list(ml.items())[0]
        assert categorized.middleware is middleware_a
        assert categorized.category == MiddlewareCategory.BUSINESS
        assert categorized.priority == 0

    def test_append_with_category_and_priority(self):
        """Test appending middleware with specific category and priority"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.AUTH, priority=5)

        categorized = list(ml.items())[0]
        assert categorized.middleware is middleware_a
        assert categorized.category == MiddlewareCategory.AUTH
        assert categorized.priority == 5

    def test_insert(self):
        """Test inserting middleware (legacy support)"""
        ml = MiddlewareList()
        ml.append(middleware_a)
        ml.insert(0, middleware_b)

        assert len(ml) == 2
        # insert uses INIT category with priority -1, so it should come first
        assert ml[0] is middleware_b
        assert ml[1] is middleware_a

    def test_extend(self):
        """Test extending with multiple middlewares"""
        ml = MiddlewareList()
        ml.extend([middleware_a, middleware_b, middleware_c])

        assert len(ml) == 3
        assert ml[0] is middleware_a
        assert ml[1] is middleware_b
        assert ml[2] is middleware_c

    def test_clear(self):
        """Test clearing all middlewares"""
        ml = MiddlewareList()
        ml.append(middleware_a)
        ml.append(middleware_b)

        assert len(ml) == 2
        ml.clear()
        assert len(ml) == 0
        assert not ml
        assert ml._is_sorted is True

    def test_category_sorting(self):
        """Test that middlewares are sorted by category"""
        ml = MiddlewareList()

        # Add middlewares in reverse category order
        ml.append(middleware_a, MiddlewareCategory.MESSAGE)  # 60
        ml.append(middleware_b, MiddlewareCategory.AUTH)  # 30
        ml.append(middleware_c, MiddlewareCategory.INIT)  # 10
        ml.append(middleware_d, MiddlewareCategory.BUSINESS)  # 50

        # Should be sorted by category value
        middlewares = ml.to_list()
        assert middlewares[0] is middleware_c  # INIT (10)
        assert middlewares[1] is middleware_b  # AUTH (30)
        assert middlewares[2] is middleware_d  # BUSINESS (50)
        assert middlewares[3] is middleware_a  # RESPONSE (60)

    def test_priority_sorting_within_category(self):
        """Test that middlewares are sorted by priority within same category"""
        ml = MiddlewareList()

        # Add middlewares in same category with different priorities
        ml.append(middleware_a, MiddlewareCategory.AUTH, priority=3)
        ml.append(middleware_b, MiddlewareCategory.AUTH, priority=1)
        ml.append(middleware_c, MiddlewareCategory.AUTH, priority=2)

        middlewares = ml.to_list()
        assert middlewares[0] is middleware_b  # priority 1
        assert middlewares[1] is middleware_c  # priority 2
        assert middlewares[2] is middleware_a  # priority 3

    def test_mixed_category_and_priority_sorting(self):
        """Test sorting with both different categories and priorities"""
        ml = MiddlewareList()

        ml.append(middleware_a, MiddlewareCategory.BUSINESS, priority=2)
        ml.append(middleware_b, MiddlewareCategory.AUTH, priority=3)
        ml.append(middleware_c, MiddlewareCategory.AUTH, priority=1)
        ml.append(middleware_d, MiddlewareCategory.INIT, priority=5)

        middlewares = ml.to_list()
        assert middlewares[0] is middleware_d  # INIT (10), priority 5
        assert middlewares[1] is middleware_c  # AUTH (30), priority 1
        assert middlewares[2] is middleware_b  # AUTH (30), priority 3
        assert middlewares[3] is middleware_a  # BUSINESS (50), priority 2

    def test_lazy_sorting(self):
        """Test that sorting only happens when needed"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.MESSAGE)

        # After append, should not be sorted
        assert ml._is_sorted is False

        # Accessing should trigger sort
        _ = ml[0]
        assert ml._is_sorted is True

        # Adding again should mark as unsorted
        ml.append(middleware_b, MiddlewareCategory.INIT)
        assert ml._is_sorted is False

    def test_configuration_lock(self):
        """Test that middlewares cannot be added after configuration"""
        ml = MiddlewareList()
        ml.append(middleware_a)

        # Mark as configured
        ml._mark_configured()

        # Should raise errors for modification attempts
        with pytest.raises(
            RuntimeError, match="Cannot add middlewares after configuration is complete"
        ):
            ml.append(middleware_b)

        with pytest.raises(
            RuntimeError, match="Cannot add middlewares after configuration is complete"
        ):
            ml.insert(0, middleware_b)

        with pytest.raises(
            RuntimeError, match="Cannot add middlewares after configuration is complete"
        ):
            ml.extend([middleware_b])

    def test_iterator_behavior(self):
        """Test iterator returns middleware functions in sorted order"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.MESSAGE)
        ml.append(middleware_b, MiddlewareCategory.INIT)

        middlewares = list(ml)
        assert middlewares[0] is middleware_b  # INIT comes first
        assert middlewares[1] is middleware_a  # RESPONSE comes second

    def test_bool_behavior(self):
        """Test boolean evaluation of MiddlewareList"""
        ml = MiddlewareList()
        assert not ml  # Empty list is False

        ml.append(middleware_a)
        assert ml  # Non-empty list is True

    def test_getitem_behavior(self):
        """Test indexing behavior"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.BUSINESS)
        ml.append(middleware_b, MiddlewareCategory.INIT)

        # Should return middlewares in sorted order
        assert ml[0] is middleware_b  # INIT comes first
        assert ml[1] is middleware_a  # BUSINESS comes second

    def test_items_method(self):
        """Test items() method returns CategorizedMiddleware objects"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.AUTH, priority=5)

        items = list(ml.items())
        assert len(items) == 1
        assert isinstance(items[0], CategorizedMiddleware)
        assert items[0].middleware is middleware_a
        assert items[0].category == MiddlewareCategory.AUTH
        assert items[0].priority == 5

    def test_to_list_method(self):
        """Test to_list() method returns sorted middleware functions"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.MESSAGE)
        ml.append(middleware_b, MiddlewareCategory.INIT)

        middlewares = ml.to_list()
        assert isinstance(middlewares, list)
        assert middlewares[0] is middleware_b  # INIT first
        assert middlewares[1] is middleware_a  # RESPONSE second

    def test_mark_configured_sorts_middlewares(self):
        """Test that _mark_configured() triggers sorting"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.MESSAGE)
        ml.append(middleware_b, MiddlewareCategory.INIT)

        assert ml._is_sorted is False
        assert ml._configured is False

        ml._mark_configured()

        assert ml._is_sorted is True
        assert ml._configured is True

    def test_insert_uses_init_category(self):
        """Test that insert() uses INIT category with priority -1"""
        ml = MiddlewareList()
        ml.append(middleware_a, MiddlewareCategory.INIT, priority=0)
        ml.insert(0, middleware_b)  # Should get INIT category, priority -1

        # middleware_b should come first due to lower priority (-1 vs 0)
        assert ml[0] is middleware_b
        assert ml[1] is middleware_a

        # Check the categorized middleware
        items = list(ml.items())
        inserted_middleware = next(
            item for item in items if item.middleware is middleware_b
        )
        assert inserted_middleware.category == MiddlewareCategory.INIT
        assert inserted_middleware.priority == -1

    def test_empty_extend(self):
        """Test extending with empty list"""
        ml = MiddlewareList()
        ml.extend([])

        assert len(ml) == 0
        assert not ml
