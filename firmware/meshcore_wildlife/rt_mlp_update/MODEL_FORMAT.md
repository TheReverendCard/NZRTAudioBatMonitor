# Numeric model format, version 1

Little-endian, exactly 24,772 bytes.  No pickle, executable code, tensors of variable dimensions or dynamic operators.

| Offset | Type | Value |
|---|---|---|
| 0 | 8 ASCII bytes | `NZRTMLP1` |
| 8 | uint32 | Package schema 1 |
| 12 | uint32 | Parameter count 6187 |
| 16 | float32 | Classification threshold, strictly between 0 and 1 |
| 20 | uint32 | Feature schema 1 |
| 24 | 6187 float32 | Arrays below, C order |

Arrays: StandardScaler mean[165], scale[165], weights0[165,32], bias0[32], weights1[32,16], bias1[16], weights2[16,1], bias2[1].  Scales must be at least 1e-12; all values must be finite.  Class order [0,1], ReLU hidden layers, logistic output.  SHA-256 covers the complete file including header and threshold.

Feature schema 1 is the canonical WAV extractor source SHA-256 `27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923`: 192→96 kHz aligned Kaiser halfband resampling; Hann 1024, hop512, per-frame mean subtraction; 8–45 kHz magnitude spectrum; row median background subtraction; clipped log excess; 32 bands × five temporal summaries plus five globals.  The RT uses a bounded two-second PCM16 input policy.  No model trained on BMP features may be installed with this schema.

To export from a trusted training process that already owns its fitted scaler `s` and classifier `m`:

```python
import numpy as np
np.savez('rt_candidate.npz',
    feature_source_sha256='27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923',
    classes=m.classes_, mean=s.mean_, scale=s.scale_,
    w0=m.coefs_[0], b0=m.intercepts_[0],
    w1=m.coefs_[1], b1=m.intercepts_[1],
    w2=m.coefs_[2], b2=m.intercepts_[2])
```

Then, with NumPy installed:

```powershell
py export_numeric_model.py rt_candidate.npz --threshold 0.9832595196 --output rt_candidate.bin
```

Use the threshold chosen for that new model on held-out validation data.  Preserve its training report, split, model provenance and review grades alongside the exported package.  Architecture and metadata declarations do not prove a retrained model is accurate or was trained with the correct preprocessing.  No automatic training or promotion is performed by the device.
