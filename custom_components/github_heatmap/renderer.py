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

    for day in days:
        current = date.fromisoformat(
            day["date"]
        )

        # GitHub weeks run Sunday -> Saturday.
        # Row 0 is reserved for the month marker,
        # so weekdays occupy rows 1 -> 7.
        row = current.weekday() + 2

        if row < 1 or row > 7:
            continue

        level = min(
            max(
                int(day.get("level", 0)),
                0,
            ),
            4,
        )

        column[row] = LEVEL_COLORS[level]

        if current.day == 1:
            column[0] = MONTH_MARKER

    return column


def build_grid(
    days: list[dict],
    avatar: list[int] | None = None,
    reserve_left: bool = False,
) -> list[int]:
    """Build a 32x8 column-major pixel buffer."""

    if not days:
        return [0] * (
            PANEL_W * PANEL_H
        )

    days = sorted(
        days,
        key=lambda item: item["date"],
    )

    last_date = date.fromisoformat(
        days[-1]["date"]
    )

    anchor_date = last_date

    while anchor_date.weekday() != 5:
        anchor_date += timedelta(
            days=1
        )

    week_map: dict[
        int,
        list[dict],
    ] = {}

    for day in days:
        current = date.fromisoformat(
            day["date"]
        )

        diff = (
            anchor_date - current
        ).days

        week_index = diff // 7

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

    # Avatar: columns 0-7.
    # Column 8: one-pixel separator.
    has_avatar = (
        avatar is not None
        and len(avatar) == 64
    )

    heatmap_offset = (
        9
        if has_avatar or reserve_left
        else 0
    )

    available = (
        PANEL_W - heatmap_offset
    )

    count = min(
        len(columns),
        available,
    )

    # Oldest visible week left,
    # newest visible week right.
    for index in range(count):
        source_index = (
            count - 1 - index
        )

        target_column = (
            heatmap_offset + index
        )

        column = columns[
            source_index
        ]

        for row in range(PANEL_H):
            pixels[
                target_column
                * PANEL_H
                + row
            ] = column[row]

    if avatar is not None and len(avatar) == 64:
        # Avatar data is row-major.
        # Internal bitmap is column-major.
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

    expected = (
        PANEL_W * PANEL_H
    )

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
