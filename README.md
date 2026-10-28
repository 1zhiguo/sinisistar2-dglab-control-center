# SiNiSistar2 × DG-LAB

Windows control center for SiNiSistar2 v1.3.1. Supports Coyote Pulse and Opossum
vibration through DG-LAB V3 / V4, independent A/B rules, waveform editing,
CG feedback queues, a game HUD and an event inspector. Chinese / English / Japanese UI.

Website: https://sinisistar2-dglab.web.app/
Game hub: https://dglab-x-game.web.app/

## Windows 1.0.2 test build

Download the portable Windows x64 ZIP from Releases (tag `v1.0.2`). Extract the
entire folder and run `SiNiSistar2-x-DGlab.exe`; no separate Python installation
is needed. The release includes plugin installation resources and uses clean
default settings. No game, publisher settings, personal saves or logs are included.
Development and batch-testing controls are hidden by default.
Observer 0.6.0 combines shared animation and declared CG playback signals with
HP/grab fallback. Gallery feedback uses independent playback and take sessions.

## Run from source

Use Windows x64 and Python 3.10 or newer. Extract the entire source ZIP, open
PowerShell in the project folder, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-native.txt
.\run_native.cmd
```

In Devices & game, select your own v1.3.1 installation, close the game and install
the observer plugin. The source repository does not redistribute runtime ZIPs,
compiled DLLs or extracted game artwork. Before using the one-click installer,
prepare the files listed in `installer_payload/manifest.json` from the stated
upstream sources, and build the observer / optional trainer from the C# sources.
The installer verifies pinned hashes and rejects missing or mismatched files.
Decorative game artwork and bundled monster previews are omitted; this does not
affect the connection, policy or waveform code. Launch the game, connect phone and
PC to the same LAN and pair with the corresponding V3 / V4 app. Configure presets
and caps in the app. `Ctrl+F12` zeros and locks both outputs; `Ctrl+F11` adjusts HUD.

The observer reads game state. The separately installed optional trainer can change
HP, MP, attack multiplier and status effects only after explicit in-app actions.
Its source is in `trainer/`; it is not part of the read-only observer.

## Source and validation

`src/` contains the Python/QML application, `observer/` and `trainer/` the C# plugin
sources, and `tests/` the automated checks. `tools/` includes local development and
capture utilities. Some integration tests require your own game and will not run
in a clean source-only checkout. Run the pure-Python suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

C# build helpers require Roslyn 4.11, .NET 6 reference assemblies, BepInEx IL2CPP
references and (for the trainer) interop assemblies generated from your own game.
See `tools/build_observer.py` and `tools/build_trainer.py` for expected local paths.
Build dependencies, game assemblies and prebuilt plugin DLLs are not committed.
Pinned installation manifests are included in `installer_payload/`.

`website/dist/` is the static product website. Screenshots show the actual app in
offline mode with devices disconnected. See `website/README.md` for preview details.

## License and assets

Project code is GPL-3.0-only. Third-party runtimes and game-derived UI artwork and
small previews retain their original rights; see `THIRD_PARTY_NOTICES.md`.
The game itself, saves, local settings, credentials and telemetry are not included.
This is an unofficial companion and is not affiliated with DG-LAB or the game maker.
