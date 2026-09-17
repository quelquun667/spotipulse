"""Renders the shareable PNG recap card (Pillow)."""

from __future__ import annotations

import colorsys
from collections.abc import Callable, Sequence
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import asset_path
from .api import Artist, Track
from .genres import GenreCount

WIDTH, HEIGHT = 1080, 1350  # 4:5, the Instagram feed format
MARGIN = 72
BG = (18, 18, 18)
GREEN = (30, 215, 96)
TEXT = (245, 245, 245)
MUTED = (179, 179, 179)
DIM = (120, 120, 120)

ImageLoader = Callable[[str | None], Image.Image | None]

_FONT_CANDIDATES = {
    "black": ["seguibl.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Helvetica-Bold.ttf"],
    "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Helvetica-Bold.ttf"],
    "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttf"],
}


@lru_cache(maxsize=64)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES[weight]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# ---------- text helpers ----------


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    words = text.split()
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            current = " ".join(words[i:])
            break
    if current:
        lines.append(current)
    lines = lines[:max_lines]
    lines[-1] = _fit(draw, lines[-1], font, max_width)
    return lines


def _spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, spacing: float = 2.5) -> int:
    """Letter-spaced label. Returns its width."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + spacing
    return int(x - xy[0] - spacing)


def _spaced_width(draw: ImageDraw.ImageDraw, text: str, font, spacing: float = 2.5) -> int:
    return int(sum(draw.textlength(c, font=font) for c in text) + spacing * max(0, len(text) - 1))


# ---------- image helpers ----------


def _placeholder(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    k = size / 300
    draw.ellipse((95 * k, 185 * k, 155 * k, 235 * k), fill=GREEN)
    draw.rectangle((143 * k, 70 * k, 155 * k, 210 * k), fill=GREEN)
    draw.polygon([(155 * k, 70 * k), (215 * k, 95 * k), (215 * k, 125 * k), (155 * k, 100 * k)], fill=GREEN)
    return image


def _mask(size: int, radius: int | None) -> Image.Image:
    """Anti-aliased rounded-square (or circle when radius is None) mask."""
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    if radius is None:
        draw.ellipse((0, 0, big - 1, big - 1), fill=255)
    else:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * 4, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _paste_art(canvas: Image.Image, image: Image.Image | None, xy, size: int, radius: int | None) -> None:
    art = ImageOps.fit((image or _placeholder(size)).convert("RGB"), (size, size), Image.LANCZOS)
    canvas.paste(art, xy, _mask(size, radius))


def _shadow(
    canvas: Image.Image, box, radius: int, blur: int = 28, opacity: int = 150, offset: int = 18
) -> None:
    x0, y0, x1, y1 = box
    pad = blur * 3
    layer = Image.new("L", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), 0)
    ImageDraw.Draw(layer).rounded_rectangle(
        (pad, pad, pad + x1 - x0, pad + y1 - y0), radius=radius, fill=opacity
    )
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    black = Image.new("RGB", layer.size, (0, 0, 0))
    canvas.paste(black, (x0 - pad, y0 - pad + offset), layer)


def accent_color(image: Image.Image | None) -> tuple[int, int, int]:
    """A vivid version of the cover's dominant color, or Spotify green without a cover."""
    if image is None:
        return GREEN
    small = image.convert("RGB").resize((24, 24), Image.BILINEAR)
    best, best_score = None, -1.0
    raw = small.tobytes()
    for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3], strict=True):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        score = s * v
        if score > best_score:
            best, best_score = (h, s, v), score
    if best is None or best_score < 0.12:
        return GREEN
    h, s, _ = best
    r, g, b = colorsys.hsv_to_rgb(h, max(0.55, min(s, 0.85)), 0.85)
    return int(r * 255), int(g * 255), int(b * 255)


def _background(accent: tuple[int, int, int], hero: Image.Image | None) -> Image.Image:
    base = Image.new("RGB", (WIDTH, HEIGHT), BG)
    if hero is not None:
        blurred = ImageOps.fit(hero.convert("RGB"), (WIDTH, HEIGHT), Image.LANCZOS)
        blurred = blurred.filter(ImageFilter.GaussianBlur(70))
        base = Image.blend(base, blurred, 0.28)
    # soft glow of the accent color from the top-left corner
    glow = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(glow).ellipse((-420, -520, 900, 640), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    base = Image.composite(Image.new("RGB", (WIDTH, HEIGHT), accent), base, glow)
    # fade to near-black towards the bottom so the lists stay readable
    fade = Image.linear_gradient("L").resize((WIDTH, HEIGHT)).point(lambda v: int(v * 0.8))
    return Image.composite(Image.new("RGB", (WIDTH, HEIGHT), BG), base, fade)


def _load(images: ImageLoader | None, url: str | None) -> Image.Image | None:
    if images is None or not url:
        return None
    try:
        return images(url)
    except Exception:
        return None


# ---------- card ----------


def _header(card: Image.Image, draw: ImageDraw.ImageDraw, period_label: str) -> None:
    logo_file = asset_path("logo.png")
    text_x = MARGIN
    if logo_file:
        logo = Image.open(logo_file).convert("RGBA").resize((56, 56), Image.LANCZOS)
        card.paste(logo, (MARGIN, MARGIN), logo)
        text_x = MARGIN + 72
    draw.text((text_x, MARGIN + 28), "spotipulse", font=_font("semibold", 30), fill=TEXT, anchor="lm")

    period = period_label.upper()
    label = f"LAST {period[2:]}" if period.startswith("1 ") else f"LAST {period}"  # "1 YEAR" -> "LAST YEAR"
    font = _font("bold", 22)
    width = _spaced_width(draw, label, font)
    x1 = WIDTH - MARGIN
    x0 = x1 - width - 48
    draw.rounded_rectangle((x0, MARGIN + 4, x1, MARGIN + 52), radius=24, fill=GREEN)
    _spaced(draw, (x0 + 24, MARGIN + 14), label, font, BG)


def _hero(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    track: Track | None,
    cover: Image.Image | None,
    listening_label: str | None,
    y: int,
) -> None:
    height = 320
    panel = Image.new("RGBA", (WIDTH - 2 * MARGIN, height), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        (0, 0, panel.width - 1, height - 1), radius=36, fill=(255, 255, 255, 20)
    )
    card.paste(panel, (MARGIN, y), panel)

    size = 272
    art_xy = (MARGIN + 24, y + 24)
    _shadow(card, (*art_xy, art_xy[0] + size, art_xy[1] + size), radius=22)
    _paste_art(card, cover, art_xy, size, radius=22)

    x = art_xy[0] + size + 36
    max_width = WIDTH - MARGIN - 32 - x
    _spaced(draw, (x, y + 36), "#1 TRACK", _font("bold", 22), GREEN)
    if track is None:
        draw.text((x, y + 80), "No top tracks yet", font=_font("black", 44), fill=TEXT)
        return
    title_font = _font("black", 50)
    lines = _wrap(draw, track.name, title_font, max_width, max_lines=2)
    ty = y + 72
    for line in lines:
        draw.text((x, ty), line, font=title_font, fill=TEXT)
        ty += 60
    draw.text(
        (x, ty + 6),
        _fit(draw, track.artist_line, _font("semibold", 30), max_width),
        font=_font("semibold", 30),
        fill=MUTED,
    )
    album = " · ".join(part for part in (track.album, track.year) if part)
    if album:
        draw.text(
            (x, ty + 48),
            _fit(draw, album, _font("regular", 24), max_width),
            font=_font("regular", 24),
            fill=DIM,
        )
    if listening_label:
        font = _font("bold", 26)
        width = int(draw.textlength(listening_label, font=font))
        py = y + height - 24 - 52
        pill = Image.new("RGBA", (width + 44, 52), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, 51), radius=26, fill=(*GREEN, 48))
        card.paste(pill, (x, py), pill)
        draw.text((x + 22, py + 26), listening_label, font=font, fill=GREEN, anchor="lm")


def _ranked_rows(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    heading: str,
    rows: Sequence[tuple[int, str, str, Image.Image | None]],
    round_art: bool,
) -> None:
    _spaced(draw, (x, y), heading, _font("bold", 22), MUTED)
    y += 48
    if not rows:
        draw.text((x, y + 8), "Nothing here yet", font=_font("regular", 26), fill=DIM)
        return
    art = 72
    title_font, sub_font, rank_font = _font("semibold", 28), _font("regular", 22), _font("bold", 28)
    for rank, title, subtitle, image in rows:
        draw.text((x + 16, y + art // 2), str(rank), font=rank_font, fill=DIM, anchor="mm")
        _paste_art(card, image, (x + 44, y), art, radius=None if round_art else 12)
        tx = x + 44 + art + 18
        text_width = width - (tx - x)
        if subtitle:
            draw.text((tx, y + 6), _fit(draw, title, title_font, text_width), font=title_font, fill=TEXT)
            draw.text((tx, y + 42), _fit(draw, subtitle, sub_font, text_width), font=sub_font, fill=MUTED)
        else:
            draw.text(
                (tx, y + art // 2),
                _fit(draw, title, title_font, text_width),
                font=title_font,
                fill=TEXT,
                anchor="lm",
            )
        y += art + 12


def _genre_pills(draw: ImageDraw.ImageDraw, genres: Sequence[GenreCount], y: int) -> None:
    font = _font("semibold", 24)
    x = MARGIN
    for i, genre in enumerate(genres[:6]):
        label = genre.genre.title()
        width = int(draw.textlength(label, font=font)) + 40
        if x + width > WIDTH - MARGIN:
            break
        box = (x, y, x + width, y + 48)
        if i == 0:
            draw.rounded_rectangle(box, radius=24, fill=GREEN)
            draw.text((x + width / 2, y + 24), label, font=font, fill=BG, anchor="mm")
        else:
            draw.rounded_rectangle(box, radius=24, outline=(90, 90, 90), width=2)
            draw.text((x + width / 2, y + 24), label, font=font, fill=TEXT, anchor="mm")
        x += width + 12


def render_recap(
    tracks: Sequence[Track],
    artists: Sequence[Artist],
    genres: Sequence[GenreCount],
    period_label: str,
    listening_label: str | None,
    out_dir: Path,
    now: datetime | None = None,
    images: ImageLoader | None = None,
    user_name: str | None = None,
) -> Path:
    """Draw the recap card and save it as PNG. `images` downloads a cover from its URL (optional)."""
    now = now or datetime.now()
    hero_track = tracks[0] if tracks else None
    hero_cover = _load(images, hero_track.image_url) if hero_track else None
    accent = accent_color(hero_cover)

    card = _background(accent, hero_cover)
    draw = ImageDraw.Draw(card)

    _header(card, draw, period_label)

    draw.text((MARGIN, 168), "My Spotify Recap", font=_font("black", 78), fill=TEXT)
    subtitle = f"{now:%B} {now.day}, {now.year}"
    if user_name:
        subtitle = f"{user_name}  ·  {subtitle}"
    draw.text(
        (MARGIN, 268),
        _fit(draw, subtitle, _font("regular", 28), WIDTH - 2 * MARGIN),
        font=_font("regular", 28),
        fill=MUTED,
    )

    _hero(card, draw, hero_track, hero_cover, listening_label, y=336)

    column = (WIDTH - 2 * MARGIN - 48) // 2
    list_y = 700
    track_rows = [
        (rank, t.name, t.artist_line, _load(images, t.image_url))
        for rank, t in enumerate(tracks[1:6], start=2)
    ]
    artist_rows = [
        (rank, a.name, ", ".join((a.genres or ())[:2]).title(), _load(images, a.image_url))
        for rank, a in enumerate(artists[:5], start=1)
    ]
    _ranked_rows(card, draw, MARGIN, list_y, column, "TOP TRACKS", track_rows, round_art=False)
    _ranked_rows(card, draw, MARGIN + column + 48, list_y, column, "TOP ARTISTS", artist_rows, round_art=True)

    if genres:
        _genre_pills(draw, genres, y=1188)

    footer_font = _font("regular", 22)
    draw.line((MARGIN, 1262, WIDTH - MARGIN, 1262), fill=(50, 50, 50), width=2)
    draw.text((MARGIN, 1296), "made with spotipulse", font=footer_font, fill=DIM, anchor="lm")
    draw.text(
        (WIDTH - MARGIN, 1296), "your Spotify stats, in the terminal", font=footer_font, fill=DIM, anchor="rm"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"spotipulse-recap-{now:%Y%m%d-%H%M%S}.png"
    card.save(path, optimize=True)
    return path
