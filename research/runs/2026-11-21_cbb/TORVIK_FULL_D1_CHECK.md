# Full Division I Torvik check, 2027 season

The source is `https://barttorvik.com/2027_team_results.csv`. ChatGPT downloaded it directly on 2026-11-21 and it was uploaded unmodified.

- SHA256 of the uploaded bytes: `52bc8d3bc34438ac40e7a55a7be19d9002f248e67d436814ad7b23b6dadc1935`
- 365 rows and 365 unique teams, in a column layout that matches Torvik's team_results export.

| Field | Mean (365 teams) | Median | Constant in this PR |
|---|---|---|---|
| adjoe | 107.183 | 106.353 | 107.0 |
| adjde | 107.230 | 108.096 | (same scale as adjoe) |
| adjt | 69.449 | 69.292 | 69.0 |

**Conclusion:** the 107.0 / 69.0 league constants agree with the full Division I averages within 0.2 efficiency points and 0.45 possessions. The old 105 / 67.5 constants were about 2 points too low on both.

The raw CSV is not committed. The hash identifies the bytes, but it doesn't prove when they were published. This is one mid-season snapshot, so the historical point-in-time calibration and graded results are still open.

Recompute with:

```sh
python3 -c "import csv,statistics as s;r=list(csv.DictReader(open('2027_team_results.csv')));print({k:round(s.mean(float(x[k]) for x in r),3) for k in ('adjoe','adjde','adjt')})"
```
