<p align="center">
  <img src="assets/logo.png" alt="spotipulse" width="160">
</p>

<h1 align="center">spotipulse</h1>

<p align="center">A terminal dashboard for your Spotify stats — now playing, top tracks & artists, listening history.</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-1DB954?logo=python&logoColor=white">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-1DB954">
  <a href="https://github.com/quelquun667/spotipulse/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/quelquun667/spotipulse/actions/workflows/ci.yml/badge.svg"></a>
</p>

---

**spotipulse** puts your Spotify listening in a fast, keyboard-driven terminal dashboard. Spotify's API only
gives you three fixed windows (4 weeks, 6 months, 1 year), so spotipulse also keeps a **local history** of what
you play. That's what powers the day-by-day graph, listening streaks and week-over-week comparisons that
tools which only wrap the API can't show.

## Features

- **Startup splash**: the logo in green block art
- **Now Playing**: title, artist, album and release year, the real cover art in your terminal, a live
  progress bar, where it's playing from ("From playlist Chill Vibes"), the device and its volume,
  shuffle/repeat state, and the next 5 tracks in your queue (refreshes every ~3 s)
- **Top**: top 50 tracks and top 50 artists for **4 Weeks / 6 Months / 1 Year**, with a **trend** column
  (▲ climbed, ▼ dropped, NEW) comparing each period with the next longer one, cover/avatar preview,
  type-to-filter search and an estimated listening time for the period
- **Genres**: bar chart of your top genres, built from your top 50 artists
- **History**: day-by-day listening graph from the local database, current and longest streak,
  last 7/30 days compared with the 7/30 days before
- **Recently Played**: your last 50 tracks with timestamps and cover art
- **Profile**: your name and avatar, liked songs, saved albums, playlists and followed artists counts,
  your favorite track/artist/genre of the last 4 weeks and last year, and your playlists
- **Export recap**: press `e` to save a Wrapped-style PNG card of the selected period — your #1 track with
  its cover, top tracks and artists with their artwork, top genres, listening time, your name and profile
  picture, on a background tinted by your #1 cover. Three sizes: feed (4:5), story (9:16) and square;
  `Shift+E` picks one
- **Equalizer**: little bars bouncing next to "Now playing" while music plays
- **Light theme** (`t`) and an optional **cover-colored** Now Playing tab
- **Compact view**: press `c` (or start with `spotipulse --mini`) for just what's playing, readable in a tiny
  terminal window
- **Adapts to your window**: panels, covers and table columns resize or step aside as the terminal gets
  narrower or shorter; tabs that no longer fit scroll
- **Instant start**: the last tops, profile, recently played list and covers are kept on disk, shown
  immediately at launch, then refreshed in the background
- **Help**: press `?` for every keyboard shortcut
- **Settings without editing files**: press `s` in the app, or use `spotipulse config set …`
- Spotify-green theme, rounded panels, full keyboard and mouse support

## Screenshot

> _Screenshot / terminal recording coming soon._

## Requirements

- Python **3.11+**
- A Spotify account
- A Spotify Developer app (free, takes 2 minutes, see below)

## Spotify Developer app setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and click **Create app**.
2. Give it any name and description. Under **Redirect URIs**, add exactly:

   ```
   http://127.0.0.1:8888/callback
   ```

   It must match character for character: `127.0.0.1`, not `localhost`, with no trailing slash.

   Reusing an existing app that already has another redirect URI (for example port `8899`)? Either add the
   URI above to it, or set `redirect_uri` in `~/.config/spotipulse/config.toml` to the one it already has.
3. Under **Which API/SDKs are you planning to use?**, tick **Web API**, then save.
4. Open the app's **Settings** and copy the **Client ID** and **Client Secret**.
   spotipulse asks for them the first time you run it.

> **Important — Spotify's Development Mode rules (2026):**
> - the account that owns the app needs an active **Spotify Premium** subscription;
> - every account that logs in (including yours) must be added in the app's **User Management** tab
>   (name + the email of the Spotify account), up to 5 users;
> - you must be logged into that same Spotify account in your browser when you approve.

## Installation

1. Check that you have Python 3.11 or newer:

   ```bash
   python --version        # Windows: py -3.11 --version
   ```

2. Install [pipx](https://pipx.pypa.io) if you don't have it yet:

   ```bash
   python -m pip install --user pipx
   python -m pipx ensurepath
   ```

   On Windows, use `py -3.11` in place of `python` if `python --version` shows an older version.

   `ensurepath` adds pipx's command folder (`~/.local/bin`, or `C:\Users\<you>\.local\bin` on Windows) to
   your `PATH`. **Close every terminal and open a new one** so it takes effect. In VS Code, restart VS Code
   itself: its terminals keep the old `PATH` until then.
3. Clone and install spotipulse:

   ```bash
   git clone https://github.com/quelquun667/spotipulse.git
   cd spotipulse
   pipx install .
   ```

   If `pipx` isn't found yet, use `python -m pipx install .` (or `py -3.11 -m pipx install .`).
4. Run it from any directory, just by its name:

   ```bash
   spotipulse
   ```

`pipx` installs spotipulse in its own isolated environment and puts the `spotipulse` command on your `PATH`.
You don't need to activate a virtualenv, and the command works from any folder.

### Updating

`pipx install .` copies the code at the moment you run it. After pulling new changes (or editing the code),
reinstall:

```bash
cd spotipulse
git pull
pipx install . --force
```

### Uninstalling

```bash
pipx uninstall spotipulse
```

Your config, login and history in `~/.config/spotipulse/` are kept. Delete that folder too for a clean slate.

<details>
<summary>Development install</summary>

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

</details>

## First run

The first time you type `spotipulse`:

1. It tells you you're not connected and asks **Open the browser to log in now? [Y/n]**.
2. It asks for your **Client ID** and **Client Secret** (the secret is hidden as you type). They're saved to
   `~/.config/spotipulse/config.toml`.
3. Your browser opens on Spotify's consent page. Approve it, and the dashboard starts.

spotipulse asks for read-only permissions: what's playing and your playback state, your top items and
recently played tracks, and your library, playlists and followed artists (for the Profile tab). It never
changes anything in your account. After an update that needs a new permission, it asks you to log in once
more.

After that, `spotipulse` goes straight to the dashboard and refreshes your login silently in the background.
Spotify logins expire 6 months after you first approve the app. When that happens, spotipulse says so and
opens the browser again.

Everything lives in `~/.config/spotipulse/`, outside the repository:

| File           | What it is                                           |
| -------------- | ---------------------------------------------------- |
| `config.toml`  | your Client ID/Secret and settings (see [Settings](#settings)) |
| `token_cache`  | your Spotify login token                             |
| `history.db`   | your local listening history (SQLite)                |
| `cache/`       | last fetched data and covers, for an instant start (safe to delete) |

> **About local history:** spotipulse logs a track once you've listened to it for 30 seconds **while
> spotipulse is open**. Leave it running on the Now Playing tab and the History tab fills up over time.

## Usage

```
spotipulse               launch the dashboard
spotipulse --logout      forget your Spotify login
spotipulse --no-splash   skip the startup logo
spotipulse --mini        start in the compact view
spotipulse --config      open the settings file in your editor
spotipulse config        list, get, set or reset settings (see Settings)
spotipulse --version     print the version
```

### Keybindings

| Key               | Action                                               |
| ----------------- | ---------------------------------------------------- |
| `1` – `6`         | Now Playing / Top / Genres / History / Recently Played / Profile (on AZERTY, `&` `é` `"` `'` `(` `-` work too, no Shift needed) |
| `w` / `m` / `y`   | switch period: 4 Weeks / 6 Months / 1 Year           |
| `←` / `→`         | switch period (on the period tabs)                   |
| `/`               | filter top tracks & artists                          |
| `Esc`             | clear the filter                                     |
| `↑` / `↓`         | move through a table (updates the cover preview)     |
| `Tab`             | move focus between widgets                           |
| `c`               | compact view on / off                                |
| `s`               | settings: change and save them without leaving the app |
| `?` or `,`        | show all keyboard shortcuts (`,` so AZERTY needs no Shift) |
| `r`               | refresh everything                                   |
| `Ctrl+L`          | redraw the screen (clears terminal artifacts)        |
| `e`               | export a PNG recap of the selected period            |
| `E` (Shift + e)   | export, choosing the format (feed / story / square)  |
| `t`               | switch between dark and light theme                  |
| `L` (Shift + l)   | log out and quit                                     |
| `q`               | quit                                                 |

Recap cards are saved to `~/Pictures`, or to your home folder if that doesn't exist (see
[`export_dir`](#export_dir) and [`recap_format`](#recap_format)).

### Window size

spotipulse works from about 60×15 upwards. Below 140 columns the Top and Recently Played cover previews
step aside; below 100 columns the Top tables stack and the Now Playing cover hides; below 36 rows the header
and the "Up next" panel make room. For a very small window, use the compact view (`c`).

## Settings

### Three ways to change a setting

**1. In the app — press `s`.** A list of every setting with its current value:

| Key | Does |
| --- | ---- |
| `↑` `↓` | pick a setting (its description, allowed values and default show below) |
| `←` `→`, `Enter`, `Space` | change the value (for `export_dir`, `Enter` opens a box to type the folder) |
| `d` | back to the default |
| `Esc` or `s` | close |

Changes are **saved to the file immediately** and apply right away. The one exception is `covers`, which
needs a restart (the screen tells you).

**2. From the command line — `spotipulse config`.**

```bash
spotipulse config                        # list every setting: value, default, allowed values
spotipulse config set theme light        # change one
spotipulse config set animations false
spotipulse config set export_dir "~/Desktop/Spotify cards"
spotipulse config get theme              # print one value
spotipulse config reset theme            # back to the default
spotipulse config path                   # where the file is
```

Values are checked before anything is written: `spotipulse config set theme blue` answers
`theme must be one of dark, light` and leaves the file alone. For `true` / `false` settings, `on` / `off`
and `yes` / `no` work too. If spotipulse is running, restart it (or use `s`) to pick up the change.

**3. In the file — `spotipulse --config`.** Opens `config.toml` in your editor: `$VISUAL` / `$EDITOR` if
you've set one, otherwise the app your system uses for `.toml` files (Notepad as a last resort on Windows).
The file is created if it doesn't exist yet, with every setting listed, commented out, next to a short
description. Remove the `#` in front of a line to use it, save, and restart spotipulse.

The file lives at `~/.config/spotipulse/config.toml` — on Windows, `C:\Users\<you>\.config\spotipulse\config.toml`.
Settings you don't write down keep their default. A typo or an unknown value doesn't break anything
silently: spotipulse refuses to start and names the wrong line, and `spotipulse config reset <name>` puts
it back.

> **TOML in 20 seconds:** text goes between quotes (`theme = "light"`), numbers and `true` / `false` go
> without (`animations = false`). Lines starting with `#` are comments. `spotipulse config set` and the
> `s` screen write the right syntax for you.

### All settings at a glance

| Setting | Default | Values | What it changes |
| ------- | ------- | ------ | --------------- |
| [`theme`](#theme) | `"dark"` | `"dark"`, `"light"` | colors of the whole dashboard |
| [`covers`](#covers) | `"auto"` | `"auto"`, `"blocks"`, `"unicode"`, `"off"` | how album art is drawn |
| [`accent_from_cover`](#accent_from_cover) | `false` | `true`, `false` | tint Now Playing with the cover's color |
| [`animations`](#animations) | `true` | `true`, `false` | equalizer bars and fades |
| [`recap_format`](#recap_format) | `"feed"` | `"feed"`, `"story"`, `"square"` | size of the card `e` exports |
| [`export_dir`](#export_dir) | `~/Pictures` | any folder | where recap cards are saved |
| [`refresh_interval`](#refresh_interval) | `3` | a number of seconds, 1 or more | how often Now Playing updates |

The same file with every setting written out at its default:

```toml
[app]
theme = "dark"
covers = "auto"
accent_from_cover = false
animations = true
recap_format = "feed"
export_dir = "~/Pictures"
refresh_interval = 3
```

[`config.example.toml`](config.example.toml) has the same file with a comment on every line.

### `theme`

`"dark"` (default) or `"light"`. The light theme uses a darker green so text stays readable on white.

**`t`** switches for the current session only, without touching the file. To keep a theme, set it with
`s` or `spotipulse config set theme light`.

```toml
theme = "light"
```

### `covers`

How album art, artist pictures and your avatar are drawn in the terminal.

| Value | What you get | When to use it |
| ----- | ------------ | -------------- |
| `"auto"` **(default)** | Real images through your terminal's graphics protocol (Sixel, or Kitty's). The sharpest result. | Windows Terminal, Kitty, WezTerm, foot, iTerm2. |
| `"blocks"` | Cover art drawn with colored half-block characters. Plain text, so it can never leave anything behind on screen. | If `"auto"` leaves leftovers on screen or flickers. |
| `"unicode"` | A coarser text-only rendering (one block per cell instead of two). | Terminals that mangle half-blocks, or if you prefer a chunkier look. |
| `"off"` | No artwork at all, just text. | Slow connections, or if you simply don't want images. |

```toml
covers = "blocks"
```

> **If images misbehave:** some terminals (Windows Terminal among them) leave leftover pixels of a cover on
> screen after switching tabs, and flicker while you select text with the mouse. That's the terminal's
> graphics protocol, not spotipulse. Press `Ctrl+L` to redraw; if it keeps happening, switch to `"blocks"`.

Recap cards always use the real cover images, whatever this setting is: it only affects the terminal.

### `accent_from_cover`

`false` (default) or `true`. When on, the Now Playing tab takes the main color of the current cover: the
panel borders, the "Now playing" label, the artist name, the progress bar and the equalizer. It changes
with every track, with a short fade. The rest of the app keeps its green.

If a cover is mostly black, white or grey, there's no color to pick and the tab stays green.

```toml
accent_from_cover = true
```

### `animations`

`true` (default) or `false`. Covers everything that moves:

- the **equalizer** next to "Now playing" — small bars bouncing while music plays, still when paused.
  They're decorative: Spotify doesn't share audio data any more, so they don't follow the beat;
- the short **fade** when you switch tabs or open the help, the compact view or the export menu;
- the **color fade** of `accent_from_cover`.

Turn it off if you prefer a still screen, or if your terminal flickers.

```toml
animations = false
```

### `recap_format`

The size of the card that **`e`** exports. **`Shift+E`** always lets you pick another one for a single
export.

| Value | Size | Made for | Layout |
| ----- | ---- | -------- | ------ |
| `"feed"` **(default)** | 1080×1350 (4:5) | Instagram / Discord post | #1 track, top 5 tracks and top 5 artists side by side, genres |
| `"story"` | 1080×1920 (9:16) | Instagram / Snapchat story, phone wallpaper | bigger #1, tracks as a list, artists as a row of round pictures |
| `"square"` | 1080×1080 (1:1) | square post, thumbnail | compact: top 4 tracks and artists, genres |

Every card shows your Spotify name and profile picture next to the date (when you have one).

```toml
recap_format = "story"
```

### `export_dir`

Where recap cards are saved. Defaults to your `Pictures` folder, or your home folder if there isn't one.
`~` means your home folder.

```toml
export_dir = "~/Desktop"
```

Files are named `spotipulse-recap-<date>-<time>.png`, with `-story` or `-square` added for those formats.

### `refresh_interval`

Seconds between two checks of what's playing: `3` by default, `1` at least. The progress bar keeps moving
smoothly in between either way. Raise it if you want spotipulse to make fewer requests to Spotify.

```toml
refresh_interval = 5
```

### The `[spotify]` section

It holds your `client_id`, `client_secret` and `redirect_uri`. spotipulse writes it on first run; you only
touch it to use another Spotify app or another redirect URI (see
[Spotify Developer app setup](#spotify-developer-app-setup)). Keep this file private: it contains your app
secret.

## Troubleshooting

| Problem | Fix |
| ------- | --- |
| **Config problem: … must be one of …** at startup | A setting has a value spotipulse doesn't know. Fix it with `spotipulse --config`, or reset it with `spotipulse config reset <name>`. |
| `spotipulse: command not found` / `not recognized` | Open a **new** terminal (restart VS Code if you use its terminal). Still missing? Run `python -m pipx ensurepath` and check that `~/.local/bin` is on your `PATH`. |
| Spotify shows **INVALID_CLIENT: Invalid redirect URI** | The redirect URI in your Spotify app must be exactly `http://127.0.0.1:8888/callback`. Save it in the dashboard, then run `spotipulse` again. |
| **Login failed** / wrong Client ID or Secret | Delete `~/.config/spotipulse/config.toml` and run `spotipulse`: it asks for them again. |
| **Couldn't start the local login server** | Something else uses port 8888. Close it and try again. |
| **Login failed: … server_error** or **access_denied** | Development Mode refused the account: check it has **Premium**, is listed under **User Management** with the right email, and is the account logged in on open.spotify.com. Then run `spotipulse` again. |
| **Spotify refused the request** (403) | Same cause: add your account's email under **User Management** in the Spotify dashboard. |
| The browser never opens | Copy the address printed in the terminal into your browser. |
| History tab is empty | Normal at first: plays are logged while spotipulse is open, after 30 s of each track. |
| Leftover bits of image on screen, or flicker when selecting text | Your terminal's image protocol is misbehaving. Press `Ctrl+L` to redraw; if it keeps happening, set `covers = "blocks"` (or `"off"`) in `config.toml`. |
| Covers look blocky | You're on `covers = "blocks"`. Set `covers = "auto"` in `config.toml` for real images. |

## Roadmap

- Terminal recording in this README
- Optional PyPI release (`pipx install spotipulse`)

> Spotify removed audio features (danceability, energy, tempo…) and recommendations for apps created after
> November 2024, so spotipulse can't show those.

## License

[MIT](LICENSE)

## Acknowledgments

- [Textual](https://github.com/Textualize/textual): the TUI framework
- [Spotipy](https://github.com/spotipy-dev/spotipy): the Spotify Web API client
- [textual-image](https://github.com/lnqs/textual-image): images in the terminal
- [Pillow](https://python-pillow.org): recap card rendering
