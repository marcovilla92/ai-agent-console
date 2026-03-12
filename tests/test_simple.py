"""Simple sanity-check tests."""


def test_addition():
    assert 1 + 1 == 2


def test_string_concat():
    assert "hello" + " " + "world" == "hello world"


def test_list_append():
    items = [1, 2, 3]
    items.append(4)
    assert items == [1, 2, 3, 4]
    assert len(items) == 4
