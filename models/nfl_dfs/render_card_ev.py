"""Phone card (dark neon) for a game's EV output: python render_card_ev.py out/<tag>_ev.json out/<tag>_card.png"""
import json, sys
from PIL import Image, ImageDraw, ImageFont
ev = json.load(open(sys.argv[1])); outp = sys.argv[2]
F = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed%s.ttf"
f = lambda s, b=False: ImageFont.truetype(F % ("-Bold" if b else ""), s)
W, H = 1080, 1900
im = Image.new("RGB", (W, H), (8, 10, 18)); d = ImageDraw.Draw(im)
NEON, PINK, GOLD, DIM, WH = (57, 255, 140), (255, 70, 150), (255, 200, 40), (130, 140, 160), (240, 244, 255)
def tile(x, y, w, h, fill=(18, 22, 38), line=(40, 48, 78)):
    d.rounded_rectangle((x, y, x + w, y + h), 18, fill=fill, outline=line, width=2)
def flame(x, y, s=1.0):
    pts = [(x+14*s, y), (x+26*s, y+18*s), (x+22*s, y+16*s), (x+28*s, y+34*s), (x+14*s, y+44*s), (x, y+34*s), (x+6*s, y+20*s), (x+10*s, y+24*s)]
    d.polygon(pts, fill=(255, 120, 30)); d.polygon([(x+14*s, y+22*s), (x+20*s, y+34*s), (x+14*s, y+42*s), (x+8*s, y+34*s)], fill=GOLD)
def stars(x, y, n, sz=26):
    for i in range(5): d.text((x + i * (sz + 2), y), "★", font=f(sz), fill=GOLD if i < n else (50, 56, 80))
def odds(o): return f"+{o}" if o > 0 else str(o)
# header
tile(30, 30, W-60, 170, (14, 18, 32), NEON)
d.text((60, 52), "PIT  STEELERS", font=f(54, True), fill=GOLD)
d.text((60, 118), "@  CIN  BENGALS", font=f(54, True), fill=(255, 110, 40))
d.text((620, 56), "SUNDAY NIGHT FOOTBALL", font=f(28, True), fill=WH)
d.text((620, 98), "7:20 PM CT · Paycor Stadium", font=f(28), fill=DIM)
d.text((620, 140), "Cincinnati, OH · open air", font=f(26), fill=DIM)
# projection strip
y = 220; p = ev["proj"]
for i, (lab, val, col) in enumerate([("PIT", p["PIT"], GOLD), ("CIN", p["CIN"], (255, 110, 40)), ("TOTAL", p["total"], NEON), ("CIN WIN", "58%", PINK)]):
    x = 30 + i * 262; tile(x, y, 244, 120)
    d.text((x+20, y+14), lab, font=f(26), fill=DIM); d.text((x+20, y+50), str(val), font=f(54, True), fill=col)
d.text((30, y+132), "DK: CIN -3.5 (-110) · O/U 49.5 · ML CIN -192 / PIT +160 · 20,000 sims, same sim as DFS", font=f(24), fill=DIM)
# game card
y = 395
d.text((30, y), "GAME CARD", font=f(34, True), fill=NEON)
tile(30, y+50, 500, 330)
rows = ["Fair ML: CIN -138 / PIT +138", "CIN -3.5 covers 52% (DK 50%)", "Over 49.5 hits 45% (DK 49%)", "PIT team total 22.1 (DK 22.5)", "CIN team total 26.6 (DK 26.5)", "No side or total clears +EV at DK"]
for i, r in enumerate(rows): d.text((52, y+68+i*50), r, font=f(27, i == 5), fill=WH if i < 5 else GOLD)
# prop card
d.text((560, y), "PROP CARD · ranked by EV", font=f(34, True), fill=PINK)
plays = [x for x in ev["plays"] if x["kind"] == "Prop"]
py = y + 50
for i, x in enumerate(plays[:6]):
    tile(560, py, 490, 150, (22, 26, 44), PINK if i < 2 else (40, 48, 78))
    if i < 2: flame(1000, py+10)
    d.text((578, py+8), x["play"].replace("rush_yds", "rush yds").replace("receptions", "rec").replace("completions", "comp"), font=f(25, True), fill=WH)
    d.text((578, py+44), f"{odds(x['price'])}  win {x['p_model']*100:.0f}%  mkt {x['p_market_nv']*100:.0f}%", font=f(24), fill=NEON)
    d.text((578, py+78), f"raw EV {x['raw_ev']*100:+.1f}%  blended {x['blended_ev']*100:+.1f}%", font=f(24), fill=WH)
    stars(578, py+112, x["stars"], 24)
    d.text((780, py+114), f"{x['size_u']}u · {x['conf']}", font=f(24), fill=GOLD)
    py += 160
yb = max(y + 400, py + 10)
# key inputs
d.text((30, yb), "KEY INPUTS", font=f(34, True), fill=GOLD)
tile(30, yb+50, W-60, 330)
inp = ["Weather: ~42°F, wind 0-2 mph, ~1% precip, no effect",
       "PIT: Freiermuth (TE) Q illness; Skowronek cleared; Pittman, Wilson on IR",
       "CIN: Iosivas (WR) OUT; Chase, Higgins, Brown, Burrow active",
       "Pace/volume: CIN 38.5 pass + 24.5 rush att; PIT 33.5 + 25.5",
       "PIT off bye; Bengals won 4 straight (30+ pts each)",
       "Model vs DK: Brown rush, Gesicki, Dowdle inputs sit far off DK lines;",
       f"{len(ev['model_market_disagree'])} plays hidden as input gaps, not edges"]
for i, r in enumerate(inp): d.text((52, yb+66+i*42), r, font=f(26), fill=WH if i < 5 else (255, 140, 140))
d.text((30, yb+400), f"Lines captured {ev['captured'].split(',')[0]} · size = quarter-Kelly, no game cap", font=f(22), fill=DIM)
d.text((30, yb+430), "RUN IT rules v2 · sources: DraftKings (screens), nflverse, ESPN/Rotowire roles", font=f(22), fill=DIM)
im.crop((0, 0, W, yb+480)).save(outp)
print(outp, im.size)
