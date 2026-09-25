"""PHI boundary: only de-identified text may leave the device."""


def deidentify(text: str) -> str:
    """Rule-based scrub (names, dates, IDs) followed by an LFM pass."""
    raise NotImplementedError


def contains_phi(payload: str) -> bool:
    """Guard for every outbound request (Nimble, BFL). A hit is an audit violation."""
    raise NotImplementedError
