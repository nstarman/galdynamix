__all__ = ["Integrator"]

from typing import Any, Protocol, runtime_checkable

import galax.typing as gt
from galax.coordinates import AbstractPhaseSpacePosition, PhaseSpacePosition
from galax.units import UnitSystem
from galax.utils.dataclasses import _DataclassInstance


@runtime_checkable
class FCallable(Protocol):
    """Protocol for the integration callable."""

    def __call__(self, t: gt.FloatScalar, w: gt.Vec6, args: tuple[Any, ...]) -> gt.Vec6:
        """Integration function.

        Parameters
        ----------
        t : float
            The time. This is the integration variable.
        w : Array[float, (6,)]
            The position and velocity.
        args : tuple[Any, ...]
            Additional arguments.

        Returns
        -------
        Array[float, (6,)]
            Velocity and acceleration [v (3,), a (3,)].
        """
        ...


@runtime_checkable
class Integrator(_DataclassInstance, Protocol):
    """:class:`typing.Protocol` for integrators.

    The integrators are classes that are used to integrate the equations of
    motion.
    They must not be stateful since they are used in a functional way.
    """

    # TODO: shape hint of the return type
    def __call__(
        self,
        F: FCallable,
        w0: AbstractPhaseSpacePosition | gt.BatchVec6,
        /,
        ts: gt.BatchQVecTime | gt.BatchVecTime | gt.QVecTime | gt.VecTime,
        *,
        units: UnitSystem,
    ) -> PhaseSpacePosition:
        """Integrate.

        Parameters
        ----------
        F : FCallable, positional-only
            The function to integrate.
            (t, w, args) -> (v, a).
        w0 : AbstractPhaseSpacePosition | Array[float, (6,)], positional-only
            Initial conditions ``[q, p]``.
        ts : (Quantity | Array)[float, (T,)]
            Times to return the computation.
            It's necessary to at least provide the initial and final times.
        units : UnitSystem
            The unit system to use.

        Returns
        -------
        PhaseSpacePosition[float, (T, 7)]
            The solution of the integrator [q, p, t], where q, p are the
            generalized 3-coordinates.
        """
        ...
