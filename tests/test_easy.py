"""Test facilissimi - verifica base di Python."""


def test_somma():
    assert 5 + 3 == 8


def test_lista_vuota():
    lista = []
    assert len(lista) == 0
    lista.append("ciao")
    assert len(lista) == 1


def test_in_operator():
    frutta = ["mela", "banana", "arancia"]
    assert "banana" in frutta
    assert "kiwi" not in frutta


def test_tipo():
    assert isinstance(42, int)
    assert isinstance("testo", str)
    assert isinstance([1, 2], list)


def test_set_unici():
    numeri = [1, 2, 2, 3, 3, 3]
    unici = set(numeri)
    assert len(unici) == 3
