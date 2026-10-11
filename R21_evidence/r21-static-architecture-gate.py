"""R21 drone pair: stricter static-structure-only feature gate, no content fabrication."""
from pathlib import Path
import cv2,numpy as np,json
cv2.setNumThreads(1)
p=Path(__file__).parent
s0=Path(r'C:\Users\Public\OpenPQ\living-r20-source-gate-20261011\R20_drone_0028.jpg')
s1=Path(r'C:\Users\Public\OpenPQ\living-sunset-r13-real-cell-20261010\photos\08.jpg')
roi0=(.14,.00,.96,.98);roi1=(.55,.00,.99,.80)
def load(path,roi):
 im=cv2.imread(str(path));h,w=im.shape[:2];l,t,r,b=int(roi[0]*w),int(roi[1]*h),int(roi[2]*w),int(roi[3]*h)
 im=im[t:b,l:r];h,w=im.shape[:2];sc=min(1,1500/w)
 if sc<1: im=cv2.resize(im,(round(w*sc),round(h*sc)),interpolation=cv2.INTER_AREA)
 g=cv2.createCLAHE(2,(8,8)).apply(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY))
 k,d=cv2.SIFT_create(nfeatures=4200,contrastThreshold=.016,edgeThreshold=14,sigma=1.5).detectAndCompute(g,None)
 return im,k,d
i0,k0,d0=load(s0,roi0);i1,k1,d1=load(s1,roi1)
fl=cv2.FlannBasedMatcher(dict(algorithm=1,trees=4),dict(checks=64))
f=fl.knnMatch(d0,d1,k=2);r=fl.knnMatch(d1,d0,k=2)
back={(m.trainIdx,m.queryIdx) for m,n in r if m.distance<.82*n.distance}
matches=[m for m,n in f if m.distance<.82*n.distance and (m.queryIdx,m.trainIdx) in back]
a=np.array([k0[m.queryIdx].pt for m in matches],np.float32)
b=np.array([k1[m.trainIdx].pt for m in matches],np.float32)
def pick(P,box,dim):
 return (P[:,0]>=box[0]*dim[1])&(P[:,0]<=box[2]*dim[1])&(P[:,1]>=box[1]*dim[0])&(P[:,1]<=box[3]*dim[0])
regions={
 'all_feature_matches':((0,0,1,1),(0,0,1,1)),
 'architectural_facade_wide':((.06,.0,.84,.72),(.12,.04,.83,.74)),
 'tower_core_only':((.41,.07,.87,.70),(.32,.27,.83,.74)),
 'exclude_low_road':((.0,.0,1,.72),(.0,.0,1,.67))
}
records=[]
for name,(box0,box1) in regions.items():
 take=pick(a,box0,i0.shape)&pick(b,box1,i1.shape)
 pts0=a[take];pts1=b[take]
 Fcount=Hcount=0;inmask=None;Fshape='not_estimated'
 if len(pts0)>=8:
  F,mf=cv2.findFundamentalMat(pts0,pts1,cv2.FM_RANSAC,2.7,.995,3000)
  if F is not None and mf is not None and F.shape==(3,3):
   inmask=mf.ravel().astype(bool);Fcount=int(inmask.sum());Fshape=str(F.shape)
  H,mh=cv2.findHomography(pts0,pts1,cv2.RANSAC,4.5,maxIters=3000)
  if mh is not None:Hcount=int(mh.sum())
 row={'region':name,'reciprocalInRegion':int(take.sum()),'f_inliers':Fcount,'h_inliers':Hcount,
      'candidate45Reached':Fcount>=45,'F_shape':Fshape}
 records.append(row);print('STATIC_GATE',json.dumps(row),flush=True)
report={'method':'R21 same SIFT matches filtered by fixed image-space bounding regions around static Apollo components, excluding buses, people and road; heuristic gate only',
'results':records,
'interpretation':'Aerial overlap is real but may be facade planar. Static facade feature gate alone cannot show road-level hidden geometry or metric camera baselines.',
'status':'PHOTO_RECON_SOURCE_INSUFFICIENT_FOR_GROUND_WALK',
'limitations':'ROI masks are human heuristic bounding boxes, not learned precise building segmentation; no ground truth; this QA is extra caution, not professional survey.',
'master':'NO_PROD_NO_DEPLOY_NO_MERGE'}
(p/'R21_STATIC_ARCHITECTURE_ONLY_GATE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FINISH_STATIC',report['status'],flush=True)