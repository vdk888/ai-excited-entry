# ai-excited-entry

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/vdk888/ai-excited-entry/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard)
[![reward](https://make.fun/badge/ai-excited-01/vdk888/ai-excited-entry/reward.svg)](https://make.fun/bounty/ai-excited-01)

**Paper Boom**: a paper dart outrunning its own sonic boom. Behind it trails the Mach cone, a pleated
sheet of folded paper ringed by white shock lines, with torn shards flying off its edges, while the plane's nose
races ahead toward a single white-hot flare. Drawn entirely by code: SDF-style polygons, adaptive 3x3
supersampling, and a hand-written PNG encoder (stdlib only).

- `python3 render.py` renders `art/entry.png` (about 48 s); `--preview [--size N] [--cand K]` gives a fast draft;
  `--candidates` renders the configs into `candidates/` (paper boom violet, match-lights-the-sunrise,
  paper boom teal; round 2's pick is `--cand 4`, paper-dart-ahead).
- `python3 main.py` copies `art/entry.png` to `$MAKEFUN_OUTPUT_DIR/entry.png` (default `/output`), byte for byte;
  it falls back to the renderer only if the art is missing or is not a PNG.
- Tests: `python3 -m unittest`. 7/7 pass: identical bytes on two runs, valid PNG (CRCs, IHDR, IDAT length),
  472,694 bytes, main.py about 0.03 s, render.py about 48 s and deterministic
  (sha256 93c47ca1...0dec08a), 300 px preview, stdlib-only imports.
