# HD+ canister color A/B (D-219)

Human visual acceptance for the `beam_color` setting: the vertical beam and the
rings above and below a power-up can, purple as in the original PC release.

    python tools/experiments/beam_color/prepare_visual_ab.py [--entry knaar_20_human]

prepares a new private workspace under `private/work/beam_color/acceptance/`
with independent copies of the registered save and two launchers. It never
starts the game. `A.cmd`: HD+ with `beam_color=original`; `B.cmd`: the same
options with `restored`; mods off. The launcher checks the SHA-256 of
`r3hd.exe` and `rexruntime.dll` against the manifest and refuses a changed
build. Without `-Manual`, `visual_ab.ps1` is a dry run.

Only a person runs `A.cmd` / `B.cmd` and types PLAY. Walk to a power-up can
before taking it; compare the beam and the upper/lower rings with the PC
reference; the swirl around Rayman and other orange effects must not change.
Exit normally before starting the other case.
