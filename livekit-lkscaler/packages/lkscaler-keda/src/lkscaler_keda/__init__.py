"""KEDA autoscaler integration for LKScaler."""

from .config import KedaAutoscalerConfig
from .deletion_cost import PodDeletionCostReconciler, choose_deletion_cost
from .policy import AutoscalerDecision, AutoscalerPolicy
from .scaler import ExternalMetricValue, KedaExternalScaler

__version__ = "0.1.0"

__all__ = [
	"AutoscalerDecision",
	"AutoscalerPolicy",
	"PodDeletionCostReconciler",
	"ExternalMetricValue",
	"KedaAutoscalerConfig",
	"KedaExternalScaler",
	"choose_deletion_cost",
]