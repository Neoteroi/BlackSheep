import pytest
from pytest import raises
from blacksheep.server.normalization import (get_from_body_parameter,
                                             MultipleFromBodyBinders,
                                             FromJson)


class Pet:
    def __init__(self, name):
        self.name = name


class Cat(Pet):
    pass


class Dog(Pet):
    pass


def valid_method_one(a: FromJson(Cat)):
    print(a)


def valid_method_two(a: FromJson(Cat), b: str):
    print(a, b)


def valid_method_three(b: str, a: FromJson(Cat)):
    print(b, a)


def valid_method_four(a: FromJson(Dog)):
    print(a)


def invalid_method_one(a: FromJson(Cat), b: FromJson(Cat)):
    print(a, b)


def invalid_method_two(a: FromJson(Cat), b: FromJson(Dog)):
    print(a, b)


def invalid_method_three(a: FromJson(Cat), b: FromJson(Dog), c: FromJson(Dog)):
    print(a, b, c)


@pytest.mark.parametrize('valid_method,expected_type', [
    [valid_method_one, Cat],
    [valid_method_two, Cat],
    [valid_method_three, Cat],
    [valid_method_four, Dog]
])
def test_get_body_parameter_valid_method(valid_method, expected_type):
    from_body_param = get_from_body_parameter(valid_method)

    assert from_body_param.expected_type is expected_type


@pytest.mark.parametrize('invalid_method', [
    invalid_method_one,
    invalid_method_two,
    invalid_method_three
])
def test_get_body_parameter_invalid_method(invalid_method):

    with raises(MultipleFromBodyBinders):
        get_from_body_parameter(invalid_method)
