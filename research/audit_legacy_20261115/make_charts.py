import json,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
r=json.load(open(ROOT/'results/audit_metrics.json'))
cal=r['results']['calibration_by_bin'];fig,ax=plt.subplots(figsize=(8,6))
ax.plot([0,1],[0,1],linestyle='--',alpha=.8,label='Perfect calibration')
ax.scatter([x['mean_p'] for x in cal],[x['actual_win_rate'] for x in cal],s=[max(40,5*x['n']) for x in cal],alpha=.8,label='Nov 11 card bins')
for x in cal:ax.annotate(f"n={x['n']}",(x['mean_p'],x['actual_win_rate']),xytext=(5,5),textcoords='offset points',fontsize=8)
ax.set(xlabel='Mean recorded win probability',ylabel='Observed win percentage',title='SportsEdge — Nov 11 late CBB calibration (65 selections)',xlim=(0,1),ylim=(0,1));ax.legend();fig.tight_layout();fig.savefig(ROOT/'results/nov11_reliability_diagram.png',dpi=160);plt.close(fig)
games=r['results']['original_card_by_game'];keys=list(games);vals=[games[k]['net_units'] for k in keys]
fig,ax=plt.subplots(figsize=(11,6));ax.barh(range(len(keys)),vals);ax.set_yticks(range(len(keys)),keys);ax.axvline(0,linestyle='--');ax.set(xlabel='Hypothetical units at original recorded prices (flat 1u)',title='Nov 11 original 65 selections grouped by 10 games');fig.tight_layout();fig.savefig(ROOT/'results/nov11_game_cluster_units.png',dpi=160);plt.close(fig)
