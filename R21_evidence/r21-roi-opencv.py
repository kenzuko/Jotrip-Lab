"""Bounded OpenCV R21: transparent feature matching test of actual Apollo photos. NO geometry generation."""
import cv2, numpy as np, json, time, gc
from pathlib import Path
cv2.setNumThreads(1)
root=Path(__file__).parent
r13=Path(r'C:\Users\Public\OpenPQ\living-sunset-r13-real-cell-20261010\photos')
r20=Path(r'C:\Users\Public\OpenPQ\living-r20-source-gate-20261011')
sources={'drone0028':r20/'R20_drone_0028.jpg','drone0031':r13/'08.jpg','ground06':r13/'06.jpg','ground07':r13/'07.jpg'}
bounds={'drone0028':(.14,.00,.96,.98),'drone0031':(.55,.00,.99,.80),
        'ground06':(.15,.00,.77,.98),'ground07':(.18,.00,.82,.95)}
pairs=[('drone0028','drone0031'),('ground06','ground07'),('drone0028','ground06')]
cases=[('whole_sift',False,False),('apollo_roi_sift',True,False),('apollo_roi_rootsift',True,True)]
res=[]
matchimgs=[]
def feats(name,roi,useRoot,maxW=1500):
 im=cv2.imread(str(sources[name]))
 if im is None:raise ValueError('MISSING '+name)
 h,w=im.shape[:2]
 if roi:
  x0,y0,x1,y1=bounds[name];l,r=int(x0*w),int(x1*w);t,b=int(y0*h),int(y1*h)
  im=im[t:b,l:r]
 else:l=t=0
 ih,iw=im.shape[:2]
 scl=min(1,maxW/iw)
 if scl<1:im=cv2.resize(im,(round(iw*scl),round(ih*scl)),interpolation=cv2.INTER_AREA)
 g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
 g=cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(g)
 sift=cv2.SIFT_create(nfeatures=4200,contrastThreshold=.016,edgeThreshold=14,sigma=1.5)
 kp,des=sift.detectAndCompute(g,None)
 if useRoot and des is not None:
  des=des/(np.sum(np.abs(des),axis=1,keepdims=True)+1e-7)
  des=np.sqrt(np.maximum(0,des))
 return im,kp,des,(l,t,scl)
def evalcase(a,b,case,roi,useRoot):
 t0=time.time()
 im0,k0,d0,tf0=feats(a,roi,useRoot)
 im1,k1,d1,tf1=feats(b,roi,useRoot)
 flann=cv2.FlannBasedMatcher(dict(algorithm=1,trees=4),dict(checks=64))
 fwd=flann.knnMatch(d0,d1,k=2);rev=flann.knnMatch(d1,d0,k=2)
 f=[m for m,n in fwd if m.distance<.82*n.distance]
 back={(m.trainIdx,m.queryIdx) for m,n in rev if m.distance<.82*n.distance}
 good=[m for m in f if (m.queryIdx,m.trainIdx) in back]
 pt0=np.float32([k0[m.queryIdx].pt for m in good]).reshape(-1,2)
 pt1=np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1,2)
 nf=nh=0;cov=0;inl=None;fm=None
 if len(good)>=8:
  fm,mf=cv2.findFundamentalMat(pt0,pt1,cv2.FM_RANSAC,2.7,.995,3000)
  if mf is not None and fm is not None and fm.shape==(3,3):
   inl=mf.ravel().astype(bool);nf=int(inl.sum())
   if nf>=8:
    bb=np.ptp(pt0[inl],axis=0)
    cov=round(float(np.prod(bb)/np.prod(im0.shape[:2])),3)
  h,mh=cv2.findHomography(pt0,pt1,cv2.RANSAC,4.5,maxIters=2500)
  nh=int(mh.ravel().sum()) if mh is not None else 0
 row={'pair':a+'__'+b,'method':case,'roi':roi,'detected':[len(k0),len(k1)],
      'reciprocal_matches':len(good),'f_inliers':nf,'h_inliers':nh,'coverage':cov,
      'durationSec':round(time.time()-t0,2),
      'candidateThresholdReached':nf>=45 and nf>nh+12 and cov>=.2,
      'license':'Existing R13/R20 genuine Apollo images CC BY-SA 4.0'}
 if nf>=8:
  vis=cv2.drawMatches(im0,k0,im1,k1,[good[j] for j in np.where(inl)[0][:80]],None,
                     matchColor=(60,220,80),singlePointColor=(255,255,0),flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
  w=min(1600,vis.shape[1]);h=round(vis.shape[0]*w/vis.shape[1]);vis=cv2.resize(vis,(w,h))
  path=root/f'R21_{a}_{b}_{case}.jpg'
  cv2.imwrite(str(path),vis,[cv2.IMWRITE_JPEG_QUALITY,86])
  row['visualFile']=path.name
 return row
for a,b in pairs:
 for case,roi,useRoot in cases:
  try:
   row=evalcase(a,b,case,roi,useRoot);res.append(row)
   print('R21_FEATURE_PAIR',row['pair'],case,'F',row['f_inliers'],'H',row['h_inliers'],
         'area',row['coverage'],'reciprocal',row['reciprocal_matches'],'sec',row['durationSec'],flush=True)
  except Exception as e:
   res.append({'pair':a+'__'+b,'method':case,'error':str(e)})
   print('CASE_ERROR',a,b,case,str(e),flush=True)
  gc.collect()
report={'status':'FEATURE_MATCH_REVIEW_ONLY_NOT_SCAN','R20_gate':'VISUAL_FAIL_SOURCE_BLOCKED',
'results':sorted(res,key=lambda x:x.get('f_inliers',0),reverse=True),
'bestPair':max(res,key=lambda x:x.get('f_inliers',0)),'truth':'No actual camera calibration, metric scale, 3D pose, 10x10 m mesh, or real street behind Apollo. Features alone are not 3D.',
'license':'Images from Wikimedia Commons, CC BY-SA 4.0 (Vivu Vietnam), derivatives attribution and SA required',
'release':'NO_MERGE_NO_DEPLOY_NO_PRODUCTION'}
(root/'R21_OPENCV_ROI_GEOMETRY_QA.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FINAL_R21',report['bestPair'].get('f_inliers',0),report['bestPair']['pair'],report['bestPair']['method'],flush=True)