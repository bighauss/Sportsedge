"""The runner patch applies exactly, once, and the patched parsers/dedupe behave (fixture text copied from adea86f5)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models", "cbb"))
import cbb_apply_runner_patch as PT  # noqa: E402
import cbb_numeric as NUM  # noqa: E402

FIXTURE = (
    'import contracts as C                         # noqa: E402\n'
    'import cbb_pricing as PR                      # noqa: E402\n'
    'import cbbd_native_score_model as NM          # noqa: E402\n'
    '\n\n'
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
    '        return "BAD"\n'
    '\n\n'
    'def dedupe(pre):\n'
    '    from collections import defaultdict\n'
    '    keyed = defaultdict(list)\n'
    '    for q, gid in pre:\n'
    '        keyed[(gid, q.period, q.market, q.line)].append(q)\n'
    '    return keyed\n'
)


class Q:
    def __init__(self, player, line=19.5, period="FG", market="PLAYER_POINTS"):
        self.player, self.line, self.period, self.market = player, line, period, market


def load(text):
    ns = {"NUM": NUM}
    body = "\n".join(l for l in text.splitlines() if not l.startswith(("import contracts", "import cbb_pricing",
                                                                          "import cbbd_native", "import cbb_numeric")))
    exec(body, ns)
    return ns


class Patch(unittest.TestCase):
    def test_unpatched_fixture_has_the_reported_defects(self):
        ns = load(FIXTURE)
        self.assertEqual(ns["_int_price"]("1+10"), 110)
        self.assertEqual(ns["_int_price"]("1e3"), 1000)
        with self.assertRaises(OverflowError):
            ns["_int_price"]("inf")
        self.assertTrue(ns["_num"]("nan") != ns["_num"]("nan"))
        self.assertEqual(len(ns["dedupe"]([(Q("A"), "g"), (Q("B"), "g")])), 1)

    def test_patched_fixture_fixes_them_with_the_same_contract(self):
        ns = load(PT.apply(FIXTURE))
        for s in ("1+10", "1e3", "inf", "-inf", "nan", "9" * 5000, "\u00b9\u00b9\u2070"):
            self.assertEqual(ns["_int_price"](s), "BAD", s)
        for s in ("nan", "inf", "1e999", "0." + "0" * 400 + "1"):
            self.assertEqual(ns["_num"](s), "BAD", s)
        self.assertEqual((ns["_int_price"]("-110"), ns["_int_price"](""), ns["_int_price"](None)), (-110, None, None))
        self.assertEqual((ns["_num"]("144.5"), ns["_num"]("")), (144.5, None))
        self.assertEqual(len(ns["dedupe"]([(Q("Cooper Flagg"), "g"), (Q("Khaman Maluach"), "g")])), 2)
        self.assertEqual(len(ns["dedupe"]([(Q("Cooper  Flagg"), "g"), (Q("cooper flagg"), "g")])), 1)
        self.assertEqual(len(ns["dedupe"]([(Q(None, 144.5, market="TOTAL"), "g"), (Q(None, 144.5, market="TOTAL"), "g")])), 1)

    def test_idempotent(self):
        once = PT.apply(FIXTURE)
        self.assertEqual(PT.apply(once), once)

    def test_aborts_without_writing_when_a_target_is_missing_or_ambiguous(self):
        with self.assertRaises(SystemExit):
            PT.apply(FIXTURE.replace("def _num", "def _num2"))
        with self.assertRaises(SystemExit):
            PT.apply(FIXTURE + "        keyed[(gid, q.period, q.market, q.line)].append(q)\n")


if __name__ == "__main__":
    unittest.main()
