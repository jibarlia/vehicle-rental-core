from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """Timezone-aware wall clock.

    Injected into services rather than called inline so tests can freeze time
    without patching module internals.
    """
    return datetime.now(UTC)
