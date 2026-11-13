"""Create an isolated S3 bench project for a generated bundle, no flashing."""
import argparse,json,shutil,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def project(bundle,dst):
    hashes=json.loads((bundle/'files.json').read_text())
    if ('manifest.json' not in hashes or set(hashes)!={p.name for p in bundle.iterdir() if p.name!='files.json'}) or any(Path(n).name!=n or hashlib.sha256((bundle/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):raise ValueError('bundle integrity')
    m=json.loads((bundle/'manifest.json').read_text());name=m['profile']
    if name not in ('bmp_lr','bmp_shared_lr','wav_lr','wav_mlp','bmp_mlp','bmp_cnn','legacy','audible','evolved','ultrasound_rise','low_side_check','both_checks','rt_score1'):raise ValueError('unsupported')
    dst.mkdir(parents=True,exist_ok=False)
    shutil.copytree(HERE/'bench',dst,dirs_exist_ok=True);comp=dst/'components'/'s3math';shutil.copytree(HERE/'component',comp)
    (dst/'CMakeLists.txt').write_text((dst/'CMakeLists.txt').read_text().replace('set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../component")',''))
    shutil.copy2(bundle/'esp_dsp.yml',comp/'idf_component.yml')
    main=dst/'main'
    (main/'CMakeLists.txt').write_text((main/'CMakeLists.txt').read_text().replace('REQUIRES component','REQUIRES s3math'))
    for n in hashes:
        if n.endswith('.hpp'):shutil.copy2(bundle/n,main/n)
    if name in ('audible','ultrasound_rise','low_side_check','both_checks'):
        if name!='audible':
            p=main/'bench.cpp'
            rule={'ultrasound_rise':'Ultrasound','low_side_check':'LowSide','both_checks':'Both'}[name]
            p.write_text(p.read_text().replace('bat_s3::Audible audible','bat_s3::Replay<bat_s3::ReplayRule::'+rule+'> audible').replace('AUDIBLE synthetic',name+' synthetic'))
        return
    if name=='rt_score1':
        code='#include "score1.hpp"\nalignas(16) static float x[3840];\n'
        job='static bat_s3_score1::Analyzer obj;if(!bat_s3::fft_init())return INFINITY;for(int i=0;i<3840;i++)x[i]=(i%8<4)?.2f:-.2f;obj.window(x,x,.02f,true);obj.window(x,x,.02f,false);obj.window(x,x,.02f,true);auto f=obj.finish(4);return obj.valid() && f.pulses==2?0.f:1.f;'
    elif name=='evolved':
        code='#include "winner.hpp"\nalignas(16) static float x[3840];\n'
        job='static bat_s3::Evolved obj;x[0]=1;return obj.check(x,evolved::weights,evolved::bias,evolved::threshold)?1.f:0.f;'
    elif name=='legacy':
        code='static bat_s3::Legacy obj;alignas(16) static float x[3840];\n';job='for(int i=0;i<3840;i++)x[i]=i%7*.02f;obj.prime(x,3840);obj.prime(x,3840);obj.prime(x,1920);for(int j=0;j<150;j++)if(obj.check(x))return 1.f;for(float& v:x)v*=10;return obj.check(x)?0.f:1.f;'
    elif name=='bmp_cnn':
        code='#include "candidate.hpp"\nusing namespace bmp_cnn; static Workspace s;static float x[3*64*W];\n'
        job='for(int i=0;i<3*64*W;i++)x[i]=float(i%17)/16;return std::fabs(window_logit(x,s)-probe_logit);'
    else:
        code='#include "candidate.hpp"\nusing namespace '+name+';\n'
        job='float worst=0;for(int i=0;i<4;i++)worst=std::max(worst,std::fabs(score(probe[i])-expected[i]));return worst;'
    if name.startswith('wav_'):
        code+='#include "wav_frontend.hpp"\n#include "esp_heap_caps.h"\n'
        job=job.replace('return worst;', 'float f[165]; auto* w=(float*)heap_caps_aligned_alloc(16,sizeof(float)*bat_s3_wav::WORK_FLOATS,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);static int16_t pcm[4096]={};if(!w || !bat_s3::fft_init() || !bat_s3_wav::compute(pcm,4096,w,f))return INFINITY; for(int j=0;j<164;j++)worst=std::max(worst,std::fabs(f[j]));worst=std::max(worst,std::fabs(f[164]-std::log(4.f)));heap_caps_free(w);return worst;')
        with (dst/'sdkconfig.defaults').open('a') as f:f.write('CONFIG_SPIRAM=y\nCONFIG_SPIRAM_MODE_OCT=y\n')
    # Allocate the larger CNN input/workspace from PSRAM, not internal .bss.
    if name=='bmp_cnn':
        code=code.replace('static Workspace s;static float x[3*64*W];','#include_placeholder')
        code=code.replace('#include_placeholder','\n#include "esp_heap_caps.h"\n#include <new>\n')
        job='void* a=heap_caps_aligned_alloc(16,sizeof(Workspace),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);float* x=(float*)heap_caps_aligned_alloc(16,3*64*W*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!a||!x)return INFINITY;auto& s=*new(a) Workspace;'+job
        with (dst/'sdkconfig.defaults').open('a') as f:f.write('CONFIG_SPIRAM=y\nCONFIG_SPIRAM_MODE_OCT=y\n')
    (main/'bench.cpp').write_text('#include "first_pass.hpp"\n#include "esp_timer.h"\n#include <cstdio>\n'+code+
        'float probe_run(){'+job+'}\nextern "C" void app_main(){auto start=esp_timer_get_time();float v=probe_run();printf("S3 '+name+' probe_value=%g elapsed_us=%lld\\n",double(v),(long long)(esp_timer_get_time()-start));}\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();project(a.bundle,a.destination)
