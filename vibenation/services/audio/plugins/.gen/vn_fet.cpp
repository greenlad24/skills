/* ------------------------------------------------------------
license: "MIT"
name: "vn_fet"
Code generated with Faust 2.70.3 (https://faust.grame.fr)
Compilation options: -a /root/vibenation/vibenation/services/audio/plugins/common/vn_arch.cpp -lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -double -ftz 0
------------------------------------------------------------ */

#ifndef  __mydsp_H__
#define  __mydsp_H__

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


#ifndef FAUSTFLOAT
#define FAUSTFLOAT float
#endif 

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <math.h>

#ifndef FAUSTCLASS 
#define FAUSTCLASS mydsp
#endif

#ifdef __APPLE__ 
#define exp10f __exp10f
#define exp10 __exp10
#endif

#if defined(_WIN32)
#define RESTRICT __restrict
#else
#define RESTRICT __restrict__
#endif

static double mydsp_faustpower2_f(double value) {
	return value * value;
}

class mydsp : public dsp {
	
 private:
	
	int fSampleRate;
	double fConst2;
	double fConst3;
	FAUSTFLOAT fHslider0;
	double fRec2[2];
	double fConst4;
	double fConst5;
	FAUSTFLOAT fEntry0;
	FAUSTFLOAT fHslider1;
	double fConst6;
	FAUSTFLOAT fHslider2;
	double fRec3[2];
	double fRec4[2];
	FAUSTFLOAT fHbargraph0;
	FAUSTFLOAT fHslider3;
	double fRec5[2];
	double fRec1[2];
	double fVec0[2];
	double fConst7;
	double fRec0[2];
	double fConst8;
	double fConst9;
	FAUSTFLOAT fHslider4;
	double fRec6[2];
	FAUSTFLOAT fHslider5;
	double fRec7[2];
	double fConst10;
	
 public:
	mydsp() {}

	void metadata(Meta* m) { 
		m->declare("basics.lib/name", "Faust Basic Element Library");
		m->declare("basics.lib/tabulateNd", "Copyright (C) 2023 Bart Brouns <bart@magnetophon.nl>");
		m->declare("basics.lib/version", "1.12.0");
		m->declare("compile_options", "-a /root/vibenation/vibenation/services/audio/plugins/common/vn_arch.cpp -lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -double -ftz 0");
		m->declare("filename", "vn_fet.dsp");
		m->declare("filters.lib/dcblockerat:author", "Julius O. Smith III");
		m->declare("filters.lib/dcblockerat:copyright", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/dcblockerat:license", "MIT-style STK-4.3 license");
		m->declare("filters.lib/lowpass0_highpass1", "MIT-style STK-4.3 license");
		m->declare("filters.lib/name", "Faust Filters Library");
		m->declare("filters.lib/pole:author", "Julius O. Smith III");
		m->declare("filters.lib/pole:copyright", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/pole:license", "MIT-style STK-4.3 license");
		m->declare("filters.lib/version", "1.3.0");
		m->declare("filters.lib/zero:author", "Julius O. Smith III");
		m->declare("filters.lib/zero:copyright", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/zero:license", "MIT-style STK-4.3 license");
		m->declare("license", "MIT");
		m->declare("maths.lib/author", "GRAME");
		m->declare("maths.lib/copyright", "GRAME");
		m->declare("maths.lib/license", "LGPL with exception");
		m->declare("maths.lib/name", "Faust Math Library");
		m->declare("maths.lib/version", "2.7.0");
		m->declare("name", "vn_fet");
		m->declare("platform.lib/name", "Generic Platform Library");
		m->declare("platform.lib/version", "1.3.0");
		m->declare("vn.lib/name", "vn.lib");
		m->declare("vn_class", "CompressorPlugin");
		m->declare("vn_comment", "1176-style FET compressor: input, output, ratio 4/8/12/20/all, attack 20-800 us, release 50-1100 ms, colour, mix. Outputs gain reduction in dB.");
		m->declare("vn_name", "VN FET Compressor");
		m->declare("vn_oversample", "2");
	}

	virtual int getNumInputs() {
		return 1;
	}
	virtual int getNumOutputs() {
		return 1;
	}
	
	static void classInit(int sample_rate) {
	}
	
	virtual void instanceConstants(int sample_rate) {
		fSampleRate = sample_rate;
		double fConst0 = std::min<double>(1.92e+05, std::max<double>(1.0, double(fSampleRate)));
		double fConst1 = 25.132741228718345 / fConst0;
		fConst2 = 1.0 - fConst1;
		fConst3 = std::exp(-(5e+01 / fConst0));
		fConst4 = 1.0 - fConst3;
		fConst5 = 0.05 * fConst4;
		fConst6 = 1.0 / fConst0;
		fConst7 = 1.0 / (fConst1 + 1.0);
		fConst8 = 0.06 * fConst4;
		fConst9 = 0.02 * fConst4;
		fConst10 = 0.01 * fConst4;
	}
	
	virtual void instanceResetUserInterface() {
		fHslider0 = FAUSTFLOAT(0.0);
		fEntry0 = FAUSTFLOAT(0.0);
		fHslider1 = FAUSTFLOAT(3e+02);
		fHslider2 = FAUSTFLOAT(3e+02);
		fHslider3 = FAUSTFLOAT(5e+01);
		fHslider4 = FAUSTFLOAT(0.0);
		fHslider5 = FAUSTFLOAT(1e+02);
	}
	
	virtual void instanceClear() {
		for (int l0 = 0; l0 < 2; l0 = l0 + 1) {
			fRec2[l0] = 0.0;
		}
		for (int l1 = 0; l1 < 2; l1 = l1 + 1) {
			fRec3[l1] = 0.0;
		}
		for (int l2 = 0; l2 < 2; l2 = l2 + 1) {
			fRec4[l2] = 0.0;
		}
		for (int l3 = 0; l3 < 2; l3 = l3 + 1) {
			fRec5[l3] = 0.0;
		}
		for (int l4 = 0; l4 < 2; l4 = l4 + 1) {
			fRec1[l4] = 0.0;
		}
		for (int l5 = 0; l5 < 2; l5 = l5 + 1) {
			fVec0[l5] = 0.0;
		}
		for (int l6 = 0; l6 < 2; l6 = l6 + 1) {
			fRec0[l6] = 0.0;
		}
		for (int l7 = 0; l7 < 2; l7 = l7 + 1) {
			fRec6[l7] = 0.0;
		}
		for (int l8 = 0; l8 < 2; l8 = l8 + 1) {
			fRec7[l8] = 0.0;
		}
	}
	
	virtual void init(int sample_rate) {
		classInit(sample_rate);
		instanceInit(sample_rate);
	}
	
	virtual void instanceInit(int sample_rate) {
		instanceConstants(sample_rate);
		instanceResetUserInterface();
		instanceClear();
	}
	
	virtual mydsp* clone() {
		return new mydsp();
	}
	
	virtual int getSampleRate() {
		return fSampleRate;
	}
	
	virtual void buildUserInterface(UI* ui_interface) {
		ui_interface->openVerticalBox("vn_fet");
		ui_interface->declare(&fHslider2, "log", "");
		ui_interface->declare(&fHslider2, "name", "Attack");
		ui_interface->declare(&fHslider2, "unit", "us");
		ui_interface->addHorizontalSlider("attack", &fHslider2, FAUSTFLOAT(3e+02), FAUSTFLOAT(2e+01), FAUSTFLOAT(8e+02), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHslider3, "name", "Colour");
		ui_interface->declare(&fHslider3, "unit", "%");
		ui_interface->addHorizontalSlider("colour", &fHslider3, FAUSTFLOAT(5e+01), FAUSTFLOAT(0.0), FAUSTFLOAT(1e+02), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHbargraph0, "name", "Gain Reduction");
		ui_interface->declare(&fHbargraph0, "unit", "dB");
		ui_interface->addHorizontalBargraph("gr", &fHbargraph0, FAUSTFLOAT(0.0), FAUSTFLOAT(4e+01));
		ui_interface->declare(&fHslider0, "name", "Input");
		ui_interface->declare(&fHslider0, "unit", "dB");
		ui_interface->addHorizontalSlider("input", &fHslider0, FAUSTFLOAT(0.0), FAUSTFLOAT(-2e+01), FAUSTFLOAT(4e+01), FAUSTFLOAT(0.1));
		ui_interface->declare(&fHslider5, "name", "Mix");
		ui_interface->declare(&fHslider5, "unit", "%");
		ui_interface->addHorizontalSlider("mix", &fHslider5, FAUSTFLOAT(1e+02), FAUSTFLOAT(0.0), FAUSTFLOAT(1e+02), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHslider4, "name", "Output");
		ui_interface->declare(&fHslider4, "unit", "dB");
		ui_interface->addHorizontalSlider("output", &fHslider4, FAUSTFLOAT(0.0), FAUSTFLOAT(-3e+01), FAUSTFLOAT(2e+01), FAUSTFLOAT(0.1));
		ui_interface->declare(&fEntry0, "enum", "4:1|8:1|12:1|20:1|All");
		ui_interface->declare(&fEntry0, "name", "Ratio");
		ui_interface->addNumEntry("ratio", &fEntry0, FAUSTFLOAT(0.0), FAUSTFLOAT(0.0), FAUSTFLOAT(4.0), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHslider1, "log", "");
		ui_interface->declare(&fHslider1, "name", "Release");
		ui_interface->declare(&fHslider1, "unit", "ms");
		ui_interface->addHorizontalSlider("release", &fHslider1, FAUSTFLOAT(3e+02), FAUSTFLOAT(5e+01), FAUSTFLOAT(1.1e+03), FAUSTFLOAT(1.0));
		ui_interface->closeBox();
	}
	
	virtual void compute(int count, FAUSTFLOAT** RESTRICT inputs, FAUSTFLOAT** RESTRICT outputs) {
		FAUSTFLOAT* input0 = inputs[0];
		FAUSTFLOAT* output0 = outputs[0];
		double fSlow0 = double(fHslider0);
		double fSlow1 = double(fEntry0);
		int iSlow2 = fSlow1 >= 3.0;
		int iSlow3 = fSlow1 >= 2.0;
		int iSlow4 = fSlow1 >= 1.0;
		int iSlow5 = fSlow1 >= 4.0;
		int iSlow6 = ((iSlow2) ? ((iSlow5) ? 1 : 2) : ((iSlow3) ? 3 : ((iSlow4) ? 4 : 6)));
		double fSlow7 = 0.5 * double(iSlow6);
		double fSlow8 = double(((iSlow2) ? ((iSlow5) ? -17 : -16) : ((iSlow3) ? -17 : ((iSlow4) ? -18 : -20))));
		double fSlow9 = 0.5 * double(-iSlow6);
		double fSlow10 = double(2 * iSlow6);
		int iSlow11 = ((iSlow2) ? ((iSlow5) ? 30 : 19) : ((iSlow3) ? 11 : ((iSlow4) ? 7 : 3)));
		double fSlow12 = double(iSlow11);
		int iSlow13 = fSlow1 == 4.0;
		double fSlow14 = ((iSlow13) ? 0.8 : 1.0);
		double fSlow15 = double(fHslider1);
		double fSlow16 = 1.0 - std::exp(-(fConst6 / std::max<double>(0.005 * fSlow15 * fSlow14, 1e-06)));
		double fSlow17 = 1.0 - std::exp(-(fConst6 / std::max<double>(1e-06 * double(fHslider2) * ((iSlow13) ? 0.5 : 1.0) * double(iSlow11 + 1), 1e-06)));
		double fSlow18 = 0.0002380952380952381 * (fSlow15 + -5e+01);
		double fSlow19 = fSlow18 + 0.2;
		double fSlow20 = 1.0 - std::exp(-(fConst6 / std::max<double>(0.001 * fSlow15 * fSlow14, 1e-06)));
		double fSlow21 = 0.8 - fSlow18;
		double fSlow22 = ((iSlow13) ? 0.12 : 0.06);
		double fSlow23 = 0.01 * double(fHslider3);
		double fSlow24 = double(fHslider4);
		double fSlow25 = double(fHslider5);
		for (int i0 = 0; i0 < count; i0 = i0 + 1) {
			fRec2[0] = fSlow0 + fConst3 * fRec2[1];
			double fTemp0 = std::pow(1e+01, fConst5 * fRec2[0]);
			double fTemp1 = double(input0[i0]);
			double fTemp2 = fTemp1 * fTemp0;
			double fTemp3 = std::fabs(fTemp2) + 1.0;
			double fTemp4 = 2e+01 * std::log10(std::max<double>(std::fabs(fRec1[1]), 1e-09));
			double fTemp5 = fTemp4 - fSlow8;
			double fTemp6 = fSlow12 * ((fTemp5 > fSlow7) ? fTemp5 : ((fTemp5 > fSlow9) ? mydsp_faustpower2_f(fTemp4 + fSlow7 - fSlow8) / fSlow10 : 0.0));
			fRec3[0] = fRec3[1] + (fTemp6 - fRec3[1]) * ((fTemp6 > fRec3[1]) ? fSlow17 : fSlow16);
			fRec4[0] = fRec4[1] + (fTemp6 - fRec4[1]) * ((fTemp6 > fRec4[1]) ? fSlow17 : fSlow20);
			fHbargraph0 = FAUSTFLOAT(std::min<double>(4e+01, std::max<double>(0.0, fSlow21 * fRec4[0] + fSlow19 * fRec3[0])));
			double fTemp7 = std::pow(1e+01, -(0.05 * fHbargraph0));
			fRec5[0] = fSlow23 + fConst3 * fRec5[1];
			fRec1[0] = fTemp2 * fTemp7 / (fConst4 * (fTemp1 * fRec5[0] * fSlow22 * fTemp0 * std::min<double>(1.0, 1.04 - fTemp7) * (0.6 * (mydsp_faustpower2_f(fTemp1) * mydsp_faustpower2_f(fTemp0) / mydsp_faustpower2_f(fTemp3)) + 0.25) / fTemp3) + 1.0);
			double fTemp8 = mydsp_faustpower2_f(std::min<double>(2.0, std::max<double>(-2.0, fRec1[0])));
			fVec0[0] = fTemp8;
			fRec0[0] = fConst7 * (fTemp8 - fVec0[1] + fConst2 * fRec0[1]);
			double fTemp9 = fRec1[0] - fConst8 * fRec5[0] * fRec0[0];
			fRec6[0] = fSlow24 + fConst3 * fRec6[1];
			fRec7[0] = fSlow25 + fConst3 * fRec7[1];
			output0[i0] = FAUSTFLOAT(fTemp1 * (1.0 - fConst10 * fRec7[0]) + fConst10 * (fRec7[0] * fTemp9 * std::pow(1e+01, fConst5 * fRec6[0]) / (fConst9 * fRec5[0] * mydsp_faustpower2_f(fTemp9) + 1.0)));
			fRec2[1] = fRec2[0];
			fRec3[1] = fRec3[0];
			fRec4[1] = fRec4[0];
			fRec5[1] = fRec5[0];
			fRec1[1] = fRec1[0];
			fVec0[1] = fVec0[0];
			fRec0[1] = fRec0[0];
			fRec6[1] = fRec6[0];
			fRec7[1] = fRec7[0];
		}
	}

};

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

#endif
