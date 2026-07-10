import numpy as np
import pytest

from autodirector.dsp import Calibrator, Frontend, PitchPrior, VocalPresence

from synthaudio import (SR, mix, synth_instrumental, synth_lead_guitar,
                        synth_speech, synth_vocal)


def run_frontend(audio, fe=None):
    fe = fe or Frontend(samplerate=SR)
    hops = []
    for start in range(0, len(audio), 4800):
        hops.extend(fe.process(audio[start:start + 4800]))
    return hops


def confidences(audio, detector=None):
    det = detector or VocalPresence()
    return [det.update(h) for h in run_frontend(audio)]


class TestFrontend:
    def test_pitch_tracking_on_pure_tone(self):
        t = np.arange(SR * 2) / SR
        tone = 0.3 * np.sin(2 * np.pi * 440.0 * t)
        hops = run_frontend(tone)
        voiced = [h for h in hops if h.voicing > 0.5]
        assert len(voiced) > len(hops) * 0.8
        f0s = np.array([h.f0_hz for h in voiced])
        assert np.median(np.abs(f0s - 440.0)) < 8.0

    def test_noise_is_unvoiced(self):
        rng = np.random.default_rng(7)
        noise = rng.normal(0, 0.2, SR * 2)
        hops = run_frontend(noise)
        assert np.mean([h.voicing for h in hops]) < 0.4

    def test_rms_tracks_level(self):
        t = np.arange(SR) / SR
        loud = 0.5 * np.sin(2 * np.pi * 220 * t)
        quiet = 0.005 * np.sin(2 * np.pi * 220 * t)
        rms_loud = np.mean([h.rms_db for h in run_frontend(loud)])
        rms_quiet = np.mean([h.rms_db for h in run_frontend(quiet)])
        assert rms_loud - rms_quiet > 30.0

    def test_streaming_matches_any_chunking(self):
        audio = synth_vocal(2.0)
        h1 = run_frontend(audio)
        fe = Frontend(samplerate=SR)
        h2 = []
        for start in range(0, len(audio), 733):  # awkward chunk size
            h2.extend(fe.process(audio[start:start + 733]))
        assert len(h1) == len(h2)
        assert abs(h1[50].rms_db - h2[50].rms_db) < 1e-6


class TestVocalDetection:
    def make_calibrated(self):
        """Calibration wizard on synthetic material: 10s instrumental,
        then 10s instrumental+vocals."""
        instrumental = synth_instrumental(10.0)
        with_vocals = mix(synth_instrumental(10.0, seed=11),
                          synth_vocal(10.0), gains=[0.7, 1.0])
        cal = Calibrator()
        det = VocalPresence()
        for h in run_frontend(instrumental):
            det.update(h)
            cal.collect(det.features(), vocal=False)
        det2 = VocalPresence()
        for h in run_frontend(with_vocals):
            det2.update(h)
            cal.collect(det2.features(), vocal=True)
        result = cal.finish()
        assert result is not None
        return result

    def test_calibration_separates_classes(self):
        result = self.make_calibrated()
        assert result.d_prime >= 1.5, \
            f"synthetic material must calibrate cleanly (d'={result.d_prime:.2f})"
        assert result.dwell_multiplier == 1.0

    def test_vocals_score_higher_than_instrumental(self):
        cal = self.make_calibrated()
        instrumental = synth_instrumental(8.0, seed=21)
        with_vocals = mix(synth_instrumental(8.0, seed=22),
                          synth_vocal(8.0, seed=23), gains=[0.7, 1.0])
        det_i = VocalPresence(calibration=cal)
        det_v = VocalPresence(calibration=cal)
        ci = confidences(instrumental, det_i)
        cv = confidences(with_vocals, det_v)
        # Ignore the fill-up warmup window
        ci, cv = ci[64:], cv[64:]
        assert np.mean(cv) - np.mean(ci) > 0.35
        assert np.mean(cv) > 0.6
        assert np.mean(ci) < 0.35

    def test_lead_guitar_scores_below_vocals(self):
        # The honest hard case: sustained lead with vibrato. It may fool
        # single features, but must score clearly below actual vocals.
        cal = self.make_calibrated()
        solo = mix(synth_instrumental(8.0, seed=31),
                   synth_lead_guitar(8.0), gains=[0.7, 0.9])
        vocals = mix(synth_instrumental(8.0, seed=32),
                     synth_vocal(8.0, seed=33), gains=[0.7, 1.0])
        cs = np.mean(confidences(solo, VocalPresence(calibration=cal))[64:])
        cv = np.mean(confidences(vocals, VocalPresence(calibration=cal))[64:])
        assert cv - cs > 0.15, f"solo={cs:.2f} vocals={cv:.2f}"

    def test_pitch_prior_modulates_but_never_vetoes(self):
        cal = self.make_calibrated()
        vocals = mix(synth_instrumental(6.0, seed=41),
                     synth_vocal(6.0, f0=220.0, seed=42), gains=[0.7, 1.0])
        prior = PitchPrior(f0_lo=180.0, f0_hi=320.0)      # matches
        off_prior = PitchPrior(f0_lo=500.0, f0_hi=900.0)  # doesn't match
        c_match = np.mean(confidences(
            vocals, VocalPresence(calibration=cal, pitch_prior=prior))[64:])
        c_off = np.mean(confidences(
            vocals, VocalPresence(calibration=cal, pitch_prior=off_prior))[64:])
        assert c_match > c_off, "prior must modulate confidence"
        assert c_off > 0.4, "prior must never act as a veto"

    def test_pitch_prior_enrollment(self):
        hops = run_frontend(synth_vocal(8.0, f0=220.0))
        prior = PitchPrior.enroll([h.f0_hz for h in hops])
        assert prior is not None
        assert prior.f0_lo < 220.0 < prior.f0_hi

    def test_speech_reads_as_vocal_activity(self):
        # Podcast-side sanity: the same feature stack sees speech.
        speech = synth_speech(8.0)
        c = np.mean(confidences(speech)[64:])
        assert c > 0.4
