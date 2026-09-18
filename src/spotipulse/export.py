"""Renders the shareable PNG recap card (Pillow)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import asset_path
from .api import Artist, Track
from .genres import GenreCount
from .palette import accent_color

WIDTH, HEIGHT = 1080, 1350  # the default "feed" format (4:5)
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


def _background(size: tuple[int, int], accent: tuple[int, int, int], hero: Image.Image | None) -> Image.Image:
    width, height = size
    base = Image.new("RGB", size, BG)
    if hero is not None:
        blurred = ImageOps.fit(hero.convert("RGB"), size, Image.LANCZOS)
        blurred = blurred.filter(ImageFilter.GaussianBlur(70))
        base = Image.blend(base, blurred, 0.28)
    # soft glow of the accent color from the top-left corner
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse((-420, -520, 900, 640), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    base = Image.composite(Image.new("RGB", size, accent), base, glow)
    # fade to near-black towards the bottom so the lists stay readable
    fade = Image.linear_gradient("L").resize(size).point(lambda v: int(v * 0.8))
    return Image.composite(Image.new("RGB", size, BG), base, fade)


def _load(images: ImageLoader | None, url: str | None) -> Image.Image | None:
    if images is None or not url:
        return None
    try:
        return images(url)
    except Exception:
        return None


# ---------- layouts ----------


@dataclass(frozen=True)
class Layout:
    """Where everything goes on one card size. All values are pixels."""

    width: int
    height: int
    title_y: int
    title_size: int
    subtitle_y: int
    hero_y: int
    hero_height: int
    hero_art: int
    hero_title_size: int
    lists_y: int
    row_art: int
    track_rows: int  # tracks listed under the #1 (so #2 .. #track_rows+1)
    artists_as_row: bool  # story: a row of big round avatars instead of a second column
    genres_y: int
    footer_y: int


LAYOUTS: dict[str, Layout] = {
    # 4:5 — Instagram / Discord post
    "feed": Layout(1080, 1350, 168, 78, 282, 336, 320, 272, 50, 700, 72, 5, False, 1188, 1262),
    # 9:16 — Instagram / Snapchat story, phone wallpaper
    "story": Layout(1080, 1920, 210, 86, 332, 400, 420, 372, 58, 870, 84, 5, True, 1748, 1830),
    # 1:1 — square post, thumbnail
    "square": Layout(1080, 1080, 150, 64, 244, 296, 248, 200, 42, 578, 56, 4, False, 914, 994),
}
FORMATS = tuple(LAYOUTS)


# ---------- card ----------


def _header(card: Image.Image, draw: ImageDraw.ImageDraw, period_label: str, width: int) -> None:
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
    label_width = _spaced_width(draw, label, font)
    x1 = width - MARGIN
    x0 = x1 - label_width - 48
    draw.rounded_rectangle((x0, MARGIN + 4, x1, MARGIN + 52), radius=24, fill=GREEN)
    _spaced(draw, (x0 + 24, MARGIN + 14), label, font, BG)


def _title(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    user_name: str | None,
    avatar: Image.Image | None,
    now: datetime,
) -> None:
    draw.text((MARGIN, layout.title_y), "My Spotify Recap", font=_font("black", layout.title_size), fill=TEXT)
    font = _font("regular", 28)
    x, y = MARGIN, layout.subtitle_y
    if avatar is not None:
        size = 48
        _paste_art(card, avatar, (x, y - 6), size, radius=None)
        x += size + 16
    subtitle = f"{now:%B} {now.day}, {now.year}"
    if user_name:
        subtitle = f"{user_name}  ·  {subtitle}"
    draw.text(
        (x, y + 18), _fit(draw, subtitle, font, layout.width - MARGIN - x), font=font, fill=MUTED, anchor="lm"
    )


def _hero(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    track: Track | None,
    cover: Image.Image | None,
    listening_label: str | None,
) -> None:
    y, height, size = layout.hero_y, layout.hero_height, layout.hero_art
    pad = (height - size) // 2
    panel = Image.new("RGBA", (layout.width - 2 * MARGIN, height), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        (0, 0, panel.width - 1, height - 1), radius=36, fill=(255, 255, 255, 20)
    )
    card.paste(panel, (MARGIN, y), panel)

    art_xy = (MARGIN + pad, y + pad)
    _shadow(card, (*art_xy, art_xy[0] + size, art_xy[1] + size), radius=22)
    _paste_art(card, cover, art_xy, size, radius=22)

    x = art_xy[0] + size + 36
    max_width = layout.width - MARGIN - 32 - x
    label_y = y + pad + 12
    _spaced(draw, (x, label_y), "#1 TRACK", _font("bold", 22), GREEN)
    if track is None:
        draw.text((x, label_y + 44), "No top tracks yet", font=_font("black", 40), fill=TEXT)
        return
    title_size = layout.hero_title_size
    title_font = _font("black", title_size)
    ty = label_y + 36
    for line in _wrap(draw, track.name, title_font, max_width, max_lines=2):
        draw.text((x, ty), line, font=title_font, fill=TEXT)
        ty += int(title_size * 1.2)
    artist_font = _font("semibold", max(24, title_size * 3 // 5))
    draw.text(
        (x, ty + 6), _fit(draw, track.artist_line, artist_font, max_width), font=artist_font, fill=MUTED
    )
    album = " · ".join(part for part in (track.album, track.year) if part)
    album_y = ty + 6 + artist_font.size + 12
    pill_y = y + height - pad - 52
    # small cards: the listening-time pill wins over the album line when they'd overlap
    if album and not (listening_label and album_y + 30 > pill_y):
        album_font = _font("regular", 24)
        draw.text((x, album_y), _fit(draw, album, album_font, max_width), font=album_font, fill=DIM)
    if listening_label:
        font = _font("bold", 26)
        width = int(draw.textlength(listening_label, font=font))
        py = pill_y
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
    art: int,
) -> int:
    """A heading then numbered rows with artwork. Returns the y below the last row."""
    _spaced(draw, (x, y), heading, _font("bold", 22), MUTED)
    y += 48
    if not rows:
        draw.text((x, y + 8), "Nothing here yet", font=_font("regular", 26), fill=DIM)
        return y + 48
    big = art >= 72
    title_font = _font("semibold", 30 if art >= 84 else 28 if big else 24)
    sub_font = _font("regular", 22 if big else 19)
    rank_font = _font("bold", 28 if big else 24)
    gap = 16 if art >= 84 else 12
    for rank, title, subtitle, image in rows:
        draw.text((x + 16, y + art // 2), str(rank), font=rank_font, fill=DIM, anchor="mm")
        _paste_art(card, image, (x + 44, y), art, radius=None if round_art else max(8, art // 6))
        tx = x + 44 + art + 18
        text_width = width - (tx - x)
        if subtitle:
            middle = y + art // 2
            draw.text(
                (tx, middle - 2),
                _fit(draw, title, title_font, text_width),
                font=title_font,
                fill=TEXT,
                anchor="ls",
            )
            draw.text(
                (tx, middle + 6),
                _fit(draw, subtitle, sub_font, text_width),
                font=sub_font,
                fill=MUTED,
                anchor="lt",
            )
        else:
            draw.text(
                (tx, y + art // 2),
                _fit(draw, title, title_font, text_width),
                font=title_font,
                fill=TEXT,
                anchor="lm",
            )
        y += art + gap
    return y


def _artist_row(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    y: int,
    rows: Sequence[tuple[int, str, str, Image.Image | None]],
) -> None:
    """Story format: the top artists as a row of big round avatars with their names underneath."""
    _spaced(draw, (MARGIN, y), "TOP ARTISTS", _font("bold", 22), MUTED)
    y += 56
    if not rows:
        draw.text((MARGIN, y + 8), "Nothing here yet", font=_font("regular", 26), fill=DIM)
        return
    size = 152
    span = layout.width - 2 * MARGIN
    step = (span - size) / max(1, len(rows) - 1) if len(rows) > 1 else 0
    name_font, rank_font = _font("semibold", 24), _font("bold", 20)
    for i, (rank, name, _, image) in enumerate(rows):
        x = int(MARGIN + i * step)
        _paste_art(card, image, (x, y), size, radius=None)
        badge = 40
        draw.ellipse((x + size - badge, y, x + size, y + badge), fill=GREEN)
        draw.text((x + size - badge / 2, y + badge / 2), str(rank), font=rank_font, fill=BG, anchor="mm")
        cx = x + size / 2
        draw.text(
            (cx, y + size + 30),
            _fit(draw, name, name_font, int(min(step, size + 40)) - 8),
            font=name_font,
            fill=TEXT,
            anchor="mm",
        )


def _genre_pills(draw: ImageDraw.ImageDraw, genres: Sequence[GenreCount], y: int, width: int) -> None:
    font = _font("semibold", 24)
    x = MARGIN
    for i, genre in enumerate(genres[:6]):
        label = genre.genre.title()
        pill = int(draw.textlength(label, font=font)) + 40
        if x + pill > width - MARGIN:
            break
        box = (x, y, x + pill, y + 48)
        if i == 0:
            draw.rounded_rectangle(box, radius=24, fill=GREEN)
            draw.text((x + pill / 2, y + 24), label, font=font, fill=BG, anchor="mm")
        else:
            draw.rounded_rectangle(box, radius=24, outline=(90, 90, 90), width=2)
            draw.text((x + pill / 2, y + 24), label, font=font, fill=TEXT, anchor="mm")
        x += pill + 12


def _footer(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    font = _font("regular", 22)
    y = layout.footer_y
    draw.line((MARGIN, y, layout.width - MARGIN, y), fill=(50, 50, 50), width=2)
    draw.text((MARGIN, y + 34), "made with spotipulse", font=font, fill=DIM, anchor="lm")
    draw.text(
        (layout.width - MARGIN, y + 34),
        "your Spotify stats, in the terminal",
        font=font,
        fill=DIM,
        anchor="rm",
    )


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
    avatar_url: str | None = None,
    fmt: str = "feed",
) -> Path:
    """Draw the recap card and save it as PNG.

    `images` downloads a cover from its URL (optional); `fmt` is one of FORMATS.
    """
    layout = LAYOUTS.get(fmt, LAYOUTS["feed"])
    now = now or datetime.now()
    hero_track = tracks[0] if tracks else None
    hero_cover = _load(images, hero_track.image_url) if hero_track else None
    size = (layout.width, layout.height)

    card = _background(size, accent_color(hero_cover), hero_cover)
    draw = ImageDraw.Draw(card)

    _header(card, draw, period_label, layout.width)
    _title(card, draw, layout, user_name, _load(images, avatar_url), now)
    _hero(card, draw, layout, hero_track, hero_cover, listening_label)

    track_rows = [
        (rank, t.name, t.artist_line, _load(images, t.image_url))
        for rank, t in enumerate(tracks[1 : 1 + layout.track_rows], start=2)
    ]
    artist_count = 5 if layout.artists_as_row else layout.track_rows
    artist_rows = [
        (rank, a.name, ", ".join((a.genres or ())[:2]).title(), _load(images, a.image_url))
        for rank, a in enumerate(artists[:artist_count], start=1)
    ]
    if layout.artists_as_row:
        bottom = _ranked_rows(
            card,
            draw,
            MARGIN,
            layout.lists_y,
            layout.width - 2 * MARGIN,
            "TOP TRACKS",
            track_rows,
            round_art=False,
            art=layout.row_art,
        )
        _artist_row(card, draw, layout, bottom + 24, artist_rows)
    else:
        column = (layout.width - 2 * MARGIN - 48) // 2
        _ranked_rows(
            card,
            draw,
            MARGIN,
            layout.lists_y,
            column,
            "TOP TRACKS",
            track_rows,
            round_art=False,
            art=layout.row_art,
        )
        _ranked_rows(
            card,
            draw,
            MARGIN + column + 48,
            layout.lists_y,
            column,
            "TOP ARTISTS",
            artist_rows,
            round_art=True,
            art=layout.row_art,
        )

    if genres:
        _genre_pills(draw, genres, layout.genres_y, layout.width)
    _footer(draw, layout)

    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if fmt == "feed" else f"-{fmt}"
    path = out_dir / f"spotipulse-recap-{now:%Y%m%d-%H%M%S}{suffix}.png"
    card.save(path, optimize=True)
    return path
