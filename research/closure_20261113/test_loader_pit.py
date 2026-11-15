"""Loader PIT enforcement, sentinel validity, and §5 composite keys."""
import pytest

from pga_h2h_screen import loader
from pga_h2h_screen.features import compute_features
from pga_h2h_screen.loader import LoaderError, load_corpus, parse_event

from make_fixtures import make_event, make_row, write_corpus

PLAYERS = [1, 2, 3, 4, 5, 6]
SCORES = {k: [68 + k, 70 + k, 69 + k, 71 + k] for k in PLAYERS}


def _field(sg_by_player, fin_offset=0):
    rows = []
    for i, pid in enumerate(PLAYERS):
        rows.append(make_row(
            pid, fin=str(i + 1 + fin_offset), owgr_rank=10 * pid,
            close=5.0 + pid, sgs=[sg_by_player[pid]] * 4, scores=SCORES[pid],
        ))
    return rows


def _history_events():
    base_sg = {k: 2.0 - 0.4 * k for k in PLAYERS}
    events = []
    # Recurring event 900: editions 2020/2021/2022, player 1 hot (+4.0).
    for d in ("2020-06-07", "2021-06-06", "2022-06-05"):
        sg = dict(base_sg); sg[1] = 4.0
        events.append(make_event(900, d, _field(sg), name="Recurring Open"))
    # Fillers: 10 more events -> >= 40 measured rounds in the window.
    for i, d in enumerate(("2021-08-08", "2021-10-03", "2021-12-05",
                           "2022-02-06", "2022-04-03", "2022-08-07",
                           "2022-10-02", "2022-12-04", "2023-02-05",
                           "2023-04-02")):
        events.append(make_event(901 + i, d, _field(base_sg)))
    return events


def _target(sg1):
    sg = {k: 2.0 - 0.4 * k for k in PLAYERS}
    sg[1] = sg1
    return make_event(900, "2023-06-04", _field(sg), name="Recurring Open")


def _features(tmp_path, events, target):
    write_corpus(str(tmp_path), events + [target])
    corpus = load_corpus(str(tmp_path))
    tgt = corpus.events[("900", 2023)]
    return compute_features(corpus, tgt)


def test_target_own_rounds_never_enter_features(tmp_path):
    """§5: the target event's own rounds are not features, whatever they say."""
    hist = _history_events()
    fa = _features(tmp_path / "a", hist, _target(-10.0))
    fb = _features(tmp_path / "b", hist, _target(+10.0))
    assert fa == fb
    assert fa[1].measured_rounds >= 40  # priced


def test_future_and_same_day_events_never_enter_features(tmp_path):
    """§5/R-SKILL-1: strictly-before dating; later data changes nothing."""
    hist = _history_events()
    before = _features(tmp_path / "a", hist, _target(0.0))
    future = make_event(990, "2023-07-02", _field({k: 30.0 for k in PLAYERS}))
    same_day = make_event(991, "2023-06-04", _field({k: 30.0 for k in PLAYERS}))
    after = _features(tmp_path / "b", hist + [future, same_day], _target(0.0))
    assert before == after


def test_course_fit_uses_all_prior_editions(tmp_path):
    """R-COURSE-1: 3 prior editions, player 1 mean SG 4.0 over 12 rounds."""
    feats = _features(tmp_path, _history_events(), _target(0.0))
    # adj = (12 / (12 + 8)) * 4.0 = 2.4
    assert feats[1].course_adj == pytest.approx(2.4)
    # Player 2's 900-edition SG equals his base SG; adj = 0.6 * base.
    assert feats[2].course_adj == pytest.approx(0.6 * (2.0 - 0.8))


def test_unpriced_below_40_measured_rounds(tmp_path):
    """§4.1: a player with thin history is UNPRICED, not prior-filled."""
    hist = _history_events()
    rookie = make_row(99, fin="7", owgr_rank=300, close=50.0,
                      sgs=[3.0] * 4, scores=[68, 70, 69, 71])
    tgt = _target(0.0)
    tgt["rows"].append(rookie)
    feats = _features(tmp_path, hist, tgt)
    assert 99 not in feats


@pytest.mark.parametrize("raw,expected", [
    (-9999, None), (-9998, None), (0, None), (-5, None), (None, None),
    ("5", None), (1, 1), (250, 250),
])
def test_owgr_rank_validity(raw, expected):
    """Amendment 1 §3.2 step 1: integer >= 1 only; sentinels = no rank."""
    assert loader.valid_owgr_rank(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (-9999.0, None), (None, None), (1.0, None), (0.5, None), (7.625, 7.625),
])
def test_close_validity(raw, expected):
    """R-REFA-1: present, not the sentinel, and > 1.0."""
    assert loader.valid_close(raw) == expected


def test_dg_pts_and_dg_rank_are_never_loaded(tmp_path):
    """Amendment 1 §3.1: dg_pts is lookahead and dg_rank unused — dropped."""
    ev_a = make_event(700, "2024-05-05", [make_row(1, dg_pts=1.0)])
    ev_b = make_event(700, "2024-05-05", [make_row(1, dg_pts=999.0)])
    ev_b["rows"][0]["excluded"]["dg_rank"] = 1
    pa = parse_event(ev_a)
    pb = parse_event(ev_b)
    assert pa.rows == pb.rows
    assert not hasattr(pa.rows[0], "dg_pts")


def test_duplicate_composite_key_refused(tmp_path):
    ev = make_event(700, "2024-05-05", [make_row(1)])
    write_corpus(str(tmp_path), [ev])
    # Same (event_id, date) under a different file name.
    import json, os
    with open(os.path.join(str(tmp_path), "copy.json"), "w") as f:
        json.dump(ev, f)
    with pytest.raises(LoaderError):
        load_corpus(str(tmp_path))


def test_same_event_id_different_years_is_two_events(tmp_path):
    """§5 composite keys: annual editions are distinct events."""
    evs = [make_event(700, "2023-05-07", [make_row(1)]),
           make_event(700, "2024-05-05", [make_row(1)])]
    write_corpus(str(tmp_path), evs)
    corpus = load_corpus(str(tmp_path))
    assert set(corpus.events) == {("700", 2023), ("700", 2024)}
