"""Validate the small public dataset, source archives, posts, and media assets."""
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/published/traffic-objective-v2'
def sha(value): return hashlib.sha256(value).hexdigest()
def main():
    checks=json.loads((DATA/'checksums.json').read_text())
    for name,digest in checks.items(): assert sha((DATA/name).read_bytes())==digest,name
    rows=json.loads((DATA/'episodes.json').read_text())
    assert len(rows)==10 and len(list(csv.DictReader((DATA/'episodes.csv').open())))==10
    assert len({r['route_sha256'] for r in rows})==1
    for r in rows:
        assert r['generated']==78 and r['completed']+r['unfinished']==78
        assert r['planning_horizon']==15 and r['simulation_duration']==120
        assert r['objective']['terminal_queue_penalty']==(0 if r['condition']=='original' else 10)
        assert sum(a['completed'] for a in r['by_approach'].values())==r['completed']
    data=json.loads((DATA/'replays.json').read_text())['episodes']
    assert len(data)==5
    schedules=[]
    for episode in data:
        demand=episode['demand']; result=episode['result']
        schedules.append([(d['id'],d['depart']) for d in demand])
        assert len(demand)==78 and len(episode['frames'])==240
        assert sum(d['arrival'] is not None and d['arrival']<=120 for d in demand)==result['completed']
        total=sum(min(120,d['arrival'] if d['arrival'] is not None else 120)-d['depart'] for d in demand)
        assert abs(total/78-result['mean_system_seconds'])<=.001
        assert abs(total-result['total_system_seconds'])<=.002
    assert all(s==schedules[0] for s in schedules)
    for archive in DATA.glob('source-*.zip'):
        with zipfile.ZipFile(archive) as z:
            meta=json.loads(z.read('snapshot.json'))
            source={p:z.read(p).decode() for p in meta['core_files']}
            digest=sha(json.dumps(source,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
            assert digest==meta['core_source_sha256'],archive.name
            assert not any(Path(p).name=='.env' for p in z.namelist())
    posts=json.loads((ROOT/'marketing/thread.json').read_text()); assert len(posts)==5
    # Twitter-text's single-weight Unicode ranges; no URLs occur in this copy.
    def weight(char):
        n=ord(char)
        return 1 if n<=0x10ff or 0x2000<=n<=0x200d or 0x2010<=n<=0x201f or 0x2032<=n<=0x2037 else 2
    for post in posts:
        assert sum(weight(c) for c in post['text'])<=280
        if post['attachment']: assert (ROOT/post['attachment']).is_file()
    for stem in ['01-experiment-overview','02-before-after-results','03-objective-explained']:
        for ext in ['png','svg','pdf']: assert (ROOT/'media'/f'{stem}.{ext}').is_file()
        header=(ROOT/'media'/f'{stem}.png').read_bytes()[:24]
        assert struct.unpack('>II',header[16:24])==(1920,1080)
    proof=json.loads((ROOT/'media/verification.json').read_text())
    video=ROOT/'media/demo.mp4'
    assert proof['full_decode_verified'] and 30<=proof['duration_seconds']<=45
    assert proof['sha256']==sha(video.read_bytes()) and video.stat().st_size<10*1024*1024
    assert proof['codec']=='H.264' and proof['pixel_format']=='yuv420p'
    for p in list(DATA.glob('*.json'))+list((ROOT/'marketing').glob('*.md')):
        assert not re.search(r'sk-or-v1-[A-Za-z0-9]{24,}',p.read_text()),p
    print('Release verified: 10 summaries, 5 replay traces, 3 source archives, 5 posts, 3 graphics, and a decoded MP4.')
if __name__=='__main__': main()
