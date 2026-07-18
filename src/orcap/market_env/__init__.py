"""Strategic inference-provider market simulation.

The package separates a framework-independent market kernel from provider
strategies and learning libraries.  Public-data calibration and executable
router adapters can depend on this package; the kernel must not depend on them.
"""

from .kernel import MarketKernel
from .routers import (
    InversePriceRouter,
    LowestCostRouter,
    RandomRouter,
    ReliabilityWeightedRouter,
)
from .scenario import MarketScenario, load_scenario
from .types import (
    Availability,
    EpochResult,
    ProviderAction,
    ProviderSpec,
    RequestOutcome,
    Workload,
)

__all__ = [
    "Availability",
    "EpochResult",
    "InversePriceRouter",
    "LowestCostRouter",
    "MarketKernel",
    "MarketScenario",
    "ProviderAction",
    "ProviderSpec",
    "RandomRouter",
    "ReliabilityWeightedRouter",
    "RequestOutcome",
    "Workload",
    "load_scenario",
]
