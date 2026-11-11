import subprocess, numpy as np, os, time, json
D=os.path.expanduser("~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite")
SRC=D+"/imports/315aafc9-c76f-4c04-a408-7c37c008fbc3/source.mp4"
E=json.load(open(D+"/projects/prj_e95348a97316/edits/ed_38a4c36a3aae.json"))
W,H=540,960
t=time.time()
p=subprocess.Popen(["ffmpeg","-v","error","-i",SRC,"-vf",f"scale={W}:{H},format=gray","-f","rawvideo","-"],stdout=subprocess.PIPE)
buf=[]; i=0; ev=[]
def dil(m):
    o=m.copy(); o[1:]|=m[:-1]; o[:-1]|=m[1:]; o[:,1:]|=m[:,:-1]; o[:,:-1]|=m[:,1:]; return o
while True:
    b=p.stdout.read(W*H)
    if len(b)<W*H: break
    a=np.frombuffer(b,np.uint8).reshape(H,W).astype(np.int16)
    g=(np.abs(np.diff(a,axis=1))[:-1,:]+np.abs(np.diff(a,axis=0))[:,:-1])>36
    buf.append(g); buf=buf[-7:]
    if len(buf)==7:
        c=i-3  # centre frame index: onset at c
        after=buf[3]&buf[4]&buf[5]&buf[6]
        before=dil(buf[0]|buf[1]|buf[2])
        on=after&~before
        before2=buf[0]&buf[1]&buf[2]&buf[3]
        off=before2&~dil(buf[4]|buf[5]|buf[6])
        for kind,m in (("on",on),("off",off)):
            r=m.sum(axis=1); band=np.convolve(r,np.ones(30),"same"); y=int(band.argmax())
            ev.append((c/30 if kind=="on" else (c)/30, 0 if kind=="on" else 1, int(band.max()), y))
    i+=1
ev=np.array(ev); np.save(os.path.dirname(os.path.abspath(__file__))+"/onset.npy",ev)
print("sec %.1f"%(time.time()-t))
on=ev[ev[:,1]==0]
for thr in (150,250,400):
    hot=on[on[:,2]>=thr]
    # group into events 0.2 s apart
    times=[]; 
    for tm in hot[:,0]:
        if not times or tm-times[-1][-1]>0.2: times.append([tm])
        else: times[-1].append(tm)
    starts=[g[0] for g in times]
    found=0; miss=[]
    for l in E["clean"]:
        for r in l["ranges"]:
            if any(r["start"]-0.15<=s<=r["start"]+0.45 for s in starts): found+=1
            else: miss.append(r["start"])
    print("thr",thr,"onset events",len(starts),"layer starts matched",found,"missed",miss)
