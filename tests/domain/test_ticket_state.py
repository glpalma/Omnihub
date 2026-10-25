import pytest

from app.domain.models import TicketStatus
from app.domain.ticket_state import InvalidTransitionError, VALID_TRANSITIONS, transition


# ---- valid transitions ----

def test_new_to_open():
    assert transition(TicketStatus.NEW, TicketStatus.OPEN) == TicketStatus.OPEN


def test_open_to_waiting_customer():
    assert transition(TicketStatus.OPEN, TicketStatus.WAITING_CUSTOMER) == TicketStatus.WAITING_CUSTOMER


def test_open_to_resolved():
    assert transition(TicketStatus.OPEN, TicketStatus.RESOLVED) == TicketStatus.RESOLVED


def test_waiting_customer_to_open():
    assert transition(TicketStatus.WAITING_CUSTOMER, TicketStatus.OPEN) == TicketStatus.OPEN


def test_waiting_customer_to_resolved():
    assert transition(TicketStatus.WAITING_CUSTOMER, TicketStatus.RESOLVED) == TicketStatus.RESOLVED


def test_resolved_to_closed():
    assert transition(TicketStatus.RESOLVED, TicketStatus.CLOSED) == TicketStatus.CLOSED


def test_resolved_can_reopen():
    """resolved → open is allowed to handle false positives."""
    assert transition(TicketStatus.RESOLVED, TicketStatus.OPEN) == TicketStatus.OPEN


# ---- invalid transitions ----

def test_cannot_skip_from_new_to_resolved():
    with pytest.raises(InvalidTransitionError):
        transition(TicketStatus.NEW, TicketStatus.RESOLVED)


def test_cannot_skip_from_new_to_closed():
    with pytest.raises(InvalidTransitionError):
        transition(TicketStatus.NEW, TicketStatus.CLOSED)


def test_cannot_go_backwards_from_open_to_new():
    with pytest.raises(InvalidTransitionError):
        transition(TicketStatus.OPEN, TicketStatus.NEW)


def test_closed_is_terminal():
    """Nothing should leave CLOSED."""
    for target in TicketStatus:
        if target != TicketStatus.CLOSED:
            with pytest.raises(InvalidTransitionError):
                transition(TicketStatus.CLOSED, target)


def test_error_message_is_informative():
    with pytest.raises(InvalidTransitionError, match="new.*closed"):
        transition(TicketStatus.NEW, TicketStatus.CLOSED)


def test_all_statuses_have_transition_entry():
    """Every status must appear as a key so there are no surprises."""
    for status in TicketStatus:
        assert status in VALID_TRANSITIONS
