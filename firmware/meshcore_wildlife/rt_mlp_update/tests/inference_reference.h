#pragma once
// Portable C++ shadow-only scorer for WAV MLP v0.1.
// Never call this to suppress recording or to replace RT-SCORE-1 triggers.
// The 165 features must match training/phase1/train_baseline_models.py's
// wav_features() exactly; no feature implementation is supplied here.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include "../payload/nzrt/wav_mlp_model_parameters.h"

namespace nzrt { namespace wav_mlp {
constexpr std::size_t kFeatures = 165;
constexpr std::size_t kHidden1 = 32;
constexpr std::size_t kHidden2 = 16;
// Model export checked against owner WAV report SHA-256.
inline float score(const float features[kFeatures]) noexcept {
    if (!features) return NAN;
    double a[kHidden1];
    for(std::size_t j=0;j<kHidden1;++j) {
        double z=static_cast<double>(kBias0[j]);
        for(std::size_t i=0;i<kFeatures;++i) {
            float f=features[i];
            if(!std::isfinite(f)) return NAN;
            const double scaled=(static_cast<double>(f)-static_cast<double>(kScalerMean[i]))/
                                      static_cast<double>(kScalerScale[i]);
            z += scaled * static_cast<double>(kWeights0[i*kHidden1+j]);
        }
        a[j] = z>0.0 ? z : 0.0;
    }
    double b[kHidden2];
    for(std::size_t j=0;j<kHidden2;++j) {
        double z=static_cast<double>(kBias1[j]);
        for(std::size_t i=0;i<kHidden1;++i)
            z += a[i]*static_cast<double>(kWeights1[i*kHidden2+j]);
        b[j]=z>0.0?z:0.0;
    }
    double z=static_cast<double>(kBias2[0]);
    for(std::size_t i=0;i<kHidden2;++i)z+=b[i]*static_cast<double>(kWeights2[i]);
    // Stable logistic output; no math-library vector or ml runtime required.
    const double p=(z>=0.) ? 1.0/(1.0+std::exp(-z))
            : std::exp(z)/(1.0+std::exp(z));
    return static_cast<float>(p);
}
inline bool positive(float probability) noexcept {
    return std::isfinite(probability) && probability >= kValidationThreshold;
}
}}
