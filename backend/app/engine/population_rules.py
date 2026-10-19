"""Official brief p.2: inclusive population upper bounds, then nine soldiers."""

POPULATION_UPPER_BOUNDS = (
    5_000_000, 10_000_000, 25_000_000, 50_000_000,
    75_000_000, 100_000_000, 125_000_000, 150_000_000,
)


def soldiers_from_population(population: int) -> int:
    if type(population) is not int:
        raise TypeError("Population must be an integer")
    if population <= 0:
        raise ValueError("Population must be positive")
    for soldiers, upper_bound in enumerate(POPULATION_UPPER_BOUNDS, start=1):
        if population <= upper_bound:
            return soldiers
    return 9
