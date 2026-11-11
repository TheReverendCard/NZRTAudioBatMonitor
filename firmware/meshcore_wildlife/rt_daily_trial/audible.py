"""Read-only comparison of fixed candidate first-pass rules on saved Xiao audio."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import re
import tempfile
import zipfile

import numpy as np
import wave
from contextlib import contextmanager
from scipy.signal import lfilter

RULES = ['saved_clip', 'ultrasound_rise', 'audible_check', 'low_side_check', 'both_checks']


def table(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def save(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@contextmanager
def audio(path):
    if path.suffix.lower()=='.wav':
        with wave.open(str(path), 'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getcomptype()!='NONE':
                raise ValueError('requires mono 16-bit PCM WAV')
            rate=w.getframerate()
            def blocks():
                while data:=w.readframes(round(rate*.005)*512):
                    yield np.frombuffer(data,dtype='<i2').astype('float32')/32768
            yield rate,w.getnframes(),blocks()
    else:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise ValueError('FLAC reading requires soundfile in Daily Python') from exc
        with sf.SoundFile(path) as stream:
            if stream.channels!=1:
                raise ValueError('requires mono audio')
            yield stream.samplerate,stream.frames,stream.blocks(blocksize=round(stream.samplerate*.005)*512,dtype='float32')


def replay(path):
    keep = dict.fromkeys(RULES, False)
    keep['saved_clip'] = True
    with audio(path) as (rate, expected, blocks):
        if rate < 96000:
            raise ValueError('requires mono audio at 96 kHz or higher')
        size = round(rate * .005)
        window = np.hanning(size)
        freq = np.fft.rfftfreq(size, 1/rate)
        bands = [(2,15),(18,45),(18,24),(27,33)]
        bins = [(freq >= low*1000) & (freq < high*1000) for low,high in bands]
        ultrasound = bins[1]
        state = None
        total = 0
        for chunk in blocks:
            total += len(chunk)
            frames = chunk[:len(chunk)//size*size].reshape(-1,size)
            if not len(frames):
                continue
            power = abs(np.fft.rfft(frames*window))**2
            energy = np.stack([power[:,mask].mean(axis=1) for mask in bins],axis=1)
            if state is None:
                if len(energy) < 11:
                    raise ValueError('clip lacks 50 ms of baseline plus one test frame')
                state = energy[:10].mean(axis=0)
                energy,power = energy[10:],power[10:]
            # Previous-frame causal background, 0.2 s time constant.
            decay = np.exp(-.005/.2)
            smooth,_ = lfilter([1-decay],[1,-decay],energy,axis=0,zi=(state*decay)[None,:])
            background = np.vstack((state, smooth[:-1]))
            state = smooth[-1]
            rise = 10*np.log10((energy+1e-12)/(background+1e-12))
            hot = rise[:,1] >= 5.1
            audible_ok = (rise[:,0] < 3) | (rise[:,1]-rise[:,0] >= 6)
            peak = freq[ultrasound][power[:,ultrasound].argmax(axis=1)]
            excess = np.maximum(energy-background,0)
            lower_tail = (peak >= 23000) & (peak <= 27000) & (excess[:,2] > 2*excess[:,3])
            for name, mask in zip(RULES[1:], (hot, hot & audible_ok, hot & ~lower_tail, hot & audible_ok & ~lower_tail)):
                keep[name] |= bool(mask.any())
        if total != expected or state is None:
            raise ValueError('incomplete or empty audio')
    return {name:int(v) for name,v in keep.items()}


