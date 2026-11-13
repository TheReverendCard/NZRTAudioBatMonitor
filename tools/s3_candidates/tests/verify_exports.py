"""Compare the actual generated C++ scorers with their desktop model on fixed probe inputs.
Usage: python tests/verify_exports.py [--upload <directory containing the two reviewed checkpoints>]
"""
import sys, tempfile,subprocess,json,shutil,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import export_all as ex
import numpy as np
from scipy.signal import sosfilt
def build(tmp,unit,src):
    p=tmp/(unit+'.cpp');p.write_text(src)
    b=tmp/unit;subprocess.run(['g++','-O2','-std=c++11','-I',str(HERE/'component/include'),'-I',str(tmp),str(p),'-o',str(b)],check=True);return b
def run(exe,*arrays):
    return np.frombuffer(subprocess.run([str(exe)],input=b''.join(a.astype('<f4').tobytes() for a in arrays),capture_output=True,check=True).stdout,'<f4')
def check_rt(tmp):
    cpp=build(tmp,'filters','''#include "first_pass.hpp"
#include <cstdio>
static bat_s3::Replay<bat_s3::ReplayRule::Ultrasound> u;static bat_s3::Replay<bat_s3::ReplayRule::LowSide> l; static bat_s3::Replay<bat_s3::ReplayRule::Both> bth;static bat_s3::Audible a;static bat_s3::Evolved e;alignas(16) float x[3840];
int main(){float w[5][3]={{0,0,0},{0,-3,-5},{0,-2,2},{0,1,0},{0,3,0}},b[3]={0,-.5f,2.5f};if(!a.init()||!u.init()||!l.init()||!bth.init())return 2;
while(fread(x,4,3840,stdin)==3840){float ap,up;bool h;if(!a.energies(x,ap,up)||!a.check(x,h))return 3;
bool hu,hl,hb;if(!u.check(x,hu)||!l.check(x,hl)||!bth.check(x,hb))return 4;float o[]={ap,up,float(h),float(e.check(x,w,b,1)),bat_s3::legacy_rms(x),float(hu),float(hl),float(hb)};fwrite(o,4,8,stdout);}}''')
    rng=np.random.default_rng(461);x=(rng.normal(0,.08,(54,3840))).astype('f4')
    for i in [5,8,15,22,38,47]:
        x[i]+=.02*np.cos(2*np.pi*np.arange(3840)*39800/192000)
    x[30]+=.6*np.cos(2*np.pi*np.arange(3840)*41100/192000)
    x[12]+=.8*np.cos(2*np.pi*np.arange(3840)*23400/192000)
    x[41,:960]+=.8*np.cos(2*np.pi*np.arange(960)*36000/192000)+2*np.cos(2*np.pi*np.arange(960)*4800/192000)
    power=abs(np.fft.rfft(x.reshape(-1,960)*np.hanning(960)))**2
    bands=np.stack([power[:,10:75].mean(1),power[:,90:225].mean(1)],axis=1)
    bg=bands[:10].mean(0);hot=np.zeros(len(bands),bool)
    for i,p in enumerate(bands[10:],10):
        ar,ur=(p+1e-12)/(bg+1e-12);hot[i]=ur>=3.235937 and (ar<1.995262 or ur>=ar*3.981072);bg+=.024690088*(p-bg)
    diffs=[]
    for lo,hi in [(18000,24000),(24000,27000),(27000,33000),(36000,44500)]:
        c=(lo*hi)**.5;omega=2*np.pi*c/192000;al=np.sin(omega)*(hi-lo)/(2*c)
        a=sosfilt([[al/(1+al),0,-al/(1+al),1,-2*np.cos(omega)/(1+al),(1-al)/(1+al)]],x.ravel())
        p=np.mean(a.reshape(-1,1920)**2,1);bg=p[:5].mean();v=[0]*5
        for y in p[5:]:v.append(min(8,y/(bg+1e-12))-1);bg+=.05*(y-bg)
        diffs.append(np.array(v))
    a,b,c,d=diffs; ev=np.maximum(0,-3*a-2*b+c+3*d-.5)-np.maximum(0,-5*a+2*b+2.5)>1
    got=run(cpp,x).reshape(-1,8)
    bands4=np.column_stack([bands,power[:,90:120].mean(1),power[:,135:165].mean(1)])
    bg=bands4[:10].mean(0); decisions=np.zeros((len(bands4),3),bool)
    for i,p in enumerate(bands4[10:],10):
        rise=10*np.log10((p+1e-12)/(bg+1e-12)); excess=np.maximum(p-bg,0)
        peak_hz=(power[i,90:225].argmax()+90)*200
        tail=23000<=peak_hz<=27000 and excess[2]>2*excess[3]; good=rise[0]<3 or rise[1]-rise[0]>=6
        decisions[i]=[rise[1]>=5.1,rise[1]>=5.1 and not tail,rise[1]>=5.1 and good and not tail];bg+=.024690088*(p-bg)
    expected=decisions.reshape(-1,4,3).any(axis=1)
    np.testing.assert_equal(got[:,5:],expected);assert expected[:,0].sum()>expected[:,1].sum()>expected[:,2].sum()
    np.testing.assert_allclose(got[:,:2],bands[::4],rtol=2e-5,atol=1e-6)
    np.testing.assert_equal(got[:,2],hot.reshape(-1,4).any(1));np.testing.assert_equal(got[:,3],ev.reshape(-1,2).any(1));assert got[:,2].sum() and got[:,3].sum()
    np.testing.assert_allclose(got[:,4],np.sqrt((x*x).mean(1)),rtol=3e-6)
def check_score1(tmp):
    shutil.copy2(HERE/'tests/score1_reference.hpp',tmp/'score1_reference.hpp')
    cpp=build(tmp,'score1_compare','#include "score1.hpp"\n#include "score1_reference.hpp"\n#include <cstdio>\nstatic WildlifeScoring::Analyzer ref;static bat_s3_score1::Analyzer opt;alignas(16) float x[3840];int main(){if(!bat_s3::fft_init())return 2;for(int i=0;fread(x,4,3840,stdin)==3840;i++){bool hot=i%3!=1;ref.window(x,x,.06f,hot);opt.window(x,x,.06f,hot);if(i%5==4){auto a=ref.finish(3.2f);auto b=opt.finish(3.2f);float v[]={float(a.score),float(b.score),float(a.bat_like),float(b.bat_like),a.harmonic_fraction,b.harmonic_fraction,float(a.pulses),float(b.pulses)};fwrite(v,4,8,stdout);if(!opt.valid())return 3;ref.reset();opt.reset();}}}')
    rng=np.random.default_rng(71);x=rng.normal(0,.25,(75,3840)).astype('f4');t=np.arange(3840)/192000
    for i in range(35):x[i]=.4*np.sin(2*np.pi*39750*t)+(.35 if i<17 else 0)*np.sin(2*np.pi*19875*t)
    v=run(cpp,x).reshape(-1,8);np.testing.assert_equal(v[:,::2],v[:,1::2]);assert len(set(v[:,0]))>1 and len(set(v[:,4]))>1
def check_legacy(tmp):
    cpp=build(tmp,'legacy','#include "first_pass.hpp"\n#include <cstdio>\nstatic bat_s3::Legacy obj;alignas(16) static float x[9600];int main(){if(fread(x,4,9600,stdin)!=9600)return 2;obj.prime(x,9600);while(fread(x,4,3840,stdin)==3840){float v=obj.check(x);fwrite(&v,4,1,stdout);}}')
    rng=np.random.default_rng(51); x=rng.normal(0,.01,9600+156*3840).astype("f4");x[-3840*3:-3840]*=3
    y=sosfilt([[.65745519149,-1.31491038298,.65745519149,1,-1.19391336772,.43590739824],[.26471264609,.52942529219,.26471264609,1,-.11506372344,.17391430782]],x)
    rms=np.sqrt(np.mean(y[9600:].reshape(-1,3840)**2,axis=1));bg=rms[:150].mean();out=[False]*150
    for v in rms[150:]:
        rel=v/(bg+1e-12);out.append(rel>=1.8)
        if rel<1.4:bg+=.003*(v-bg)
    np.testing.assert_equal(run(cpp,x),out);assert sum(out)==2
def test_dense(folder,model,tmp,root):
    import joblib
    kind,filename,report=ex.FAMILIES[folder]
    if model is not None:
        dir=root/'Daily_Run_Reports/Model_Experiments'/folder/'fixture';dir.mkdir(parents=True)
        state=dir/filename;joblib.dump(model,state,compress=3)
        info={'model_family':kind[:3],'feature_version':'band_robust32_v1','threshold':.52,'model_sha256':ex.sha(state),'input_manifest_sha256':'3'*64}
        if folder=='bmp_sharedband':info.update(model_branch='shared_frequency_bmp',feature_version='band_robust32_bmp_shared_bins_30_63_v1')
        if kind.endswith('mlp'):info.update(candidate_joblib_sha256=ex.sha(state),validation_selected_threshold=.52)
        ex.write(dir/report,info)
    else:dir=root/'Daily_Run_Reports/Model_Experiments'/folder/'field'
    row=ex.candidate(folder,dir/filename,dir/report,root/'exports',root,True)
    bundle=root/'exports'/row['bundle'];shutil.copy2(bundle/'candidate.hpp',tmp/'candidate.hpp')
    exe=build(tmp,'predict','''#include "candidate.hpp"
#include <cstdio>
int main(){float x[165];while(fread(x,4,165,stdin)==165){float p=NS::score(x);fwrite(&p,4,1,stdout);}}'''.replace('NS',kind))
    if model is None:
        from restricted_model import restricted_load
        model=restricted_load(dir/filename)
    s=model.steps[0][1]; x=(np.random.default_rng(123).normal(size=(64,165))*s.scale_+s.mean_).astype('f4')
    np.testing.assert_allclose(run(exe,x),model.predict_proba(x)[:,1],rtol=0,atol=2e-5)
    return bundle
def test_pcm(tmp,bundle,folder):
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    from reference_wav_features import wav_features
    from restricted_model import restricted_load
    import warnings
    model=restricted_load(folder/'candidate.joblib')
    shutil.copy2(bundle/'candidate.hpp',tmp/'candidate.hpp')
    exe=build(tmp,'pcm','#include "candidate.hpp"\n#include "wav_frontend.hpp"\n#include <cstdio>\nstatic int16_t x[384000];alignas(16) static float scratch[bat_s3_wav::WORK_FLOATS],out[166];int main(){if(!bat_s3::fft_init())return 1;int n=fread(x,2,384000,stdin);if(!bat_s3_wav::compute(x,n,scratch,out))return 2;out[165]=wav_mlp::score(out);fwrite(out,4,166,stdout);}')
    rng=np.random.default_rng(9);clips=[np.zeros(48000),rng.normal(0,.03,192000)]
    for path in sorted(folder.glob('*.wav')):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error');fs,x=wavfile.read(path)
            if fs not in (96000,192000) or x.ndim!=1 or x.dtype!=np.int16 or len(x)<fs*.12:continue
            x=x[:fs*2].astype('f4')/32768;clips.append(resample_poly(x,2,1) if fs==96000 else x)
        except (ValueError,OSError,Warning):continue
        if len(clips)>=8:break
    fmax=pmax=0
    for x in clips:
        pcm=(np.clip(x,-1,32767/32768)*32768).round().astype('<i2');p=tmp/'clip.wav';wavfile.write(p,192000,pcm);ref=wav_features(p)
        vals=np.frombuffer(subprocess.run([str(exe)],input=pcm.tobytes(),capture_output=True,check=True).stdout,'<f4')
        fmax=max(fmax,float(np.max(abs(vals[:165]-ref))));pmax=max(pmax,abs(float(vals[165])-model.predict_proba(ref[None,:])[0,1]))
    assert fmax<.006 and pmax<.005,(fmax,pmax)
    print('PCM parity: cases',len(clips),'max feature/probability differences',fmax,pmax)
def test_cnn(tmp,root,state,rep):
    import torch
    row=ex.candidate('cnn_bmp_mil',state,rep,root/'exports',root,True);bundle=root/'exports'/row['bundle']
    shutil.copy2(bundle/'candidate.hpp',tmp/'candidate.hpp')
    exe=build(tmp,'vision','''#include "candidate.hpp"
#include <cstdio>
static bmp_cnn::Workspace s;static float x[bmp_cnn::K*3*64*bmp_cnn::W];
int main(){while(fread(x,sizeof(x),1,stdin)==1){float p=bmp_cnn::score(x,s);fwrite(&p,4,1,stdout);}}''')
    from torch import nn
    d=torch.load(state,weights_only=True,map_location='cpu');n=nn.Sequential(nn.Conv2d(3,8,5,2,2),nn.ReLU(),nn.Conv2d(8,16,3,2,1),nn.ReLU(),nn.Conv2d(16,24,3,2,1),nn.ReLU(),nn.AdaptiveAvgPool2d((4,6)),nn.Flatten(),nn.Linear(576,24),nn.ReLU(),nn.Dropout(.25),nn.Linear(24,1)).eval()
    n.load_state_dict({k[7:]:v for k,v in d['state_dict'].items()});x=np.random.default_rng(42).normal(size=(2,d['max_windows'],3,64,d['width'])).astype('f4')
    with torch.no_grad():expected=torch.sigmoid(n(torch.from_numpy(x.reshape(-1,3,64,d['width']))).reshape(2,-1).amax(1)).numpy()
    np.testing.assert_allclose(run(exe,x),expected,rtol=0,atol=2e-5)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--upload',type=Path);args=ap.parse_args()
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    rng=np.random.default_rng(55);x=rng.normal(size=(100,165));y=(x[:,0]>0).astype(int)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);check_rt(root);check_legacy(root);check_score1(root)
        for folder in ['bmp','wav','bmp_sharedband','nn_mlp_bmp','nn_mlp_wav']:
            m=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(32,16),max_iter=3,random_state=3) if 'mlp' in folder else LogisticRegression()).fit(x,y)
            test_dense(folder,m,root,root)
        if args.upload:
            d=root/'Daily_Run_Reports/Model_Experiments/nn_mlp_wav/field';d.mkdir(parents=True)
            for f in ('candidate.joblib','report.json'):shutil.copy2(args.upload/f,d/f)
            bundle=test_dense('nn_mlp_wav',None,root,root);assert (bundle/'weights.bin').stat().st_size==24772
            test_pcm(root,bundle,args.upload)
            test_cnn(root,root,args.upload/'candidate_state.pt',args.upload/'report(1).json')
        print('PASS: first-pass DSP reference and compiled generated scorers; optional owner models tested =',bool(args.upload))
if __name__=='__main__':main()
