package com.stagemix.engine

import kotlin.math.pow

/**
 * Audio-feedback (howl) recognizer, running on the console's 100-bin
 * RTA (~20 Hz frames, log-spaced 20 Hz..20 kHz, 10 bins/octave).
 *
 * A howl has a signature nothing musical shares for long: ONE narrow
 * bin towering far above the rest of the spectrum, at a FIXED
 * frequency, SUSTAINED across frames. Cymbal crashes are broadband;
 * notes move; a howl parks and grows.
 *
 * Detection is deliberately conservative (research: level detectors
 * mistake howl for signal, and false alarms on rock are common), and
 * the response is the safe one: VETO all upward automation and tell
 * the human where it is — never auto-EQ in v1.
 *
 *  - candidate: bin >= frame median + [towerDb] AND >= [floorDb]
 *  - persistence: same bin (±1 drift allowed) for >= [holdFrames]
 *  - veto clears [clearSec] after the peak is gone; frequency reported
 */
class FeedbackWatchdog(
    private val towerDb: Float = 25f,
    private val floorDb: Float = -40f,
    private val holdFrames: Int = 10,      // ~0.5 s at 20 Hz
    private val clearSec: Double = 3.0,
) {
    var vetoActive = false; private set
    var lastFreqHz: Int = 0; private set

    private var candidateBin = -1
    private var candidateCount = 0
    private var lastSeenT = -1.0

    fun onRta(bins: FloatArray, tSec: Double) {
        if (bins.size < 100) return
        // frame median as the "rest of the spectrum" reference
        val sorted = bins.copyOf().also { it.sort() }
        val median = sorted[bins.size / 2]
        var peakBin = -1
        var peakVal = -128f
        for (i in bins.indices) {
            if (bins[i] > peakVal) { peakVal = bins[i]; peakBin = i }
        }
        val isCandidate = peakVal >= median + towerDb && peakVal >= floorDb &&
                isNarrow(bins, peakBin)
        if (isCandidate && (candidateBin < 0 ||
                    kotlin.math.abs(peakBin - candidateBin) <= 1)) {
            candidateBin = peakBin
            candidateCount++
            lastSeenT = tSec
            if (candidateCount >= holdFrames && !vetoActive) {
                vetoActive = true
                lastFreqHz = binHz(peakBin)
            }
        } else if (isCandidate) {
            // a different frequency: restart persistence there
            candidateBin = peakBin
            candidateCount = 1
            lastSeenT = tSec
        } else if (vetoActive && tSec - lastSeenT > clearSec) {
            vetoActive = false
            candidateBin = -1
            candidateCount = 0
        } else if (!vetoActive) {
            candidateBin = -1
            candidateCount = 0
        }
    }

    /** narrow = immediate neighbours already well below the peak */
    private fun isNarrow(bins: FloatArray, peak: Int): Boolean {
        val l = bins.getOrElse(peak - 2) { -128f }
        val r = bins.getOrElse(peak + 2) { -128f }
        return bins[peak] - maxOf(l, r) >= 12f
    }

    private fun binHz(bin: Int): Int =
        (20.0 * 2.0.pow(bin / 10.0)).toInt()
}
