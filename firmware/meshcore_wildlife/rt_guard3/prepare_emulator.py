"""Prepare standalone ESP-IDF policy/quantile probe sources, no board connection."""
from modify import HERE,emit
out=HERE/'emulator/main/generated';emit(out)
(out/'RTFeaturesReference.h').write_text((HERE/'base/RTFeatures.h').read_text().replace('namespace RTFeatures {','namespace RTFeaturesReference {'))
print('ESP-IDF v5.4.2: cd emulator; idf.py set-target esp32s3; idf.py build')
print('Run image in esp-emu 0.50.0 with exit marker GUARD3_S3_PASS. This is not a full RT or timing test.')
