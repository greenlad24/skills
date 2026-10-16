/* VibeNation Faust -> LV2 architecture file.
 *
 * Port layout (must match common/gen_ttl.py):
 *   0 .. nin-1                 audio inputs
 *   nin .. nin+nout-1          audio outputs
 *   then every Faust UI widget in declaration (depth-first) order:
 *     sliders / checkboxes / nentries  -> input control ports
 *     bargraphs                        -> output control ports
 *   last: "latency" output control port (samples)
 *
 * Oversampling: declare vn_oversample "2"; in the .dsp runs the whole Faust
 * program at 2x the host rate between polyphase IIR half-band filters.
 */
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
#include <xmmintrin.h>
#include <pmmintrin.h>

#include <faust/dsp/dsp.h>
#include <faust/gui/UI.h>
#include <faust/gui/meta.h>

#include <lv2/core/lv2.h>

#include "vn_os.h"

<<includeIntrinsic>>

<<includeclass>>

#ifndef VN_URI
#error "VN_URI must be defined"
#endif

namespace {

struct VNZone {
    FAUSTFLOAT* zone;
    float lo, hi;
    bool output;
};

struct ZoneCollector : public UI {
    std::vector<VNZone> zones;
    void add(FAUSTFLOAT* z, float lo, float hi, bool out) { zones.push_back({z, lo, hi, out}); }
    void openTabBox(const char*) override {}
    void openHorizontalBox(const char*) override {}
    void openVerticalBox(const char*) override {}
    void closeBox() override {}
    void addButton(const char*, FAUSTFLOAT* z) override { add(z, 0, 1, false); }
    void addCheckButton(const char*, FAUSTFLOAT* z) override { add(z, 0, 1, false); }
    void addVerticalSlider(const char*, FAUSTFLOAT* z, FAUSTFLOAT, FAUSTFLOAT lo, FAUSTFLOAT hi, FAUSTFLOAT) override { add(z, lo, hi, false); }
    void addHorizontalSlider(const char*, FAUSTFLOAT* z, FAUSTFLOAT, FAUSTFLOAT lo, FAUSTFLOAT hi, FAUSTFLOAT) override { add(z, lo, hi, false); }
    void addNumEntry(const char*, FAUSTFLOAT* z, FAUSTFLOAT, FAUSTFLOAT lo, FAUSTFLOAT hi, FAUSTFLOAT) override { add(z, lo, hi, false); }
    void addHorizontalBargraph(const char*, FAUSTFLOAT* z, FAUSTFLOAT lo, FAUSTFLOAT hi) override { add(z, lo, hi, true); }
    void addVerticalBargraph(const char*, FAUSTFLOAT* z, FAUSTFLOAT lo, FAUSTFLOAT hi) override { add(z, lo, hi, true); }
    void addSoundfile(const char*, const char*, Soundfile**) override {}
    void declare(FAUSTFLOAT*, const char*, const char*) override {}
};

struct OSMeta : public Meta {
    int os = 1;
    void declare(const char* key, const char* value) override {
        if (!strcmp(key, "vn_oversample")) os = std::max(1, std::min(2, atoi(value)));
    }
};

static const int kChunk = 1024;   // host-rate samples per internal compute call
static const int kMaxCh = 2;

struct VNPlugin {
    mydsp dsp;
    int nin = 0, nout = 0, os = 1;
    std::vector<VNZone> zones;
    std::vector<float*> ctl;          // connected control ports (same order as zones)
    const float* ain[kMaxCh] = {nullptr, nullptr};
    float* aout[kMaxCh] = {nullptr, nullptr};
    float* latency = nullptr;
    // working buffers
    float inbuf[kMaxCh][2 * kChunk];
    float outbuf[kMaxCh][2 * kChunk];
    float copyin[kMaxCh][kChunk];
    vn::Upsampler2x up[kMaxCh];
    vn::Downsampler2x down[kMaxCh];
};

LV2_Handle instantiate(const LV2_Descriptor*, double rate, const char*, const LV2_Feature* const*) {
    VNPlugin* p = new VNPlugin();
    OSMeta m;
    p->dsp.metadata(&m);
    p->os = m.os;
    p->nin = p->dsp.getNumInputs();
    p->nout = p->dsp.getNumOutputs();
    if (p->nin > kMaxCh || p->nout > kMaxCh) { delete p; return nullptr; }
    p->dsp.init((int)std::lround(rate * p->os));
    ZoneCollector c;
    p->dsp.buildUserInterface(&c);
    p->zones = c.zones;
    p->ctl.assign(p->zones.size(), nullptr);
    for (int i = 0; i < kMaxCh; ++i) { p->up[i].init(); p->down[i].init(); }
    return (LV2_Handle)p;
}

void connect_port(LV2_Handle h, uint32_t port, void* data) {
    VNPlugin* p = (VNPlugin*)h;
    uint32_t i = port;
    if (i < (uint32_t)p->nin) { p->ain[i] = (const float*)data; return; }
    i -= p->nin;
    if (i < (uint32_t)p->nout) { p->aout[i] = (float*)data; return; }
    i -= p->nout;
    if (i < p->zones.size()) { p->ctl[i] = (float*)data; return; }
    i -= p->zones.size();
    if (i == 0) p->latency = (float*)data;
}

void activate(LV2_Handle h) {
    VNPlugin* p = (VNPlugin*)h;
    p->dsp.instanceClear();
    for (int i = 0; i < kMaxCh; ++i) { p->up[i].reset(); p->down[i].reset(); }
}

void run(LV2_Handle h, uint32_t nframes) {
    VNPlugin* p = (VNPlugin*)h;
    const unsigned int csr = _mm_getcsr();
    _mm_setcsr(csr | 0x8040);  // FTZ + DAZ: no denormal stalls in the recursive filters

    for (size_t z = 0; z < p->zones.size(); ++z) {
        const VNZone& vz = p->zones[z];
        if (vz.output || !p->ctl[z]) continue;
        float v = *p->ctl[z];
        if (!(v == v)) v = vz.lo;              // NaN guard
        *vz.zone = std::min(vz.hi, std::max(vz.lo, v));
    }

    uint32_t done = 0;
    while (done < nframes) {
        const int n = (int)std::min<uint32_t>(kChunk, nframes - done);
        FAUSTFLOAT* ins[kMaxCh];
        FAUSTFLOAT* outs[kMaxCh];
        if (p->os == 1) {
            for (int c = 0; c < p->nin; ++c) {
                if (p->ain[c]) memcpy(p->copyin[c], p->ain[c] + done, n * sizeof(float));
                else memset(p->copyin[c], 0, n * sizeof(float));
                ins[c] = p->copyin[c];
            }
            for (int c = 0; c < p->nout; ++c) outs[c] = p->outbuf[c];
            p->dsp.compute(n, ins, outs);
            for (int c = 0; c < p->nout; ++c)
                if (p->aout[c]) memcpy(p->aout[c] + done, p->outbuf[c], n * sizeof(float));
        } else {
            for (int c = 0; c < p->nin; ++c) {
                if (p->ain[c]) memcpy(p->copyin[c], p->ain[c] + done, n * sizeof(float));
                else memset(p->copyin[c], 0, n * sizeof(float));
                p->up[c].process(p->copyin[c], p->inbuf[c], n);
                ins[c] = p->inbuf[c];
            }
            for (int c = 0; c < p->nout; ++c) outs[c] = p->outbuf[c];
            p->dsp.compute(2 * n, ins, outs);
            for (int c = 0; c < p->nout; ++c)
                if (p->aout[c]) p->down[c].process(p->outbuf[c], p->aout[c] + done, n);
        }
        done += n;
    }

    for (size_t z = 0; z < p->zones.size(); ++z) {
        const VNZone& vz = p->zones[z];
        if (vz.output && p->ctl[z]) {
            float v = *vz.zone;
            if (!std::isfinite(v)) v = 0.f;
            *p->ctl[z] = std::min(vz.hi, std::max(vz.lo, v));
        }
    }
    if (p->latency) *p->latency = (p->os > 1) ? 3.0f : 0.0f;
    _mm_setcsr(csr);
}

void deactivate(LV2_Handle) {}
void cleanup(LV2_Handle h) { delete (VNPlugin*)h; }
const void* extension_data(const char*) { return nullptr; }

const LV2_Descriptor descriptor = {VN_URI, instantiate, connect_port, activate, run, deactivate, cleanup, extension_data};

} // namespace

extern "C" LV2_SYMBOL_EXPORT const LV2_Descriptor* lv2_descriptor(uint32_t index) {
    return index == 0 ? &descriptor : nullptr;
}
