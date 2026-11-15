"""Candidate R1: manifest-skip rule for loader.load_corpus.

The extracted-content dir contains the packet's own manifest
(content_manifest.json) beside the event files. The candidate loader
skips ONLY manifest-shaped payloads (events list + corpus_sha256,
no event_id/rows); everything else keeps the original fail-closed
behavior. All fixtures are synthetic.
"""
import json
import os

import pytest

from pga_h2h_screen.loader import LoaderError, load_corpus

from make_fixtures import make_event, make_row, write_corpus


def _manifest_payload(n_events=2):
    return {
        "canonical_form": "synthetic",
        "corpus_sha256": "a" * 64,
        "event_count": n_events,
        "events": [
            {"event_id": str(700 + i), "date": "2024-05-05",
             "content_sha256": "b" * 64, "content_file": f"{700 + i}.json"}
            for i in range(n_events)
        ],
        "status": "ADMITTED — SYNTHETIC TEST",
    }


def _write(path_dir, fname, payload):
    os.makedirs(path_dir, exist_ok=True)
    with open(os.path.join(path_dir, fname), "w", encoding="utf-8") as f:
        json.dump(payload, f)


def test_manifest_file_skipped(tmp_path):
    """A manifest-shaped content_manifest.json is skipped, not parsed."""
    ev = make_event(700, "2024-05-05", [make_row(1)])
    write_corpus(str(tmp_path), [ev])
    _write(str(tmp_path), "content_manifest.json", _manifest_payload())
    corpus = load_corpus(str(tmp_path))
    assert set(corpus.events) == {("700", 2024)}


def test_manifest_shaped_file_skipped_under_any_name(tmp_path):
    """The skip keys on payload shape, so a renamed manifest also skips."""
    ev = make_event(700, "2024-05-05", [make_row(1)])
    write_corpus(str(tmp_path), [ev])
    _write(str(tmp_path), "packet_manifest_copy.json", _manifest_payload())
    corpus = load_corpus(str(tmp_path))
    assert len(corpus.events) == 1


def test_157_events_load_with_manifest_present(tmp_path):
    """157 synthetic events + a manifest load as exactly 157 events."""
    events = [
        make_event(1000 + i, "2024-05-05", [make_row(1)])
        for i in range(157)
    ]
    write_corpus(str(tmp_path), events)
    _write(str(tmp_path), "content_manifest.json",
           _manifest_payload(n_events=157))
    corpus = load_corpus(str(tmp_path))
    assert len(corpus.events) == 157


def test_malformed_event_still_raises(tmp_path):
    """An event-shaped file (has event_id) that is broken still raises."""
    ev = make_event(700, "2024-05-05", [make_row(1)])
    del ev["rows"]  # has event_id, missing rows -> malformed event
    write_corpus(str(tmp_path), [make_event(701, "2024-05-06", [make_row(1)])])
    _write(str(tmp_path), "700_2024-05-05.json", ev)
    _write(str(tmp_path), "content_manifest.json", _manifest_payload())
    with pytest.raises(LoaderError):
        load_corpus(str(tmp_path))


def test_unknown_shaped_json_still_raises(tmp_path):
    """A JSON that is neither event nor manifest still raises."""
    write_corpus(str(tmp_path),
                 [make_event(700, "2024-05-05", [make_row(1)])])
    _write(str(tmp_path), "mystery.json", {"hello": "world", "n": 3})
    with pytest.raises(LoaderError):
        load_corpus(str(tmp_path))


def test_manifest_name_alone_does_not_skip(tmp_path):
    """Fail-closed: content_manifest.json with a non-manifest payload
    (here an unknown shape) is NOT skipped on its name alone."""
    write_corpus(str(tmp_path),
                 [make_event(700, "2024-05-05", [make_row(1)])])
    _write(str(tmp_path), "content_manifest.json", {"hello": "world"})
    with pytest.raises(LoaderError):
        load_corpus(str(tmp_path))


def test_duplicate_key_still_raises_with_manifest_present(tmp_path):
    """Duplicate composite keys remain a hard error (§5) after the fix."""
    ev = make_event(700, "2024-05-05", [make_row(1)])
    write_corpus(str(tmp_path), [ev])
    _write(str(tmp_path), "copy.json", ev)
    _write(str(tmp_path), "content_manifest.json", _manifest_payload())
    with pytest.raises(LoaderError):
        load_corpus(str(tmp_path))
