# HD+ out-of-range lock-on color A/B (D-221)

Human visual acceptance for the `lockon_far_color` setting: the dashed ring shown
around a locked target that is beyond the fist's reach, blue as in the original
PC release (the HD eight-dash design is kept).

    python tools/experiments/lockon_color/prepare_visual_ab.py [--entry knaar_20_human]

prepares a new private workspace under `private/work/lockon_color/acceptance/`
with independent copies of the registered save and two launchers. It never
starts the game. `A.cmd`: HD+ with `lockon_far_color=original`; `B.cmd`: the
same options with `restored`; mods off. The launcher checks the SHA-256 of
`r3hd.exe` and `rexruntime.dll` against the manifest and refuses a changed
build. Without `-Manual`, `visual_ab.ps1` is a dry run.

Only a person runs `A.cmd` / `B.cmd` and types PLAY. Lock on to an enemy with
the right trigger and back away until the dashed ring replaces the close-range
ring and arrow (about 20 units); compare it with the PC reference. The
close-range ring and arrows and all other effects must not change. Exit
normally before starting the other case.
