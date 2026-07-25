from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, replace
from html.parser import HTMLParser

from .models import Ticket
from .risk import redact_pii

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_text(value: str) -> str:
    decoded = html.unescape(value)
    if "<" in decoded and ">" in decoded:
        parser = _TextExtractor()
        parser.feed(decoded)
        decoded = " ".join(parser.parts)
    decoded = unicodedata.normalize("NFKC", decoded)
    decoded = CONTROL_RE.sub(" ", decoded)
    lines = [
        HORIZONTAL_SPACE_RE.sub(" ", line).strip()
        for line in decoded.splitlines()
    ]
    compact = "\n".join(line for line in lines if line)
    return BLANK_LINES_RE.sub("\n\n", compact).strip()


@dataclass(frozen=True)
class PreparedTicket:
    normalized_ticket: Ticket
    safe_ticket: Ticket
    sanitized_text: str


def prepare_ticket(ticket: Ticket) -> PreparedTicket:
    normalized_subject = normalize_text(ticket.subject)
    normalized_text = normalize_text(ticket.text)
    normalized = replace(
        ticket,
        subject=normalized_subject,
        text=normalized_text,
    )
    safe_subject = redact_pii(normalized_subject)
    safe_text = redact_pii(normalized_text)
    return PreparedTicket(
        normalized_ticket=normalized,
        safe_ticket=replace(
            normalized,
            subject=safe_subject,
            text=safe_text,
        ),
        sanitized_text=f"{safe_subject} {safe_text}".strip(),
    )
