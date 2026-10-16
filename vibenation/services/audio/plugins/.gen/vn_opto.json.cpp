/* ------------------------------------------------------------
license: "MIT"
name: "vn_opto"
Code generated with Faust 2.70.3 (https://faust.grame.fr)
Compilation options: -lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -single -ftz 0
------------------------------------------------------------ */

#ifndef  __mydsp_H__
#define  __mydsp_H__

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

static float mydsp_faustpower2_f(float value) {
	return value * value;
}
static float mydsp_faustpower3_f(float value) {
	return value * value * value;
}

class mydsp : public dsp {
	
 private:
	
	int fSampleRate;
	float fConst1;
	FAUSTFLOAT fHslider0;
	float fRec0[2];
	float fConst2;
	float fConst3;
	FAUSTFLOAT fEntry0;
	FAUSTFLOAT fHslider1;
	float fRec4[2];
	float fConst4;
	FAUSTFLOAT fHslider2;
	float fConst5;
	float fRec15[2];
	float fRec16[2];
	float fConst6;
	FAUSTFLOAT fHslider3;
	float fRec11[2];
	float fRec12[2];
	FAUSTFLOAT fHslider4;
	float fConst7;
	float fRec6[2];
	float fRec7[2];
	float fConst8;
	float fRec5[2];
	float fConst9;
	float fConst10;
	float fConst11;
	float fRec20[2];
	float fConst12;
	float fConst13;
	float fRec3[2];
	float fConst14;
	float fConst15;
	float fRec21[2];
	float fConst16;
	float fConst17;
	float fRec2[2];
	FAUSTFLOAT fHbargraph0;
	float fRec1[2];
	float fConst19;
	float fVec0[2];
	float fConst20;
	float fRec22[2];
	FAUSTFLOAT fHslider5;
	float fRec23[2];
	FAUSTFLOAT fHslider6;
	float fRec24[2];
	float fConst21;
	
 public:
	mydsp() {}

	void metadata(Meta* m) { 
		m->declare("compile_options", "-lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -single -ftz 0");
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
		float fConst0 = std::min<float>(1.92e+05f, std::max<float>(1.0f, float(fSampleRate)));
		fConst1 = std::exp(-(5e+01f / fConst0));
		fConst2 = 1.0f - fConst1;
		fConst3 = 0.05f * fConst2;
		fConst4 = 0.45f * fConst2;
		fConst5 = std::tan(628.31854f / fConst0);
		fConst6 = std::tan(4712.389f / fConst0);
		fConst7 = std::tan(15707.963f / fConst0);
		fConst8 = std::exp(-(125.0f / fConst0));
		fConst9 = 1.0f - fConst8;
		fConst10 = 1.0f - std::exp(-(4e+01f / fConst0));
		fConst11 = 1.0f - std::exp(-(3333.3333f / fConst0));
		fConst12 = 1.0f - std::exp(-(16.666666f / fConst0));
		fConst13 = 1.0f - std::exp(-(1e+02f / fConst0));
		fConst14 = 1.0f - std::exp(-(0.06666667f / fConst0));
		fConst15 = 1.0f - std::exp(-(0.5f / fConst0));
		fConst16 = 1.0f / fConst0;
		fConst17 = 1.0f - std::exp(-(12.5f / fConst0));
		float fConst18 = 25.132742f / fConst0;
		fConst19 = 1.0f - fConst18;
		fConst20 = 1.0f / (fConst18 + 1.0f);
		fConst21 = 0.01f * fConst2;
	}
	
	virtual void instanceResetUserInterface() {
		fHslider0 = FAUSTFLOAT(0.0f);
		fEntry0 = FAUSTFLOAT(0.0f);
		fHslider1 = FAUSTFLOAT(3e+01f);
		fHslider2 = FAUSTFLOAT(0.0f);
		fHslider3 = FAUSTFLOAT(0.0f);
		fHslider4 = FAUSTFLOAT(0.0f);
		fHslider5 = FAUSTFLOAT(3e+01f);
		fHslider6 = FAUSTFLOAT(1e+02f);
	}
	
	virtual void instanceClear() {
		for (int l0 = 0; l0 < 2; l0 = l0 + 1) {
			fRec0[l0] = 0.0f;
		}
		for (int l1 = 0; l1 < 2; l1 = l1 + 1) {
			fRec4[l1] = 0.0f;
		}
		for (int l2 = 0; l2 < 2; l2 = l2 + 1) {
			fRec15[l2] = 0.0f;
		}
		for (int l3 = 0; l3 < 2; l3 = l3 + 1) {
			fRec16[l3] = 0.0f;
		}
		for (int l4 = 0; l4 < 2; l4 = l4 + 1) {
			fRec11[l4] = 0.0f;
		}
		for (int l5 = 0; l5 < 2; l5 = l5 + 1) {
			fRec12[l5] = 0.0f;
		}
		for (int l6 = 0; l6 < 2; l6 = l6 + 1) {
			fRec6[l6] = 0.0f;
		}
		for (int l7 = 0; l7 < 2; l7 = l7 + 1) {
			fRec7[l7] = 0.0f;
		}
		for (int l8 = 0; l8 < 2; l8 = l8 + 1) {
			fRec5[l8] = 0.0f;
		}
		for (int l9 = 0; l9 < 2; l9 = l9 + 1) {
			fRec20[l9] = 0.0f;
		}
		for (int l10 = 0; l10 < 2; l10 = l10 + 1) {
			fRec3[l10] = 0.0f;
		}
		for (int l11 = 0; l11 < 2; l11 = l11 + 1) {
			fRec21[l11] = 0.0f;
		}
		for (int l12 = 0; l12 < 2; l12 = l12 + 1) {
			fRec2[l12] = 0.0f;
		}
		for (int l13 = 0; l13 < 2; l13 = l13 + 1) {
			fRec1[l13] = 0.0f;
		}
		for (int l14 = 0; l14 < 2; l14 = l14 + 1) {
			fVec0[l14] = 0.0f;
		}
		for (int l15 = 0; l15 < 2; l15 = l15 + 1) {
			fRec22[l15] = 0.0f;
		}
		for (int l16 = 0; l16 < 2; l16 = l16 + 1) {
			fRec23[l16] = 0.0f;
		}
		for (int l17 = 0; l17 < 2; l17 = l17 + 1) {
			fRec24[l17] = 0.0f;
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
		ui_interface->addHorizontalSlider("colour", &fHslider5, FAUSTFLOAT(3e+01f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1e+02f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHslider0, "name", "Gain");
		ui_interface->declare(&fHslider0, "unit", "dB");
		ui_interface->addHorizontalSlider("gain", &fHslider0, FAUSTFLOAT(0.0f), FAUSTFLOAT(-2e+01f), FAUSTFLOAT(3e+01f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fHbargraph0, "name", "Gain Reduction");
		ui_interface->declare(&fHbargraph0, "unit", "dB");
		ui_interface->addHorizontalBargraph("gr", &fHbargraph0, FAUSTFLOAT(0.0f), FAUSTFLOAT(4e+01f));
		ui_interface->declare(&fHslider6, "name", "Mix");
		ui_interface->declare(&fHslider6, "unit", "%");
		ui_interface->addHorizontalSlider("mix", &fHslider6, FAUSTFLOAT(1e+02f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1e+02f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fEntry0, "enum", "Compress|Limit");
		ui_interface->declare(&fEntry0, "name", "Mode");
		ui_interface->addNumEntry("mode", &fEntry0, FAUSTFLOAT(0.0f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1.0f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHslider1, "name", "Peak Reduction");
		ui_interface->declare(&fHslider1, "unit", "%");
		ui_interface->addHorizontalSlider("peak_reduction", &fHslider1, FAUSTFLOAT(3e+01f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1e+02f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fHslider4, "name", "Sidechain High 5 kHz");
		ui_interface->declare(&fHslider4, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_high", &fHslider4, FAUSTFLOAT(0.0f), FAUSTFLOAT(-12.0f), FAUSTFLOAT(12.0f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fHslider2, "name", "Sidechain Low 200 Hz");
		ui_interface->declare(&fHslider2, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_low", &fHslider2, FAUSTFLOAT(0.0f), FAUSTFLOAT(-12.0f), FAUSTFLOAT(12.0f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fHslider3, "name", "Sidechain Mid 1.5 kHz");
		ui_interface->declare(&fHslider3, "unit", "dB");
		ui_interface->addHorizontalSlider("sc_mid", &fHslider3, FAUSTFLOAT(0.0f), FAUSTFLOAT(-12.0f), FAUSTFLOAT(12.0f), FAUSTFLOAT(0.1f));
		ui_interface->closeBox();
	}
	
	virtual void compute(int count, FAUSTFLOAT** RESTRICT inputs, FAUSTFLOAT** RESTRICT outputs) {
		FAUSTFLOAT* input0 = inputs[0];
		FAUSTFLOAT* output0 = outputs[0];
		float fSlow0 = float(fHslider0);
		int iSlow1 = int(float(fEntry0));
		float fSlow2 = ((iSlow1) ? 6.0f : 1e+01f);
		float fSlow3 = 0.5f * fSlow2;
		float fSlow4 = float(fHslider1);
		float fSlow5 = std::pow(1e+01f, 0.025f * float(fHslider2));
		float fSlow6 = std::sqrt(fSlow5);
		float fSlow7 = fConst5 / fSlow6;
		float fSlow8 = fConst5 * ((fSlow7 + 1.6666666f) / fSlow6) + 1.0f;
		float fSlow9 = 2.0f / fSlow8;
		float fSlow10 = fConst5 / (fSlow6 * fSlow8);
		float fSlow11 = 1.0f / fSlow8;
		float fSlow12 = mydsp_faustpower2_f(fSlow5) + -1.0f;
		float fSlow13 = 1.6666666f * (fSlow5 + -1.0f);
		float fSlow14 = std::pow(1e+01f, 0.025f * float(fHslider3));
		float fSlow15 = fConst6 * (fConst6 + 1.4285715f / fSlow14) + 1.0f;
		float fSlow16 = 2.0f / fSlow15;
		float fSlow17 = fConst6 / fSlow15;
		float fSlow18 = 1.0f / fSlow15;
		float fSlow19 = 1.4285715f * ((mydsp_faustpower2_f(fSlow14) + -1.0f) / fSlow14);
		float fSlow20 = std::pow(1e+01f, 0.025f * float(fHslider4));
		float fSlow21 = std::sqrt(fSlow20);
		float fSlow22 = fConst7 * fSlow21;
		float fSlow23 = fConst7 * fSlow21 * (fSlow22 + 1.6666666f) + 1.0f;
		float fSlow24 = 2.0f / fSlow23;
		float fSlow25 = fConst7 * (fSlow21 / fSlow23);
		float fSlow26 = 1.0f / fSlow23;
		float fSlow27 = 1.0f - mydsp_faustpower2_f(fSlow20);
		float fSlow28 = 1.6666666f * (1.0f - fSlow20);
		float fSlow29 = ((iSlow1) ? 9.0f : 2.0f);
		float fSlow30 = 0.01f * float(fHslider5);
		float fSlow31 = float(fHslider6);
		for (int i0 = 0; i0 < count; i0 = i0 + 1) {
			fRec0[0] = fSlow0 + fConst1 * fRec0[1];
			fRec4[0] = fSlow4 + fConst1 * fRec4[1];
			float fTemp0 = fConst4 * fRec4[0];
			float fTemp1 = fRec15[1] + fSlow7 * (fRec1[1] - fRec16[1]);
			fRec15[0] = fSlow9 * fTemp1 - fRec15[1];
			float fTemp2 = fRec16[1] + fSlow10 * fTemp1;
			fRec16[0] = 2.0f * fTemp2 - fRec16[1];
			float fRec17 = fRec1[1];
			float fRec18 = fSlow11 * fTemp1;
			float fRec19 = fTemp2;
			float fTemp3 = fRec17 + fSlow13 * fRec18 + fSlow12 * fRec19;
			float fTemp4 = fRec11[1] + fConst6 * (fTemp3 - fRec12[1]);
			fRec11[0] = fSlow16 * fTemp4 - fRec11[1];
			float fTemp5 = fRec12[1] + fSlow17 * fTemp4;
			fRec12[0] = 2.0f * fTemp5 - fRec12[1];
			float fRec13 = fTemp3;
			float fRec14 = fSlow18 * fTemp4;
			float fTemp6 = fRec13 + fSlow19 * fRec14;
			float fTemp7 = fRec6[1] + fSlow22 * (fTemp6 - fRec7[1]);
			fRec6[0] = fSlow24 * fTemp7 - fRec6[1];
			float fTemp8 = fRec7[1] + fSlow25 * fTemp7;
			fRec7[0] = 2.0f * fTemp8 - fRec7[1];
			float fRec8 = fTemp6;
			float fRec9 = fSlow26 * fTemp7;
			float fRec10 = fTemp8;
			float fTemp9 = fSlow20 * (fSlow20 * fRec8 + fSlow28 * fRec9) + fSlow27 * fRec10;
			fRec5[0] = fConst8 * fRec5[1] + mydsp_faustpower2_f(fTemp9);
			float fTemp10 = std::fabs(fTemp9);
			fRec20[0] = fRec20[1] + (fTemp10 - fRec20[1]) * ((fTemp10 > fRec20[1]) ? fConst11 : fConst10);
			float fTemp11 = std::max<float>(1e+01f * std::log10(std::max<float>(1e-18f, fConst9 * fRec5[0])), 2e+01f * std::log10(std::max<float>(fRec20[0], 1e-09f)) + -4.0f);
			float fTemp12 = fTemp11 + fTemp0;
			float fTemp13 = fSlow29 * ((fTemp12 > fSlow3) ? fTemp12 : ((fTemp12 > -fSlow3) ? 0.5f * (mydsp_faustpower2_f(fTemp0 + fTemp11 + fSlow3) / fSlow2) : 0.0f));
			fRec3[0] = fRec3[1] + (fTemp13 - fRec3[1]) * ((fTemp13 > fRec3[1]) ? fConst13 : fConst12);
			float fTemp14 = std::min<float>(1.0f, 0.083333336f * fTemp13);
			fRec21[0] = fRec21[1] + (fTemp14 - fRec21[1]) * ((fTemp14 > fRec21[1]) ? fConst15 : fConst14);
			fRec2[0] = fRec2[1] + (fRec3[0] - fRec2[1]) * ((fRec3[0] > fRec2[1]) ? fConst17 : 1.0f - std::exp(-(fConst16 / std::max<float>(4.5f * fRec21[0] + 0.5f, 1e-06f))));
			fHbargraph0 = FAUSTFLOAT(std::min<float>(4e+01f, std::max<float>(0.0f, 0.5f * (fRec3[0] + fRec2[0]))));
			float fTemp15 = float(input0[i0]);
			fRec1[0] = fTemp15 * std::pow(1e+01f, -(0.05f * fHbargraph0));
			float fTemp16 = std::max<float>(-1.5f, std::min<float>(1.5f, fRec1[0]));
			float fTemp17 = mydsp_faustpower2_f(fTemp16);
			fVec0[0] = fTemp17;
			fRec22[0] = fConst20 * (fTemp17 - fVec0[1] + fConst19 * fRec22[1]);
			fRec23[0] = fSlow30 + fConst1 * fRec23[1];
			fRec24[0] = fSlow31 + fConst1 * fRec24[1];
			output0[i0] = FAUSTFLOAT(fTemp15 * (1.0f - fConst21 * fRec24[0]) + fConst21 * fRec24[0] * (fRec1[0] + fConst2 * fRec23[0] * (0.08f * fRec22[0] - 0.05f * mydsp_faustpower3_f(fTemp16))) * std::pow(1e+01f, fConst3 * fRec0[0]));
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

#endif
