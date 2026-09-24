"""Demographic data interfaces.

The database builder lives in ``reid_score.demographics.builder`` and is not
imported here, so that ``python -m reid_score.demographics.builder`` runs
without a double-import warning.
"""

from .lookup import (
    BUNDLED_DATABASES,
    QI_COLUMNS,
    REQUIRED_COLUMNS,
    DemographicLookup,
    PopulationMatch,
    normalize_geography,
)
from .uniqueness import NO_QI_POPULATION, UniquenessCalculator, UniquenessResult

__all__ = [
    "BUNDLED_DATABASES",
    "DemographicLookup",
    "NO_QI_POPULATION",
    "PopulationMatch",
    "QI_COLUMNS",
    "REQUIRED_COLUMNS",
    "UniquenessCalculator",
    "UniquenessResult",
    "normalize_geography",
]
