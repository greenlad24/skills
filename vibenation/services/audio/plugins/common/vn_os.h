// VibeNation 2x oversampling: polyphase IIR half-band (elliptic, 8 coefficients,
// transition 0.04 -> passband flat to 20.1 kHz at 48 kHz, ~100 dB image/alias rejection).
// Coefficients from common/halfband_design.py (algorithm after L. de Soras' hiir).
// Round-trip group delay ~3 samples at low frequencies (reported as plugin latency).
#pragma once

namespace vn {

static const double kHB[8] = {
    0.04063346092419326, 0.1505051290226746, 0.30075705599187408, 0.46077450496145061,
    0.6095243148961883,  0.73850384111885725, 0.84922381039206607, 0.9497427837050002};

// Cascade of 4 first-order allpasses in z^-1 (polyphase branch of a half-band filter).
struct APChain {
    double c[4];
    double x1[4], y1[4];
    void init(int odd) {
        for (int i = 0; i < 4; ++i) { c[i] = kHB[2 * i + odd]; x1[i] = y1[i] = 0.0; }
    }
    void reset() { for (int i = 0; i < 4; ++i) x1[i] = y1[i] = 0.0; }
    inline double tick(double x) {
        for (int i = 0; i < 4; ++i) {
            const double y = c[i] * (x - y1[i]) + x1[i];
            x1[i] = x; y1[i] = y; x = y;
        }
        return x;
    }
};

struct Upsampler2x {
    APChain a, b;
    void init() { a.init(0); b.init(1); }
    void reset() { a.reset(); b.reset(); }
    inline void process(const float* in, float* out, int n) {
        for (int i = 0; i < n; ++i) {
            const double x = in[i];
            out[2 * i]     = (float)a.tick(x);
            out[2 * i + 1] = (float)b.tick(x);
        }
    }
};

struct Downsampler2x {
    APChain a, b;
    void init() { a.init(0); b.init(1); }
    void reset() { a.reset(); b.reset(); }
    inline void process(const float* in, float* out, int n) {
        for (int i = 0; i < n; ++i) {
            out[i] = (float)(0.5 * (a.tick(in[2 * i + 1]) + b.tick(in[2 * i])));
        }
    }
};

} // namespace vn
