from spotipulse.genres import fill_missing_genres, top_genres

from conftest import make_artist


def test_counts_and_ranking():
    artists = [
        make_artist(0, ("french rap", "rap")),
        make_artist(1, ("indie pop",)),
        make_artist(2, ("rap", "trap")),
        make_artist(3, ("indie pop", "bedroom pop")),
    ]
    result = top_genres(artists)
    assert [(g.genre, g.count) for g in result[:2]] == [("rap", 2), ("indie pop", 2)]
    # rap wins the tie: its artists rank higher (#1 and #3 vs #2 and #4)
    assert result[0].score > result[1].score


def test_genres_are_normalised_and_not_double_counted():
    artists = [make_artist(0, ("Pop", "pop ", "")), make_artist(1, ())]
    result = top_genres(artists)
    assert [(g.genre, g.count) for g in result] == [("pop", 1)]


def test_limit():
    artists = [make_artist(i, (f"genre {i}",)) for i in range(30)]
    assert len(top_genres(artists, limit=5)) == 5


def test_fill_missing_genres_only_fetches_unknown():
    calls = []

    def fetch(artist_id):
        calls.append(artist_id)
        return make_artist(9, ("jazz",))

    artists = [make_artist(0, ("pop",)), make_artist(1, None), make_artist(2, ())]
    filled = fill_missing_genres(artists, fetch)
    assert calls == ["artist1"]
    assert [a.genres for a in filled] == [("pop",), ("jazz",), ()]


def test_fill_missing_genres_survives_errors():
    def fetch(artist_id):
        raise RuntimeError("offline")

    assert fill_missing_genres([make_artist(0, None)], fetch)[0].genres == ()
