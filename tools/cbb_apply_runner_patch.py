#!/usr/bin/env python3
"""Apply the CBB runner integration of cbb_numeric to models/cbb/cbb_run_it_pipeline.py by EXACT-STRING replacement.

Why a patch and not a rewrite: the pipeline is a ~40KB production file; whole-file copies risk silent transcription
drift. Every replacement below must match the target exactly ONCE or the script aborts without writing anything.

  python tools/cbb_apply_runner_patch.py models/cbb/cbb_run_it_pipeline.py            # dry run, prints what would change
  python tools/cbb_apply_runner_patch.py models/cbb/cbb_run_it_pipeline.py --write

Changes (all at adea86f5 text):
  1. import cbb_numeric as NUM
  2. _int_price / _num delegate to NUM.strict_price / NUM.strict_line (same None / value / "BAD" contract, so every
     caller is unchanged): '1+10', '1e3', 'inf', 'nan', 5,000-digit and Unicode-digit cells all become "BAD".
  3. duplicate key (gid, period, market, line) -> NUM.semantic_identity(..., player): different players on one
     line are no longer duplicates; provider ids are NOT part of the duplicate key.
"""
import sys

MARKER = "import cbb_numeric as NUM"

PATCHES = [
    (
        "import cbbd_native_score_model as NM          # noqa: E402\n",
        "import cbbd_native_score_model as NM          # noqa: E402\n"
        "import cbb_numeric as NUM                      # noqa: E402\n",
    ),
    (
        'def _int_price(v):\n'
        '    try:\n'
        '        s = str(v).strip().replace("+", "")\n'
        '        if not s:\n'
        '            return None\n'
        '        p = int(float(s))\n'
        '        return p if abs(p) >= 100 and float(s).is_integer() else "BAD"\n'
        '    except (TypeError, ValueError):\n'
        '        return "BAD"\n'
        '\n'
        '\n'
        'def _num(v):\n'
        '    try:\n'
        '        s = str(v).strip()\n'
        '        return float(s) if s else None\n'
        '    except (TypeError, ValueError):\n'
        '        return "BAD"\n',
        'def _int_price(v):\n'
        '    return NUM.strict_price(v)      # None | int | "BAD"; never raises\n'
        '\n'
        '\n'
        'def _num(v):\n'
        '    return NUM.strict_line(v)       # None | finite float | "BAD"; never raises\n',
    ),
    (
        "        keyed[(gid, q.period, q.market, q.line)].append(q)\n",
        "        keyed[NUM.semantic_identity(gid, q.period, q.market, q.line, q.player)].append(q)\n",
    ),
]


def apply(text):
    if MARKER in text:
        return text                          # already applied
    for i, (old, new) in enumerate(PATCHES, 1):
        n = text.count(old)
        if n != 1:
            raise SystemExit("PATCH %d target found %d times (need exactly 1); nothing written" % (i, n))
    for old, new in PATCHES:
        text = text.replace(old, new)
    return text


def main(argv):
    path = argv[0]
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new = apply(text)
    if new == text:
        print("already applied" if MARKER in text else "no change")
        return 0
    if "--write" in argv[1:]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        print("patched", path)
    else:
        print("dry run OK: 3 exact-match replacements would apply; re-run with --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
