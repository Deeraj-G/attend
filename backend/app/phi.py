"""PHI boundary: only de-identified text may leave the device."""

import re

# Rule layer for the outbound guard. Catches structured identifiers; free-text names
# still need the LFM pass in deidentify().
_PHI_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),  # dates like 03/14/1962
    re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b"),  # ISO dates
    re.compile(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4}\b", re.I
    ),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"\(?\b\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"),  # phone
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),  # email
    re.compile(r"\b(mrn|dob|ssn|medical record|date of birth)\b", re.I),
    re.compile(r"\b\d{6,}\b"),  # long IDs (MRN, account numbers)
    re.compile(r"\b(mr|mrs|ms|miss)\.? [A-Z][a-z]+", re.I),  # honorific + name
]


def deidentify(text: str) -> str:
    """Rule-based scrub (names, dates, IDs) followed by an LFM pass."""
    raise NotImplementedError


def contains_phi(payload: str) -> bool:
    """Guard for every outbound request (Nimble, BFL). A hit is an audit violation."""
    return any(p.search(payload) for p in _PHI_PATTERNS)
