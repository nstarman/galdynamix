"""Tests for the `galax.potential.LM10Potential` class."""

from collections.abc import Mapping
from typing_extensions import override

import pytest
from plum import convert

import quaxed.numpy as jnp
import unxt as u
from unxt.unitsystems import galactic

import galax.potential as gp
import galax.typing as gt
from ...test_composite import AbstractCompositePotential_Test
from galax._interop.optional_deps import OptDeps


class TestLM10Potential(AbstractCompositePotential_Test):
    """Test the `galax.potential.LM10Potential` class."""

    @pytest.fixture(scope="class")
    def pot_cls(self) -> type[gp.LM10Potential]:
        return gp.LM10Potential

    @pytest.fixture(scope="class")
    def pot_map(
        self, pot_cls: type[gp.LM10Potential]
    ) -> dict[str, dict[str, u.Quantity]]:
        """Composite potential."""
        return {
            "disk": pot_cls._default_disk,
            "bulge": pot_cls._default_bulge,
            "halo": pot_cls._default_halo,
        }

    # ==========================================================================

    @override
    def test_init_units_from_args(
        self,
        pot_cls: type[gp.AbstractCompositePotential],
        pot_map: Mapping[str, gp.AbstractBasePotential],
    ) -> None:
        """Test unit system from None."""
        pot = pot_cls(**pot_map, units=None)
        assert pot.units == galactic

    # ==========================================================================

    def test_potential(self, pot: gp.LM10Potential, x: gt.QuSz3) -> None:
        expect = u.Quantity(-0.00242568, unit="kpc2 / Myr2")
        assert jnp.isclose(
            pot.potential(x, t=0), expect, atol=u.Quantity(1e-8, expect.unit)
        )

    def test_gradient(self, pot: gp.LM10Potential, x: gt.QuSz3) -> None:
        expect = u.Quantity([0.00278038, 0.00533753, 0.0111171], "kpc / Myr2")
        got = convert(pot.gradient(x, t=0), u.Quantity)
        assert jnp.allclose(got, expect, atol=u.Quantity(1e-8, expect.unit))

    def test_density(self, pot: gp.LM10Potential, x: gt.QuSz3) -> None:
        expect = u.Quantity(19085831.78310305, "solMass / kpc3")
        assert jnp.isclose(
            pot.density(x, t=0), expect, atol=u.Quantity(1e-8, expect.unit)
        )

    def test_hessian(self, pot: gp.LM10Potential, x: gt.QuSz3) -> None:
        expect = u.Quantity(
            [
                [0.00234114, -0.00081663, -0.0013405],
                [-0.00081663, 0.00100949, -0.00267623],
                [-0.0013405, -0.00267623, -0.00227171],
            ],
            "1/Myr2",
        )
        assert jnp.allclose(
            pot.hessian(x, t=0), expect, atol=u.Quantity(1e-8, expect.unit)
        )

    # ---------------------------------
    # Convenience methods

    def test_tidal_tensor(self, pot: gp.AbstractBasePotential, x: gt.QuSz3) -> None:
        """Test the `AbstractBasePotential.tidal_tensor` method."""
        expect = u.Quantity(
            [
                [0.0019815, -0.00081663, -0.0013405],
                [-0.00081663, 0.00064985, -0.00267623],
                [-0.0013405, -0.00267623, -0.00263135],
            ],
            "1/Myr2",
        )
        assert jnp.allclose(
            pot.tidal_tensor(x, t=0), expect, atol=u.Quantity(1e-8, expect.unit)
        )

    # ==========================================================================
    # Interoperability

    @pytest.mark.skipif(not OptDeps.GALA.installed, reason="requires gala")
    @pytest.mark.parametrize(
        ("method0", "method1", "atol"),
        [
            ("potential", "energy", 1e-8),
            ("gradient", "gradient", 1e-8),
            # ("density", "density", 1e-8),  # TODO: get gala and galax to agree
            # ("hessian", "hessian", 1e-8),  # TODO: get gala and galax to agree
        ],
    )
    def test_method_gala(
        self,
        pot: gp.AbstractBasePotential,
        method0: str,
        method1: str,
        x: gt.QuSz3,
        atol: float,
    ) -> None:
        """Test the equivalence of methods between gala and galax.

        This test only runs if the potential can be mapped to gala.
        """
        super().test_method_gala(pot, method0, method1, x, atol)
