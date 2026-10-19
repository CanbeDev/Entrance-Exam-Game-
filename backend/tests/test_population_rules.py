import pytest

from app.engine.population_rules import soldiers_from_population


@pytest.mark.parametrize("boundary,value", [
    (5_000_000, 1), (10_000_000, 2), (25_000_000, 3), (50_000_000, 4),
    (75_000_000, 5), (100_000_000, 6), (125_000_000, 7), (150_000_000, 8),
])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_official_boundaries(boundary, value, offset):
    assert soldiers_from_population(boundary + offset) == value + (offset == 1)


@pytest.mark.parametrize("population,expected", [(1, 1), (506, 1), (1_476_625_576, 9)])
def test_extremes(population, expected):
    assert soldiers_from_population(population) == expected


@pytest.mark.parametrize("population", [0, -1, -5_000_000])
def test_nonpositive_rejected(population):
    with pytest.raises(ValueError):
        soldiers_from_population(population)


@pytest.mark.parametrize("population", [True, False, 5_000_000.0, "5000000", None])
def test_noninteger_rejected(population):
    with pytest.raises(TypeError):
        soldiers_from_population(population)
