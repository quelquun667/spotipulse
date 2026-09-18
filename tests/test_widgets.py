from spotipulse.widgets import column_widths
from spotipulse.widgets.help import SECTIONS, help_table

SPEC = [("rank", "#", 3, 0), ("title", "Title", 12, 3), ("artist", "Artist", 10, 1), ("length", "Len", 6, 0)]


def test_fixed_columns_keep_their_width_and_the_rest_is_shared():
    widths = {key: width for key, _, width in column_widths(80, SPEC)}
    assert widths["rank"] == 3 and widths["length"] == 6
    # 80 - padding (2 per column + 1) - minimums (31) = 40 extra, split 3:1
    assert widths["title"] == 12 + 30
    assert widths["artist"] == 10 + 10


def test_columns_never_shrink_below_their_minimum():
    widths = {key: width for key, _, width in column_widths(20, SPEC)}
    assert widths == {"rank": 3, "title": 12, "artist": 10, "length": 6}


def test_help_lists_every_tab_key():
    keys = [key for _, rows in SECTIONS for key, _ in rows]
    for expected in ("1 / &", "6 / -", "c", "? / ,", "q"):
        assert expected in keys
    assert help_table().row_count > len(keys)


def test_cover_art_follows_the_configured_mode():
    from spotipulse.widgets import NoCover, cover_art, set_cover_mode

    try:
        set_cover_mode("blocks")
        assert type(cover_art()).__name__ == "HalfcellImage"
        set_cover_mode("unicode")
        assert type(cover_art()).__name__ == "UnicodeImage"
        set_cover_mode("off")
        widget = cover_art(id="x")
        assert isinstance(widget, NoCover)
        widget.image = "ignored"  # setting a cover on it is a no-op
        assert widget.image is None
        set_cover_mode("auto")
        auto_widget = type(cover_art())
        set_cover_mode("nonsense")  # unknown values fall back to the default mode
        assert type(cover_art()) is auto_widget
    finally:
        set_cover_mode("auto")


def test_equalizer_steps_stay_in_range():
    import random

    from spotipulse.widgets.equalizer import LEVELS, TOP, next_levels, render_bars

    rng = random.Random(1)
    levels = [2] * 6
    seen = set()
    for _ in range(200):
        levels = next_levels(levels, rng)
        assert len(levels) == 6 and all(1 <= level <= TOP for level in levels)
        seen.update(levels)
    assert len(seen) > 4  # it actually moves
    assert render_bars([1, TOP], None).plain == LEVELS[1] + LEVELS[TOP]


def test_progress_bar_splits_played_and_remaining():
    from spotipulse.widgets.now_playing import progress_bar

    bar = progress_bar(30_000, 120_000, 20, "#FF0000")
    assert bar.plain == "━" * 20
    assert bar.spans[0].end == 5  # a quarter played
    assert progress_bar(0, 0, 10, "#FF0000").plain == "━" * 10
