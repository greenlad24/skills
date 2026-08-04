package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.pow

/**
 * Audio-feedback (howl) recognizer, running on the console's 100-bin
 * RTA (~20 Hz frames, log-spaced 20 Hz..20 kHz, 10 bins/octave).
 *
 * Telling a howl from a sustained musical note is the whole problem —
 * this band has a HARMONICA, a flute/sax, an organ-ish keyboard and
 * singers who hold notes, and every one of those is a narrow, parked,
 * loud peak. Two discriminators (both validated against synthetic
 * spectra for all four instruments) do the work:
 *
 *  1. HARMONIC PARTNERS. A real instrument puts energy at 2f and 3f
 *     (+10 and +16 bins on a 10-bin/octave log scale). Acoustic
 *     feedback is a single room/mic resonance with no harmonic family
 *     — a driver's distortion harmonic sits far below the noise floor.
 *     A peak with a partner is music, never a howl.
 *  2. GROWTH PATH. The tower test (peak >= median + 25 dB) is blind
 *     while the band plays, because the band raises the median. A howl
 *     that is narrow, parked at one frequency and has RISEN >= 12 dB
 *     within a second is a howl even if it never towers.
 *
 * The response stays conservative: freeze upward automation and name
 * the frequency for the human to notch. Never auto-EQ.
 */
class FeedbackWatchdog(
    private val towerDb: Float = 25f,
    private val floorDb: Float = -40f,
    private val holdFrames: Int = 10,          // ~0.5 s at 20 Hz
    private val clearSec: Double = 3.0,
    private val riseDb: Float = 12f,
    private val riseWindowFrames: Int = 20,    // ~1 s at 20 Hz
    private val partnerRelDb: Float = 30f,     // partner within 30 dB of peak
    private val partnerAboveMedianDb: Float = 8f,
) {
    var vetoActive = false; private set
    var lastFreqHz: Int = 0; private set

    /** how far a peak may wander and still count as the same event */
    private val CONTINUITY_BINS = 3

    private var watchBin = -1
    private val hist = ArrayList<Float>()
    private var grewLatch = false
    private var candidateCount = 0
    private var lastSeenT = -1.0

    fun onRta(bins: FloatArray, tSec: Double) {
        if (bins.size < 100) return
        for (v in bins) if (v.isNaN() || v.isInfinite()) return

        val sorted = bins.copyOf().also { it.sort() }
        val median = sorted[bins.size / 2]
        var peakBin = 0
        var peakVal = -128f
        for (i in bins.indices) if (bins[i] > peakVal) {
            peakVal = bins[i]; peakBin = i
        }

        // Track this frequency's level over time. A howl parks; a
        // melody moves, which resets the history.
        if (watchBin >= 0 && abs(peakBin - watchBin) <= CONTINUITY_BINS) {
            hist.add(peakVal)
            if (hist.size > riseWindowFrames + holdFrames + 5) hist.removeAt(0)
        } else {
            hist.clear(); hist.add(peakVal)
            grewLatch = false
            candidateCount = 0
        }
        watchBin = peakBin

        val l = if (peakBin - 2 >= 0) bins[peakBin - 2] else -128f
        val r = if (peakBin + 2 < bins.size) bins[peakBin + 2] else -128f
        val narrow = peakVal - maxOf(l, r) >= 12f

        // 2f is +10 bins, 3f is +16 bins on a 10-bin/octave scale
        val hasPartner = intArrayOf(10, 16).any { off ->
            ((peakBin + off - 1)..(peakBin + off + 1)).any { pb ->
                val v = if (pb in bins.indices) bins[pb] else -128f
                v >= peakVal - partnerRelDb && v >= median + partnerAboveMedianDb
            }
        }
        val towered = peakVal >= median + towerDb
        if (hist.size >= riseWindowFrames && peakVal - hist.first() >= riseDb)
            grewLatch = true

        val isCandidate = narrow && !hasPartner && peakVal >= floorDb &&
                (towered || grewLatch)

        if (isCandidate) {
            candidateCount++
            lastSeenT = tSec
            if (candidateCount >= holdFrames && !vetoActive) {
                vetoActive = true
                lastFreqHz = binHz(peakBin)
            }
        } else if (vetoActive && tSec - lastSeenT > clearSec) {
            vetoActive = false
            candidateCount = 0
            grewLatch = false
            hist.clear()
            watchBin = -1
        } else if (!vetoActive) {
            candidateCount = 0
        }
    }

    private fun binHz(bin: Int): Int = (20.0 * 2.0.pow(bin / 10.0)).toInt()
}
