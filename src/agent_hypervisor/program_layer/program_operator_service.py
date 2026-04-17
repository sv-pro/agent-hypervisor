"""
program_operator_service.py — Operator surface for reviewed programs (SYS-4A).

Thin read-mostly wrapper over ProgramStore.  Does not mutate program status.
"""

from __future__ import annotations

from typing import Optional

from .compatibility import check_compatibility, preview_program_under_world
from .operator_event_log import OperatorEventLog
from .operator_models import ProgramSummary
from .program_store import ProgramStore
from .review_models import ProgramDiff, ReviewedProgram
from .world_registry import WorldRegistry

try:
    from .compatibility import ProgramWorldCompatibility
except ImportError:
    pass


class ProgramOperatorService:
    """
    Operator-facing surface for reviewing program artifacts.

    Read-only with respect to program status — lifecycle mutations (accept,
    reject, etc.) still go through review_lifecycle.py.
    """

    def __init__(
        self,
        store: ProgramStore,
        registry: WorldRegistry,
        event_log: OperatorEventLog,
    ) -> None:
        self._store = store
        self._registry = registry
        self._event_log = event_log

    # ------------------------------------------------------------------
    # List / inspect
    # ------------------------------------------------------------------

    def list_programs(self, status: Optional[str] = None) -> list[ProgramSummary]:
        """
        Return ProgramSummary for all programs, optionally filtered by status.

        compatible_with_active_world is computed against the current active
        world if one is set; otherwise it is None.
        """
        active_world = self._registry.get_active()
        summaries: list[ProgramSummary] = []
        for prog_id in self._store.list_ids():
            try:
                prog = self._store.load(prog_id)
            except (KeyError, ValueError):
                continue
            prog_status = prog.status.value if hasattr(prog.status, "value") else str(prog.status)
            if status is not None and prog_status != status:
                continue

            compat: Optional[bool] = None
            if active_world is not None:
                compat = check_compatibility(prog, active_world).compatible

            summaries.append(
                ProgramSummary(
                    program_id=prog.id,
                    status=prog_status,
                    world_version_at_creation=prog.metadata.world_version,
                    compatible_with_active_world=compat,
                    last_replay_verdict=None,
                )
            )

        self._event_log.log(
            action="list_programs",
            target_type="program",
            target_id="*",
            result="ok",
            details={"count": len(summaries), "status_filter": status},
        )
        return summaries

    def get_program(self, program_id: str) -> ReviewedProgram:
        prog = self._store.load(program_id)
        self._event_log.log(
            action="get_program",
            target_type="program",
            target_id=program_id,
            result="ok",
        )
        return prog

    def get_program_diff(self, program_id: str) -> ProgramDiff:
        prog = self._store.load(program_id)
        self._event_log.log(
            action="get_program_diff",
            target_type="program",
            target_id=program_id,
            result="ok",
        )
        return prog.diff

    def get_program_compatibility(
        self,
        program_id: str,
        world_id: Optional[str] = None,
        version: Optional[str] = None,
    ) -> "ProgramWorldCompatibility":
        """
        Return per-step compatibility verdict.

        If world_id is None, uses the active world.  Raises ValueError if
        neither is available.
        """
        prog = self._store.load(program_id)

        if world_id is not None:
            world = self._registry.get(world_id, version)
        else:
            world = self._registry.get_active()
            if world is None:
                raise ValueError(
                    "No world_id provided and no active world is set."
                )

        result = check_compatibility(prog, world)
        self._event_log.log(
            action="get_program_compatibility",
            target_type="program",
            target_id=program_id,
            result="ok",
            details={
                "world_id": world.world_id,
                "version": world.version,
                "compatible": result.compatible,
            },
        )
        return result
