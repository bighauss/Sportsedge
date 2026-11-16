"""Synthetic-only tests for historical original board ↔ printed card replay."""
import csv
from hashlib import sha256
import io
import unittest

from original_board_card_source_join import audit, AuditBlocked


def board_bytes(data):
    header = ("sport", "home", "away", "market", "line", "price_a", "price_b")
    io_ = io.StringIO(newline="")
    writer = csv.DictWriter(io_, fieldnames=header, lineterminator="\r\n")
    writer.writeheader()
    for row in data:
        writer.writerow(dict(zip(header, ("CBB", *row))))
    return io_.getvalue().encode("ascii")


def source_board():
    return board_bytes([
        ("Stanford", "Rice", "ML", "", "-3200", "1400"),
        ("Stanford", "Rice", "SPREAD", "-7.5", "-720", "404"),
        ("Washington", "Mississippi Valley", "HOME_TT", "82.5", "-780", "444"),
        ("Washington", "Mississippi Valley", "TOTAL", "141.5", "-475", "325"),
        ("Hawaii", "Portland", "1H_TOTAL", "74.5", "-105", "-125"),
        ("Stanford", "Rice", "AWAY_TT", "73.5", "459", "-820"),
        ("Stanford", "Rice", "1H_ML", "", "-800", "575"),
    ])


def card_bytes(lines=None):
    regular = [
        ("CBB Rice +7.5", "+404", "37.3%", "+88.1%"),
        ("CBB 1H Under 74.5", "-125", "60.4%", "+8.7%"),
        ("CBB Rice Over 73.5", "+459", "29.6%", "+65.6%"),
        ("CBB 1H Rice ML", "+575", "24.1%", "+60.3%"),
    ]
    doubted = [
        ("CBB Rice ML", "+1400", "15.9%", "+139.2%"),
        ("CBB Washington Under 82.5", "+444", "41.6%", "+126.4%"),
        ("CBB Under 141.5", "+325", "42.0%", "+78.4%"),
    ]
    if lines is not None:
        regular, doubted = lines
    p = ["# FROZEN SYNTHETIC FIXTURE",
         f"CARD ({len(regular)}) - demonstration",
         "| # | Pick | Price | Model % | Fair | Edge | EV | Score | Stars |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i, (name, odds, chance, ev) in enumerate(regular, 1):
        p.append(f"| {i} | {name} | {odds} | {chance} | +100 | +10.0% | {ev} | 75 | **** |")
    p.append(f"MODEL-DOUBTED ({len(doubted)}) - original quarantine")
    for i, (name, odds, chance, ev) in enumerate(doubted, 1):
        p.append(f"| {i} | {name} | {odds} | {chance} | +100 | +10.0% | {ev} | 75 | **** |")
    return ("\n".join(p) + "\n").encode("utf-8")


def run(b=None, c=None, **overrides):
    b = source_board() if b is None else b
    c = card_bytes() if c is None else c
    config = dict(
        expected_board_sha=sha256(b).hexdigest(),
        expected_card_sha=sha256(c).hexdigest(),
        original_board_saved_utc="2026-11-10T02:17:44.831Z",
        printed_card_saved_utc="2026-11-10T02:22:24.393Z",
        earliest_game_start_utc="2026-11-10T03:00:00Z",
        expected_board_rows=7
    )
    config.update(overrides)
    return audit(b, c, **config)


class HistoricalSourcePairingTests(unittest.TestCase):
    def test_every_fixture_row_matches_unique_original_board(self):
        report = run()
        self.assertEqual(report["unique_source_matches"], 7)
        self.assertEqual(report["model_doubted"], 3)
        self.assertEqual(report["arithmetic_discrepancies"], 0)
        self.assertEqual(set(r["game"] for r in report["matches"]),
                         {"Rice @ Stanford", "Mississippi Valley @ Washington",
                          "Portland @ Hawaii"})
        self.assertTrue(all(r["approved_stake_units"] == 0 for r in report["matches"]))
        self.assertTrue(all("MISSING_ORIGINAL" in r["quote_receipt"] for r in report["matches"]))

    def test_american_opposite_price_and_spread_sign(self):
        matches = run()["matches"]
        rice = next(r for r in matches if r["printed_selection"] == "CBB Rice +7.5")
        self.assertEqual(rice["board_line"], "-7.5")
        self.assertEqual(rice["matched_side"], "B")
        self.assertEqual((rice["price_american"], rice["opposing_price_american"]),
                         (404, -720))
        self.assertAlmostEqual(rice["model_minus_no_vig_pp"], 18.868063, places=4)

    def test_team_total_and_generic_total_do_not_collide(self):
        matches = run()["matches"]
        team = next(r for r in matches if r["printed_selection"] ==
                    "CBB Washington Under 82.5")
        full = next(r for r in matches if r["printed_selection"] ==
                    "CBB Under 141.5")
        self.assertEqual((team["board_market"], full["board_market"]),
                         ("HOME_TT", "TOTAL"))
        self.assertEqual(team["matched_side"], "B")
        self.assertEqual(full["matched_side"], "B")

    def test_moneyline_and_first_half_are_distinct(self):
        m = run()["matches"]
        full = next(r for r in m if r["printed_selection"] == "CBB Rice ML")
        half = next(r for r in m if r["printed_selection"] == "CBB 1H Rice ML")
        self.assertEqual(full["board_market"], "ML")
        self.assertEqual(half["board_market"], "1H_ML")
        self.assertEqual(full["opposing_price_american"], -3200)

    def test_1h_moneyline_conditional_display_requires_push_draws(self):
        r = run()
        half = next(x for x in r["matches"] if
                    x["printed_selection"] == "CBB 1H Rice ML")
        self.assertIsNone(half["ev_arithmetic_consistent_with_display_rounding"])
        self.assertEqual(half["ev_math_check"],
            "PUSH_AWARE_1H_ML_ORIGINAL_WIN_LOSS_DRAWS_REQUIRED")
        self.assertAlmostEqual(half["approx_implied_push_share_from_display"],
                               0.037895, places=3)
        self.assertEqual(r["push_aware_ml_rows_needing_original_draws"], 1)
        self.assertEqual(r["arithmetic_discrepancies"], 0)

    def test_board_or_card_sha_tamper_is_rejected(self):
        for kwargs in ({"expected_board_sha": "0"*64}, {"expected_card_sha": "0"*64}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AuditBlocked):
                run(**kwargs)

    def test_pretip_timing_and_timezone_are_required(self):
        for kwargs in (
            {"printed_card_saved_utc": "2026-11-10T03:00:00Z"},
            {"original_board_saved_utc": "2026-11-10T03:00:00Z"},
            {"printed_card_saved_utc": "2026-11-10T02:22:24"},
            {"original_board_saved_utc": "2026-11-10T02:30:00Z"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(AuditBlocked):
                run(**kwargs)

    def test_ambiguous_duplicate_board_quote_is_not_selected(self):
        src = source_board().decode("ascii")
        source = board_bytes([
            ("Stanford", "Rice", "ML", "", "-3200", "1400"),
            ("Stanford", "Rice", "SPREAD", "-7.5", "-720", "404"),
            ("Washington", "Mississippi Valley", "HOME_TT", "82.5", "-780", "444"),
            ("Washington", "Mississippi Valley", "TOTAL", "141.5", "-475", "325"),
            ("Hawaii", "Portland", "1H_TOTAL", "74.5", "-105", "-125"),
            ("Stanford", "Rice", "AWAY_TT", "73.5", "459", "-820"),
            ("Stanford", "Rice", "1H_ML", "", "-800", "575"),
            ("Hawaii", "Portland", "TOTAL", "141.5", "-475", "325"),
        ])
        with self.assertRaisesRegex(AuditBlocked, "NOT_UNIQUE"):
            run(b=source, expected_board_rows=8)

    def test_unpaired_offer_blocks_not_invents_opposing_price(self):
        changed = source_board().replace(b"1400", b"1500")
        with self.assertRaises(AuditBlocked):
            run(b=changed)

    def test_missing_printed_row_is_not_silently_dropped(self):
        raw = card_bytes().decode()
        # Preserve the original declared count while stripping a data row.
        removed = raw.replace(
            "| 1 | CBB Rice +7.5 | +404 | 37.3% | +100 | +10.0% | +88.1% | 75 | **** |\n", "")
        with self.assertRaises(AuditBlocked):
            run(c=removed.encode())

    def test_nonfinite_or_bad_price_blocks(self):
        for token in ("NaN%", "101.1%", "inf%"):
            raw = card_bytes().replace(b"15.9%", token.encode())
            with self.assertRaises(AuditBlocked):
                run(c=raw)
        raw = card_bytes().replace(b"+1400", b"+99")
        with self.assertRaises(AuditBlocked):
            run(c=raw)

    def test_ev_disagreement_flagged_without_optimizing(self):
        raw = card_bytes().replace(b"+139.2%", b"+999.0%")
        result = run(c=raw)
        self.assertEqual(result["arithmetic_discrepancies"], 1)
        self.assertEqual(result["model_doubted"], 3)

    def test_source_sport_and_csv_header_rejected(self):
        raw = source_board().replace(b"CBB,", b"CFB,")
        with self.assertRaises(AuditBlocked):
            run(b=raw)
        raw = source_board().replace(b"sport,home,away", b"sport,sport,away")
        with self.assertRaises(AuditBlocked):
            run(b=raw)


if __name__ == "__main__":
    unittest.main()
