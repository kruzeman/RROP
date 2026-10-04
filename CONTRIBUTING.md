# Contributing to RROP

[Русская версия](CONTRIBUTING.ru.md)

RROP focuses on Rings of Power. Keep changes scoped to its recompilation,
hardware runtime, presentation or tools. Other game profiles belong in the
original GenesisRecomp project.

Use a feature branch and a pull request. Describe the problem, expected behavior,
changed behavior and the checks actually performed. Distinguish static review,
synthetic tests and real-ROM playtesting; none establishes a full playthrough.

For bug reports include the source commit, platform, compiler, build/run
commands, audio mode and the last terminal output. For gameplay issues add
the location and actions preceding the problem. For Void errors, the text
report described in [diagnostics](docs/diagnostics.md) is useful.

Do not attach commercial ROMs, generated game C, compiled game executables,
extracted assets or full machine saves to public issues or pull requests.
Use synthetic inputs for regression tests. Review diagnostic reports before
sharing them, particularly when extending their contents.

```sh
make test
make demo
```

Tests use Python's standard unittest framework, a C/C++ compiler and, for
window/font checks, SDL2/SDL2_ttf. Tests needing an original game ROM skip when
it is absent. Windows CI uses MSYS2 UCRT64; SDK downloads are checksum verified.

Preserve third-party notices. Contributions to the project's original code
are supplied under its MIT license.
