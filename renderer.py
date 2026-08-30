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
    """Convert one week into an 8-pixel column."""

    column = [0] * PANEL_H

    for day in days:
        current = date.fromisoformat(
            day["date"]
        )

        row = (current.weekday() + 1) % 7
        row += 1

        if row > 7:
            row = 1

        level = min(
            max(int(day.get("level", 0)), 0),
            4,
        )

        column[row] = LEVEL_COLORS[level]

        if current.day == 1:
            column[0] = MONTH_MARKER

    return column


def build_grid(
    days: list[dict],
    avatar: list[int] | None = None,
) -> list[int]:
    """Build 32x8 column-major pixel buffer."""

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
        anchor_date += timedelta(days=1)

    week_map: dict[int, list[dict]] = {}

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

    columns = []

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

    heatmap_offset = (
        9 if avatar else 0
    )

    available = (
        PANEL_W - heatmap_offset
    )

    count = min(
        len(columns),
        available,
    )

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

    if avatar:
        for y in range(8):
            for x in range(8):
                pixels[
                    x * 8 + y
                ] = avatar[
                    y * 8 + x
                ]

    return pixels


def to_row_major(
    pixels: list[int],
) -> list[int]:
    """Convert column-major pixels to AWTRIX row-major."""

    output = []

    for y in range(PANEL_H):
        for x in range(PANEL_W):
            output.append(
                pixels[
                    x * PANEL_H + y
                ]
            )

    return output
