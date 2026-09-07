"""PWG polymer waveguide intelligence module.

This package is intentionally independent from the existing channel-1 and
channel-3 news pipelines.
"""

from .models import (
    PWG_MATURITY_LEVELS,
    PWG_SOURCE_LEVELS,
    PWGIntelligenceCard,
)

__all__ = [
    "PWGIntelligenceCard",
    "PWG_MATURITY_LEVELS",
    "PWG_SOURCE_LEVELS",
]
