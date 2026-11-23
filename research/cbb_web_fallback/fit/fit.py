# Fit HCA and residual SDs from 2026-27 finals (CBS scoreboards 11/18-11/21) vs Barttorvik 2027 ratings.
# LEAKAGE: ratings captured 11/23 include these games -> in-sample; SDs are a LOWER bound (true OOS SDs larger).
import statistics as st, math
R={'Michigan St.':(119.9,94.7,68.6),'Wichita St.':(113.3,99.6,70.2),'New Mexico':(113.8,101.6,70.7),'Kent St.':(104.7,108.2,69.4),
'LSU':(117.4,98.5,70.9),'Queens':(112.7,116.6,72.5),'Little Rock':(106.2,115.0,69.7),'Fordham':(109.3,104.1,69.0),'Portland':(107.2,108.9,70.7),
'Syracuse':(114.1,103.2,69.4),'N. Illinois':(111.7,115.8,64.6),'Bowling Green':(109.9,112.3,69.0),'Drake':(108.3,108.7,68.2),'Missouri St.':(101.5,109.4,67.4),
'Middle Tenn.':(106.7,107.6,67.6),'Indiana St.':(101.7,109.9,70.5),'UTRGV':(101.9,108.6,66.1),'Austin Peay':(104.8,107.3,69.6),'Central Arkansas':(106.7,107.5,69.6),
'Jacksonville':(106.1,113.4,66.8),'Longwood':(103.9,110.0,70.9),'ETSU':(104.9,106.1,66.0),'Penn':(108.8,105.8,72.5),'La Salle':(107.7,109.5,69.2),
'South Florida':(112.2,104.8,71.5),'George Mason':(110.7,100.7,66.8),'San Diego':(110.6,108.2,66.6),'UC Irvine':(105.6,99.3,70.2),'UTSA':(106.7,110.1,70.7),
'Northeastern':(108.3,114.1,70.7),'Southern Miss':(103.0,110.6,71.4),'Winthrop':(104.5,114.3,73.7),'Wofford':(105.8,114.8,69.9),'S. Illinois':(103.9,106.9,71.2),
'East Carolina':(104.3,106.8,70.6),'UMass':(102.7,104.0,70.5),'UNCW':(114.7,109.3,68.7),'Brown':(98.5,106.7,68.2),'Vermont':(108.7,110.9,64.9),
'Mercer':(104.6,111.4,70.8),'LMU':(111.4,109.3,68.1),'Michigan':(118.9,96.7,73.0),'Villanova':(117.2,99.4,69.2),'Elon':(105.8,109.5,68.0),
'Northern Arizona':(107.1,117.8,65.2),'Cal Poly':(108.7,111.5,72.9),'Radford':(102.0,110.5,69.8),'Chattanooga':(108.7,112.8,68.3),'Presbyterian':(104.9,112.4,68.1),
'Tennessee Tech':(110.1,110.7,73.0),'TAMUCC':(100.1,105.0,68.6),'Oral Roberts':(105.4,111.6,69.3),'Valparaiso':(107.8,106.5,68.4),'Troy':(106.6,107.4,65.4),
'Bradley':(100.1,104.9,66.1),'Pacific':(106.6,102.8,67.4),'Duke':(119.8,92.9,71.8),'Washington St.':(109.8,108.4,67.7),'Denver':(104.3,112.0,68.4),
'E. Michigan':(106.5,106.6,66.4),'Florida St.':(115.8,100.3,72.3),'Oklahoma St.':(118.0,102.1,72.0),'Minnesota':(113.5,98.2,66.1),'Temple':(109.7,107.9,68.7),
'UAB':(110.4,106.7,70.1),'George Washington':(112.3,99.3,69.4),'SF Austin':(107.7,106.0,68.1),'Northwestern':(109.9,103.3,66.0),'Virginia Tech':(119.7,100.1,69.7),
'Rhode Island':(108.9,106.0,68.4),'Liberty':(109.5,107.7,65.7),'UT Martin':(99.1,107.7,67.7),'Dayton':(110.1,102.0,68.5),'Utah':(105.8,102.3,67.2),
'North Texas':(107.6,104.2,67.6),'Appalachian St.':(103.5,105.7,65.0),'Central Michigan':(105.8,111.3,69.3),'Pittsburgh':(113.3,100.6,69.5),'Coastal Carolina':(103.4,109.3,70.1),
'Tennessee':(117.2,95.2,68.1),'Georgia St.':(109.0,112.4,66.6),'Jacksonville St.':(105.0,109.9,66.1),'Harvard':(106.1,106.0,66.1),'Monmouth':(104.2,107.6,69.7),
'Princeton':(105.9,106.8,66.5),'Murray St.':(111.9,100.9,74.3),'Wisconsin':(112.0,99.9,69.6),'Oakland':(106.0,113.1,67.8),'Purdue':(119.0,99.0,65.3),
'SE Louisiana':(102.6,113.1,68.2),'Kennesaw St.':(106.9,104.4,73.7),'Saint Joseph\'s':(102.3,99.9,71.7),'Drexel':(101.6,107.4,66.5),'UMKC':(105.0,113.4,67.9),
'Iona':(101.5,107.4,66.6),'W. Kentucky':(109.7,103.3,71.5),'Richmond':(110.2,105.3,69.1),'W. Michigan':(110.4,108.8,67.5),'Iowa':(118.8,100.4,64.1),
'Xavier':(114.8,98.6,73.2),'Tulsa':(111.0,102.8,69.4),'Mississippi St.':(116.1,101.2,69.8),'UT Arlington':(102.9,106.0,70.9),'Campbell':(109.1,112.5,66.2),
'Kansas St.':(112.7,102.6,71.5),'Utah Valley':(110.6,105.6,70.6),'Lipscomb':(104.3,110.1,71.8),'Alabama A&M':(102.9,112.0,67.8),'South Alabama':(107.3,113.3,64.2),
'SMU':(116.3,100.5,72.1),'UCF':(115.7,104.6,70.7),'Vanderbilt':(118.9,95.6,69.6),'Georgia':(119.3,101.7,71.1),'Georgia Tech':(109.5,106.0,72.2),
'Kentucky':(118.3,103.6,68.6),'Indiana':(121.1,100.6,68.8),'Marshall':(102.9,106.4,72.2),'North Carolina':(114.4,98.9,71.7),'Sam Houston':(108.5,105.4,72.4),
'Boise St.':(110.8,102.6,71.9),'NC State':(121.9,102.4,68.8),'Seton Hall':(111.7,98.3,66.4),'Alabama St.':(104.6,112.2,67.2),'Fresno St.':(106.5,107.9,71.2),
'Saint Louis':(116.4,102.1,71.6),'Saint Mary\'s':(116.6,100.7,71.3),'Florida':(124.6,96.1,68.7),'West Virginia':(116.7,98.7,67.1),'Notre Dame':(118.0,103.1,69.1),
'Auburn':(117.3,100.1,69.0),'Buffalo':(105.9,110.1,69.4),'St. Bonaventure':(110.6,103.3,68.0),'Montana St.':(109.3,104.0,67.8),'High Point':(114.2,99.8,69.5),
'Butler':(111.2,102.6,73.6),'Robert Morris':(102.6,108.2,68.0),'Toledo':(106.5,106.9,70.9),'Charleston':(111.4,110.2,70.5),'Tulane':(108.5,111.1,69.5),
'Louisiana Tech':(99.5,106.9,67.5),'Ga. Southern':(101.2,110.5,72.3),'Houston Christian':(103.3,111.9,68.6),'SEMO':(101.9,110.5,71.1),'St. Thomas':(112.3,110.7,67.0),
'Stetson':(104.4,113.7,67.6),'Louisville':(119.5,98.2,70.5),'Southern Utah':(104.1,111.8,71.2),'Texas':(120.9,98.6,69.5),'Texas A&M':(119.1,98.5,74.3),
'TCU':(114.3,100.0,69.7),'Rutgers':(116.7,103.7,69.8),'UNLV':(111.3,106.7,71.6),'Oregon':(119.3,102.7,68.9),'Oregon St.':(116.7,105.2,73.3),
'UCSB':(115.2,105.7,66.9),'Pepperdine':(111.1,111.6,69.6),'UTEP':(106.8,105.5,67.7),'New Mexico St.':(106.4,108.7,67.4),'Sacramento St.':(107.1,108.6,72.5),
'Stanford':(109.5,101.4,67.6),'VCU':(115.6,100.8,69.2),'Santa Clara':(113.2,101.8,72.8),'Houston':(124.4,93.4,67.8),'Kansas':(122.6,93.9,73.0),
'Chicago St.':None}
G=[ # away,as,home,hs,neutral   (11/18-11/21, both teams rated)
('Michigan St.',91,'Detroit',70,0),('New Mexico',60,'Wichita St.',85,0),('Queens',75,'LSU',106,0),('Little Rock',87,'Jacksonville',99,0),
('Fordham',87,'Portland',69,1),('N. Illinois',86,'Bowling Green',68,0),('Drake',65,'Missouri St.',67,0),('Middle Tenn.',69,'Indiana St.',59,1),
('UTRGV',79,'Austin Peay',73,0),('Central Arkansas',82,'Jacksonville',67,1),('Longwood',68,'ETSU',74,0),('Penn',83,'La Salle',73,0),
('South Florida',62,'George Mason',73,0),('San Diego',67,'UC Irvine',64,1),('Northeastern',82,'Southern Miss',80,1),('Winthrop',86,'Wofford',91,0),
('S. Illinois',85,'East Carolina',69,1),('Brown',71,'Vermont',84,0),('LMU',80,'Pacific',73,1),('Michigan',73,'Villanova',79,1),
('Northern Arizona',88,'Cal Poly',89,0),('Radford',73,'Chattanooga',65,0),('Presbyterian',69,'Tennessee Tech',97,0),('TAMUCC',74,'Oral Roberts',78,0),
('Valparaiso',77,'Troy',72,1),('Bradley',62,'Pacific',63,0),('Duke',78,'Washington St.',74,1),('Denver',68,'E. Michigan',70,1),
('Oklahoma St.',70,'Minnesota',85,1),('Temple',85,'Middle Tenn.',76,1),('UAB',81,'George Washington',76,1),('Indiana St.',76,'SF Austin',86,1),
('Northwestern',70,'Virginia Tech',87,1),('Rhode Island',68,'Liberty',71,1),('UT Martin',76,'S. Illinois',73,1),('Dayton',63,'Utah',46,1),
('North Texas',75,'Appalachian St.',81,0),('Central Michigan',82,'Pittsburgh',104,0),('Coastal Carolina',51,'Tennessee',78,0),('Georgia St.',77,'Jacksonville St.',82,0),
('Monmouth',64,'Princeton',75,0),('Murray St.',70,'Wisconsin',53,1),('Oakland',49,'Purdue',95,0),('SE Louisiana',59,'Kennesaw St.',96,0),
("Saint Joseph's",64,'Drexel',75,0),('UMKC',61,'Iona',62,0),('W. Kentucky',82,'Richmond',68,1),('Iowa',83,'Xavier',65,0),('Tulsa',61,'Mississippi St.',72,1),
('Campbell',80,'Kansas St.',70,0),('East Carolina',79,'Utah Valley',90,1),('Lipscomb',69,'Alabama A&M',85,0),('South Alabama',55,'SMU',101,0),
('UCF',74,'Vanderbilt',82,0),('Georgia',88,'Georgia Tech',82,0),('Kentucky',76,'Indiana',90,1),('Marshall',72,'North Carolina',88,0),
('Sam Houston',83,'Boise St.',69,0),('NC State',81,'Seton Hall',87,1),('Alabama St.',68,'Fresno St.',80,0),('Saint Louis',78,"Saint Mary's",95,0),
('Florida',85,'West Virginia',72,1),('Notre Dame',78,'Auburn',73,1),('NC State',93,'Murray St.',83,1),('Buffalo',69,'St. Bonaventure',78,0),
('Montana St.',74,'High Point',85,0),('Northeastern',77,'Butler',84,0),('Robert Morris',76,'Toledo',83,0),('Charleston',70,'Drake',86,0),
('Tulane',67,'Louisiana Tech',74,0),('Ga. Southern',86,'Houston Christian',79,0),('SEMO',61,'St. Thomas',93,0),('Stetson',69,'Louisville',83,0),
('Southern Utah',68,'Texas',92,0),('Texas A&M',97,'TCU',92,0),('Rutgers',89,'UNLV',70,1),('Wisconsin',69,'Seton Hall',74,1),('Oregon',71,'Oregon St.',82,1),
('UCSB',88,'Pepperdine',80,0),('UTEP',84,'New Mexico St.',69,0),('Sacramento St.',65,'Stanford',78,0),('VCU',83,'Santa Clara',77,0),('Houston',92,'Kansas',83,1),
]
G=G[1:]  # Detroit unrated; dropped
LE,LT=107.3,69.3
rm,rt,rtt,home_res=[],[],[],[]
for a,sa,h,sh,n in G:
  A,H=R[a],R[h]; poss=A[2]*H[2]/LT
  pa=A[0]*H[1]/LE*poss/100; ph=H[0]*A[1]/LE*poss/100
  if not n: home_res.append((sh-sa)-(ph-pa))
rows=[]
HCA=st.mean(home_res)
for a,sa,h,sh,n in G:
  A,H=R[a],R[h]; poss=A[2]*H[2]/LT
  pa=A[0]*H[1]/LE*poss/100-(0 if n else HCA/2); ph=H[0]*A[1]/LE*poss/100+(0 if n else HCA/2)
  rm.append((sh-sa)-(ph-pa)); rt.append((sh+sa)-(ph+pa)); rtt+= [sh-ph, sa-pa]
sd=lambda x:math.sqrt(sum(v*v for v in x)/len(x))
print(f"n={len(G)} (non-neutral {len(home_res)})  HCA={HCA:.2f} (se {st.stdev(home_res)/math.sqrt(len(home_res)):.2f})")
print(f"margin SD={sd(rm):.2f} bias={st.mean(rm):+.2f}  total SD={sd(rt):.2f} bias={st.mean(rt):+.2f}  TT SD={sd(rtt):.2f}")
