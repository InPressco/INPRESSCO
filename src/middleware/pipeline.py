"""middleware/pipeline.py — Classe Pipeline MWP."""
import logging
from typing import Callable, Awaitable
from .context import Context

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Exécute une séquence de steps asynchrones sur un Context partagé.
    Si un step lève une exception ou positionne ctx.skip_remaining=True,
    les steps suivants sont ignorés.
    """

    def __init__(self, name: str):
        self.name = name
        self._steps: list[Callable[[Context], Awaitable[None]]] = []

    def add(self, step_fn: Callable[[Context], Awaitable[None]]) -> "Pipeline":
        self._steps.append(step_fn)
        return self

    async def run(self, context: Context) -> Context:
        logger.info(f"[{self.name}] Démarrage — {len(self._steps)} steps")

        for step in self._steps:
            if context.skip_remaining:
                logger.warning(f"[{self.name}] skip_remaining=True, arrêt avant {step.__name__}")
                break

            step_name = step.__name__
            try:
                logger.info(f"[{self.name}] → {step_name}")
                await step(context)
                logger.info(f"[{self.name}] ✓ {step_name}")

            except StopPipeline as e:
                logger.warning(f"[{self.name}] ⚠ {step_name} : {e} — pipeline arrêté proprement")
                context.skip_remaining = True
                break

            except Exception as e:
                logger.error(f"[{self.name}] ✗ {step_name} : {e}", exc_info=True)
                context.add_error(step_name, e)
                context.skip_remaining = True
                break

        if context.errors:
            logger.error(f"[{self.name}] Terminé avec erreurs : {context.errors}")
        else:
            logger.info(f"[{self.name}] Terminé sans erreur")

        return context


class StopPipeline(Exception):
    """Lever cette exception pour arrêter le pipeline proprement (pas d'erreur)."""
    pass
