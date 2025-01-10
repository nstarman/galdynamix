"""Test the :mod:`galax.integrate` module."""

from galax.dynamics import integrate
from galax.dynamics._src.integrate import funcs, integrator, interp, utils


def test_all() -> None:
    """Test the API."""
    assert set(integrate.__all__) == set(
        integrator.__all__ + funcs.__all__ + utils.__all__ + interp.__all__
    )
