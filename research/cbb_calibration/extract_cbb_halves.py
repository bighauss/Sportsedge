"""Extract halftime and final scores from ncaahoopR_data pbp_logs, one date at a time.
Raw pbp files are deleted after parsing (only derived scores kept). Usage: extract_cbb_halves.py OUT.csv NCAAHOOPR_DATA_CLONE (resumable)."""
import csv, os, shutil, subprocess, sys
REPO = sys.argv[2] if len(sys.argv) > 2 else "ncaahoopR_data"  # partial clone of lbenz730/ncaahoopR_data
out = sys.argv[1]
done = set()
if os.path.exists(out):
    done = {(r["season"], r["date"]) for r in csv.DictReader(open(out))}
w = open(out, "a", newline=""); cw = csv.writer(w)
if not done:
    cw.writerow(["season", "date", "game_id", "home", "away", "h1_home", "h1_away",
                 "final_home", "final_away", "max_half", "n_plays", "h1_plays"])
for season in ("2021-22", "2022-23", "2023-24", "2024-25"):
    names = subprocess.check_output(["git", "-C", REPO, "ls-tree", "--name-only", "HEAD", f"{season}/pbp_logs/"]).decode().split()
    for d in sorted(names):
        date = d.rsplit("/", 1)[-1]
        if (season, date) in done:
            continue
        subprocess.run(["git", "-C", REPO, "sparse-checkout", "add", d], capture_output=True)
        path = os.path.join(REPO, d)
        for fn in sorted(os.listdir(path)) if os.path.isdir(path) else []:
            try:
                rows = list(csv.DictReader(open(os.path.join(path, fn), newline="")))
                h1 = [r for r in rows if r["half"] == "1"]
                if not rows or not h1:
                    continue
                cw.writerow([season, date, rows[0]["game_id"], rows[0]["home"], rows[0]["away"],
                             h1[-1]["home_score"], h1[-1]["away_score"], rows[-1]["home_score"], rows[-1]["away_score"],
                             max(int(r["half"]) for r in rows if r["half"].isdigit()), len(rows), len(h1)])
            except (KeyError, ValueError, csv.Error, UnicodeDecodeError):
                continue
        w.flush()
        shutil.rmtree(path, ignore_errors=True)
        print(season, date, flush=True)
