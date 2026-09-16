# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- `spotipulse` command with automatic Spotify login: browser OAuth flow, silent token refresh, a clear
  message when the 6-month refresh token expires, and `--logout`
- First-run prompt for Client ID/Secret, saved to `~/.config/spotipulse/config.toml`
- Startup splash with the logo in block art
- Now Playing tab with cover art, live progress bar and podcast episode support
- Top tab: top 20 tracks & artists for 4 Weeks / 6 Months / 1 Year, live filter, cover/avatar preview and
  estimated listening time
- Genres tab: bar chart of top genres from your top 50 artists
- History tab: local SQLite listening log, 30-day graph, current/longest streak, 7- and 30-day comparisons
- Recently Played tab: last 50 tracks with timestamps and cover art
- PNG recap card export (`e`)
- Logo assets: SVG, PNG, block-art splash and GitHub social preview
