"""Synthetic contract tests; not evidence of real provider access or model profitability."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import hoop_explorer_research as he

FREEZE = "2026-11-15T18:00:00Z"
TIP = "2026-11-15T19:00:00Z"
COLUMNS = {
    "player_id": "Athlete ID", "team_id": "Team ID", "season": "Season",
    "minutes": "Minutes", "name": "Player", "rapm": "RAPM",
    "usage_pct": "USG%", "turnover_pct": "TO%",
    "three_rate_pct": "3PR", "three_pct": "3P%", "orb_pct": "OR%"
}
P1 = {"Athlete ID": "p1", "Team ID": "umd", "Season": "2027",
      "Minutes": "300", "Player": "Primary Guard", "RAPM": "3.2",
      "USG%": "25", "TO%": "12", "3PR": "45", "3P%": "35", "OR%": "3"}
P2 = {"Athlete ID": "p2", "Team ID": "ind", "Season": "2027",
      "Minutes": "300", "Player": "Second Guard", "RAPM": "3",
      "USG%": "24", "TO%": "13", "3PR": "47", "3P%": "36", "OR%": "3.5"}
P3 = {"Athlete ID": "p3", "Team ID": "pur", "Season": "2027",
      "Minutes": "75", "Player": "Small Sample", "RAPM": "-5",
      "USG%": "10", "TO%": "30", "3PR": "5", "3P%": "25", "OR%": "15"}
LINEUP_COLUMNS = {
    "lineup_id": "ID", "team_id": "TEAM", "season": "SEASON",
    "possessions": "POSS", "net_rating": "NET", "player_ids": "MEMBERS"
}
L1 = {"ID": "line1", "TEAM": "umd", "SEASON": "2027", "POSS": "100",
      "NET": "20", "MEMBERS": "p1;x2;x3;x4;x5"}
L2 = {"ID": "line2", "TEAM": "umd", "SEASON": "2027", "POSS": "300",
      "NET": "-10", "MEMBERS": "p2;x2;x3;x4;x5"}


def make_csv(rows):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return b.getvalue().encode()


class HoopExplorerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def bundle(self, rows=None, *, kind="player", fmt="csv", mutate=None):
        rows = rows if rows is not None else ([P1, P2, P3] if kind == "player" else [L1, L2])
        raw = make_csv(rows) if fmt == "csv" else json.dumps({"rows": rows}).encode()
        export = self.root / ("source_" + kind + "." + fmt)
        export.write_bytes(raw)
        manifest = {
            "provider": "hoop_explorer", "kind": kind, "format": fmt,
            "source_url": "https://hoop-explorer.com/PlayerLeaderboard",
            "access_basis": "manual_user_export", "scope_id": "men_div1_2027",
            "season": 2027, "sha256": hashlib.sha256(raw).hexdigest(),
            "data_through_utc": "2026-11-15T17:00:00Z",
            "published_utc": "2026-11-15T17:10:00Z",
            "captured_utc": "2026-11-15T17:30:00Z",
            "columns": COLUMNS if kind == "player" else LINEUP_COLUMNS,
            "disjoint_partition": kind == "lineup",
        }
        if mutate:
            mutate(manifest)
        path = self.root / ("manifest_" + kind + ".json")
        path.write_text(json.dumps(manifest))
        return export, path

    def load(self, export, manifest, kind="player", **kw):
        return he.load_export(export, manifest, kind=kind, freeze_utc=FREEZE,
                              tipoff_utc=TIP, **kw)

    def test_csv_normalizes_provenance(self):
        players, ev = self.load(*self.bundle())
        self.assertEqual([p["player_id"] for p in players], ["p1", "p2", "p3"])
        self.assertEqual(players[0]["rapm"], 3.2)
        self.assertEqual(ev["rows"], 3)
        self.assertTrue(ev["clock_consistent_not_source_authenticated"])

    def test_json_rows_supported(self):
        players, ev = self.load(*self.bundle(fmt="json"))
        self.assertEqual(len(players), 3)
        self.assertEqual(ev["kind"], "player")

    def test_hash_mismatch_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m.update(sha256="0"*64))
        with self.assertRaisesRegex(he.Blocked, "EXPORT_HASH_MISMATCH"):
            self.load(export, manifest)

    def test_missing_publication_time_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m.pop("published_utc"))
        with self.assertRaisesRegex(he.Blocked, "UTC_Z_REQUIRED"):
            self.load(export, manifest)

    def test_future_stat_window_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m.update(
            data_through_utc="2026-11-15T20:00:00Z"))
        with self.assertRaisesRegex(he.Blocked, "LOOKAHEAD"):
            self.load(export, manifest)

    def test_future_capture_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m.update(
            captured_utc="2026-11-15T18:01:00Z"))
        with self.assertRaisesRegex(he.Blocked, "LOOKAHEAD"):
            self.load(export, manifest)

    def test_tip_before_freeze_blocked(self):
        export, manifest = self.bundle()
        with self.assertRaisesRegex(he.Blocked, "LOOKAHEAD"):
            he.load_export(export, manifest, kind="player",
                           freeze_utc=FREEZE, tipoff_utc="2026-11-15T17:00:00Z")

    def test_invalid_unauthorized_basis_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m.update(access_basis="scrape"))
        with self.assertRaisesRegex(he.Blocked, "AUTHORIZED_EXPORT_BASIS"):
            self.load(export, manifest)

    def test_missing_required_column_mapping_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m["columns"].pop("player_id"))
        with self.assertRaisesRegex(he.Blocked, "REQUIRED_EXPLICIT_COLUMN_MAP"):
            self.load(export, manifest)

    def test_mapped_column_absent_blocked(self):
        export, manifest = self.bundle(mutate=lambda m: m["columns"].update(rapm="Not Real"))
        with self.assertRaisesRegex(he.Blocked, "MISSING_MAPPED_EXPORT_FIELDS"):
            self.load(export, manifest)

    def test_duplicate_ids_blocked(self):
        export, manifest = self.bundle(rows=[P1, dict(P1)])
        with self.assertRaisesRegex(he.Blocked, "DUPLICATE_ENTITY_ID"):
            self.load(export, manifest)

    def test_mixed_seasons_blocked(self):
        export, manifest = self.bundle(rows=[P1, {**P2, "Season": "2026"}])
        with self.assertRaisesRegex(he.Blocked, "MIXED_SEASONS"):
            self.load(export, manifest)

    def test_nonfinite_stats_blocked(self):
        export, manifest = self.bundle(rows=[{**P1, "RAPM": "NaN"}])
        with self.assertRaisesRegex(he.Blocked, "NUMBER_OUT_OF_RANGE"):
            self.load(export, manifest)

    def test_archive_is_immutable_and_idempotent(self):
        export, manifest = self.bundle()
        _, evidence = self.load(export, manifest, archive_dir=self.root/"archive")
        receipt = Path(evidence["archive_path"])
        self.assertEqual(receipt.read_bytes(), export.read_bytes())
        self.load(export, manifest, archive_dir=self.root/"archive")

    def test_similar_players_minimum_features_and_low_minutes_flag(self):
        players, ev = self.load(*self.bundle())
        report = he.similar_players(players, "p1")
        self.assertEqual(report["nearest"][0]["player_id"], "p2")
        self.assertTrue(report["nearest"][1]["low_minutes_warning"])
        with self.assertRaisesRegex(he.Blocked, "TARGET_PLAYER_NOT_UNIQUELY"):
            he.similar_players(players, "not-on-roster")

    def test_roster_fit_user_supplied_profile(self):
        players, ev = self.load(*self.bundle())
        result = he.roster_fit(players, {
            "name": "guard profile",
            "targets": {"usage_pct": 25, "turnover_pct": 12, "three_pct": 35}})
        self.assertEqual(result["ranked_descriptive_fit"][0]["player_id"], "p1")
        with self.assertRaisesRegex(he.Blocked, "ROLE_REQUIRES"):
            he.roster_fit(players, {"targets": {"usage_pct": 15}})

    def test_lineup_padding_not_site_method(self):
        self.assertAlmostEqual(he.pad_rate(30, 100, 0, 300), 7.5)
        self.assertEqual(he.pad_rate(-10, 100, 0, 100), -5)

    def test_wowy_requires_explicit_disjoint_partition(self):
        lineups, ev = self.load(*self.bundle(kind="lineup"), kind="lineup")
        with self.assertRaisesRegex(he.Blocked, "DISJOINT"):
            he.lineup_context(lineups, "umd", "p1", prior_net=0, pad_k=200)
        result = he.lineup_context(lineups, "umd", "p1", prior_net=0, pad_k=200,
                                   partition_verified=True)
        self.assertEqual(result["on"]["possessions"], 100)
        self.assertEqual(result["off"]["possessions"], 300)
        self.assertEqual(result["raw_on_minus_off"], 30)
        self.assertEqual(result["padded_on_minus_off"], 12.6667)
        self.assertFalse(result["causal_effect_estimated"])

    def test_duplicate_lineup_members_blocked(self):
        bad = {**L1, "MEMBERS": "p1;p1;x3;x4;x5"}
        export, manifest = self.bundle(rows=[bad], kind="lineup")
        with self.assertRaisesRegex(he.Blocked, "FIVE_DISTINCT"):
            self.load(export, manifest, kind="lineup")

    def test_report_paper_zero_units(self):
        players, pe = self.load(*self.bundle())
        report = he.research_report(players, pe, target_player_id="p1")
        self.assertFalse(report["official"])
        self.assertFalse(report["pricing_enabled"])
        self.assertEqual(report["stake_u"], 0)
        self.assertFalse(report["source_authenticated"])

    def test_cli_generates_report(self):
        players, manifest = self.bundle()
        output = self.root/"output.json"
        he.main(["--players-export", str(players), "--players-manifest", str(manifest),
                 "--freeze-utc", FREEZE, "--tipoff-utc", TIP,
                 "--target-player-id", "p1", "--out", str(output)])
        self.assertEqual(json.loads(output.read_text())["sport"], "CBB")


if __name__ == "__main__":
    unittest.main()
