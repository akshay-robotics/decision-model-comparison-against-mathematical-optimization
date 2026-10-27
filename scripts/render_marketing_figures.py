"""Regenerate three social/GitHub figures from the published pilot dataset."""

import argparse
import json
import os
import tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'trafficlab-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BG, INK, MUTED, GREEN, ORANGE = '#f5f3ed', '#18332e', '#60756b', '#34735b', '#cc674b'
NAMES = {'gurobi': 'Gurobi', 'microsoft': 'Microsoft', 'jev': 'Jev 1.13', 'luna': 'Luna', 'sol-medium': 'Sol · medium'}
ORDER = list(NAMES)


def base(title, subtitle):
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    fig.text(.055, .935, 'TRAFFIC DECISION LAB  /  EARLY EXPERIMENT', color=GREEN, fontsize=12, weight='bold')
    fig.text(.055, .855, title, color=INK, fontsize=33, weight='bold')
    fig.text(.055, .802, subtitle, color=MUTED, fontsize=16)
    return fig


def card(fig, x, y, w, h, title, body, accent=GREEN):
    fig.add_artist(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012,rounding_size=.012',
                                  transform=fig.transFigure, facecolor='white', edgecolor='#dbe3d9'))
    fig.text(x+.018,y+h-.065,title,color=accent,fontsize=20,weight='bold')
    fig.text(x+.018,y+h-.12,body,color=INK,fontsize=17,linespacing=1.65,va='top')


def save(fig, output, name):
    for extension in ('png', 'svg', 'pdf'):
        path = output / f'{name}.{extension}'
        fig.savefig(path, facecolor=BG)
        if extension == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
    plt.close(fig)


def render(data, output):
    output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans', 'svg.fonttype':'none'})
    rows=json.loads((data/'episodes.json').read_text())
    old={r['controller']:r for r in rows if r['condition']=='original'}
    new={r['controller']:r for r in rows if r['condition']=='terminal'}
    fig=base('Can models make useful signal decisions?', 'Five controllers. Identical demand. One shared planning task.')
    card(fig,.065,.31,.255,.39,'Same input format','NS / EW queues\nArrival forecast\nSignal phase + timers\nLegal actions')
    card(fig,.375,.31,.25,.39,'Five controllers','Gurobi\nMicrosoft · Jev · Luna\nSol, medium reasoning\nChoose NS or EW')
    card(fig,.68,.31,.255,.39,'Same rules','15 s planning horizon\n120 s SUMO episode\n5 / 3 / 2 s signal timing\n78 cars · demand seed 7')
    for a,b in [(.33,.365),(.635,.67)]:
        fig.add_artist(FancyArrowPatch((a,.51),(b,.51),transform=fig.transFigure,arrowstyle='->',mutation_scale=24,color=GREEN,lw=2))
    fig.text(.065,.20,'TRAFFIC OUTCOMES',fontsize=13,weight='bold',color=GREEN)
    fig.text(.065,.15,'Completion, all-demand system time, travel / wait, approach coverage.',fontsize=17,color=INK)
    fig.text(.065,.085,'States diverge after different actions. Optimization quality is evaluated separately on frozen instances.',fontsize=13,color=MUTED)
    fig.text(.065,.045,'No new frozen optimization benchmark has been run for the revised objective.',fontsize=13,color=MUTED)
    save(fig,output,'01-experiment-overview')

    fig=base('Same traffic. A different objective.', 'The terminal-queue penalty changed outcomes unevenly.')
    axes=[fig.add_axes([.16,.25,.34,.46]),fig.add_axes([.60,.25,.34,.46])]
    y=np.arange(5)
    for ax,key,title,limit in [(axes[0],'completed','Completed cars / 78  ↑',78),(axes[1],'mean_system_seconds','Mean system time, seconds  ↓',44)]:
        before=[old[n][key] for n in ORDER]; after=[new[n][key] for n in ORDER]
        ax.set_facecolor(BG)
        ax.barh(y-.17,before,height=.29,color='#c7d0c5',label='Original objective')
        ax.barh(y+.17,after,height=.29,color=GREEN,label='Final-queue penalty')
        for i,(a,b) in enumerate(zip(before,after)):
            ax.text(a+.8,i-.17,f'{a:.0f}' if key=='completed' else f'{a:.2f}',va='center',fontsize=13,color=MUTED)
            ax.text(b+.8,i+.17,f'{b:.0f}' if key=='completed' else f'{b:.2f}',va='center',fontsize=13,color=INK,weight='bold')
        ax.set_ylim(4.6,-.6); ax.set_xlim(0,limit+8)
        ax.set_yticks(y,[NAMES[n] for n in ORDER] if ax is axes[0] else ['']*5,fontsize=16)
        ax.set_title(title,fontsize=18,color=INK,pad=16,loc='left')
        for spine in ax.spines.values(): spine.set_visible(False)
        ax.tick_params(axis='both',length=0,labelcolor=MUTED); ax.grid(axis='x',color='#e2e6dc',zorder=0)
        ax.set_axisbelow(True)
    axes[0].legend(loc='upper left',bbox_to_anchor=(0,-.10),ncol=2,frameon=False,fontsize=12)
    fig.text(.055,.12,'Changing the objective changed controller behavior, but did not improve every controller.',fontsize=18,color=INK,weight='bold')
    fig.text(.055,.055,'One seed · one episode per condition/model · 15 s planning · 120 s simulation. System time includes all generated cars through cutoff.',fontsize=11,color=MUTED)
    save(fig,output,'02-before-after-results')

    fig=base('Give unfinished queues a cost.', 'One additional term. The same revised question for every model.')
    card(fig,.065,.36,.255,.34,'Accumulated queues','Add NS + EW queues\nafter each second.\nIncludes the final step.')
    card(fig,.375,.36,.25,.34,'Switching cost','0.5 × initiated switches\nSafety timings remain\nthe same.')
    card(fig,.68,.36,.255,.34,'Final-queue cost','10 × cars still queued\nat the planning boundary.\nAdded once.',accent=ORANGE)
    fig.text(.33,.49,'+',fontsize=34,color=INK); fig.text(.635,.49,'+',fontsize=34,color=INK)
    fig.text(.065,.24,'J = Σ(q_NS + q_EW) + 0.5 × switches + 10 × final queue',fontsize=26,color=INK,weight='bold')
    fig.text(.065,.15,'Example: 3 cars left in the modeled final queue → +30 cost units.',fontsize=18,color=ORANGE)
    fig.text(.065,.075,'Weight 10 was fixed before the rerun. A modeled queue penalty is not a direct count of completed SUMO trips.',fontsize=13,color=MUTED)
    save(fig,output,'03-objective-explained')
    print('Rendered three figures as PNG, SVG, and PDF.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data/published/traffic-objective-v2')
    parser.add_argument('--output',type=Path,default=ROOT/'media')
    args=parser.parse_args(); render(args.data,args.output)
