# Reused local reference code and waveforms

The read-only Win32/DPI primitives, connection transport and waveform design
references are from the user-provided Ricca and Stellar Blade projects under
GPL-3.0. They are copied into this independent project; no runtime import of
those projects is required.

`src/sinisistar_dglab/assets/ricca-pulse-presets.json` copies seven official
Coyote V3 presets plus Ricca's `death_penalty` and `death_ramp` from the local
Ricca project's `src/ricca_dglab/waveforms.py`. Original frame bytes are retained.
Ricca identifies the official preset source as DG-LAB dglab-kit:
https://github.com/dungeonlab-open/dglab-kit/tree/main/src/waveform

The death presets and their Chinese labels are Ricca's own designs, not an
official DG-LAB punishment recommendation. Preserve upstream authors' rights
and GPL-3.0 licensing; see LICENSE. Pattern frequency bytes and amplitude bytes
are sampled separately; the application's channel caps still bound strength.

`_v4_base.py`, `_v4_protocol.py`, and `_v4_hub.py` adapt the user-provided
Ricca GPL-3.0 V4 connection implementation. New latest-frame workers are in
`v4.py`; they share transport and discovery while retaining separate Pulse and
OVC selection, authorization, caps and cleanup. Protocol reference:
https://github.com/dungeonlab-open/dglab-kit/blob/main/README.md

`assets/ovc-presets.json` retains the five OVC amplitude sequences and native
frequency bytes from dglab-kit `src/waveform/ovc.ts`, as represented in the local
Ricca source. These are vibration patterns and use independent OVC units.

`installer_payload/` contains the BepInEx 6.0.0-be.754 IL2CPP/.NET 6 runtime
subset from the verified HeatSeekar v0.9.0 archive (SHA-256 recorded in the
payload manifest). Only runtime files are included; no HeatSeekar functional
plugin or patcher is installed. BepInEx and .NET components retain their own
licenses/notices in the runtime files. The Unity reference-library cache is
the previously verified local Unity 2022.3.62 reference package; it is used for
interop generation, not a redistributed game assembly. The observer DLL is
this project's GPL-3.0 source build. Payload hashes/provenance are pinned by
`install_manager.py` and `installer_payload/manifest.json`.

The four connection-guide images in `assets/connection-guide/` are copied from
the user-provided Manaka control center reference. The reference project notice
is preserved beside them as `REFERENCE-LICENSE.md`; these reference images are
separate from this project's GPL source code and retain their original rights.
No Manaka application source code is imported by this UI redesign.

The development-only `tools/build_monster_catalog.py` uses UnityPy 1.25.4
(MIT, https://github.com/K0lb3/UnityPy) to inspect the user's local game and
generate build-bound byte-location and sprite-geometry profiles. UnityPy's
UnityFS and Sprite reader implementations were also used as format references.
UnityPy and its research dependencies are not required or shipped at runtime.
The dedicated runtime reader uses standard Python, existing Pillow, and Windows
.NET Framework. The profiles contain locations, geometry and checksums, not
game image pixels. At the user's request `assets/monster-previews/` now also
contains small previews copied from the supplied local game, with identical
PNG files deduplicated. These graphics retain their original rights and are
separate from this project's GPL source. Original full-resolution game assets,
game bundles are not included. Local preview updates remain optional.

`assets/optional-saves/full-cg.zip` is the 1.3.1 completion save supplied by the
user as `sinisistar2_save_by_Alicelel.zip`, attributed to Alicelel. It contains
only System, SystemSpare and File01, and is separate from the GPL source code.
It is an optional data payload, never imported during startup or plugin
installation. Import backs up the player's files, keeps existing preferences,
merges system flags and places the completion save in an unused slot. The
publisher's personal saves and backups are not distributed. Provenance and
integrity are recorded in `assets/optional-saves/manifest.json`.

`assets/lilia/` contains 13 small visible layers from the supplied game's clothed
normal player model (SiNiSistar2 v1.3.1). The fully transparent skirt overlay,
alternate body states, weapons and CG images are excluded. Pixel graphics
retain the game's original rights, separate from this project's GPL source.
`source.json` records bundle and Sprite identities and PNG checksums. The
patrol, turn, arm/leg swing and pauses in `LiliaWalk.qml` are decorative UI
animation authored for this project; no game walking animation or game code
is executed. `tools/build_lilia_mascot.py` is a development-only reproduction
script using the audited local research copies, not a runtime dependency.
