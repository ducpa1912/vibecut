import subprocess, sys, numpy as np, os, time
D=os.path.expanduser("~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite")
SRC=D+"/imports/315aafc9-c76f-4c04-a408-7c37c008fbc3/source.mp4"
R=D+"/projects/prj_e95348a97316/renders/"
BASE=R+"ed_38a4c36a3aae_20261111-164411.mp4"; FINAL=R+"ed_38a4c36a3aae_20261111-191517.mp4"
def read(path,t0,t1,box):
    x,y,w,h=box
    n=int(round((t1-t0)*30))
    out=subprocess.run(["ffmpeg","-v","error","-ss",f"{t0:.3f}","-i",path,"-frames:v",str(n),"-vf",f"crop={w}:{h}:{x}:{y},format=gray","-f","rawvideo","-"],capture_output=True).stdout
    return np.frombuffer(out,np.uint8).reshape(-1,h,w).astype(np.float32)
def grad(a):
    gx=np.abs(np.diff(a,axis=-1))[...,:-1,:]; gy=np.abs(np.diff(a,axis=-2))[...,:,:-1]
    return gx+gy
def template(src):
    g=grad(src)                       # T,h,w
    # ink: strong edge on nearly every frame, at the same pixel
    strong=g>40
    return strong.mean(axis=0)>0.8
def score(frames,tpl):
    g=grad(frames)>40
    return (g&tpl).sum(axis=(1,2))/max(1,tpl.sum())
for name,(a,b),box in (("7.3",(5.75,7.35),(0.28,0.484,0.44,0.032)),("95.6",(93.5,95.6),(0.23,0.484,0.53,0.032))):
    x=int(box[0]*1080)-20; y=int(box[1]*1920)-20; w=int(box[2]*1080)+40; h=int(box[3]*1920)+40
    w-=w%2; h-=h%2
    t=time.time()
    mid=read(SRC,a+0.5,b-0.3,(x,y,w,h)); tpl=template(mid)
    t0=b-0.5; 
    s_src=score(read(SRC,t0,t0+1.0,(x,y,w,h)),tpl)
    s_base=score(read(BASE,t0,t0+1.0,(x,y,w,h)),tpl)
    s_fin=score(read(FINAL,t0,t0+1.0,(x,y,w,h)),tpl)
    print(name,"ink px",int(tpl.sum()),"of",tpl.size,"sec %.2f"%(time.time()-t))
    for i in range(len(s_src)):
        print("  %.3f src %.2f base %.2f final %.2f"%(t0+i/30,s_src[i],s_base[i],s_fin[i]))
