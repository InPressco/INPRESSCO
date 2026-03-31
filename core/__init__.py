"""core/ — Référentiel système InPressco.

Source de vérité unique importable par tous les outils du workspace.
Usage : from core import SKILLS_REGISTRY, PIPELINE_STRUCTURE, ANTI_PATTERNS
"""
from .system_reference import (
    PRINCIPES,
    PIPELINE_STRUCTURE,
    SKILLS_REGISTRY,
    DOLIBARR_CONVENTIONS,
    CHAINES_ORCHESTRATION,
    REVIEW_GATES,
    ANTI_PATTERNS,
    EQUIPE,
    IDENTITE_INPRESSCO,
    SYSTEM_VERSION,
    SYSTEM_UPDATED_AT,
)

__all__ = [
    "PRINCIPES",
    "PIPELINE_STRUCTURE",
    "SKILLS_REGISTRY",
    "DOLIBARR_CONVENTIONS",
    "CHAINES_ORCHESTRATION",
    "REVIEW_GATES",
    "ANTI_PATTERNS",
    "EQUIPE",
    "IDENTITE_INPRESSCO",
    "SYSTEM_VERSION",
    "SYSTEM_UPDATED_AT",
]
