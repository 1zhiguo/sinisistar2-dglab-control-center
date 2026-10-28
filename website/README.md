# SiNiSistar2 × DG-LAB website

Buildless product page matching the Manaka / Ricca site structure. Actual native
application screenshots, offline with no connected devices. Chinese, English and
Japanese copy; responsive layout and keyboard-accessible image viewer.

`dist/` contains deployable static files. `tools/build_product_site.py` builds HTML,
translations and optimized screenshots from `artifacts/website-capture/`. Capture
with the application's `--offline --screenshot` option and an isolated settings file.

Preview: `python -m http.server 4328 --bind 127.0.0.1 --directory website/dist`.
Hosting site: `sinisistar2-dglab`; deployment is Hosting only. Source downloads are
clearly labeled as source ZIPs, not prebuilt Windows executables.

Live: https://sinisistar2-dglab.web.app/ (Firebase project `guoguo-game-hub`).
Source: https://github.com/1zhiguo/sinisistar2-dglab-control-center.
The active sanitized Git checkout is `public_repo/sinisistar2-source/` in the
development workspace. It excludes runtime binaries and extracted game artwork.

Windows 1.0.1 downloads use Tencent COS, Baidu Netdisk and GitHub Releases.
`website/downloads.json` is the version, URL and checksum source of truth.
The source ZIP is separately labeled for developers; Windows users do not need Python.

The actual four-channel HUD animation appears above the overview screenshot.
Rebuild it on Windows with `python tools/build_hud_demo.py` before building the site.
This display-only QML fixture creates no game reader or device connection.
The GIF is an eight-second loop with a pause control and a reduced-motion poster.

The Gameplay screenshots section precedes Application interface and displays
user-provided game1.png, game2.png and game3.png in order. The site builder
converts them to full-resolution WebP assets; the source PNGs remain unchanged.
