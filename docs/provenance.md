# Source provenance

RROP was extracted from Rings of Power development in
https://github.com/kruzeman/GenesisRecomp at commit `5a3207c2efa90919b3c3295980fb5dfc5f1834ea`
on 2026-10-04. That revision includes the adaptive window, controller-hint
preference and initial object-pool diagnostics.

The source was copied without old Git history, commercial ROMs, generated C,
game executables, screenshots, local saves or temporary SDK/build files.
Builders, documentation and tests specific to other games were excluded.
The shared recompiler/runtime and their synthetic regression tests were kept.

The original GenesisRecomp repository and its Theme Park branch were not
modified by the extraction. RROP starts its own project history.

Original RROP code is MIT licensed. Vendored ymfm files retain their original
BSD-3-Clause license and pinned upstream revision; see
[third-party notices](../THIRD_PARTY_NOTICES.md). Original game data and externally
installed fonts are outside RROP's license.
