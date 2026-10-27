import random

from sqlforge.seeding import set_seed


def test_same_seed_same_draws():
    set_seed(123)
    first = [random.random() for _ in range(5)]
    set_seed(123)
    second = [random.random() for _ in range(5)]
    assert first == second


def test_different_seed_different_draws():
    set_seed(1)
    first = [random.random() for _ in range(5)]
    set_seed(2)
    second = [random.random() for _ in range(5)]
    assert first != second
