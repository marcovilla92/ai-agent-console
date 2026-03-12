"""Test fondamentali - tuple, slicing, f-string, comprehension, eccezioni."""

import pytest


def test_tuple_unpacking():
    nome, eta, citta = ("Marco", 30, "Roma")
    assert nome == "Marco"
    assert eta == 30
    assert citta == "Roma"


def test_list_slicing():
    numeri = [0, 1, 2, 3, 4, 5]
    assert numeri[1:4] == [1, 2, 3]
    assert numeri[:3] == [0, 1, 2]
    assert numeri[::2] == [0, 2, 4]
    assert numeri[::-1] == [5, 4, 3, 2, 1, 0]


def test_fstring_formatting():
    nome = "Luca"
    punti = 42
    msg = f"{nome} ha {punti} punti"
    assert msg == "Luca ha 42 punti"
    assert f"{3.14159:.2f}" == "3.14"


def test_list_comprehension():
    quadrati = [x * x for x in range(5)]
    assert quadrati == [0, 1, 4, 9, 16]
    pari = [x for x in range(10) if x % 2 == 0]
    assert pari == [0, 2, 4, 6, 8]


def test_eccezione_raises():
    with pytest.raises(ZeroDivisionError):
        _ = 1 / 0
    with pytest.raises(KeyError):
        _ = {}["chiave_mancante"]
