"""Within-coffee (fixed effects) least-squares estimator for the grind model."""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from coffee_records.services.stats import FloatArray, r_squared

IntArray = npt.NDArray[np.int_]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class WithinCoffeeFit:
    """Result of fit_within_coffee.

    Attributes:
        coefficients: Global coefficient per feature (0 for inactive features).
        intercepts: Per-group intercept, indexed by group number.
        active: Which features had enough within-group variation to be fitted.
        within_ranges: Largest within-group range of each feature.
        r_squared: R² of the full model (None if y is constant).
    """

    coefficients: FloatArray
    intercepts: FloatArray
    active: BoolArray
    within_ranges: FloatArray
    r_squared: float | None


def fit_within_coffee(
    features: FloatArray,
    y: FloatArray,
    groups: IntArray,
    min_within_range: float,
) -> WithinCoffeeFit:
    """Fit ``y = features @ a + c[group]`` with the within-group estimator.

    Within-group (fixed effects) estimator — the right tool for panel data.

    Demean both X and y within each coffee group before fitting.  By the
    Frisch-Waugh-Lovell theorem this is algebraically identical to OLS with
    coffee dummy variables.

    Feature selection: only include features whose within-coffee range exceeds
    ``min_within_range`` in at least one coffee group.  Features that never vary
    within any single coffee (e.g. temperature always 70 °F, dose always 19 g)
    get coefficient 0 automatically — no spurious coefficient is estimated from
    zero variation, so the planner remains accurate when those features take
    values different from the training constant.

    The fit is closed-form: a single least-squares solve, then each group's
    intercept is its mean residual.

    Args:
        features: Shape ``(n_rows, n_features)``.
        y: Shape ``(n_rows,)``.
        groups: Group number in ``range(n_groups)`` for each row; every group
            must have at least one row.
        min_within_range: Minimum within-group range for a feature to be fitted.

    Returns:
        The fitted coefficients, intercepts and diagnostics.
    """
    n_groups = int(groups.max()) + 1
    n_features = features.shape[1]
    group_masks = [groups == g for g in range(n_groups)]

    feature_means = np.zeros((n_groups, n_features))
    y_means = np.zeros(n_groups)
    within_ranges = np.zeros(n_features)
    for g, mask in enumerate(group_masks):
        members = features[mask]
        feature_means[g] = members.mean(axis=0)
        y_means[g] = float(y[mask].mean())
        if len(members) > 1:
            within_ranges = np.maximum(
                within_ranges, members.max(axis=0) - members.min(axis=0)
            )

    active = within_ranges > min_within_range
    features_within = features - feature_means[groups]
    y_within = y - y_means[groups]

    coefficients = np.zeros(n_features)
    if active.any():
        coefficients[active] = np.linalg.lstsq(
            features_within[:, active], y_within, rcond=None
        )[0]

    residuals = y - features @ coefficients
    intercepts = np.array([float(residuals[mask].mean()) for mask in group_masks])
    predictions = features @ coefficients + intercepts[groups]
    return WithinCoffeeFit(
        coefficients=coefficients,
        intercepts=intercepts,
        active=active,
        within_ranges=within_ranges,
        r_squared=r_squared(y, predictions),
    )
