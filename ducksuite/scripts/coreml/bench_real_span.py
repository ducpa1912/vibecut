"""Compare GPU fillers on every frame of a short real-source crop; scratch only."""
import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from duckcore import media
from duckcore.engine.textfill.coreml_fill import LamaCoreMLFiller
from duckcore.engine.textfill.torch_fill import LamaGpuFiller
from duckcore.engine.textfill import _GpuOrCpu

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('torch', type=Path)
parser.add_argument('package', type=Path)
parser.add_argument('evidence', type=Path)
args = parser.parse_args()
args.evidence.mkdir(parents=True, exist_ok=True)
# Two real subtitle regions active in the opening second. This is a raw crop
# benchmark, not a claim about a whole render or the ink-shaped production mask.
x,y,w,h = 270,840,540,240
command = [media.ffmpeg(), '-v','error','-ss','0.2','-i',str(args.source),
           '-t','0.5','-vf',f'crop={w}:{h}:{x}:{y},fps=30',
           '-pix_fmt','rgb24','-f','rawvideo','-']
frames=np.frombuffer(subprocess.check_output(command),np.uint8).reshape(-1,h,w,3)
mask=np.zeros((h,w),bool);mask[35:98,160:360]=True;mask[135:205,50:490]=True
result={'frames':len(frames),'crop':[x,y,w,h],'engines':{}}
outputs={}
for label, factory in [('pytorch',lambda:LamaGpuFiller(args.torch)),
                       ('coreml',lambda:_GpuOrCpu(
                           lambda:LamaCoreMLFiller(args.package,cache=args.evidence/'cache'),
                           lambda:LamaGpuFiller(args.torch)))]:
    start=time.perf_counter();filler=factory();load=time.perf_counter()-start
    start=time.perf_counter();outputs[label]=np.stack([filler.fill(frame,mask) for frame in frames])
    result['engines'][label]={'load_s':load,'span_s':time.perf_counter()-start,
                            'fell_back': not getattr(filler,'cache_valid',True),
                            'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
diff=np.abs(outputs['pytorch'].astype(np.int16)-outputs['coreml'].astype(np.int16))
result['max_diff']=int(diff.max());result['mean_hole']=float(diff[:,mask].mean())
result['per_frame_max']=[int(d.max()) for d in diff]
(args.evidence/'real-span.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
