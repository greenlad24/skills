"""The canonical VideoJob state machine (§1.4).

This is a SHARED CONTRACT: every section's status values map to `JobState`, and every
worker/stage transitions jobs only through `transition()`. The `AWAITING_APPROVAL`
state is a *durable pause* — it holds no worker or connection, and the only way out
of it is a human-triggered decision.
"""

from __future__ import annotations

import enum


class JobState(str, enum.Enum):
    """Finite job states. Values match §1.4 exactly (string-valued for DB ENUM / JSON)."""

    QUEUED = "QUEUED"
    RESEARCHING = "RESEARCHING"          # Stage 1+2: product research + swipe mining
    SCRIPTING = "SCRIPTING"              # Stage 3: claim-safe Thai script + scenes
    GENERATING = "GENERATING"            # Stage 4: hero image + b-roll + avatar + TTS
    EDITING = "EDITING"                  # Stage 5: creative re-cut / assembly
    CAPTIONING = "CAPTIONING"            # Stage 6: Thai captions + baked AI label
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # Stage 7: the single human gate (durable pause)
    POSTING = "POSTING"                  # Stage 8: auto-post via posting provider
    POSTED = "POSTED"                    # Published; awaiting manual product tag
    FAILED = "FAILED"                    # Stage exhausted retries / hard error
    REJECTED = "REJECTED"                # Operator rejected at the gate (discard); terminal
    CANCELLED = "CANCELLED"              # Operator cancelled before completion; terminal


# Allowed transitions map (§1.4 state diagram). Key = current state, value = set of
# states it may move to.
ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.RESEARCHING, JobState.CANCELLED},
    JobState.RESEARCHING: {JobState.SCRIPTING, JobState.FAILED},
    JobState.SCRIPTING: {JobState.GENERATING, JobState.FAILED},
    JobState.GENERATING: {JobState.EDITING, JobState.FAILED},
    JobState.EDITING: {JobState.CAPTIONING, JobState.FAILED},
    JobState.CAPTIONING: {JobState.AWAITING_APPROVAL, JobState.FAILED},
    # The gate: only human-triggered edges leave AWAITING_APPROVAL.
    JobState.AWAITING_APPROVAL: {
        JobState.POSTING,     # operator APPROVE
        JobState.EDITING,     # operator REJECT + re-cut notes (cheap loop, no regen)
        JobState.REJECTED,    # operator REJECT (discard)
        JobState.CANCELLED,   # operator cancel
    },
    JobState.POSTING: {JobState.POSTED, JobState.FAILED},
    # Manual retry re-enters QUEUED and resumes from last_completed_stage.
    JobState.FAILED: {JobState.QUEUED},
    # Terminal states.
    JobState.POSTED: set(),
    JobState.REJECTED: set(),
    JobState.CANCELLED: set(),
}

# States from which the ONLY legal transitions are triggered by a human action
# (the approval gate). Workers must never auto-advance out of these.
HUMAN_GATED_STATES: frozenset[JobState] = frozenset({JobState.AWAITING_APPROVAL})

# The human-triggerable target states out of the gate.
HUMAN_TRIGGERED_TARGETS: frozenset[JobState] = frozenset(
    {JobState.POSTING, JobState.EDITING, JobState.REJECTED, JobState.CANCELLED}
)

# Terminal states — no outbound transitions.
TERMINAL_STATES: frozenset[JobState] = frozenset(
    {JobState.POSTED, JobState.REJECTED, JobState.CANCELLED}
)


class IllegalTransitionError(Exception):
    """Raised when a transition is not permitted by ALLOWED_TRANSITIONS."""

    def __init__(self, current: JobState, target: JobState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Illegal state transition: {current.value} -> {target.value}")


def can_transition(current: JobState, target: JobState) -> bool:
    """Pure predicate: is `current -> target` allowed?"""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def is_terminal(state: JobState) -> bool:
    return state in TERMINAL_STATES


def requires_human(state: JobState) -> bool:
    """True if leaving `state` requires a human decision (the approval gate)."""
    return state in HUMAN_GATED_STATES


def transition(job, new_state: JobState, *, by_human: bool = False) -> JobState:
    """Transition `job.state` to `new_state`, mutating the job in place.

    `job` is any object with a mutable `.state` attribute (the SQLAlchemy VideoJob,
    or a lightweight test double). Raises `IllegalTransitionError` on an illegal
    edge — including any attempt to auto-advance out of the human gate without
    `by_human=True`.

    Returns the new state on success. Persistence (commit) is the caller's job.
    """
    current = job.state
    # Normalize: `state` may be a raw string (from the DB) or a JobState.
    if isinstance(current, str):
        current = JobState(current)

    if not can_transition(current, new_state):
        raise IllegalTransitionError(current, new_state)

    # Enforce the durable-pause semantics: only a human decision may leave the gate.
    if requires_human(current) and not by_human:
        raise IllegalTransitionError(current, new_state)

    job.state = new_state
    return new_state
