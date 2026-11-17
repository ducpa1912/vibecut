"""Measure cold/cached load and incremental RSS in isolated GPU processes."""
import argparse
import gc
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
parser = argparse.ArgumentParser()
parser.add_argument('engine', choices=['coreml','pytorch'])
parser.add_argument('model', type=Path)
parser.add_argument('evidence', type=Path)
args = parser.parse_args()
import numpy as np
from duckcore.engine.textfill.coreml_fill import BUCKETS, LamaCoreMLFiller
from duckcore.engine.textfill.torch_fill import LamaGpuFiller

def rss():
    return int(subprocess.check_output(['ps','-o','rss=','-p',str(__import__('os').getpid())])) * 1024


def metal_memory():
    try:
        import torch
        return {'mps_allocated_bytes': torch.mps.current_allocated_memory(),
                'mps_driver_bytes': torch.mps.driver_allocated_memory()}
    except Exception:
        return {}

args.evidence.mkdir(parents=True, exist_ok=True)
rows = []
for attempt in range(2):
    start = time.perf_counter()
    filler = (LamaCoreMLFiller(args.model, cache=args.evidence/'load-cache')
              if args.engine=='coreml' else LamaGpuFiller(args.model))
    rows.append({'phase':f'load-{attempt+1}', 'seconds':time.perf_counter()-start,
                 'rss_bytes':rss(), 'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    del filler
    gc.collect()
    if args.engine == 'pytorch':
        from duckcore.engine.textfill.torch_fill import release_gpu_memory
        release_gpu_memory()
    (args.evidence/f'{args.engine}-memory.json').write_text(json.dumps(rows,indent=2))
filler = (LamaCoreMLFiller(args.model, cache=args.evidence/'load-cache')
          if args.engine=='coreml' else LamaGpuFiller(args.model))
for h,w in BUCKETS:
    image=np.full((h,w,3),100,np.uint8);mask=np.zeros((h,w),bool);mask[h//3:2*h//3,w//3:2*w//3]=True
    start=time.perf_counter();filler.fill(image,mask)
    rows.append({'phase':f'bucket-{h}x{w}', 'seconds':time.perf_counter()-start,
                 'rss_bytes':rss(), 'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 **(metal_memory() if args.engine == 'pytorch' else {})})
    (args.evidence/f'{args.engine}-memory.json').write_text(json.dumps(rows,indent=2))
    print(rows[-1],flush=True)
