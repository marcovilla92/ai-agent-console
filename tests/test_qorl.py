"""Simple qorl (quick sanity) tests."""


def test_true_is_truthy():
    assert True


def test_basic_math():
    assert 2 * 3 == 6
    assert 10 // 3 == 3


def test_dict_operations():
    d = {"a": 1, "b": 2}
    d["c"] = 3
    assert len(d) == 3
    assert d["c"] == 3
    assert "a" in d


def test_set_operations():
    s = {1, 2, 3}
    s.add(4)
    assert 4 in s
    assert len(s) == 4
    assert s & {2, 3} == {2, 3}


def test_string_operations():
    s = "hello world"
    assert s.upper() == "HELLO WORLD"
    assert s.split() == ["hello", "world"]
    assert s.replace("world", "qorl") == "hello qorl"


def test_list_comprehension():
    squares = [x * x for x in range(5)]
    assert squares == [0, 1, 4, 9, 16]
    evens = [x for x in range(10) if x % 2 == 0]
    assert evens == [0, 2, 4, 6, 8]


def test_exception_handling():
    import pytest

    with pytest.raises(ZeroDivisionError):
        _ = 1 / 0

    with pytest.raises(KeyError):
        d = {}
        _ = d["missing"]
