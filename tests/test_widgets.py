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
    for expected in ("1 / &", "6 / -", "c", "?", "q"):
        assert expected in keys
    assert help_table().row_count > len(keys)
