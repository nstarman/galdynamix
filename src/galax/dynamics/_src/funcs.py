"""galax: Galactic Dynamix in Jax."""

__all__ = [
    "specific_angular_momentum",
    "lagrange_points",
    "tidal_radius",
]


from functools import partial

import jax
from jaxtyping import Float, Shaped
from plum import convert, dispatch

import coordinax as cx
import quaxed.numpy as jnp
import unxt as u

import galax.coordinates as gc
import galax.potential as gp
import galax.typing as gt
from galax.potential._src.funcs import d2potential_dr2

# ===================================================================
# Specific angular momentum


@dispatch
@partial(jax.jit, inline=True)
def specific_angular_momentum(
    x: gt.LengthBtSz3, v: gt.SpeedBtSz3, /
) -> Shaped[u.Quantity["angular momentum"], "*batch 3"]:
    """Compute the specific angular momentum.

    Arguments:
    ---------
    x: Quantity[Any, (3,), "length"]
        3d Cartesian position (x, y, z).
    v: Quantity[Any, (3,), "speed"]
        3d Cartesian velocity (v_x, v_y, v_z).

    Returns
    -------
    Quantity[Any, (3,), "angular momentum"]
        Specific angular momentum.

    Examples
    --------
    >>> import unxt as u
    >>> import galax.dynamics as gd

    >>> x = u.Quantity([8.0, 0.0, 0.0], "m")
    >>> v = u.Quantity([0.0, 8.0, 0.0], "m/s")
    >>> gd.specific_angular_momentum(x, v)
    Quantity['diffusivity'](Array([ 0.,  0., 64.], dtype=float64), unit='m2 / s')

    """
    return jnp.linalg.cross(x, v)


@dispatch
@partial(jax.jit, inline=True)
def specific_angular_momentum(
    x: cx.vecs.AbstractPos3D, v: cx.vecs.AbstractVel3D, /
) -> gt.BtQuSz3:
    """Compute the specific angular momentum.

    Examples
    --------
    >>> import unxt as u
    >>> import coordinax as cx
    >>> import galax.dynamics as gd

    >>> x = cx.CartesianPos3D.from_([8.0, 0.0, 0.0], "m")
    >>> v = cx.CartesianVel3D.from_([0.0, 8.0, 0.0], "m/s")
    >>> gd.specific_angular_momentum(x, v)
    Quantity['diffusivity'](Array([ 0.,  0., 64.], dtype=float64), unit='m2 / s')

    """
    # TODO: keep as a vector.
    #       https://github.com/GalacticDynamics/vector/issues/27
    x = convert(x.vconvert(cx.CartesianPos3D), u.Quantity)
    v = convert(v.vconvert(cx.CartesianVel3D, x), u.Quantity)
    return specific_angular_momentum(x, v)


@dispatch
@partial(jax.jit, inline=True)
def specific_angular_momentum(w: cx.Space) -> gt.BtQuSz3:
    """Compute the specific angular momentum.

    Examples
    --------
    >>> import coordinax as cx
    >>> w = cx.Space(length=cx.CartesianPos3D.from_([[[7., 0, 0], [8, 0, 0]]], "m"),
    ...              speed=cx.CartesianVel3D.from_([[[0., 5, 0], [0, 6, 0]]], "m/s"))

    >>> specific_angular_momentum(w)
    Quantity['diffusivity'](Array([[[ 0.,  0., 35.], [ 0.,  0., 48.]]], dtype=float64), unit='m2 / s')

    """  # noqa: E501
    # TODO: keep as a vector.
    #       https://github.com/GalacticDynamics/vector/issues/27
    return specific_angular_momentum(w["length"], w["speed"])


@dispatch
@partial(jax.jit, inline=True)
def specific_angular_momentum(w: gc.AbstractPhaseSpacePosition) -> gt.BtQuSz3:
    r"""Compute the specific angular momentum.

    .. math::

        \boldsymbol{{L}} = \boldsymbol{{q}} \times \boldsymbol{{p}}

    Returns
    -------
    L : Quantity[float, (*batch,3)]
        Array of angular momentum vectors in Cartesian coordinates.

    Examples
    --------
    We assume the following imports

    >>> import unxt as u
    >>> import galax.coordinates as gc
    >>> import galax.dynamics as gd

    We can compute the angular momentum of a single object

    >>> w = gc.PhaseSpacePosition(q=u.Quantity([1., 0, 0], "au"),
    ...                           p=u.Quantity([0, 2., 0], "au/yr"),
    ...                           t=u.Quantity(0, "yr"))
    >>> gd.specific_angular_momentum(w)
    Quantity[...](Array([0., 0., 2.], dtype=float64), unit='AU2 / yr')
    """
    return specific_angular_momentum(w.q, w.p)


# ===================================================================
# Orbital angular frequency


@dispatch
@partial(jax.jit, inline=True)
def _orbital_angular_frequency(
    x: gt.LengthBtSz3, v: gt.SpeedBtSz3, /
) -> Shaped[u.Quantity["frequency"], "*batch"]:
    """Compute the orbital angular frequency about the origin.

    Arguments:
    ---------
    x: Quantity[Any, (3,), "length"]
        3d Cartesian position (x, y, z).
    v: Quantity[Any, (3,), "speed"]
        3d Cartesian velocity (v_x, v_y, v_z).

    Returns
    -------
    Quantity[Any, (3,), "frequency"]
        Angular velocity.

    Examples
    --------
    >>> import unxt as u

    >>> x = u.Quantity([8.0, 0.0, 0.0], "m")
    >>> v = u.Quantity([0.0, 8.0, 0.0], "m/s")
    >>> _orbital_angular_frequency(x, v)
    Quantity['frequency'](Array(1., dtype=float64), unit='1 / s')
    """
    r = jnp.linalg.vector_norm(x, axis=-1, keepdims=True)
    omega = jnp.linalg.cross(x, v) / r**2
    return jnp.linalg.vector_norm(omega, axis=-1)


@dispatch
@partial(jax.jit, inline=True)
def _orbital_angular_frequency(
    x: cx.vecs.AbstractPos3D, v: cx.vecs.AbstractVel3D, /
) -> Shaped[u.Quantity["frequency"], "*batch"]:
    """Compute the orbital angular frequency about the origin.

    Examples
    --------
    >>> import unxt as u
    >>> import coordinax as cx

    >>> x = cx.CartesianPos3D.from_([8.0, 0.0, 0.0], "m")
    >>> v = cx.CartesianVel3D.from_([0.0, 8.0, 0.0], "m/s")
    >>> _orbital_angular_frequency(x, v)
    Quantity['frequency'](Array(1., dtype=float64), unit='1 / s')

    """
    # TODO: more directly using the vectors
    x = convert(x.vconvert(cx.CartesianPos3D), u.Quantity)
    v = convert(v.vconvert(cx.CartesianVel3D, x), u.Quantity)
    return _orbital_angular_frequency(x, v)


# ===================================================================


@partial(jax.jit, inline=True)
def tidal_radius(
    potential: gp.AbstractBasePotential,
    x: gt.LengthBtSz3,
    v: gt.SpeedBtSz3,
    /,
    prog_mass: gt.MassBBtSz0,
    t: gt.TimeBBtSz0,
) -> Float[u.Quantity["length"], "*batch"]:
    """Compute the tidal radius of a cluster in the potential.

    Parameters
    ----------
    potential : `galax.potential.AbstractBasePotential`
        The gravitational potential of the host.
    x: Quantity[float, (3,), "length"]
        3d position (x, y, z).
    v: Quantity[float, (3,), "speed"]
        3d velocity (v_x, v_y, v_z).
    prog_mass : Quantity[float, (), "mass"]
        Cluster mass.
    t: Quantity[float, (), "time"]
        Time.

    Returns
    -------
    Quantity[float, (), "length"]
        Tidal radius of the cluster.

    Examples
    --------
    >>> import jax.numpy as jnp
    >>> import galax.potential as gp

    >>> pot = gp.NFWPotential(m=1e12, r_s=20.0, units="galactic")

    >>> x = u.Quantity(jnp.asarray([8.0, 0.0, 0.0]), "kpc")
    >>> v = u.Quantity(jnp.asarray([8.0, 0.0, 0.0]), "kpc/Myr")
    >>> prog_mass = u.Quantity(1e4, "Msun")

    >>> tidal_radius(pot, x, v, prog_mass=prog_mass, t=u.Quantity(0, "Myr"))
    Quantity['length'](Array(0.06362008, dtype=float64), unit='kpc')
    """
    omega = _orbital_angular_frequency(x, v)
    d2phi_dr2 = d2potential_dr2(potential, x, t)
    return jnp.cbrt(potential.constants["G"] * prog_mass / (omega**2 - d2phi_dr2))


# ===================================================================


@partial(jax.jit, inline=True)
def lagrange_points(
    potential: gp.AbstractBasePotential,
    x: gt.LengthSz3,
    v: gt.SpeedSz3,
    prog_mass: gt.MassSz0,
    t: gt.TimeSz0,
) -> tuple[gt.LengthSz3, gt.LengthSz3]:
    """Compute the lagrange points of a cluster in a host potential.

    Parameters
    ----------
    potential : `galax.potential.AbstractBasePotential`
        The gravitational potential of the host.
    x: Quantity[float, (3,), "length"]
        Cartesian 3D position ($x$, $y$, $z$)
    v: Quantity[float, (3,), "speed"]
        Cartesian 3D velocity ($v_x$, $v_y$, $v_z$)
    prog_mass: Quantity[float, (), "mass"]
        Cluster mass.
    t: Quantity[float, (), "time"]
        Time.

    Returns
    -------
    L_1, L_2: Quantity[float, (3,), "length"]
        The lagrange points L_1 and L_2.

    Examples
    --------
    >>> import unxt as u
    >>> import galax.potential as gp

    >>> pot = gp.MilkyWayPotential()
    >>> x = u.Quantity([8.0, 0.0, 0.0], "kpc")
    >>> v = u.Quantity([0.0, 220.0, 0.0], "km/s")
    >>> prog_mass = u.Quantity(1e4, "Msun")
    >>> t = u.Quantity(0.0, "Gyr")

    >>> L1, L2 = lagrange_points(pot, x, v, prog_mass, t)
    >>> L1
    Quantity['length'](Array([7.97070926, 0.        , 0.        ], dtype=float64), unit='kpc')
    >>> L2
    Quantity['length'](Array([8.02929074, 0.        , 0.        ], dtype=float64), unit='kpc')
    """  # noqa: E501
    r_hat = cx.vecs.normalize_vector(x)
    r_t = tidal_radius(potential, x, v, prog_mass, t)
    L_1 = x - r_hat * r_t  # close
    L_2 = x + r_hat * r_t  # far
    return L_1, L_2
