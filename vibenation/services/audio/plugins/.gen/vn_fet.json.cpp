/* ------------------------------------------------------------
license: "MIT"
name: "vn_fet"
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

class mydsp : public dsp {
	
 private:
	
	int fSampleRate;
	float fConst2;
	float fConst3;
	FAUSTFLOAT fHslider0;
	float fRec2[2];
	float fConst4;
	float fConst5;
	FAUSTFLOAT fEntry0;
	FAUSTFLOAT fHslider1;
	float fConst6;
	FAUSTFLOAT fHslider2;
	float fRec3[2];
	float fRec4[2];
	FAUSTFLOAT fHbargraph0;
	FAUSTFLOAT fHslider3;
	float fRec5[2];
	float fRec1[2];
	float fVec0[2];
	float fConst7;
	float fRec0[2];
	float fConst8;
	float fConst9;
	FAUSTFLOAT fHslider4;
	float fRec6[2];
	FAUSTFLOAT fHslider5;
	float fRec7[2];
	float fConst10;
	
 public:
	mydsp() {}

	void metadata(Meta* m) { 
		m->declare("basics.lib/name", "Faust Basic Element Library");
		m->declare("basics.lib/tabulateNd", "Copyright (C) 2023 Bart Brouns <bart@magnetophon.nl>");
		m->declare("basics.lib/version", "1.12.0");
		m->declare("compile_options", "-lang cpp -ct 1 -es 1 -mcd 16 -mdd 1024 -mdy 33 -single -ftz 0");
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
		float fConst0 = std::min<float>(1.92e+05f, std::max<float>(1.0f, float(fSampleRate)));
		float fConst1 = 25.132742f / fConst0;
		fConst2 = 1.0f - fConst1;
		fConst3 = std::exp(-(5e+01f / fConst0));
		fConst4 = 1.0f - fConst3;
		fConst5 = 0.05f * fConst4;
		fConst6 = 1.0f / fConst0;
		fConst7 = 1.0f / (fConst1 + 1.0f);
		fConst8 = 0.06f * fConst4;
		fConst9 = 0.02f * fConst4;
		fConst10 = 0.01f * fConst4;
	}
	
	virtual void instanceResetUserInterface() {
		fHslider0 = FAUSTFLOAT(0.0f);
		fEntry0 = FAUSTFLOAT(0.0f);
		fHslider1 = FAUSTFLOAT(3e+02f);
		fHslider2 = FAUSTFLOAT(3e+02f);
		fHslider3 = FAUSTFLOAT(5e+01f);
		fHslider4 = FAUSTFLOAT(0.0f);
		fHslider5 = FAUSTFLOAT(1e+02f);
	}
	
	virtual void instanceClear() {
		for (int l0 = 0; l0 < 2; l0 = l0 + 1) {
			fRec2[l0] = 0.0f;
		}
		for (int l1 = 0; l1 < 2; l1 = l1 + 1) {
			fRec3[l1] = 0.0f;
		}
		for (int l2 = 0; l2 < 2; l2 = l2 + 1) {
			fRec4[l2] = 0.0f;
		}
		for (int l3 = 0; l3 < 2; l3 = l3 + 1) {
			fRec5[l3] = 0.0f;
		}
		for (int l4 = 0; l4 < 2; l4 = l4 + 1) {
			fRec1[l4] = 0.0f;
		}
		for (int l5 = 0; l5 < 2; l5 = l5 + 1) {
			fVec0[l5] = 0.0f;
		}
		for (int l6 = 0; l6 < 2; l6 = l6 + 1) {
			fRec0[l6] = 0.0f;
		}
		for (int l7 = 0; l7 < 2; l7 = l7 + 1) {
			fRec6[l7] = 0.0f;
		}
		for (int l8 = 0; l8 < 2; l8 = l8 + 1) {
			fRec7[l8] = 0.0f;
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
		ui_interface->addHorizontalSlider("attack", &fHslider2, FAUSTFLOAT(3e+02f), FAUSTFLOAT(2e+01f), FAUSTFLOAT(8e+02f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHslider3, "name", "Colour");
		ui_interface->declare(&fHslider3, "unit", "%");
		ui_interface->addHorizontalSlider("colour", &fHslider3, FAUSTFLOAT(5e+01f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1e+02f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHbargraph0, "name", "Gain Reduction");
		ui_interface->declare(&fHbargraph0, "unit", "dB");
		ui_interface->addHorizontalBargraph("gr", &fHbargraph0, FAUSTFLOAT(0.0f), FAUSTFLOAT(4e+01f));
		ui_interface->declare(&fHslider0, "name", "Input");
		ui_interface->declare(&fHslider0, "unit", "dB");
		ui_interface->addHorizontalSlider("input", &fHslider0, FAUSTFLOAT(0.0f), FAUSTFLOAT(-2e+01f), FAUSTFLOAT(4e+01f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fHslider5, "name", "Mix");
		ui_interface->declare(&fHslider5, "unit", "%");
		ui_interface->addHorizontalSlider("mix", &fHslider5, FAUSTFLOAT(1e+02f), FAUSTFLOAT(0.0f), FAUSTFLOAT(1e+02f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHslider4, "name", "Output");
		ui_interface->declare(&fHslider4, "unit", "dB");
		ui_interface->addHorizontalSlider("output", &fHslider4, FAUSTFLOAT(0.0f), FAUSTFLOAT(-3e+01f), FAUSTFLOAT(2e+01f), FAUSTFLOAT(0.1f));
		ui_interface->declare(&fEntry0, "enum", "4:1|8:1|12:1|20:1|All");
		ui_interface->declare(&fEntry0, "name", "Ratio");
		ui_interface->addNumEntry("ratio", &fEntry0, FAUSTFLOAT(0.0f), FAUSTFLOAT(0.0f), FAUSTFLOAT(4.0f), FAUSTFLOAT(1.0f));
		ui_interface->declare(&fHslider1, "log", "");
		ui_interface->declare(&fHslider1, "name", "Release");
		ui_interface->declare(&fHslider1, "unit", "ms");
		ui_interface->addHorizontalSlider("release", &fHslider1, FAUSTFLOAT(3e+02f), FAUSTFLOAT(5e+01f), FAUSTFLOAT(1.1e+03f), FAUSTFLOAT(1.0f));
		ui_interface->closeBox();
	}
	
	virtual void compute(int count, FAUSTFLOAT** RESTRICT inputs, FAUSTFLOAT** RESTRICT outputs) {
		FAUSTFLOAT* input0 = inputs[0];
		FAUSTFLOAT* output0 = outputs[0];
		float fSlow0 = float(fHslider0);
		float fSlow1 = float(fEntry0);
		int iSlow2 = fSlow1 >= 3.0f;
		int iSlow3 = fSlow1 >= 2.0f;
		int iSlow4 = fSlow1 >= 1.0f;
		int iSlow5 = fSlow1 >= 4.0f;
		int iSlow6 = ((iSlow2) ? ((iSlow5) ? 1 : 2) : ((iSlow3) ? 3 : ((iSlow4) ? 4 : 6)));
		float fSlow7 = 0.5f * float(iSlow6);
		float fSlow8 = float(((iSlow2) ? ((iSlow5) ? -17 : -16) : ((iSlow3) ? -17 : ((iSlow4) ? -18 : -20))));
		float fSlow9 = 0.5f * float(-iSlow6);
		float fSlow10 = float(2 * iSlow6);
		int iSlow11 = ((iSlow2) ? ((iSlow5) ? 30 : 19) : ((iSlow3) ? 11 : ((iSlow4) ? 7 : 3)));
		float fSlow12 = float(iSlow11);
		int iSlow13 = fSlow1 == 4.0f;
		float fSlow14 = ((iSlow13) ? 0.8f : 1.0f);
		float fSlow15 = float(fHslider1);
		float fSlow16 = 1.0f - std::exp(-(fConst6 / std::max<float>(0.005f * fSlow15 * fSlow14, 1e-06f)));
		float fSlow17 = 1.0f - std::exp(-(fConst6 / std::max<float>(1e-06f * float(fHslider2) * ((iSlow13) ? 0.5f : 1.0f) * float(iSlow11 + 1), 1e-06f)));
		float fSlow18 = 0.00023809524f * (fSlow15 + -5e+01f);
		float fSlow19 = fSlow18 + 0.2f;
		float fSlow20 = 1.0f - std::exp(-(fConst6 / std::max<float>(0.001f * fSlow15 * fSlow14, 1e-06f)));
		float fSlow21 = 0.8f - fSlow18;
		float fSlow22 = ((iSlow13) ? 0.12f : 0.06f);
		float fSlow23 = 0.01f * float(fHslider3);
		float fSlow24 = float(fHslider4);
		float fSlow25 = float(fHslider5);
		for (int i0 = 0; i0 < count; i0 = i0 + 1) {
			fRec2[0] = fSlow0 + fConst3 * fRec2[1];
			float fTemp0 = std::pow(1e+01f, fConst5 * fRec2[0]);
			float fTemp1 = float(input0[i0]);
			float fTemp2 = fTemp1 * fTemp0;
			float fTemp3 = std::fabs(fTemp2) + 1.0f;
			float fTemp4 = 2e+01f * std::log10(std::max<float>(std::fabs(fRec1[1]), 1e-09f));
			float fTemp5 = fTemp4 - fSlow8;
			float fTemp6 = fSlow12 * ((fTemp5 > fSlow7) ? fTemp5 : ((fTemp5 > fSlow9) ? mydsp_faustpower2_f(fTemp4 + fSlow7 - fSlow8) / fSlow10 : 0.0f));
			fRec3[0] = fRec3[1] + (fTemp6 - fRec3[1]) * ((fTemp6 > fRec3[1]) ? fSlow17 : fSlow16);
			fRec4[0] = fRec4[1] + (fTemp6 - fRec4[1]) * ((fTemp6 > fRec4[1]) ? fSlow17 : fSlow20);
			fHbargraph0 = FAUSTFLOAT(std::min<float>(4e+01f, std::max<float>(0.0f, fSlow21 * fRec4[0] + fSlow19 * fRec3[0])));
			float fTemp7 = std::pow(1e+01f, -(0.05f * fHbargraph0));
			fRec5[0] = fSlow23 + fConst3 * fRec5[1];
			fRec1[0] = fTemp2 * fTemp7 / (fConst4 * (fTemp1 * fRec5[0] * fSlow22 * fTemp0 * std::min<float>(1.0f, 1.04f - fTemp7) * (0.6f * (mydsp_faustpower2_f(fTemp1) * mydsp_faustpower2_f(fTemp0) / mydsp_faustpower2_f(fTemp3)) + 0.25f) / fTemp3) + 1.0f);
			float fTemp8 = mydsp_faustpower2_f(std::min<float>(2.0f, std::max<float>(-2.0f, fRec1[0])));
			fVec0[0] = fTemp8;
			fRec0[0] = fConst7 * (fTemp8 - fVec0[1] + fConst2 * fRec0[1]);
			float fTemp9 = fRec1[0] - fConst8 * fRec5[0] * fRec0[0];
			fRec6[0] = fSlow24 + fConst3 * fRec6[1];
			fRec7[0] = fSlow25 + fConst3 * fRec7[1];
			output0[i0] = FAUSTFLOAT(fTemp1 * (1.0f - fConst10 * fRec7[0]) + fConst10 * (fRec7[0] * fTemp9 * std::pow(1e+01f, fConst5 * fRec6[0]) / (fConst9 * fRec5[0] * mydsp_faustpower2_f(fTemp9) + 1.0f)));
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

#endif
