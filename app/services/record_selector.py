from __future__ import annotations

import re

from app.config import MAX_RECORDS_PER_REQUEST

_SINGLE_INT_RE = re.compile(r"^\d+$")
_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def parse_record_selection(
    selection: str,
    total_records: int,
    max_records: int = MAX_RECORDS_PER_REQUEST,
) -> list[int]:
    """Parse expressions like '1,2,3', '1-5', '1,3-6', or 'all' into 1-based record numbers."""
    if total_records <= 0:
        raise ValueError("The selected sheet has no data records.")

    cleaned = (selection or "").strip()
    if not cleaned:
        raise ValueError(
            "Please enter record numbers (for example: 1,2,3 or 1-5 or all)."
        )

    if cleaned.lower() == "all":
        if total_records > max_records:
            raise ValueError(
                f"Too many records selected ({total_records}). "
                f"Maximum allowed per request is {max_records}."
            )
        return list(range(1, total_records + 1))

    tokens = [tok.strip() for tok in cleaned.split(",")]
    if any(tok == "" for tok in tokens):
        raise ValueError(
            "Invalid selection format. Remove extra commas and use values like 1,2,3 or 1-5."
        )

    selected: list[int] = []
    seen: set[int] = set()

    for token in tokens:
        if _SINGLE_INT_RE.match(token):
            num = int(token)
            if num < 1 or num > total_records:
                raise ValueError(
                    f"Record {num} is out of range. Please choose between 1 and {total_records}."
                )
            if num not in seen:
                seen.add(num)
                selected.append(num)
            continue

        range_match = _RANGE_RE.match(token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start < 1 or end < 1:
                raise ValueError(
                    f"Invalid range '{token}': record numbers start at 1."
                )
            if start > end:
                raise ValueError(
                    f"Invalid range '{token}': start ({start}) must be less than or equal to end ({end})."
                )
            if end > total_records:
                raise ValueError(
                    f"Range '{token}' is out of range. Maximum record number is {total_records}."
                )
            for num in range(start, end + 1):
                if num not in seen:
                    seen.add(num)
                    selected.append(num)
                if len(selected) > max_records:
                    raise ValueError(
                        f"Too many records selected. Maximum allowed per request is {max_records}."
                    )
            continue

        raise ValueError(
            f"Invalid selection '{token}'. Use numbers, ranges (e.g. 1-5), or 'all'."
        )

    if len(selected) > max_records:
        raise ValueError(
            f"Too many records selected ({len(selected)}). "
            f"Maximum allowed per request is {max_records}."
        )

    return selected
