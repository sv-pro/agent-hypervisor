"""
Channel — sealed trust derivation
==================================

Trust is derived from channel identity, not from caller assertions.

Old model:
    Source("user")          # any caller can claim any identity
    Source("system")        # trust is self-reported

New model:
    channel = runtime.channel("user")   # runtime resolves trust from compiled map
    source = channel.source             # Source created by channel, not by caller
    Source(trust_level=..., ...)        # TypeError — cannot be constructed directly

Sealing mechanism:
    _SOURCE_SEAL is a module-private sentinel object. Source.__new__ checks
    for it. External code cannot import _SOURCE_SEAL, so cannot construct
    a Source without going through Channel.source. Any attempt raises TypeError
    at object creation time.
"""

from __future__ import annotations

from typing import Any

from .compile import CompiledPolicy
from .models import TrustLevel


# ── Module-private seal ───────────────────────────────────────────────────────
_SOURCE_SEAL: object = object()


# ── Source ────────────────────────────────────────────────────────────────────

class Source:
    """
    A trust-bearing identity produced by a Channel.

    Cannot be constructed directly by callers. The constructor raises
    TypeError if called without the module-private _SOURCE_SEAL token.
    Obtain Source objects through Channel.source only.

    Immutable after construction: __setattr__ is overridden to raise.
    """

    __slots__ = ("trust_level", "identity")

    def __new__(
        cls,
        trust_level: TrustLevel,
        identity: str,
        _seal: object = None,
    ) -> "Source":
        if _seal is not _SOURCE_SEAL:
            raise TypeError(
                "Source cannot be constructed directly. "
                "Obtain a Source through Channel.source — "
                "trust is derived from the channel, not from caller assertions."
            )
        return super().__new__(cls)

    def __init__(
        self,
        trust_level: TrustLevel,
        identity: str,
        _seal: object = None,
    ) -> None:
        object.__setattr__(self, "trust_level", trust_level)
        object.__setattr__(self, "identity", identity)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Source is immutable after construction")

    def __repr__(self) -> str:
        return f"Source(identity={self.identity!r}, trust={self.trust_level.value!r})"

    def __hash__(self) -> int:
        return hash((self.trust_level, self.identity))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Source):
            return NotImplemented
        return self.trust_level == other.trust_level and self.identity == other.identity


# ── Channel ───────────────────────────────────────────────────────────────────

class Channel:
    """
    Authenticated channel. The only factory for Source objects.

    The key property is that Channel — not the caller — creates the Source.
    The caller cannot inject a different trust_level into the Source because
    trust is resolved from the compiled policy, not from caller input.
    """

    __slots__ = ("_identity", "_policy")

    def __init__(self, identity: str, policy: CompiledPolicy) -> None:
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(self, "_policy", policy)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Channel is immutable after construction")

    @property
    def source(self) -> Source:
        """
        Produce a Source with the trust level assigned by the compiled policy.

        The caller provides the identity string. The trust_level is resolved
        from the compiled trust map — the caller cannot override it.
        Unknown identities resolve to UNTRUSTED (fail-secure).
        """
        trust_level = self._policy.resolve_trust(self._identity)
        return Source(
            trust_level=trust_level,
            identity=self._identity,
            _seal=_SOURCE_SEAL,
        )

    def __repr__(self) -> str:
        return f"Channel(identity={self._identity!r})"
