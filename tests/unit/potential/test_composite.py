from collections.abc import Mapping
from dataclasses import replace

import array_api_jax_compat as xp
import astropy.units as u
import jax.numpy as jnp
import pytest
from quax import quaxify
from typing_extensions import override

from jax_quantity import Quantity

from .test_base import TestAbstractPotentialBase as AbstractPotentialBase_Test
from .test_utils import FieldUnitSystemMixin
from galax.potential import (
    AbstractPotentialBase,
    CompositePotential,
    KeplerPotential,
    MiyamotoNagaiPotential,
    NFWPotential,
)
from galax.typing import Vec3
from galax.units import UnitSystem, dimensionless, galactic, solarsystem
from galax.utils._misc import first

array_equal = quaxify(jnp.array_equal)
allclose = quaxify(jnp.allclose)


# TODO: write the base-class test
class AbstractCompositePotential_Test(AbstractPotentialBase_Test, FieldUnitSystemMixin):
    """Test the `galax.potential.AbstractCompositePotential` class."""


class TestCompositePotential(AbstractCompositePotential_Test):
    """Test the `galax.potential.CompositePotential` class."""

    @pytest.fixture(scope="class")
    def pot_cls(self) -> type[CompositePotential]:
        """Composite potential class."""
        return CompositePotential

    @pytest.fixture(scope="class")
    def pot_map(self) -> Mapping[str, AbstractPotentialBase]:
        """Composite potential."""
        return {
            "disk": MiyamotoNagaiPotential(
                m=1e10 * u.solMass, a=6.5 * u.kpc, b=4.5 * u.kpc, units=galactic
            ),
            "halo": NFWPotential(
                m=1e12 * u.solMass, r_s=5 * u.kpc, softening_length=0, units=galactic
            ),
        }

    @pytest.fixture(scope="class")
    def pot(
        self,
        pot_cls: type[CompositePotential],
        pot_map: Mapping[str, AbstractPotentialBase],
    ) -> CompositePotential:
        """Composite potential."""
        return pot_cls(**pot_map)

    @pytest.fixture(scope="class")
    def pot_map_unitless(self) -> Mapping[str, AbstractPotentialBase]:
        """Composite potential."""
        return {
            "disk": MiyamotoNagaiPotential(m=1e10, a=6.5, b=4.5, units=None),
            "halo": NFWPotential(m=1e12, r_s=5, softening_length=0, units=None),
        }

    # ==========================================================================
    # TODO: use a universal `replace` function then don't need to override
    #       these tests.

    @override
    def test_init_units_invalid(
        self,
        pot_cls: type[CompositePotential],
        pot_map: Mapping[str, AbstractPotentialBase],
    ) -> None:
        """Test invalid unit system."""
        # TODO: raise a specific error. The type depends on whether beartype is
        # turned on.
        with pytest.raises(Exception):  # noqa: B017, PT011
            pot_cls(**pot_map, units=1234567890)

    @override
    def test_init_units_from_usys(
        self,
        pot_cls: type[CompositePotential],
        pot_map: Mapping[str, AbstractPotentialBase],
    ) -> None:
        """Test unit system from UnitSystem."""
        usys = UnitSystem(u.km, u.s, u.Msun, u.radian)
        pot_map_ = {k: replace(v, units=usys) for k, v in pot_map.items()}
        assert pot_cls(**pot_map_, units=usys).units == usys

    @override
    def test_init_units_from_args(
        self,
        pot_cls: type[CompositePotential],
        pot_map_unitless: Mapping[str, AbstractPotentialBase],
    ) -> None:
        """Test unit system from None."""
        pot = pot_cls(**pot_map_unitless, units=None)
        assert pot.units == dimensionless

    @override
    def test_init_units_from_tuple(
        self,
        pot_cls: type[CompositePotential],
        pot_map: Mapping[str, AbstractPotentialBase],
    ) -> None:
        """Test unit system from tuple."""
        units = (u.km, u.s, u.Msun, u.radian)
        pot_map = {k: replace(v, units=units) for k, v in pot_map.items()}
        assert pot_cls(**pot_map, units=units).units == UnitSystem(*units)

    @override
    def test_init_units_from_name(
        self,
        pot_cls: type[CompositePotential],
        pot_map: Mapping[str, AbstractPotentialBase],
        pot_map_unitless: Mapping[str, AbstractPotentialBase],
    ) -> None:
        """Test unit system from named string."""
        units = "dimensionless"
        potmap = {k: replace(v, units=units) for k, v in pot_map_unitless.items()}
        pot = pot_cls(**potmap, units=units)
        assert pot.units == dimensionless

        units = "solarsystem"
        potmap = {k: replace(v, units=units) for k, v in pot_map.items()}
        pot = pot_cls(**potmap, units=units)
        assert pot.units == solarsystem

        units = "galactic"
        potmap = {k: replace(v, units=units) for k, v in pot_map.items()}
        pot = pot_cls(**potmap, units=units)
        assert pot.units == galactic

        msg = "cannot convert invalid_value to a UnitSystem"
        with pytest.raises(NotImplementedError, match=msg):
            pot_cls(**pot_map_unitless, units="invalid_value")

    # ==========================================================================

    # --------------------------
    # `__or__`

    def test_or_incorrect(self, pot: CompositePotential) -> None:
        """Test the `__or__` method with incorrect inputs."""
        with pytest.raises(TypeError, match="unsupported operand type"):
            _ = pot | 1

    def test_or_pot(self, pot: CompositePotential) -> None:
        """Test the `__or__` method with a single potential."""
        single_pot = KeplerPotential(m=1e12 * u.solMass, units=galactic)
        newpot = pot | single_pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = tuple(newpot.items())[-1]
        assert isinstance(newkey, str)
        assert newvalue is single_pot

    def test_or_compot(self, pot: CompositePotential) -> None:
        """Test the `__or__` method with a composite potential."""
        comp_pot = CompositePotential(
            kep1=KeplerPotential(m=1e12 * u.solMass, units=galactic),
            kep2=KeplerPotential(m=1e12 * u.solMass, units=galactic),
        )
        newpot = pot | comp_pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = tuple(newpot.items())[-2]
        assert newkey == "kep1"
        assert newvalue is newpot["kep1"]

        newkey, newvalue = tuple(newpot.items())[-1]
        assert newkey == "kep2"
        assert newvalue is newpot["kep2"]

    # --------------------------
    # `__ror__`

    def test_ror_incorrect(self, pot: CompositePotential) -> None:
        """Test the `__or__` method with incorrect inputs."""
        with pytest.raises(TypeError, match="unsupported operand type"):
            _ = 1 | pot

    def test_ror_pot(self, pot: CompositePotential) -> None:
        """Test the `__ror__` method with a single potential."""
        single_pot = KeplerPotential(m=1e12 * u.solMass, units=galactic)
        newpot = single_pot | pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = first(newpot.items())
        assert isinstance(newkey, str)
        assert newvalue is single_pot

    def test_ror_compot(self, pot: CompositePotential) -> None:
        """Test the `__ror__` method with a composite potential."""
        comp_pot = CompositePotential(
            kep1=KeplerPotential(m=1e12 * u.solMass, units=galactic),
            kep2=KeplerPotential(m=1e12 * u.solMass, units=galactic),
        )
        newpot = comp_pot | pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = first(newpot.items())
        assert newkey == "kep1"
        assert newvalue is newpot["kep1"]

        newkey, newvalue = tuple(newpot.items())[1]
        assert newkey == "kep2"
        assert newvalue is newpot["kep2"]

    # --------------------------
    # `__add__`

    def test_add_incorrect(self, pot: CompositePotential) -> None:
        """Test the `__add__` method with incorrect inputs."""
        # TODO: specific error
        with pytest.raises(Exception):  # noqa: B017, PT011
            _ = pot + 1

    def test_add_pot(self, pot: CompositePotential) -> None:
        """Test the `__add__` method with a single potential."""
        single_pot = KeplerPotential(m=1e12 * u.solMass, units=galactic)
        newpot = pot + single_pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = tuple(newpot.items())[-1]
        assert isinstance(newkey, str)
        assert newvalue is single_pot

    def test_add_compot(self, pot: CompositePotential) -> None:
        """Test the `__add__` method with a composite potential."""
        comp_pot = CompositePotential(
            kep1=KeplerPotential(m=1e12 * u.solMass, units=galactic),
            kep2=KeplerPotential(m=1e12 * u.solMass, units=galactic),
        )
        newpot = pot + comp_pot

        assert isinstance(newpot, CompositePotential)

        newkey, newvalue = tuple(newpot.items())[-2]
        assert newkey == "kep1"
        assert newvalue is newpot["kep1"]

        newkey, newvalue = tuple(newpot.items())[-1]
        assert newkey == "kep2"
        assert newvalue is newpot["kep2"]

    # ==========================================================================

    def test_potential_energy(self, pot: CompositePotential, x: Vec3) -> None:
        assert jnp.isclose(pot.potential_energy(x, t=0).value, xp.asarray(-0.6753781))

    def test_gradient(self, pot: CompositePotential, x: Vec3) -> None:
        expected = Quantity(
            [0.01124388, 0.02248775, 0.03382281], pot.units["acceleration"]
        )
        assert allclose(pot.gradient(x, t=0).value, expected.value)  # TODO: not .value

    def test_density(self, pot: CompositePotential, x: Vec3) -> None:
        assert jnp.isclose(pot.density(x, t=0).value, 2.7958598e08)

    def test_hessian(self, pot: CompositePotential, x: Vec3) -> None:
        assert jnp.allclose(
            pot.hessian(x, t=0),
            xp.asarray(
                [
                    [0.00996317, -0.0025614, -0.00384397],
                    [-0.0025614, 0.00612107, -0.00768793],
                    [-0.00384397, -0.00768793, -0.00027929],
                ]
            ),
        )

    # ---------------------------------
    # Convenience methods

    def test_tidal_tensor(self, pot: AbstractPotentialBase, x: Vec3) -> None:
        """Test the `AbstractPotentialBase.tidal_tensor` method."""
        expect = [
            [0.00469486, -0.0025614, -0.00384397],
            [-0.0025614, 0.00085275, -0.00768793],
            [-0.00384397, -0.00768793, -0.00554761],
        ]
        assert allclose(pot.tidal_tensor(x, t=0), xp.asarray(expect))
