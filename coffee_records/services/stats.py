"""Small statistics helpers shared by the regression services."""

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# R² is reported to this many decimal places.
R_SQUARED_DECIMALS = 4


def r_squared(y: FloatArray, predictions: FloatArray) -> float | None:
    """Return the coefficient of determination, or None when y has no variance.

    Args:
        y: Observed values.
        predictions: Fitted values.

    Returns:
        1 − SS_res / SS_tot rounded to four decimals, or None.
    """
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot == 0:
        return None
    ss_res = float(np.sum((y - predictions) ** 2))
    return round(1 - ss_res / ss_tot, R_SQUARED_DECIMALS)
