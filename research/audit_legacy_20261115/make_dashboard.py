"""Create a read-only audit dashboard from derived CSVs; not a production tracker."""
from pathlib import Path
import csv,json
from artifact_tool import Workbook,SpreadsheetFile
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'SportsEdge_Audit_Dashboard.xlsx'
metrics=json.load(open(ROOT/'results/audit_metrics.json'))

def load(name):
    with open(ROOT/name,newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write_sheet(wb,name,headers,rows,widths=None):
    sh=wb.worksheets.add(name)
    data=[headers]+[[row.get(k) for k in headers] if isinstance(row,dict) else list(row) for row in rows]
    ncol=len(headers);nrow=len(data)
    sh.get_range_by_indexes(0,0,nrow,ncol).values=data
    sh.freeze_panes.freeze_rows(1)
    sh.get_range_by_indexes(0,0,1,ncol).format={"fill":"#253858","font":{"bold":True,"color":"#FFFFFF"},"row_height":30}
    for i,wd in enumerate(widths or [19]*ncol):sh.get_range_by_indexes(0,i,max(2,nrow),1).format.column_width=wd
    return sh

wb=Workbook.create()
over=wb.worksheets.add('Overview')
over.get_range('A1:H1').merge();over.get_range('A1').values=[['SPORTSEDGE | INDEPENDENT MODEL AUDIT']]
over.get_range('A1:H1').format={"fill":"#1C2B40","font":{"bold":True,"color":"#FFFFFF","size":16},"row_height":38}
over.get_range('A3:H3').merge();over.get_range('A3').values=[['November 14, 2026 • PAPER / 0u • no model or historical input modified']]
over.get_range('A3:H3').format={"font":{"color":"#506070","size":11}}
for c,w in [('A',23),('B',23),('C',23),('D',23),('E',23),('F',23),('G',23),('H',23)]:over.get_range(f'{c}:{c}').format.column_width=w
kpis=[('Original Nov 11 card','65 frozen selections'),('Record','31 W / 34 L'),('Hypothetical P/L','−1.58u'),('ROI','−2.43%'),('Model mean probability','60.5%'),('Observed win percentage','47.7%'),('Brier / log loss','0.2837 / 0.7668'),('Source games','10 (not 65 independent)'),('Model-doubted held out','10 picks: 5–5, −0.47u'),('Archived 20 largest','Provisional; no original per-quote receipts')]
for j,(label,val) in enumerate(kpis,start=5):
    over.get_range(f'A{j}:C{j}').merge();over.get_range(f'A{j}').values=[[label]]
    over.get_range(f'D{j}:F{j}').merge();over.get_range(f'D{j}').values=[[val]]
    if j%2:over.get_range(f'A{j}:F{j}').format.fill='#EFF2F7'
    over.get_range(f'A{j}').format.font.bold=True
for rr,t in [(17,'DO NOT INTERPRET PAPER ROI AS EXECUTED BETTING ROI'),(19,'Row-level quote timestamps, event IDs, model hash and close evidence are absent.'),(20,'1H ML EV is push-aware: CONDITIONAL win probability is not the unconditional event win rate.'),(21,'The 188 priced sides were not 188 recommended bets. Original CARD 65 and DOUBTED 10 remain separate.'),(22,'Nov 11 finals and 1H scores sourced after games from Warren Nolan. No prospective variables were constructed from finals.'),(23,'No model, feature weight, qualification threshold, or historical selection was changed.')]:
    over.get_range(f'A{rr}:H{rr}').merge();over.get_range(f'A{rr}').values=[[t]]
over.get_range('A17:H17').format={"fill":"#FCE8E6","font":{"bold":True,"color":"#A61B1B"},"row_height":28}

# CARD with native formulas for book break-even p, probability edge, and payoff.
source_card=load('results/nov11_original_65_card_graded.csv')
source_doubted=load('results/nov11_10_doubted_graded_separately.csv')
def card_tab(name,source):
    header=['Game','Pick','Market','Odds','Model p','Book break-even p','Raw edge (pp)','Recorded EV','Result','Flat 1u P/L','Original category','Quote status']
    rows=[[r['game'],r['pick'],r['bet_type'].split('|')[0],int(r['price']),float(r['model_p']),None,None,float(r['ev']),r['result'],None,r['origin'],r['point_in_time_status']] for r in source]
    sh=write_sheet(wb,name,header,rows,[32,33,18,12,13,19,18,14,11,13,18,33])
    n=len(rows)+1
    sh.get_range('F2').formulas=[['=IF(D2>0,100/(100+D2),-D2/(100-D2))']]
    sh.get_range('G2').formulas=[['=(E2-F2)*100']]
    sh.get_range('J2').formulas=[['=IF(I2="W",IF(D2>0,D2/100,100/(-D2)),IF(I2="L",-1,0))']]
    for c in ('F','G','J'):sh.get_range(f'{c}2:{c}{n}').fill_down()
    for col in ('E','F','H'):sh.get_range(f'{col}2:{col}{n}').set_number_format('0.00%')
    for col in ('G','J'):sh.get_range(f'{col}2:{col}{n}').set_number_format('0.00')
    sh.get_range(f'I2:I{n}').conditional_formats.add_custom('=I2="L"',{'font':{'color':'#BE1E2D'}})
    sh.get_range(f'I2:I{n}').conditional_formats.add_custom('=I2="W"',{'font':{'color':'#166534'}})
    return sh
card_tab('Original 65 Card',source_card)
card_tab('Doubted 10 Held',source_doubted)
old=load('results/archived_top20_original_odds_and_projection.csv')
olds=[[int(r['archived_rank']),r['game'],r['pick'],int(r['american_odds']),float(r['model_p']),float(r['book_break_even_p']),100*float(r['raw_probability_edge']),float(r['EV_recalculated']),r['archive_result'],r['audit_result'],r['severity']] for r in old]
s=write_sheet(wb,'Archived Top 20',['Rank','Match','Pick','Odds','Model p','Book break-even','Raw edge (pp)','Original EV','Archive result','Audit result','Severity'],olds,[9,38,30,12,13,17,17,15,16,15,13]);s.get_range('E2:F21').set_number_format('0.00%');s.get_range('H2:H21').set_number_format('0.0%')
gaps=metrics['market_disagreement'];rowz=[]
for r in gaps:
 rowz.append([r['game'],r['projection_home_score'],r['projection_away_score'],r['total_model'],r['total_book'],r['total_model_minus_book_pts'],r['home_margin_projection'],r['book_home_margin'],r['margin_model_minus_book_pts'],r['n_original_card']])
write_sheet(wb,'Market Gaps',['Game','Model home','Model away','Model total','Book total','Gap total pts','Model margin','Book margin','Gap margin pts','Card n'],rowz,[32,14,14,14,14,15,15,15,17,9])
cal=metrics['results']['calibration_by_bin'];rows=[[r['range'],r['n'],r['mean_p'],r['actual_win_rate']] for r in cal]
s=write_sheet(wb,'Calibration',['Model p bucket','N original card','Mean predicted p','Actual hit rate'],rows,[19,22,24,20]);s.get_range(f'C2:D{len(rows)+1}').set_number_format('0.0%')
perf=metrics['results']['original_card_by_game'];rows=[[g,v['rows'],v['wins'],v['losses'],v['net_units'],v['roi_per_unit']] for g,v in perf.items()]
s=write_sheet(wb,'Games Performance',['Game','Qualified selections','Wins','Losses','Hypothetical units','ROI'],rows,[33,23,13,13,20,15]);s.get_range(f'F2:F{len(rows)+1}').set_number_format('0.0%')
s=write_sheet(wb,'Source and Caveats',['Item','Value'],[
 ['Source', 'original census.json 716 rows, SHA 17d54f23d1be2caa326fe4aa3b50d0a31fb9ba2619f62e899553501a8bdc576e'],
 ['Source','original Nov 11 priced CSV 188 rows, SHA 331e03c2d2b8e0f065ab7086721c489b23a48f5c2449df59ac3b3233e3210661'],
 ['Source','original Nov 11 board CSV 96 markets, SHA a29a3f977b09c7a99284d0fbdad8c2f16d5c00c99ea2483f0149626bf81f77ec'],
 ['Finals','https://www.warrennolan.com/basketball/2027/scores-live?date=2026-11-11&type=All+Games'],
 ['Unverified','Per-quote receipt, event ID, accepted sportsbook fill, closing odds, forward-rule hash'],
 ['Status','PAPER / 0u and exploratory, not official wagers'],
 ['No changes','Frozen model, original selection record, and historical predictions unchanged'],
 ['Risk','10 game clusters in 65 rows; data too small for model improvement decisions'],
 ],[24,85])
SpreadsheetFile.export_xlsx(wb).save(str(OUT))
print(str(OUT),OUT.stat().st_size)
print(wb.inspect({'kind':'table','range':'Overview!A4:F10','include':'values','table_max_rows':8,'table_max_cols':6}).ndjson[:2000])
