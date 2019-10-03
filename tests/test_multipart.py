import pytest
from blacksheep.multipart import parse_multipart
from .examples.multipart import FIELDS_THREE_VALUES, FIELDS_WITH_CARRIAGE_RETURNS, FIELDS_WITH_SMALL_PICTURE


@pytest.mark.parametrize('value', [
    FIELDS_THREE_VALUES,
    FIELDS_WITH_CARRIAGE_RETURNS,
    FIELDS_WITH_SMALL_PICTURE
])
def test_function(value):

    for part in parse_multipart(value):
        print(part)
