"""Prepare standalone ESP-IDF exact-FIR/spool/quantile probe sources, no board connection."""
from modify import HERE,emit
out=HERE/'emulator/main/generated';emit(out)
(out/'RTFeaturesReference.h').write_text((HERE/'tests/reference/RTFeaturesSchema1.h').read_text().replace('namespace RTFeatures {','namespace RTFeaturesReference {'))
print('ESP-IDF v5.4.2: cd emulator; idf.py set-target esp32s3; idf.py build')
print('Run image in esp-emu 0.50.0 with exit marker GUARD4_S3_PASS. This is not a full RT or timing test.')
