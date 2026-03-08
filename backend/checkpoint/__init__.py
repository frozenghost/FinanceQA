"""Checkpointer for LangGraph agent. When Redis is enabled, use AsyncRedisSaver; else InMemorySaver."""

_checkpointer = None


def set_checkpointer(saver):
    """Set the checkpointer used by the agent (called from lifespan)."""
    global _checkpointer
    _checkpointer = saver


def get_checkpointer():
    """Return the current checkpointer or None (caller uses InMemorySaver when None)."""
    return _checkpointer
