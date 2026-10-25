from app.domain.models import TicketStatus

# All valid state transitions. Anything not listed is forbidden.
VALID_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {TicketStatus.OPEN},
    TicketStatus.OPEN: {TicketStatus.WAITING_CUSTOMER, TicketStatus.RESOLVED},
    TicketStatus.WAITING_CUSTOMER: {TicketStatus.OPEN, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.OPEN},  # reopen allowed
    TicketStatus.CLOSED: set(),  # terminal — nothing can leave here
}


class InvalidTransitionError(ValueError):
    """Raised when the requested state transition is not permitted."""


def transition(current: TicketStatus, target: TicketStatus) -> TicketStatus:
    """Validate and return *target* if the transition is valid.

    Raises InvalidTransitionError otherwise.
    """
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from {current.value!r} to {target.value!r}. "
            f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
        )
    return target
