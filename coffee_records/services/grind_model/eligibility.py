"""Which shots may be used to train the grind model.

Shots pulled with shot profiling (the "Flow Taper" flag, ``Shot.flow_taper``)
follow a different flow curve, so their grind/extraction relationship is not
comparable with standard shots. They are excluded from training.

Eligibility is decided explicitly, never by truthiness:

* ``flow_taper is False`` — not profiled: **included**.
* ``flow_taper is True``  — profiled: **excluded**.
* anything else (``None``, i.e. unknown) — **excluded** and counted
  separately. The column is NOT NULL, so this only guards against unsaved or
  malformed records; an unknown flag is never assumed to mean "not profiled".
"""

from dataclasses import dataclass, field

from coffee_records.models.shot import Shot


def profiling_flag(shot: Shot) -> bool | None:
    """Return the shot's profiling flag (True, False, or None if unknown).

    This is the single place that maps "shot profiling" onto a model column.

    Args:
        shot: Shot to inspect.

    Returns:
        The raw ``flow_taper`` value.
    """
    value: bool | None = shot.flow_taper
    return value


@dataclass
class ProfilingSplit:
    """Shots partitioned by their profiling flag.

    Attributes:
        eligible: Explicitly not profiled; used for training.
        profiled: Explicitly profiled; excluded.
        unknown: Flag missing; excluded.
    """

    eligible: list[Shot] = field(default_factory=list)
    profiled: list[Shot] = field(default_factory=list)
    unknown: list[Shot] = field(default_factory=list)

    @property
    def excluded_count(self) -> int:
        """Number of shots kept out of training."""
        return len(self.profiled) + len(self.unknown)


def split_by_profiling(shots: list[Shot]) -> ProfilingSplit:
    """Partition shots into eligible, profiled and unknown, preserving order.

    Args:
        shots: Candidate training shots.

    Returns:
        The partition.
    """
    split = ProfilingSplit()
    for shot in shots:
        flag = profiling_flag(shot)
        if flag is False:
            split.eligible.append(shot)
        elif flag is True:
            split.profiled.append(shot)
        else:
            split.unknown.append(shot)
    return split
