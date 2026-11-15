"""Writes SYNTHETIC sample inputs (fake numbers, real CFBD field names) to ./samples."""
import json, csv, os, random
random.seed(7)
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples"); os.makedirs(D, exist_ok=True)
teams = {"Alpha State":("America/New_York",900), "Bravo Tech":("America/Los_Angeles",300),
         "Charlie U":("America/Denver",7200), "Delta College":("America/Chicago",600)}
def side(q):
    return {"plays":700+int(80*q), "drives":120, "ppa":0.15+0.12*q, "successRate":0.42+0.04*q,
            "explosiveness":1.25+0.08*q, "pointsPerOpportunity":3.9+0.6*q,
            "fieldPosition":{"averageStart":70-2*q}, "havoc":{"total":0.16+0.02*q},
            "rushingPlays":{"ppa":0.10+0.12*q,"successRate":0.41+0.04*q,"rate":0.5},
            "passingPlays":{"ppa":0.22+0.14*q,"successRate":0.43+0.04*q,"rate":0.5}}
adv=[]
for i,(t,q) in enumerate(zip(teams,[0.9,0.1,-0.3,0.5])):
    o=side(q); d=side(-q*0.8); d["havoc"]["total"]=0.16+0.03*q
    adv.append({"season":2026,"team":t,"conference":"Sample","games":10,"offense":o,"defense":d})
json.dump(adv,open(f"{D}/advanced.json","w"),indent=1)
json.dump([{"year":2026,"team":t,"talent":v} for t,v in zip(teams,[880,760,640,820])],open(f"{D}/talent.json","w"))
json.dump([{"season":2026,"team":t,"percentPPA":v} for t,v in zip(teams,[0.7,0.5,0.4,0.6])],open(f"{D}/returning.json","w"))
json.dump([{"team":t,"rating":o-d,"offense":{"rating":o},"defense":{"rating":d}} for t,o,d in
           zip(teams,[9,1,-3,5],[-6,1,3,-2])],open(f"{D}/ratings.json","w"))
json.dump([{"school":t,"location":{"timezone":z,"elevation":e}} for t,(z,e) in teams.items()],open(f"{D}/teams.json","w"))
json.dump([{"id":901,"season":2026,"week":12,"homeTeam":"Alpha State","awayTeam":"Bravo Tech","neutralSite":False,"venue":"Alpha Field","startDate":"2026-11-21T17:00:00Z"},
           {"id":902,"season":2026,"week":12,"homeTeam":"Charlie U","awayTeam":"Delta College","neutralSite":False,"venue":"Charlie Mesa Stadium","startDate":"2026-11-21T21:00:00Z"}],open(f"{D}/games.json","w"),indent=1)
# lines: game 901 in CFBD nested shape, 902 flat CSV-style keys inside JSON
json.dump([{"id":901,"homeTeam":"Alpha State","awayTeam":"Bravo Tech",
            "lines":[{"provider":"sample","spread":-10.5,"overUnder":55.5,"homeMoneyline":-400,"awayMoneyline":310}],
            "spreadHomeOdds":-110,"spreadAwayOdds":-110,"overOdds":-110,"underOdds":-110,
            "homeTT":33.5,"homeTTOver":-115,"homeTTUnder":-105,"awayTT":22.5,"awayTTOver":-110,"awayTTUnder":-110,
            "h1Spread":-6.5,"h1HomeOdds":-110,"h1AwayOdds":-110,"h1Total":27.5,"h1Over":-110,"h1Under":-110}],
          open(f"{D}/lines.json","w"),indent=1)
with open(f"{D}/lines_flat.csv","w",newline="") as f:
    w=csv.writer(f); hdr=["homeTeam","awayTeam","spread","overUnder","homeMoneyline","awayMoneyline","spreadHomeOdds","spreadAwayOdds","overOdds","underOdds","homeTT","homeTTOver","homeTTUnder","awayTT","awayTTOver","awayTTUnder","h1Spread","h1HomeOdds","h1AwayOdds","h1Total","h1Over","h1Under"]
    w.writerow(hdr); w.writerow(["Charlie U","Delta College",3.5,49.5,140,-165,-110,-110,-110,-110,23.5,-110,-110,26.5,-110,-110,1.5,-110,-110,24.5,-110,-110])
with open(f"{D}/venues.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["venue","hfa","elevation_ft"]); w.writerow(["Alpha Field",3.5,900]); w.writerow(["Charlie Mesa Stadium",3.0,7200])
with open(f"{D}/injuries.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["team","player","role","status","impact"])
    for r in [["Bravo Tech","B. Starter","QB","OUT",""],["Delta College","D. Corner","DB","OUT",""],["Delta College","D. Safety","DB","OUT",""],["Alpha State","A. Tackle","OL","OUT",""]]: w.writerow(r)
json.dump([{"gameId":901,"windSpeed":18,"precipitation_type":"none","isForecast":True,"roof":"open"},
           {"gameId":902,"windSpeed":20,"precipitation_type":"snow","isForecast":False,"roof":"open"}],open(f"{D}/weather.json","w"))
with open(f"{D}/rest.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["team","days_rest"]); w.writerow(["Bravo Tech",5]); w.writerow(["Alpha State",7])
with open(f"{D}/crosscheck.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["gameId","sp_spread","fpi_spread","sasser_spread","corbie_spread"]); w.writerow([901,-12.0,-11.2,-13.0,-10.0])
with open(f"{D}/usage.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["player","team","pos","market","share","eff","games"])
    for r in [["A. Runner","Alpha State","RB","rush_yds",0.55,5.6,10],["A. Wideout","Alpha State","WR","rec_yds",0.27,9.0,10],
              ["A. Wideout","Alpha State","WR","receptions",0.27,0.66,10],["A. Passer","Alpha State","QB","pass_yds",0.95,7.9,10],
              ["B. Runner","Bravo Tech","RB","rush_yds",0.5,4.4,10],["D. Runner","Delta College","RB","rush_yds",0.6,5.0,10]]: w.writerow(r)
with open(f"{D}/props.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["gameId","player","market","line","overOdds","underOdds"])
    for r in [[901,"A. Runner","rush_yds",84.5,-115,-105],[901,"A. Wideout","rec_yds",61.5,-110,-110],[901,"A. Wideout","receptions",4.5,-130,110],
              [901,"A. Passer","pass_yds",235.5,-110,-110],[901,"B. Runner","rush_yds",62.5,-110,-110],[902,"D. Runner","rush_yds",88.5,-110,-110]]: w.writerow(r)
json.dump({"games":"games.json","advanced":"advanced.json","talent":"talent.json","returning":"returning.json",
           "ratings":"ratings.json","teams":"teams.json","venues":"venues.csv","injuries":"injuries.csv",
           "weather":"weather.json","schedule_rest":"rest.csv","crosscheck":"crosscheck.csv",
           "lines":"lines.json","lines_extra":"lines_flat.csv","usage":"usage.csv","props":"props.csv"},open(f"{D}/inputs.json","w"),indent=1)
print("samples written to", D)
