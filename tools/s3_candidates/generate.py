"""Compile known, report-hash-verified, owner-trained checkpoints to static S3 scorer headers."""
from pathlib import Path
import hashlib,json,math,struct
import numpy as np
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def f(v):
    n=float(np.float32(v))
    if not math.isfinite(n):raise ValueError("non-finite float")
    return format(n,'.9e')+'f'
def array(name,a):
    a=np.ascontiguousarray(a,dtype='<f4')
    return 'alignas(16) static constexpr float '+name+''.join('[%d]'%n for n in a.shape)+'={'+','.join(map(f,a.flat))+'};\n'
def padded(x):
    return np.pad(x,((0,0),(0,(-x.shape[1])%4)))
def dense(state,out,kind,thr,info):
    from restricted_model import restricted_load
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    model=restricted_load(state)
    if type(model)!=Pipeline or len(model.steps)!=2:raise ValueError('unknown pipeline')
    scaler,m=[s for _,s in model.steps]
    if type(scaler)!=StandardScaler or not(scaler.with_mean and scaler.with_std) or tuple(m.classes_)!=(0,1):raise ValueError('unexpected scaler/classes')
    if scaler.mean_.shape!=(165,) or scaler.scale_.shape!=(165,) or np.min(scaler.scale_)<1e-12:raise ValueError('feature contract')
    if kind.endswith('_mlp') and type(m)==MLPClassifier and (m.activation,m.out_activation_)==('relu','logistic'):
        layers=list(zip(m.coefs_,m.intercepts_))
        if [w.shape for w,b in layers]!=[(165,32),(32,16),(16,1)]:raise ValueError('unknown MLP architecture')
    elif kind.endswith('_lr') and type(m)==LogisticRegression and m.coef_.shape==(1,165):layers=[(m.coef_.T,m.intercept_)]
    else:raise ValueError('unexpected estimator')
    src=array('mean',scaler.mean_)+array('scale',scaler.scale_)
    body='alignas(16) float x0[168]{};for(int i=0;i<165;i++)x0[i]=(input[i]-mean[i])/scale[i];\n'
    for i,(w,b) in enumerate(layers):
        w=padded(w.T);nc,n=w.shape
        if b.shape!=(nc,):raise ValueError('bias shape mismatch')
        src+=array('w'+str(i),w)+array('b'+str(i),b)
        t=f'b{i}[j]+bat_s3::dot(x{i},w{i}[j],{n})'
        act=f'std::max(0.f,{t})' if nc>1 else f'bat_s3::prob({t})'
        body+=f'alignas(16) float x{i+1}[{(nc+3)&~3}]{{}};for(int j=0;j<{nc};j++)x{i+1}[j]={act};\n'
    compat=(kind=='wav_mlp' and info.get('reused_baseline_feature_source_sha256') in {'27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923','d322b0a50c021feaf97ed54d62db0545bc2c7a874171126f1fc05ed0f25be24d','39c4f60018bc11cb2f2912e9fbb7c984bfebb4408420e07dc685869a394d666b','b79395ae7bec12ee010f4e63b005105e49e5747c51b7c9f2353e0fb3181a98f3'} and info.get('feature_version')=='band_robust32_v1')
    if compat:
        vals=[scaler.mean_,scaler.scale_]+[v for pair in layers for v in pair]
        data=struct.pack('<8sIIfI',b'NZRTMLP1',1,6187,thr,1)+b''.join(np.asarray(v,dtype='<f4').tobytes() for v in vals)
        if len(data)!=24772:raise ValueError('bad RT encoding')
        (out/'weights.bin').write_bytes(data)
    # A small self-test vector for the generated implementation; not a graded field evaluation.
    rng=np.random.default_rng(453)
    xs=np.vstack([scaler.mean_,scaler.mean_+rng.normal(size=(3,165))*scaler.scale_]).astype('f4')
    src+=array('probe',xs)+array('expected',model.predict_proba(xs)[:,1])
    return src+'inline float score(const float* input){'+body+f'return x{len(layers)}[0];'+'}\n',compat
def cnn(state,out,kind,thr,info):
    import torch
    data=torch.load(state,weights_only=True,map_location='cpu')
    if data['architecture']!='cnn_bmp_mil_v0.1' or data['feature_version']!='bmp_mil_3channel_v1' or list(data['channels'])!=['original_energy','bounded_relative_contrast','valid_frequency_mask']:raise ValueError('unknown CNN')
    w=data['width']; k=data['max_windows']
    if type(w)!=int or type(k)!=int or not 32<=w<=512 or not 1<=k<=16 or (w,k)!=(info['width'],info['max_windows']):raise ValueError('CNN input contract')
    sd=data['state_dict'];src='';want=set()
    for name,shape in [(0,(8,3,5,5)),(2,(16,8,3,3)),(4,(24,16,3,3)),(8,(24,576)),(11,(1,24))]:
        key=f'blocks.{name}.';want.update([key+'weight',key+'bias']);v=sd[key+'weight'].numpy();b=sd[key+'bias'].numpy()
        if v.shape!=shape or b.shape!=(shape[0],):raise ValueError('CNN shape mismatch')
        v=(v.transpose(0,2,3,1).reshape(len(b),-1) if v.ndim==4 else v)
        src+=array('w'+str(name),padded(v))+array('b'+str(name),b)
    if set(sd)!=want:raise ValueError('unexpected CNN parameters')
    src+=f'constexpr int W={w},K={k},W1=(W+1)/2,W2=(W1+1)/2,W3=(W2+1)/2;\n'
    src+='''
// Do not put this workspace on the task stack.
struct Workspace {alignas(16) float a[32*W1*8],b[16*W2*16],pool[576],hidden[24];};
inline float window_logit(const float* chw,Workspace& s){
 bat_s3::conv<3,8,5,true>(chw,64,W,&w0[0][0],b0,s.a);
 bat_s3::conv<8,16,3>(s.a,32,W1,&w2[0][0],b2,s.b);
 bat_s3::conv<16,24,3>(s.b,16,W2,&w4[0][0],b4,s.a);
 for(int c=0;c<24;c++)for(int y=0;y<4;y++)for(int x=0;x<6;x++){
  int x0=x*W3/6,x1=((x+1)*W3+5)/6;float sum=0;
  for(int j=y*2;j<y*2+2;j++)for(int i=x0;i<x1;i++)sum+=s.a[(j*W3+i)*24+c];
  s.pool[(c*4+y)*6+x]=sum/(2*(x1-x0));}
 for(int i=0;i<24;i++)s.hidden[i]=std::max(0.f,b8[i]+bat_s3::dot(w8[i],s.pool,576));
 return b11[0]+bat_s3::dot(w11[0],s.hidden,24);}
inline float score(const float* all, Workspace& s){
 float high=window_logit(all,s);for(int i=1;i<K;i++)high=std::max(high,window_logit(all+i*3*64*W,s));
 return bat_s3::prob(high);}
'''
    # Reproducible footprint-limited device self-test against the trained PyTorch net.
    from torch import nn
    net=nn.Sequential(nn.Conv2d(3,8,5,2,2),nn.ReLU(),nn.Conv2d(8,16,3,2,1),nn.ReLU(),nn.Conv2d(16,24,3,2,1),nn.ReLU(),nn.AdaptiveAvgPool2d((4,6)),nn.Flatten(),nn.Linear(576,24),nn.ReLU(),nn.Dropout(.25),nn.Linear(24,1))
    net.load_state_dict({key[7:]:v for key,v in sd.items()});net.eval()
    probe=((np.arange(3*64*w)%17)/16.).astype('f4').reshape(1,3,64,w)
    with torch.no_grad():expect=float(net(torch.from_numpy(probe)).item())
    src+='constexpr float probe_logit='+f(expect)+';\n'
    return src,False
def generate(state,out,kind,threshold,info):
    src,compat=(cnn if kind=='bmp_cnn' else dense)(state,out,kind,threshold,info)
    (out/'candidate.hpp').write_text('#pragma once\n#include "cnn.hpp"\nnamespace '+kind+' {\nstatic constexpr float threshold='+f(threshold)+';\n'+src+'}\n',encoding='utf8')
    return compat
