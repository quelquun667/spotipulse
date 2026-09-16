"""Renders the shareable PNG recap card (Pillow)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import asset_path
from .api import Artist, Track
from .genres import GenreCount

WIDTH, HEIGHT = 1080, 1350
BG = (18, 18, 18)
PANEL = (30, 30, 30)
GREEN = (30, 215, 96)
TEXT = (240, 240, 240)
MUTED = (160, 160, 160)
MARGIN = 72

_FONT_CANDIDATES = {
    True: [
        "seguisb.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
        "Helvetica-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    False: ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttf", "LiberationSans-Regular.ttf"],
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _numbered(draw, x, y, width, heading, rows: Sequence[tuple[str, str]]) -> int:
    draw.text((x, y), heading.upper(), font=_font(26, bold=True), fill=GREEN)
    y += 50
    number_font, title_font, sub_font = _font(34, bold=True), _font(32, bold=True), _font(24)
    for i, (title, subtitle) in enumerate(rows, start=1):
        draw.text((x, y), f"{i}", font=number_font, fill=MUTED)
        draw.text((x + 50, y), _fit(draw, title, title_font, width - 50), font=title_font, fill=TEXT)
        if subtitle:
            draw.text((x + 50, y + 40), _fit(draw, subtitle, sub_font, width - 50), font=sub_font, fill=MUTED)
        y += 86 if subtitle else 56
    return y


def render_recap(
    tracks: Sequence[Track],
    artists: Sequence[Artist],
    genres: Sequence[GenreCount],
    period_label: str,
    listening_label: str | None,
    out_dir: Path,
    now: datetime | None = None,
) -> Path:
    now = now or datetime.now()
    card = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(card)

    # Header: logo + title
    logo_file = asset_path("logo.png")
    text_x = MARGIN
    if logo_file:
        logo = Image.open(logo_file).convert("RGBA").resize((110, 110), Image.LANCZOS)
        card.paste(logo, (MARGIN, MARGIN), logo)
        text_x = MARGIN + 140
    draw.text((text_x, MARGIN + 6), "My Spotify Recap", font=_font(56, bold=True), fill=TEXT)
    draw.text((text_x, MARGIN + 74), f"Last {period_label.lower()}", font=_font(30), fill=GREEN)

    y = MARGIN + 170
    if listening_label:
        draw.rounded_rectangle((MARGIN, y, WIDTH - MARGIN, y + 90), radius=24, fill=PANEL)
        draw.text((MARGIN + 32, y + 24), listening_label, font=_font(34, bold=True), fill=TEXT)
        y += 130

    column = (WIDTH - 2 * MARGIN - 48) // 2
    left_bottom = _numbered(
        draw, MARGIN, y, column, "Top tracks", [(t.name, t.artist_line) for t in tracks[:5]]
    )
    artist_rows = [(a.name, ", ".join((a.genres or ())[:2]).title()) for a in artists[:5]]
    right_bottom = _numbered(draw, MARGIN + column + 48, y, column, "Top artists", artist_rows)
    y = max(left_bottom, right_bottom) + 30

    if genres:
        draw.text((MARGIN, y), "TOP GENRES", font=_font(26, bold=True), fill=GREEN)
        y += 54
        top = genres[:5]
        peak = max(g.count for g in top)
        label_font = _font(28)
        bar_x = MARGIN + 300
        bar_max = WIDTH - MARGIN - bar_x
        for g in top:
            draw.text((MARGIN, y), _fit(draw, g.genre.title(), label_font, 280), font=label_font, fill=TEXT)
            length = max(24, int(bar_max * g.count / peak))
            draw.rounded_rectangle((bar_x, y + 6, bar_x + length, y + 34), radius=14, fill=GREEN)
            y += 52

    footer = f"spotipulse · {now:%B %d, %Y}"
    footer_font = _font(24)
    draw.text(
        ((WIDTH - draw.textlength(footer, font=footer_font)) / 2, HEIGHT - MARGIN),
        footer,
        font=footer_font,
        fill=MUTED,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"spotipulse-recap-{now:%Y%m%d-%H%M%S}.png"
    card.save(path)
    return path
