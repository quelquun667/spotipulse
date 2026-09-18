# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-18

### Added

- `spotipulse` command with automatic Spotify login: browser OAuth flow, silent token refresh, a clear
  message when the 6-month refresh token expires, and `--logout`
- First-run prompt for Client ID/Secret, saved to `~/.config/spotipulse/config.toml`
- Startup splash with the logo in block art
- Now Playing tab with cover art, live progress bar, release year, playback context ("From playlist …"),
  device, volume, shuffle/repeat state, the next 5 queued tracks, and podcast episode support
- Top tab: top 50 tracks & artists for 4 Weeks / 6 Months / 1 Year with a rank trend vs the next longer
  period, live filter, cover/avatar preview and estimated listening time
- Genres tab: bar chart of top genres from your top 50 artists
- History tab: local SQLite listening log, 30-day graph, current/longest streak, 7- and 30-day comparisons
- Recently Played tab: last 50 tracks with timestamps and cover art
- Profile tab: avatar, liked songs / saved albums / playlists / followed artists counts, favorites of the
  last 4 weeks and last year, playlist list
- Tabs switch with `1`–`6`, or the unshifted AZERTY top row
- `Ctrl+L` redraws the screen, and screens repaint fully when an overlay closes
- Asks to log in again when a new version needs extra Spotify permissions
- PNG recap card export (`e`): cover art, top 5 tracks and artists with artwork, genre pills and a
  background tinted by the #1 cover
- Compact view (`c`, or `spotipulse --mini`) and a keyboard shortcuts overlay (`?`)
- Responsive layout for narrow and short terminal windows
- `covers` setting ("auto" by default, or "blocks" / "unicode" / "off") choosing how album art is drawn
- On-disk cache of tops, profile, recently played and covers for an instant start
- Recap cards in three formats (`recap_format`: feed 4:5, story 9:16, square 1:1), with your name and profile
  picture; `Shift+E` picks the format for one export
- Decorative equalizer next to "Now playing" (`animations`), and short fades when views appear
- Light theme (`theme = "light"`, or `t` to switch)
- `accent_from_cover`: tint the Now Playing tab with the current cover's color
- Every setting is validated at startup, with a message naming the wrong line
- Logo assets: SVG, PNG, block-art splash and GitHub social preview

[0.1.0]: https://github.com/quelquun667/spotipulse/releases/tag/v0.1.0
