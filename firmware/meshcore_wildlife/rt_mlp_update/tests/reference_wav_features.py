"""Reference extracted from the original owner's baseline WAV feature code.
Canonical source SHA-256: 27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923
This is only for desktop parity probes; it does not run on an ESP32.
"""
import math
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile


def band_pools(array):
    if array.ndim!=2 or array.shape[0]<12 or array.shape[1]<1:
        raise ValueError('Invalid spectrogram dimensions: '+str(array.shape))
    bands=np.array_split(np.arange(array.shape[0]),32)
    vec=[]
    for ids in bands:
        band=array[ids]
        baseline=np.median(band,axis=1,keepdims=True)
        excess=np.maximum(band-baseline,0.0)
        strength=np.max(excess,axis=0)
        vec.extend([float(np.mean(strength)),float(np.percentile(strength,90)),
                    float(np.percentile(strength,99)),float(np.max(strength)),
                    float(np.mean(strength>0.25))])
    vec.extend([float(np.mean(array)),float(np.std(array)),
                float(np.percentile(array,99)),float(np.max(array)),
                math.log1p(array.shape[1])])
    return np.asarray(vec,dtype=np.float32)


def wav_features(path:Path):
    fs,data=wavfile.read(path,mmap=False)
    if fs<96000:raise ValueError('WAV less than 96kHz: '+str(fs))
    if data.ndim==2:data=np.mean(data.astype(np.float32),axis=1)
    if data.ndim!=1:raise ValueError('Unsupported WAV dimensions')
    if data.size<2048:raise ValueError('Too-short WAV')
    if np.issubdtype(data.dtype,np.integer):
        data=data.astype(np.float32)/max(abs(np.iinfo(data.dtype).min),np.iinfo(data.dtype).max)
    else:data=np.asarray(data,dtype=np.float32)
    if fs!=96000:
        from math import gcd
        d=gcd(int(fs),96000)
        data=signal.resample_poly(data,96000//d,fs//d).astype(np.float32)
    data=data[:30*96000]
    frequency,time,sg=signal.spectrogram(data,fs=96000,window='hann',
        nperseg=1024,noverlap=512,scaling='spectrum',mode='magnitude')
    selector=(frequency>=8000)&(frequency<=45000)
    if not selector.any():raise ValueError('No ultrasonic frequency bins')
    sg=sg[selector].astype(np.float32)
    log=np.log10(np.maximum(sg,1.e-8))
    background=np.median(log,axis=1,keepdims=True)
    excess=np.clip((log-background)*2.0,0.,3.)/3.
    return band_pools(excess)
