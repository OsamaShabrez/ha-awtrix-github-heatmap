from __future__ import annotations

from datetime import date, timedelta

from .const import PANEL_H, PANEL_W


LEVEL_COLORS = [
    0x161B22,
    0x0E4429,
    0x006D32,
    0x26A641,
    0x39D353,
]

MONTH_MARKER = 0x666666


def build_column(
    days: list[dict],
) -> list[int]:
    """Convert one GitHub week into an 8-pixel column."""

    column = [0] * PANEL_H
    marker_set = False

    for day in days:
        current = date.fromisoformat(
            day["date"]
        )

        # GitHub: Sunday=0 ... Saturday=6.
        # Row 0 is reserved for the month marker.
        row = current.weekday() + 1

        if row < 1 or row >= PANEL_H:
            continue

        level = min(
            max(int(day.get("level", 0)), 0),
            4,
        )

        column[row] = LEVEL_COLORS[level]

        if not marker_set and current.day == 1:
            column[0] = MONTH_MARKER
            marker_set = True

    return column


def build_grid(
    days: list[dict],
    avatar: list[int] | None = None,
) -> list[int]:
    """Build the 32x8 AWTRIX pixel buffer in column-major order."""

    if not days:
        return [0] * (PANEL_W * PANEL_H)

    days = sorted(
        days,
        key=lambda item: item["date"],
    )

    last_date = date.fromisoformat(
        days[-1]["date"]
    )

    # Anchor at the Saturday ending the newest week.
    days_from_saturday = (
        5 - last_date.weekday()
    ) % 7

    anchor_date = (
        last_date
        + timedelta(days=days_from_saturday)
    )

    week_map: dict[int, list[dict]] = {}

    for day in days:
        current = date.fromisoformat(
            day["date"]
        )

        diff_days = (
            anchor_date - current
        ).days

        week_index = diff_days // 7

        week_map.setdefault(
            week_index,
            [],
        ).append(day)

    max_week = max(week_map)

    columns: list[list[int]] = []

    for week_index in range(
        max_week + 1
    ):
        week = week_map.get(
            week_index,
            [],
        )

        if week:
            columns.append(
                build_column(week)
            )
        else:
            columns.append(
                [0] * PANEL_H
            )

    pixels = [
        0
    ] * (
        PANEL_W * PANEL_H
    )

    # Avatar occupies columns 0-7.
    # Column 8 is the separator.
    left_offset = (
        PANEL_H + 1
        if avatar and len(avatar) == 64
        else 0
    )

    available_columns = (
        PANEL_W - left_offset
    )

    # The physical 32x8 display cannot show all
    # ~52 calendar weeks simultaneously.
    # With the 8x8 avatar, 23 newest weeks fit.
    column_count = min(
        len(columns),
        available_columns,
    )

    # Newest week is on the right.
    # Therefore the oldest visible week is on the left.
    for index in range(column_count):
        source_index = (
            column_count - 1 - index
        )

        target_column = (
            left_offset + index
        )

        column = columns[source_index]

        for row in range(PANEL_H):
            pixels[
                target_column * PANEL_H + row
            ] = column[row]

    if avatar and len(avatar) == 64:
        # Avatar arrives row-major.
        # AWTRIX internal buffer is column-major.
        # Transpose it to keep the avatar upright.
        for y in range(8):
            for x in range(8):
                pixels[
                    x * PANEL_H + y
                ] = avatar[
                    y * PANEL_H + x
                ]

    return pixels


def to_row_major(
    pixels: list[int],
) -> list[int]:
    """Convert column-major pixels to AWTRIX row-major."""

    expected = PANEL_W * PANEL_H

    if len(pixels) != expected:
        raise ValueError(
            f"Expected {expected} pixels, "
            f"got {len(pixels)}"
        )

    output: list[int] = []

    for y in range(PANEL_H):
        for x in range(PANEL_W):
            output.append(
                pixels[
                    x * PANEL_H + y
                ]
            )

    return output
