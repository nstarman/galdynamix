__all__ = ["Integrator"]

import functools
from collections.abc import Callable, Mapping
from dataclasses import KW_ONLY
from functools import partial
from typing import Any, Literal, ParamSpec, TypeAlias, TypeVar, final, no_type_check

import diffrax
import equinox as eqx
import jax
from diffrax import DenseInterpolation, Solution
from plum import dispatch

import quaxed.numpy as xp
from unxt import AbstractUnitSystem, Quantity, unitsystem, ustrip
from xmmutablemap import ImmutableMap

import galax.coordinates as gc
import galax.typing as gt
from .type_hints import VectorField

P = ParamSpec("P")
R = TypeVar("R")
Interp = TypeVar("Interp")
Time: TypeAlias = (
    gt.TimeScalar | gt.TimeBatchableScalar | gt.RealScalar | gt.BatchableRealScalar
)
Times: TypeAlias = gt.BatchQVecTime | gt.BatchVecTime | gt.QVecTime | gt.VecTime
_call_jit_kw = {
    "static_argnums": (0, 1),
    "static_argnames": ("units", "interpolated"),
    "inline": True,
}


# ============================================================================
# Integration


@no_type_check
def vectorize_diffeq(pyfunc: Callable[P, R]) -> "Callable[P, R]":
    """Vectorize a function.

    Parameters
    ----------
    pyfunc : Callable[P, R]
        The function to vectorize.
    signature : str | None, optional
        The signature of the vectorized function. Default is `None`.

    Returns
    -------
    Callable[P, R]

    """
    input_core_dims = [("6",), (), (), ("T",)]

    @no_type_check
    @functools.wraps(pyfunc)
    def wrapped(*args: Any, **_: Any) -> R:  # P.args, P.kwargs
        vectorized_func = pyfunc

        squeezed_args = []
        rev_filled_shapes = []
        for arg, core_dims in zip(args, input_core_dims, strict=True):
            noncore_shape = xp.shape(arg)[: xp.ndim(arg) - len(core_dims)]

            pad_ndim = 1 - len(noncore_shape)
            filled_shape = pad_ndim * (1,) + noncore_shape
            rev_filled_shapes.append(filled_shape[::-1])

            squeeze_indices = tuple(
                i for i, size in enumerate(noncore_shape) if size == 1
            )
            squeezed_arg = xp.squeeze(arg, axis=squeeze_indices)
            squeezed_args.append(squeezed_arg)

        for _, axis_sizes in enumerate(zip(*rev_filled_shapes, strict=True)):
            in_axes = tuple(None if size == 1 else 0 for size in axis_sizes)
            if not all(axis is None for axis in in_axes):
                vectorized_func = jax.vmap(vectorized_func, in_axes)

        return vectorized_func(*squeezed_args)

    return wrapped


@final
class Integrator(eqx.Module, strict=True):  # type: ignore[call-arg,misc]
    """Integrator using :func:`diffrax.diffeqsolve`.

    This integrator uses the :func:`diffrax.diffeqsolve` function to integrate
    the equations of motion. :func:`diffrax.diffeqsolve` supports a wide range
    of solvers and options. See the documentation of :func:`diffrax.diffeqsolve`
    for more information.

    Parameters
    ----------
    Solver : type[diffrax.AbstractSolver], optional
        The solver to use. Default is :class:`diffrax.Dopri8`.
    stepsize_controller : diffrax.AbstractStepSizeController, optional
        The stepsize controller to use. Default is a PID controller with
        relative and absolute tolerances of 1e-7.
    diffeq_kw : Mapping[str, Any], optional
        Keyword arguments to pass to :func:`diffrax.diffeqsolve`. Default is
        ``{"max_steps": None, "event": None}``. The ``"max_steps"`` key is
        removed if ``interpolated=True`` in the :meth`Integrator.__call__`
        method.
    solver_kw : Mapping[str, Any], optional
        Keyword arguments to pass to the solver. Default is ``{"scan_kind":
        "bounded"}``.

    Examples
    --------
    First some imports:

    >>> import quaxed.numpy as jnp
    >>> from unxt import Quantity
    >>> from unxt.unitsystems import galactic
    >>> import galax.coordinates as gc
    >>> import galax.dynamics as gd
    >>> import galax.potential as gp

    Then we define initial conditions:

    >>> w0 = gc.PhaseSpacePosition(q=Quantity([10., 0., 0.], "kpc"),
    ...                            p=Quantity([0., 200., 0.], "km/s"))

    (Note that the ``t`` attribute is not used.)

    Now we can integrate the phase-space position for 1 Gyr, getting the final
    position.  The integrator accepts any function for the equations of motion.
    Here we will reproduce what happens with orbit integrations.

    >>> pot = gp.HernquistPotential(m_tot=Quantity(1e12, "Msun"),
    ...                             r_s=Quantity(5, "kpc"), units="galactic")

    >>> integrator = gd.integrate.Integrator()
    >>> t0, t1 = Quantity(0, "Gyr"), Quantity(1, "Gyr")
    >>> w = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
    >>> w
    PhaseSpacePosition(
        q=CartesianPosition3D( ... ),
        p=CartesianVelocity3D( ... ),
        t=Quantity[...](value=f64[], unit=Unit("Myr"))
    )
    >>> w.shape
    ()

    Instead of just returning the final position, we can get the state of the
    system at any times ``saveat``:

    >>> ts = Quantity(jnp.linspace(0, 1, 10), "Gyr")  # 10 steps
    >>> ws = integrator(pot._dynamics_deriv, w0, t0, t1,
    ...                 saveat=ts, units=galactic)
    >>> ws
    PhaseSpacePosition(
        q=CartesianPosition3D( ... ),
        p=CartesianVelocity3D( ... ),
        t=Quantity[...](value=f64[10], unit=Unit("Myr"))
    )
    >>> ws.shape
    (10,)

    In all these examples the integrator was used to integrate a single
    position. The integrator can also be used to integrate a batch of initial
    conditions at once, returning a batch of final conditions (or a batch of
    conditions at the requested times ``saveat``):

    >>> w0 = gc.PhaseSpacePosition(q=Quantity([[10., 0, 0], [11., 0, 0]], "kpc"),
    ...                            p=Quantity([[0, 200, 0], [0, 210, 0]], "km/s"))
    >>> ws = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
    >>> ws.shape
    (2,)

    A cool feature of the integrator is that it can return an interpolated
    solution.

    >>> w = integrator(pot._dynamics_deriv, w0, t0, t1, saveat=ts, units=galactic,
    ...                interpolated=True)
    >>> type(w)
    <class 'galax.coordinates...InterpolatedPhaseSpacePosition'>

    The interpolated solution can be evaluated at any time in the domain to get
    the phase-space position at that time:

    >>> t = Quantity(jnp.e, "Gyr")
    >>> w(t)
    PhaseSpacePosition(
        q=CartesianPosition3D( ... ),
        p=CartesianVelocity3D( ... ),
        t=Quantity[PhysicalType('time')](value=f64[1], unit=Unit("Gyr"))
    )

    The interpolant is vectorized:

    >>> t = Quantity(jnp.linspace(0, 1, 100), "Gyr")
    >>> w(t)
    PhaseSpacePosition(
        q=CartesianPosition3D( ... ),
        p=CartesianVelocity3D( ... ),
        t=Quantity[PhysicalType('time')](value=f64[1,100], unit=Unit("Gyr"))
    )

    And it works on batches:

    >>> w0 = gc.PhaseSpacePosition(q=Quantity([[10., 0, 0], [11., 0, 0]], "kpc"),
    ...                            p=Quantity([[0, 200, 0], [0, 210, 0]], "km/s"))
    >>> ws = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic,
    ...                 interpolated=True)
    >>> ws.shape
    (2,)
    >>> w(t)
    PhaseSpacePosition(
        q=CartesianPosition3D( ... ),
        p=CartesianVelocity3D( ... ),
        t=Quantity[PhysicalType('time')](value=f64[1,100], unit=Unit("Gyr"))
    )
    """

    _: KW_ONLY
    Solver: type[diffrax.AbstractSolver] = eqx.field(
        default=diffrax.Dopri8, static=True
    )
    stepsize_controller: diffrax.AbstractStepSizeController = eqx.field(
        default=diffrax.PIDController(rtol=1e-7, atol=1e-7), static=True
    )
    diffeq_kw: Mapping[str, Any] = eqx.field(
        default=(("max_steps", None), ("event", None)),
        static=True,
        converter=ImmutableMap,
    )
    solver_kw: Mapping[str, Any] = eqx.field(
        default=(("scan_kind", "bounded"),), static=True, converter=ImmutableMap
    )

    # =====================================================
    # Call

    def _process_interp(
        self, sol: Solution, w0: gt.BatchVec6, units: AbstractUnitSystem
    ) -> gc.PhaseSpacePositionInterpolant:
        # Determine if an extra dimension was added to the output
        added_ndim = int(w0.shape[:-1] in ((), (1,)))
        # If one was, then the interpolant must be reshaped since the input
        # was squeezed beforehand and the dimension must be added back.
        interp = sol.interpolation
        if added_ndim == 1:
            arr, narr = eqx.partition(interp, eqx.is_array)
            arr = jax.tree.map(lambda x: x[None], arr)
            interp = eqx.combine(arr, narr)

        return Interpolant(interp, units=units, added_ndim=added_ndim)

    # -----------------------------------------------------

    # TODO: shape hint of the return type
    @dispatch
    @partial(jax.jit, **_call_jit_kw)
    def __call__(
        self: "Integrator",
        F: VectorField,
        w0: gt.BatchVec6,
        t0: Time,
        t1: Time,
        /,
        saveat: Times | None = None,
        *,
        units: AbstractUnitSystem,
        interpolated: Literal[False, True] = False,
    ) -> gc.PhaseSpacePosition | gc.InterpolatedPhaseSpacePosition:
        """Run the integrator.

        Parameters
        ----------
        F : VectorField
            The function to integrate.
        w0 : Array[float, (6,)]
            Initial conditions ``[q, p]``.
            This is assumed to be in ``units``.
        t0, t1 : Quantity["time"]
            Initial and final times.

        saveat : (Quantity | Array)[float, (T,)] | None, optional
            Times to return the computation.  If `None`, the computation is
            returned only at the final time.

        units : `unxt.AbstractUnitSystem`
            The unit system to use.
        interpolated : bool
            Whether to return an interpolated solution.

        Returns
        -------
        `galax.coordinates.PhaseSpacePosition`[float, (time, 7)]
            The solution of the integrator [q, p, t], where q, p are the
            generalized 3-coordinates.

        Examples
        --------
        For this example, we will use the
        :class:`~galax.integrate.Integrator`

        First some imports:

        >>> import quaxed.numpy as jnp
        >>> from unxt import Quantity
        >>> from unxt.unitsystems import galactic
        >>> import galax.coordinates as gc
        >>> import galax.dynamics as gd
        >>> import galax.potential as gp

        Then we define initial conditions:

        >>> w0 = gc.PhaseSpacePosition(q=Quantity([10., 0., 0.], "kpc"),
        ...                            p=Quantity([0., 200., 0.], "km/s")
        ...                            ).w(units="galactic")
        >>> w0.shape
        (6,)

        (Note that the ``t`` attribute is not used.)

        Now we can integrate the phase-space position for 1 Gyr, getting the
        final position.  The integrator accepts any function for the equations
        of motion.  Here we will reproduce what happens with orbit integrations.

        >>> pot = gp.HernquistPotential(m_tot=Quantity(1e12, "Msun"),
        ...                             r_s=Quantity(5, "kpc"), units="galactic")

        >>> integrator = gd.integrate.Integrator()
        >>> t0, t1 = Quantity(0, "Gyr"), Quantity(1, "Gyr")
        >>> w = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
        >>> w
        PhaseSpacePosition(
            q=CartesianPosition3D( ... ),
            p=CartesianVelocity3D( ... ),
            t=Quantity[...](value=f64[], unit=Unit("Myr"))
        )
        >>> w.shape
        ()

        We can also request the orbit at specific times:

        >>> ts = Quantity(jnp.linspace(0, 1, 10), "Myr")  # 10 steps
        >>> ws = integrator(pot._dynamics_deriv, w0, t0, t1,
        ...                 saveat=ts, units=galactic)
        >>> ws
        PhaseSpacePosition(
            q=CartesianPosition3D( ... ),
            p=CartesianVelocity3D( ... ),
            t=Quantity[...](value=f64[10], unit=Unit("Myr"))
        )
        >>> ws.shape
        (10,)

        The integrator can also be used to integrate a batch of initial
        conditions at once, returning a batch of final conditions (or a batch
        of conditions at the requested times):

        >>> w0 = gc.PhaseSpacePosition(q=Quantity([[10., 0, 0], [10., 0, 0]], "kpc"),
        ...                            p=Quantity([[0, 200, 0], [0, 200, 0]], "km/s"))
        >>> ws = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
        >>> ws.shape
        (2,)

        """
        # ---------------------------------------
        # Parse inputs

        time = units["time"]
        t0_: gt.VecTime = Quantity.constructor(t0, time)
        t1_: gt.VecTime = Quantity.constructor(t1, time)
        # Either save at `saveat` or at the final time. The final time is
        # a scalar and the saveat is a vector, so a dimension is added.
        ts = Quantity.constructor(xp.asarray([t1_]) if saveat is None else saveat, time)

        diffeq_kw = dict(self.diffeq_kw)
        if interpolated and diffeq_kw.get("max_steps") is None:
            diffeq_kw.pop("max_steps")

        # ---------------------------------------
        # Perform the integration

        terms = diffrax.ODETerm(F)
        solver = self.Solver(**self.solver_kw)

        @vectorize_diffeq
        def solve_diffeq(
            y0: gt.Vec6, t0: gt.FloatScalar, t1: gt.FloatScalar, ts: gt.VecTime
        ) -> diffrax.Solution:
            return diffrax.diffeqsolve(
                terms=terms,
                solver=solver,
                t0=t0,
                t1=t1,
                y0=y0,
                dt0=None,
                args=(),
                saveat=diffrax.SaveAt(t0=False, t1=False, ts=ts, dense=interpolated),
                stepsize_controller=self.stepsize_controller,
                **diffeq_kw,
            )

        # Perform the integration (doesn't handle units)
        solution = solve_diffeq(w0, t0_.value, t1_.value, xp.atleast_2d(ts.value))

        # Parse the solution (t, [q, p])
        w = xp.concat((solution.ts[..., None], solution.ys), axis=-1)
        w = w[None] if w0.shape[0] == 1 else w  # spatial dimensions
        w = w[..., -1, :] if saveat is None else w  # time dimensions

        # ---------------------------------------
        # Return

        if interpolated:
            out_cls = gc.InterpolatedPhaseSpacePosition
            out_kw = {"interpolant": self._process_interp(solution, w0, units)}
        else:
            out_cls = gc.PhaseSpacePosition
            out_kw = {}

        return out_cls(  # shape = (*batch, T)
            t=Quantity(w[..., 0], time),
            q=Quantity(w[..., 1:4], units["length"]),
            p=Quantity(w[..., 4:7], units["speed"]),
            **out_kw,
        )

    @dispatch
    def __call__(
        self: "Integrator",
        F: VectorField,
        w0: gc.AbstractPhaseSpacePosition,
        t0: Time,
        t1: Time,
        /,
        saveat: Times | None = None,
        *,
        units: AbstractUnitSystem,
        interpolated: Literal[False, True] = False,
    ) -> gc.PhaseSpacePosition | gc.InterpolatedPhaseSpacePosition:
        """Run the integrator.

        Examples
        --------
        >>> import quaxed.numpy as xp
        >>> from unxt import Quantity
        >>> from unxt.unitsystems import galactic
        >>> import galax.coordinates as gc
        >>> import galax.dynamics as gd
        >>> import galax.potential as gp

        We define initial conditions and a potential:

        >>> w0 = gc.PhaseSpacePosition(q=Quantity([10., 0., 0.], "kpc"),
        ...                            p=Quantity([0., 200., 0.], "km/s"))

        >>> pot = gp.HernquistPotential(m_tot=Quantity(1e12, "Msun"),
        ...                             r_s=Quantity(5, "kpc"), units="galactic")

        We can integrate the phase-space position:

        >>> integrator = gd.integrate.Integrator()
        >>> t0, t1 = Quantity(0, "Gyr"), Quantity(1, "Gyr")
        >>> w = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
        >>> w
        PhaseSpacePosition(
            q=CartesianPosition3D( ... ),
            p=CartesianVelocity3D( ... ),
            t=Quantity[...](value=f64[], unit=Unit("Myr"))
        )

        """
        return self(
            F, w0.w(units=units), t0, t1, saveat, units=units, interpolated=interpolated
        )

    @dispatch
    def __call__(
        self: "Integrator",
        F: VectorField,
        w0: gc.AbstractCompositePhaseSpacePosition,
        t0: Time,
        t1: Time,
        /,
        saveat: Times | None = None,
        *,
        units: AbstractUnitSystem,
        interpolated: Literal[False, True] = False,
    ) -> gc.CompositePhaseSpacePosition:
        """Run the integrator on a composite phase-space position.

        Examples
        --------
        >>> import quaxed.numpy as xp
        >>> from unxt import Quantity
        >>> from unxt.unitsystems import galactic
        >>> import galax.coordinates as gc
        >>> import galax.dynamics as gd
        >>> import galax.potential as gp

        We define initial conditions and a potential:

        >>> w01 = gc.PhaseSpacePosition(q=Quantity([10., 0., 0.], "kpc"),
        ...                             p=Quantity([0., 200., 0.], "km/s"))
        >>> w02 = gc.PhaseSpacePosition(q=Quantity([0., 10., 0.], "kpc"),
        ...                             p=Quantity([-200., 0., 0.], "km/s"))
        >>> w0 = gc.CompositePhaseSpacePosition(w01=w01, w02=w02)

        >>> pot = gp.HernquistPotential(m_tot=Quantity(1e12, "Msun"),
        ...                             r_s=Quantity(5, "kpc"), units="galactic")

        We can integrate the composite phase-space position:

        >>> integrator = gd.integrate.Integrator()
        >>> t0, t1 = Quantity(0, "Gyr"), Quantity(1, "Gyr")
        >>> w = integrator(pot._dynamics_deriv, w0, t0, t1, units=galactic)
        >>> w
        CompositePhaseSpacePosition({'w01': PhaseSpacePosition(
            q=CartesianPosition3D( ... ),
            p=CartesianVelocity3D( ... ),
            t=Quantity...,
          'w02': PhaseSpacePosition(
            q=CartesianPosition3D( ... ),
            p=CartesianVelocity3D( ... ),
            t=Quantity...
        )})

        """
        # TODO: Interpolated form
        return gc.CompositePhaseSpacePosition(
            **{
                k: self(F, v, t0, t1, saveat, units=units, interpolated=interpolated)
                for k, v in w0.items()
            }
        )


# ============================================================================
# Interpolant


class Interpolant(eqx.Module):  # type: ignore[misc]#
    """Wrapper for ``diffrax.DenseInterpolation``."""

    interpolant: DenseInterpolation
    """:class:`diffrax.DenseInterpolation` object.

    This object is the result of the integration and can be used to evaluate the
    interpolated solution at any time. However it does not understand units, so
    the input is the time in ``units["time"]``. The output is a 6-vector of
    (q, p) values in the units of the integrator.
    """

    units: AbstractUnitSystem = eqx.field(static=True, converter=unitsystem)
    """The :class:`unxt.AbstractUnitSystem`.

    This is used to convert the time input to the interpolant and the phase-space
    position output.
    """

    added_ndim: int = eqx.field(static=True)
    """The number of dimensions added to the output of the interpolation.

    This is used to reshape the output of the interpolation to match the batch
    shape of the input to the integrator. The means of vectorizing the
    interpolation means that the input must always be a batched array, resulting
    in an extra dimension when the integration was on a scalar input.
    """

    def __call__(self, t: Quantity["time"], **_: Any) -> gc.PhaseSpacePosition:
        """Evaluate the interpolation."""
        # Parse t
        t_ = xp.atleast_1d(ustrip(self.units["time"], t))

        # Evaluate the interpolation
        ys = jax.vmap(lambda s: jax.vmap(s.evaluate)(t_))(self.interpolant)

        # Squeeze the output
        extra_dims: int = ys.ndim - 3 + self.added_ndim + (t_.ndim - t.ndim)
        ys = ys[(0,) * extra_dims]

        # Construct and return the result
        return gc.PhaseSpacePosition(
            q=Quantity(ys[..., 0:3], self.units["length"]),
            p=Quantity(ys[..., 3:6], self.units["speed"]),
            t=t,
        )
