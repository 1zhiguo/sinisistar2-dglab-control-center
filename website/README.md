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
