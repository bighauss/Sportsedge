"""Synthetic source-shape tests. Do not ship a provider archive in the repo."""
import os
import pytest

duckdb = pytest.importorskip("duckdb")
from research.market_implied.smartstake_march_audit import QUERY, audit


def test_refuse_unknown_bytes(tmp_path):
    p = tmp_path / "other.parquet"
    p.touch()
    with pytest.raises(ValueError, match="UNEXPECTED_SOURCE_BYTES"):
        audit(p)


def test_exact_cutoff_pair_and_full_denominator(tmp_path):
    path = str(tmp_path / "fixture.parquet")
    with duckdb.connect() as db:
        # Deliberately no result/won columns: no outcome can influence the audit.
        db.execute("""CREATE TABLE t(game_id VARCHAR,start_time TIMESTAMP,player VARCHAR,
            market VARCHAR,line DOUBLE,side VARCHAR,book VARCHAR,ts TIMESTAMP,odds DOUBLE)""")
        for line, sides, minute, book in [
            (.5, ["over","under"], 0, "bet365"), (1.5, ["over","under"], 0, "bet365"),
            (2.5, ["over","over","under"], 0, "bet365"), (3.5, ["over"], 0, "bet365"),
            (4.5, ["over","under"], 1, "bet365"), (5.5, ["over","under"], 0, "draftkings6_best"),
        ]:
            for side in sides:
                db.execute("INSERT INTO t VALUES ('e','2026-03-01 12:00','p','m',?,?,?,?,2.0)",
                           [line, side, book, f"2026-03-01 11:0{minute}"])
        db.execute("COPY t TO ? (FORMAT PARQUET)", [path])
        assert db.execute(QUERY, [path]).fetchone() == ("m", 5, 1, 2, 2, 1, 1)


@pytest.mark.skipif(not os.getenv("SPORTSEDGE_SMARTSTAKE_MARCH"), reason="external pinned archive")
def test_pinned_historical_replay():
    path = os.environ["SPORTSEDGE_SMARTSTAKE_MARCH"]
    rows = audit(path)
    assert sum(r["observed_contracts"] for r in rows) == 12889
    assert sum(r["paired"] for r in rows) == 696
    assert sum(r["multi_rung"] for r in rows) == 0
    example = audit(path, example=True)
    assert example["power"]["push"] == pytest.approx([.23281277864]*2)
