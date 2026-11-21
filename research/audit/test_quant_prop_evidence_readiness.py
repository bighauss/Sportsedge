"""Synthetic-only regression tests for the source-agnostic prop readiness census."""
import csv
import io
import unittest

from prop_evidence_readiness import (
    BASE_COLUMNS, audit_capture, evidence_gaps, strict_rows,
)


FIELDS = sorted(BASE_COLUMNS) + [
    "event_id", "p_model", "model_mode", "model_asof_utc",
    "features_published_utc", "game_start_utc", "model_sha256",
    "feature_snapshot_sha256", "provider_receipt_id",
    "provider_observed_utc", "provider_captured_utc",
    "original_quote_sha256", "result_source", "settled_utc",
]


def row(market="player_prop_xplus:PASS_YDS"):
    item = {k: "" for k in FIELDS}
    item.update(sport="NFL", market=market, period="FG", side="yes",
                player="Example Athlete", line="225.5",
                price_american="-110", source="DK_SCREENSHOT_USER",
                book="DK", source_file_sha256="sha256:not-authenticated")
    return item


def write_csv(rows, fields=FIELDS):
    io_stream = io.StringIO(newline="")
    writer = csv.DictWriter(io_stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return io_stream.getvalue().encode("utf-8")


class PropEvidenceReadinessTests(unittest.TestCase):
    def test_census_does_not_miscount_touchdowns_as_non_player(self):
        rows = [row("spread"), row(), row("attd"),
                row("first_td"), row("td_2plus")]
        r = audit_capture(write_csv(rows))
        self.assertEqual(r["source_rows"], 5)
        self.assertEqual(r["player_related_rows"], 4)
        self.assertEqual(r["market_family_counts"]["PLAYER_STAT_THRESHOLD"], 1)
        self.assertEqual(r["market_family_counts"]["TOUCHDOWN_EVENT"], 3)
        self.assertEqual(r["market_family_counts"]["NON_PLAYER_GAME_MARKET"], 1)
        self.assertEqual(r["prop_rows_eligible_for_verified_joint_metrics"], 0)
        self.assertEqual(r["gap_counts_nonexclusive"]["PLAYER_ID_UNBOUND"], 4)
        self.assertEqual(r["gap_counts_nonexclusive"]["GRADED_OFFICIAL_RESULT_MISSING"], 4)

    def test_raw_screenshot_hash_not_provider_authentication(self):
        r = audit_capture(write_csv([row()]))
        self.assertEqual(r["gap_counts_nonexclusive"]["ORIGINAL_PROVIDER_QUOTE_PROOF_MISSING"], 1)
        self.assertEqual(r["prop_rows_provider_authenticated"], 0)

    def test_complete_self_declared_record_is_still_not_verified(self):
        d = row()
        d.update(
            event_id="EVENT_1", player_id="GSIS_001", p_model="0.55",
            model_mode="PROJECTION",
            model_asof_utc="2026-11-15T17:00:00Z",
            features_published_utc="2026-11-15T16:00:00Z",
            game_start_utc="2026-11-15T20:00:00Z",
            model_sha256="sha256:example", feature_snapshot_sha256="sha256:example",
            provider_receipt_id="user-declared",
            provider_observed_utc="2026-11-15T17:30:00Z",
            provider_captured_utc="2026-11-15T17:31:00Z",
            original_quote_sha256="sha256:user-declared",
            grade="W", actual="250", result_source="user-declared",
            settled_utc="2026-11-15T23:30:00Z",
        )
        self.assertEqual(evidence_gaps(d), [])
        audit = audit_capture(write_csv([d]))
        self.assertEqual(audit["prop_rows_structurally_complete_unverified"], 1)
        self.assertEqual(audit["prop_rows_eligible_for_verified_joint_metrics"], 0)

    def test_anchor_or_future_feature_fails_closed(self):
        d = row()
        d.update(event_id="E1", player_id="P1", p_model="0.7",
                 model_mode="ANCHOR",
                 model_asof_utc="2026-11-15T17:00:00Z",
                 features_published_utc="2026-11-15T21:00:00Z",
                 game_start_utc="2026-11-15T20:00:00Z")
        issues = evidence_gaps(d)
        self.assertIn("INDEPENDENT_MODEL_MODE_UNVERIFIED", issues)
        self.assertIn("MODEL_OR_FEATURE_LOOKAHEAD", issues)

    def test_csv_blank_record_and_normalized_duplicate_header_refused(self):
        base = write_csv([row()])
        with self.assertRaisesRegex(ValueError, "BLANK_LOGICAL_RECORD"):
            strict_rows(base + b"\n")
        colliding_fields = FIELDS + ["PLAYER_ID"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CASEFOLD_HEADER"):
            strict_rows(write_csv([], fields=colliding_fields))

    def test_multiline_quoted_field_remains_one_logical_record(self):
        d = row()
        d["player"] = "source line one\n\nsource line three"
        got = strict_rows(write_csv([d]))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["player"], d["player"])

    def test_never_coerce_missing_result_to_a_loss_or_zero(self):
        d = row()
        d.update(event_id="E1", player_id="P1", actual="", grade="")
        self.assertIn("GRADED_OFFICIAL_RESULT_MISSING", evidence_gaps(d))
        r = audit_capture(write_csv([d]))
        self.assertNotIn("brier", r)
        self.assertNotIn("roi", r)


if __name__ == "__main__":
    unittest.main()
