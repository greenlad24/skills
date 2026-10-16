/* ------------------------------------------------------------
license: "MIT"
name: "vn_opto"
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
static double mydsp_faustpower3_f(double value) {
	return value * value * value;
}

class mydsp : public dsp {
	
 private:
	
	int fSampleRate;
	double fConst1;
	FAUSTFLOAT fHslider0;
	double fRec0[2];
	double fConst2;
	double fConst3;
	FAUSTFLOAT fEntry0;
	FAUSTFLOAT fHslider1;
	double fRec4[2];
	double fConst4;
	FAUSTFLOAT fHslider2;
	double fConst5;
	double fRec15[2];
	double fRec16[2];
	double fConst6;
	FAUSTFLOAT fHslider3;
	double fRec11[2];
	double fRec12[2];
	FAUSTFLOAT fHslider4;
	double fConst7;
	double fRec6[2];
	double fRec7[2];
	double fConst8;
	double fRec5[2];
	double fConst9;
	double fConst10;
	double fConst11;
	double fRec20[2];
	double fConst12;
	double fConst13;
	double fRec3[2];
	double fConst14;
	double fConst15;
	double fRec21[2];
	double fConst16;
	double fConst17;
	double fRec2[2];
	FAUSTFLOAT fHbargraph0;
	double fRec1[2];
	double fConst19;
	double fVec0[2];
	double fConst20;
	double fRec22[2];
	FAUSTFLOAT fHslider5;
	double fRec23[2];
	FAUSTFLOAT fHslider6;
	double fRec24[2];
	double fConst21;
	
 public:
	mydsp() {}

	void metadata(Meta* m) { 
		m->declare("compile_options", "-a /root/vibenation/vibenation/services/audio/plugins/common/vn_arch.cpp -lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -double -ftz 0");
		m->declare("filename", "vn_opto.dsp");
		m->declare("filters.lib/dcblockerat:author", "Julius O. Smith III");
		m->declare("filters.lib/dcblockerat:copyright", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/dcblockerat:license", "MIT-style STK-4.3 license");
		m->declare("filters.lib/lowpass0_highpass1", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/name", "Faust Filters Library");
		m->declare("filters.lib/pole:author", "Julius O. Smith III");
		m->declare("filters.lib/pole:copyright", "Copyright (C) 2003-2019 by Julius O. Smith III <jos@ccrma.stanford.edu>");
		m->declare("filters.lib/pole:license", "MIT-style STK-4.3 license");
		m->declare("filters.lib/svf:author", "Oleg Nesterov");
		m->declare("filters.lib/svf:copyright", "Copyright (C) 2020 Oleg Nesterov <oleg@redhat.com>");
		m->declare("filters.lib/svf:license", "MIT-style STK-4.3 license");
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
		m->declare("name", "vn_opto");
		m->declare("platform.lib/name", "Generic Platform Library");
		m->declare("platform.lib/version", "1.3.0");
		m->declare("routes.lib/name", "Faust Signal Routing Library");
		m->declare("routes.lib/version", "1.2.0");
		m->declare("signals.lib/name", "Faust Signal Routing Library");
		m->declare("signals.lib/version", "1.5.0");
		m->declare("vn.lib/name", "vn.lib");
		m->declare("vn_class", "CompressorPlugin");
		m->declare("vn_comment", "T4 optical leveler: Peak Reduction, Gain, Mix, 3-band sidechain emphasis. Outputs gain reduction in dB.");
		m->declare("vn_name", "VN Opto Leveler");
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
		fConst1 = std::exp(-(5e+01 / fConst0));
		fConst2 = 1.0 - fConst1;
		fConst3 = 0.05 * fConst2;
		fConst4 = 0.45 * fConst2;
		fConst5 = std::tan(628.3185307179587 / fConst0);
		fConst6 = std::tan(4712.38898038469 / fConst0);
		fConst7 = std::tan(15707.963267948966 / fConst0);
		fConst8 = std::exp(-(125.0 / fConst0));
		fConst9 = 1.0 - fConst8;
		fConst10 = 1.0 - std::exp(-(4e+01 / fConst0));
		fConst11 = 1.0 - std::exp(-(3333.3333333333335 / fConst0));
		fConst12 = 1.0 - std::exp(-(16.666666666666668 / fConst0));
		fConst13 = 1.0 - std::exp(-(1e+02 / fConst0));
		fConst14 = 1.0 - std::exp(-(0.06666666666666667 / fConst0));
		fConst15 = 1.0 - std::exp(-(0.5 / fConst0));
		fConst16 = 1.0 / fConst0;
		fConst17 = 1.0 - std::exp(-(12.5 / fConst0));
		double fConst18 = 25.132741228718345 / fConst0;
		fConst19 = 1.0 - fConst18;
		fConst20 = 1.0 / (fConst18 + 1.0);
		fConst21 = 0.01 * fConst2;
	}
	
	virtual void instanceResetUserInterface() {
		fHslider0 = FAUSTFLOAT(0.0);
		fEntry0 = FAUSTFLOAT(0.0);
		fHslider1 = FAUSTFLOAT(3e+01);
		fHslider2 = FAUSTFLOAT(0.0);
		fHslider3 = FAUSTFLOAT(0.0);
		fHslider4 = FAUSTFLOAT(0.0);
		fHslider5 = FAUSTFLOAT(3e+01);
		fHslider6 = FAUSTFLOAT(1e+02);
	}
	
	virtual void instanceClear() {
		for (int l0 = 0; l0 < 2; l0 = l0 + 1) {
			fRec0[l0] = 0.0;
		}
		for (int l1 = 0; l1 < 2; l1 = l1 + 1) {
			fRec4[l1] = 0.0;
		}
		for (int l2 = 0; l2 < 2; l2 = l2 + 1) {
			fRec15[l2] = 0.0;
		}
		for (int l3 = 0; l3 < 2; l3 = l3 + 1) {
			fRec16[l3] = 0.0;
		}
		for (int l4 = 0; l4 < 2; l4 = l4 + 1) {
			fRec11[l4] = 0.0;
		}
		for (int l5 = 0; l5 < 2; l5 = l5 + 1) {
			fRec12[l5] = 0.0;
		}
		for (int l6 = 0; l6 < 2; l6 = l6 + 1) {
			fRec6[l6] = 0.0;
		}
		for (int l7 = 0; l7 < 2; l7 = l7 + 1) {
			fRec7[l7] = 0.0;
		}
		for (int l8 = 0; l8 < 2; l8 = l8 + 1) {
			fRec5[l8] = 0.0;
		}
		for (int l9 = 0; l9 < 2; l9 = l9 + 1) {
			fRec20[l9] = 0.0;
		}
		for (int l10 = 0; l10 < 2; l10 = l10 + 1) {
			fRec3[l10] = 0.0;
		}
		for (int l11 = 0; l11 < 2; l11 = l11 + 1) {
			fRec21[l11] = 0.0;
		}
		for (int l12 = 0; l12 < 2; l12 = l12 + 1) {
			fRec2[l12] = 0.0;
		}
		for (int l13 = 0; l13 < 2; l13 = l13 + 1) {
			fRec1[l13] = 0.0;
		}
		for (int l14 = 0; l14 < 2; l14 = l14 + 1) {
			fVec0[l14] = 0.0;
		}
		for (int l15 = 0; l15 < 2; l15 = l15 + 1) {
			fRec22[l15] = 0.0;
		}
		for (int l16 = 0; l16 < 2; l16 = l16 + 1) {
			fRec23[l16] = 0.0;
		}
		for (int l17 = 0; l17 < 2; l17 = l17 + 1) {
			fRec24[l17] = 0.0;
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
		ui_interface->openVerticalBox("vn_opto");
		ui_interface->declare(&fHslider5, "name", "Tube Colour");
		ui_interface->declare(&fHslider5, "unit", "%");
		ui_interface->addHorizontalSlider("colour", &fHslider5, FAUSTFLOAT(3e+01), FAUSTFLOAT(0.0), FAUSTFLOAT(1e+02), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHslider0, "name", "Gain");
		ui_interface->declare(&fHslider0, "unit", "dB");
		ui_interface->addHorizontalSlider("gain", &fHslider0, FAUSTFLOAT(0.0), FAUSTFLOAT(-2e+01), FAUSTFLOAT(3e+01), FAUSTFLOAT(0.1));
		ui_interface->declare(&fHbargraph0, "name", "Gain Reduction");
		ui_interface->declare(&fHbargraph0, "unit", "dB");
		ui_interface->addHorizontalBargraph("gr", &fHbargraph0, FAUSTFLOAT(0.0), FAUSTFLOAT(4e+01));
		ui_interface->declare(&fHslider6, "name", "Mix");
		ui_interface->declare(&fHslider6, "unit", "%");
		ui_interface->addHorizontalSlider("mix", &fHslider6, FAUSTFLOAT(1e+02), FAUSTFLOAT(0.0), FAUSTFLOAT(1e+02), FAUSTFLOAT(1.0));
		ui_interface->declare(&fEntry0, "enum", "Compress|Limit");
		ui_interface->declare(&fEntry0, "name", "Mode");
		ui_interface->addNumEntry("mode", &fEntry0, FAUSTFLOAT(0.0), FAUSTFLOAT(0.0), FAUSTFLOAT(1.0), FAUSTFLOAT(1.0));
		ui_interface->declare(&fHslider1, "name", "Peak Reduction");
		ui_interface->declare(&fHslider1, "unit", "%");
		ui_interface->addHorizontalSlider("peak_reduction", &fHslider1, FAUSTFLOAT(3e+01), FAUSTFLOAT(0.0), FAUSTFLOAT(1e+02), FAUSTFLOAT(0.1));
		ui_interface->declare(&fHslider4, "name", "Sidechain High 5 kHz");
		ui_interface->declare(&fHslider4, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_high", &fHslider4, FAUSTFLOAT(0.0), FAUSTFLOAT(-12.0), FAUSTFLOAT(12.0), FAUSTFLOAT(0.1));
		ui_interface->declare(&fHslider2, "name", "Sidechain Low 200 Hz");
		ui_interface->declare(&fHslider2, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_low", &fHslider2, FAUSTFLOAT(0.0), FAUSTFLOAT(-12.0), FAUSTFLOAT(12.0), FAUSTFLOAT(0.1));
		ui_interface->declare(&fHslider3, "name", "Sidechain Mid 1.5 kHz");
		ui_interface->declare(&fHslider3, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_mid", &fHslider3, FAUSTFLOAT(0.0), FAUSTFLOAT(-12.0), FAUSTFLOAT(12.0), FAUSTFLOAT(0.1));
		ui_interface->closeBox();
	}
	
	virtual void compute(int count, FAUSTFLOAT** RESTRICT inputs, FAUSTFLOAT** RESTRICT outputs) {
		FAUSTFLOAT* input0 = inputs[0];
		FAUSTFLOAT* output0 = outputs[0];
		double fSlow0 = double(fHslider0);
		int iSlow1 = int(double(fEntry0));
		double fSlow2 = ((iSlow1) ? 6.0 : 1e+01);
		double fSlow3 = 0.5 * fSlow2;
		double fSlow4 = double(fHslider1);
		double fSlow5 = std::pow(1e+01, 0.025 * double(fHslider2));
		double fSlow6 = std::sqrt(fSlow5);
		double fSlow7 = fConst5 / fSlow6;
		double fSlow8 = fConst5 * ((fSlow7 + 1.6666666666666667) / fSlow6) + 1.0;
		double fSlow9 = 2.0 / fSlow8;
		double fSlow10 = fConst5 / (fSlow6 * fSlow8);
		double fSlow11 = 1.0 / fSlow8;
		double fSlow12 = mydsp_faustpower2_f(fSlow5) + -1.0;
		double fSlow13 = 1.6666666666666667 * (fSlow5 + -1.0);
		double fSlow14 = std::pow(1e+01, 0.025 * double(fHslider3));
		double fSlow15 = fConst6 * (fConst6 + 1.4285714285714286 / fSlow14) + 1.0;
		double fSlow16 = 2.0 / fSlow15;
		double fSlow17 = fConst6 / fSlow15;
		double fSlow18 = 1.0 / fSlow15;
		double fSlow19 = 1.4285714285714286 * ((mydsp_faustpower2_f(fSlow14) + -1.0) / fSlow14);
		double fSlow20 = std::pow(1e+01, 0.025 * double(fHslider4));
		double fSlow21 = std::sqrt(fSlow20);
		double fSlow22 = fConst7 * fSlow21;
		double fSlow23 = fConst7 * fSlow21 * (fSlow22 + 1.6666666666666667) + 1.0;
		double fSlow24 = 2.0 / fSlow23;
		double fSlow25 = fConst7 * (fSlow21 / fSlow23);
		double fSlow26 = 1.0 / fSlow23;
		double fSlow27 = 1.0 - mydsp_faustpower2_f(fSlow20);
		double fSlow28 = 1.6666666666666667 * (1.0 - fSlow20);
		double fSlow29 = ((iSlow1) ? 9.0 : 2.0);
		double fSlow30 = 0.01 * double(fHslider5);
		double fSlow31 = double(fHslider6);
		for (int i0 = 0; i0 < count; i0 = i0 + 1) {
			fRec0[0] = fSlow0 + fConst1 * fRec0[1];
			fRec4[0] = fSlow4 + fConst1 * fRec4[1];
			double fTemp0 = fConst4 * fRec4[0];
			double fTemp1 = fRec15[1] + fSlow7 * (fRec1[1] - fRec16[1]);
			fRec15[0] = fSlow9 * fTemp1 - fRec15[1];
			double fTemp2 = fRec16[1] + fSlow10 * fTemp1;
			fRec16[0] = 2.0 * fTemp2 - fRec16[1];
			double fRec17 = fRec1[1];
			double fRec18 = fSlow11 * fTemp1;
			double fRec19 = fTemp2;
			double fTemp3 = fRec17 + fSlow13 * fRec18 + fSlow12 * fRec19;
			double fTemp4 = fRec11[1] + fConst6 * (fTemp3 - fRec12[1]);
			fRec11[0] = fSlow16 * fTemp4 - fRec11[1];
			double fTemp5 = fRec12[1] + fSlow17 * fTemp4;
			fRec12[0] = 2.0 * fTemp5 - fRec12[1];
			double fRec13 = fTemp3;
			double fRec14 = fSlow18 * fTemp4;
			double fTemp6 = fRec13 + fSlow19 * fRec14;
			double fTemp7 = fRec6[1] + fSlow22 * (fTemp6 - fRec7[1]);
			fRec6[0] = fSlow24 * fTemp7 - fRec6[1];
			double fTemp8 = fRec7[1] + fSlow25 * fTemp7;
			fRec7[0] = 2.0 * fTemp8 - fRec7[1];
			double fRec8 = fTemp6;
			double fRec9 = fSlow26 * fTemp7;
			double fRec10 = fTemp8;
			double fTemp9 = fSlow20 * (fSlow20 * fRec8 + fSlow28 * fRec9) + fSlow27 * fRec10;
			fRec5[0] = fConst8 * fRec5[1] + mydsp_faustpower2_f(fTemp9);
			double fTemp10 = std::fabs(fTemp9);
			fRec20[0] = fRec20[1] + (fTemp10 - fRec20[1]) * ((fTemp10 > fRec20[1]) ? fConst11 : fConst10);
			double fTemp11 = std::max<double>(1e+01 * std::log10(std::max<double>(1e-18, fConst9 * fRec5[0])), 2e+01 * std::log10(std::max<double>(fRec20[0], 1e-09)) + -4.0);
			double fTemp12 = fTemp11 + fTemp0;
			double fTemp13 = fSlow29 * ((fTemp12 > fSlow3) ? fTemp12 : ((fTemp12 > -fSlow3) ? 0.5 * (mydsp_faustpower2_f(fTemp0 + fTemp11 + fSlow3) / fSlow2) : 0.0));
			fRec3[0] = fRec3[1] + (fTemp13 - fRec3[1]) * ((fTemp13 > fRec3[1]) ? fConst13 : fConst12);
			double fTemp14 = std::min<double>(1.0, 0.08333333333333333 * fTemp13);
			fRec21[0] = fRec21[1] + (fTemp14 - fRec21[1]) * ((fTemp14 > fRec21[1]) ? fConst15 : fConst14);
			fRec2[0] = fRec2[1] + (fRec3[0] - fRec2[1]) * ((fRec3[0] > fRec2[1]) ? fConst17 : 1.0 - std::exp(-(fConst16 / std::max<double>(4.5 * fRec21[0] + 0.5, 1e-06))));
			fHbargraph0 = FAUSTFLOAT(std::min<double>(4e+01, std::max<double>(0.0, 0.5 * (fRec3[0] + fRec2[0]))));
			double fTemp15 = double(input0[i0]);
			fRec1[0] = fTemp15 * std::pow(1e+01, -(0.05 * fHbargraph0));
			double fTemp16 = std::max<double>(-1.5, std::min<double>(1.5, fRec1[0]));
			double fTemp17 = mydsp_faustpower2_f(fTemp16);
			fVec0[0] = fTemp17;
			fRec22[0] = fConst20 * (fTemp17 - fVec0[1] + fConst19 * fRec22[1]);
			fRec23[0] = fSlow30 + fConst1 * fRec23[1];
			fRec24[0] = fSlow31 + fConst1 * fRec24[1];
			output0[i0] = FAUSTFLOAT(fTemp15 * (1.0 - fConst21 * fRec24[0]) + fConst21 * fRec24[0] * (fRec1[0] + fConst2 * fRec23[0] * (0.08 * fRec22[0] - 0.05 * mydsp_faustpower3_f(fTemp16))) * std::pow(1e+01, fConst3 * fRec0[0]));
			fRec0[1] = fRec0[0];
			fRec4[1] = fRec4[0];
			fRec15[1] = fRec15[0];
			fRec16[1] = fRec16[0];
			fRec11[1] = fRec11[0];
			fRec12[1] = fRec12[0];
			fRec6[1] = fRec6[0];
			fRec7[1] = fRec7[0];
			fRec5[1] = fRec5[0];
			fRec20[1] = fRec20[0];
			fRec3[1] = fRec3[0];
			fRec21[1] = fRec21[0];
			fRec2[1] = fRec2[0];
			fRec1[1] = fRec1[0];
			fVec0[1] = fVec0[0];
			fRec22[1] = fRec22[0];
			fRec23[1] = fRec23[0];
			fRec24[1] = fRec24[0];
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
