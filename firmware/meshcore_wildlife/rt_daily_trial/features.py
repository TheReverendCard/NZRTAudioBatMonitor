"""Prepare causal 10 ms features using the Daily Python environment."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import wave

import numpy as np
from scipy.signal import sosfilt

BANDS = ((3000,12000),(18000,24000),(24000,27000),(27000,33000),(36000,44500))


def features(samples, rate):
    if rate < 96000:
        raise ValueError('needs at least 96 kHz')
    n = round(rate*.010)
    frames = len(samples)//n
    if frames < 7:
        raise ValueError('too short for 50 ms initial background')
    x = samples[:frames*n].astype(np.float64)/32768
    out = []
    for lo,hi in BANDS:
        center = (lo*hi)**.5
        omega = 2*np.pi*center/rate
        alpha = np.sin(omega)*(hi-lo)/(2*center)
        sos = [[alpha/(1+alpha),0,-alpha/(1+alpha),1,-2*np.cos(omega)/(1+alpha),(1-alpha)/(1+alpha)]]
        filtered = sosfilt(sos,x)
        power = (filtered.reshape(frames,n)**2).mean(axis=1)
        bg = np.mean(power[:5])
        ratios = []
        for value in power[5:]:
            ratios.append(min(8,value/(bg+1e-12))-1)
            bg += .05*(value-bg)
        out.append(ratios)
    return np.asarray(out,dtype=np.float32).T.copy()


def read_audio(p):
    if p.suffix.lower()=='.flac':
        import soundfile as sf
        with sf.SoundFile(p) as f:
            if f.channels!=1 or f.subtype!='PCM_16':
                raise ValueError('requires mono PCM16')
            return f.read(dtype='int16'), f.samplerate
    with wave.open(str(p),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getcomptype()!='NONE':
            raise ValueError('requires mono PCM16')
        n=w.getnframes()
        x=np.frombuffer(w.readframes(n),dtype='<i2')
        if len(x)!=n:
            raise ValueError('truncated')
        return x,w.getframerate()


