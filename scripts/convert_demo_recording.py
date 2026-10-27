"""Convert a browser-canvas recording to a standard, fast-start H.264 MP4."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]
def convert(source,output):
    output.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg,'-y','-nostdin','-loglevel','error','-i',str(source),'-an',
                    '-vf','fps=24,scale=out_range=tv,format=yuv420p','-color_range','tv',
                    '-c:v','libx264','-preset','medium','-crf','22',
                    '-profile:v','high','-level:v','4.0','-movflags','+faststart','-map_metadata','-1',str(output)],check=True)
    decoded=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-i',str(output),'-f','null','-'],capture_output=True,text=True)
    if decoded.returncode: raise RuntimeError(decoded.stderr)
    m=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',decoded.stderr)
    duration=int(m[1])*3600+int(m[2])*60+float(m[3])
    assert 30<=duration<=45 and '1920x1080' in decoded.stderr and 'yuv420p' in decoded.stderr
    assert output.stat().st_size<10*1024*1024
    subprocess.run([ffmpeg,'-y','-loglevel','error','-ss','22','-i',str(output),'-frames:v','1',str(output.with_name('demo-poster.png'))],check=True)
    proof={'source':'Actual browser canvas capture using MediaRecorder; re-encoded without changing the scene sequence.',
           'duration_seconds':duration,'width':1920,'height':1080,'fps':24,'codec':'H.264','pixel_format':'yuv420p',
           'audio':False,'size_bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
           'full_decode_verified':True,'encoder':'imageio-ffmpeg '+imageio_ffmpeg.__version__}
    output.with_name('verification.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('recording',type=Path);p.add_argument('--output',type=Path,default=ROOT/'media/demo.mp4');a=p.parse_args();convert(a.recording,a.output)
