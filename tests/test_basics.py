"""Basic Python tests - super easy."""


def test_math():
    assert 2 + 2 == 4
    assert 10 - 3 == 7
    assert 3 * 4 == 12


def test_boolean_logic():
    assert True is not False
    assert not None
    assert bool(1) is True
    assert bool(0) is False


def test_dict_operations():
    d = {"name": "Alice", "age": 30}
    assert d["name"] == "Alice"
    assert len(d) == 2
    d["city"] = "Rome"
    assert "city" in d


def test_string_methods():
    s = "hello world"
    assert s.upper() == "HELLO WORLD"
    assert s.split() == ["hello", "world"]
    assert s.replace("world", "python") == "hello python"
