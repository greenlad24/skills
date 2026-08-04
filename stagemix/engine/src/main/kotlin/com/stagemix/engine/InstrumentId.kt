package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.log2
import kotlin.math.max
import kotlin.math.min

/**
 * What is actually plugged into this channel?
 *
 * Roles used to come from the channel number and the channel name, and
 * both lie. A house desk's labels are whatever the last engineer typed —
 * "Congo / Vox 3" is the lead singer on this rig, and taking the first
 * word of it put the lead vocal in the percussion group, eight dB under
 * where it belongs, all night. Channel numbers are worse: the band moves
 * an input and the whole profile is wrong.
 *
 * So the audio decides. Two streams feed this, both already arriving:
 * the 20 Hz input meters give the ENVELOPE of every channel at once, and
 * the RTA the Channel Doctor round-robins gives the SPECTRUM of one
 * channel at a time. Together they separate the families that are
 * physically distinct:
 *
 *   · LOW_END   — energy under ~200 Hz, no top. Kick, bass, synth bass.
 *   · HITS      — sharp attack, fast decay, low duty. Drums, congas.
 *   · VOICELIKE — 400 Hz-5 kHz, formant movement. Voice, sax, harmonica,
 *                 an amp'd guitar.
 *   · BED       — wide and even, always on. Piano, organ, pads.
 *
 * Being honest about the limit matters more than being clever: a 100-bin
 * RTA cannot reliably tell a saxophone from a singer, and pretending
 * otherwise would move the lead vocal onto a horn. So audio settles the
 * FAMILY, which it can do, and the name settles the role WITHIN the
 * family, which is what names are actually good for. When the two flatly
 * contradict each other — a channel called "Vocal" that is 90 % sub-bass
 * — the audio wins and says so in the log, because the room can hear
 * what is on the channel and the label cannot.
 */

/** the families a spectrum and an envelope can genuinely separate */
enum class Family { LOW_END, HITS, VOICELIKE, BED, UNKNOWN }

data class IdSettings(
    /** RTA frames on a channel before its spectrum is worth reading */
    val minSpectra: Int = 12,
    /** seconds of audible signal before the envelope is worth reading */
    val minActiveSec: Float = 8f,
    /** below this the verdict is not acted on */
    val actConfidence: Float = 0.55f,
    /** how much better a contradicting verdict must be to overrule a name */
    val overruleConfidence: Float = 0.75f,
)

class InstrumentId(private val settings: IdSettings = IdSettings()) {

    data class Verdict(
        val family: Family,
        val confidence: Float,
        /** plain-language evidence, for the log and the screen */
        val why: String,
    )

    // --- band edges, in RTA bins (bin i is centred at 20 Hz * 2^(i/10)) --
    private companion object {
        fun bin(hz: Double): Int = (10.0 * log2(hz / 20.0)).toInt()
        val SUB = 0..bin(80.0)                      // 20-80 Hz
        val LOW = bin(80.0) + 1..bin(200.0)         // 80-200
        val LOMID = bin(200.0) + 1..bin(400.0)      // 200-400
        val MID = bin(400.0) + 1..bin(1100.0)       // 400-1.1k
        val UPMID = bin(1100.0) + 1..bin(2500.0)    // 1.1k-2.5k
        val PRES = bin(2500.0) + 1..bin(5500.0)     // 2.5k-5.5k
        val AIR = bin(5500.0) + 1..99               // 5.5k up
    }

    /**
     * What a channel has sounded like RECENTLY.
     *
     * Every accumulator here is a mean over its last N samples, not over
     * the whole night, because channels are not one instrument all
     * evening. The harmonica player on this rig sings backing vocals
     * between solos on the same microphone; an all-time average of that
     * channel is a blend of a reed and a throat and is neither. A memory
     * of a minute or two tracks what the channel is being used for now,
     * which is the only thing the balance can act on.
     *
     * The mean is exact until [mem] samples have arrived and an
     * exponential one after that — so it is not slow to make its first
     * call, and not stubborn about changing it later.
     */
    private class Print(private val mem: Int = 900, private val memSpec: Int = 240) {
        val spec = DoubleArray(100)
        var spectra = 0
        private var prev: DoubleArray? = null
        var flux = 0f; private set

        /** cumulative, never decayed: these gate whether to speak at all */
        var activeSec = 0.0
        var totalSec = 0.0

        var duty = 0f; private set
        var sustain = 0f; private set
        var attack = 0f; private set
        var crest = 0f; private set
        var onsetRate = 0f; private set

        private var lvlN = 0
        private var actN = 0
        private var atkN = 0
        private var crestN = 0
        private var fluxN = 0
        private var lastDb = -128f
        private var wasUp = false
        private var peakWin = -128f
        private var sumWin = 0f
        private var nWin = 0
        private var onsetWin = 0
        private var onsetFrames = 0

        private fun a(n: Int, cap: Int) = 1f / min(n, cap).coerceAtLeast(1)

        fun pushSpectrum(bins: FloatArray) {
            // to linear power, then normalise: WHAT the channel is, not
            // how loud it happens to be at this moment
            val lin = DoubleArray(100)
            var tot = 0.0
            for (i in 0 until 100) {
                val v = Math.pow(10.0, bins[i] / 10.0)
                lin[i] = v; tot += v
            }
            if (tot <= 0.0 || !tot.isFinite()) return
            for (i in 0 until 100) lin[i] /= tot
            prev?.let { p ->
                var d = 0.0
                for (i in 0 until 100) d += abs(lin[i] - p[i])
                fluxN++
                flux += a(fluxN, memSpec) * (d.toFloat() - flux)
            }
            prev = lin
            spectra++
            val al = a(spectra, memSpec).toDouble()
            for (i in 0 until 100) spec[i] += al * (lin[i] - spec[i])
        }

        fun pushLevel(db: Float, dtSec: Float, active: Boolean) {
            totalSec += dtSec.toDouble()
            lvlN++
            duty += a(lvlN, mem) * ((if (active) 1f else 0f) - duty)
            if (active) {
                activeSec += dtSec.toDouble()
                actN++
                val d = db - lastDb
                val al = a(actN, mem)
                sustain += al * ((if (abs(d) < 1f) 1f else 0f) - sustain)
                if (d > 0f) { atkN++; attack += a(atkN, mem) * (d - attack) }
                // an onset is a real step up after not rising
                if (d >= 4f && !wasUp) onsetWin++
                wasUp = d >= 1f
                onsetFrames++
                if (onsetFrames >= 40) {         // ~2 s at the meter rate
                    val r = onsetWin / (onsetFrames * 0.05f)
                    onsetRate += 0.1f * (r - onsetRate)
                    onsetWin = 0; onsetFrames = 0
                }
                if (db > peakWin) peakWin = db
                sumWin += db; nWin++
                if (nWin >= 20) {                // ~1 s at the meter rate
                    crestN++
                    crest += a(crestN, mem / 20) *
                        ((peakWin - sumWin / nWin) - crest)
                    peakWin = -128f; sumWin = 0f; nWin = 0
                }
            }
            lastDb = db
        }
    }

    private val prints = HashMap<Int, Print>()

    /** one RTA frame for whichever channel the doctor is parked on */
    fun onRta(ch: Int, bins: FloatArray, active: Boolean) {
        if (bins.size < 100 || !active) return
        for (v in bins) if (v.isNaN() || v.isInfinite()) return
        prints.getOrPut(ch) { Print() }.pushSpectrum(bins)
    }

    /** one input-meter frame */
    fun onLevel(ch: Int, db: Float, dtSec: Float, active: Boolean) {
        if (db.isNaN() || db.isInfinite()) return
        prints.getOrPut(ch) { Print() }.pushLevel(db, dtSec, active)
    }

    fun forget(ch: Int) { prints.remove(ch) }
    fun forgetAll() { prints.clear() }

    /**
     * The channel's average spectrum, normalised, or null before there
     * is one. Handed out so a one-shot channel treatment can remember
     * WHAT it was built for, and notice later that the socket now has
     * something else on it.
     */
    fun spectrum(ch: Int): DoubleArray? =
        prints[ch]?.takeIf { it.spectra > 0 }?.spec?.copyOf()

    /** how much evidence there is, 0..1, for the screen */
    fun evidence(ch: Int): Float {
        val p = prints[ch] ?: return 0f
        return min(1f, min(p.spectra / settings.minSpectra.toFloat(),
            (p.activeSec / settings.minActiveSec).toFloat()))
    }

    /**
     * What family is on this channel, or null while there is not yet
     * enough of it to say.
     */
    fun verdict(ch: Int): Verdict? {
        val p = prints[ch] ?: return null
        if (p.spectra < settings.minSpectra) return null
        if (p.activeSec < settings.minActiveSec) return null

        fun band(r: IntRange): Float {
            var s = 0.0
            for (i in r) if (i in 0 until 100) s += p.spec[i]
            return s.toFloat()
        }
        val sub = band(SUB); val low = band(LOW); val loMid = band(LOMID)
        val mid = band(MID); val upMid = band(UPMID); val pres = band(PRES)
        val air = band(AIR)

        val duty = p.duty
        val sustain = p.sustain
        val attack = p.attack
        val crest = p.crest
        val flux = p.flux
        val onsetRate = p.onsetRate

        fun ramp(v: Float, at0: Float, at1: Float): Float =
            ((v - at0) / (at1 - at0)).coerceIn(0f, 1f)

        // LOW END: it is all underneath, and there is no top at all.
        //
        // The sub term is what makes this specific. A conga's fundamental
        // sits around 190 Hz — the same band a bass guitar lives in — so
        // "most of it is below 200 Hz" called every hand drum a bass. What
        // a kick and a bass have and a drum does not is real energy BELOW
        // 80 Hz, so that is what is asked for.
        val lowEnd = ramp(sub + low, 0.35f, 0.62f) * ramp(air, 0.14f, 0.03f) *
            ramp(sub, 0.06f, 0.25f)

        // HITS: struck, not blown or bowed — a hard rise and a peak far
        // above the average. Cymbals are the exception, so ride them in
        // on brightness instead.
        //
        // Deliberately NOT "silent in between": a programme meter falls
        // over about 300 ms, so a conga at two hits a second never once
        // drops below the gate and reads as 100 % duty. Crest survives
        // the ballistics where duty does not — 24 dB of peak over
        // average is a drum however smeared the gaps are.
        //
        // A struck source with nothing above 200 Hz is a kick drum, and a
        // kick belongs with the low end it anchors, not with the snare.
        val hasTop = loMid + mid + upMid + pres + air
        val struck = ramp(attack, 2f, 8f) * ramp(crest, 6f, 15f) *
            ramp(hasTop, 0.08f, 0.25f)
        val cymbal = ramp(air, 0.22f, 0.45f) * ramp(sub + low, 0.25f, 0.05f)
        val hits = max(struck, cymbal * ramp(crest, 2f, 6f))

        // VOICELIKE: the band a throat or a reed works in, nothing
        // underneath it, and a spectrum that will not sit still —
        // formants and bends move, a held chord does not.
        val voiceBand = mid + upMid + pres
        val voiceLike = ramp(voiceBand, 0.40f, 0.68f) *
            ramp(sub, 0.12f, 0.02f) * ramp(flux, 0.05f, 0.22f)

        // BED: wide, even and always there. Nothing dominates, because a
        // piano is playing five notes at once.
        //
        // The flux term is what keeps a singer out of here. A voice fills
        // much the same span as a piano and is audible much of the time,
        // so on band coverage alone the two score within a whisker of
        // each other and neither verdict is safe to act on. A held chord
        // does not MOVE; a voice never stops moving.
        val widest = maxOf(sub, low, loMid, mid, upMid, pres, air)
        val bed = ramp(widest, 0.60f, 0.30f) * ramp(duty, 0.35f, 0.75f) *
            ramp(sustain, 0.35f, 0.75f) * ramp(sub, 0.20f, 0.04f) *
            ramp(flux, 0.25f, 0.08f)

        val scores = listOf(
            Family.LOW_END to lowEnd, Family.HITS to hits,
            Family.VOICELIKE to voiceLike, Family.BED to bed)
        val best = scores.maxByOrNull { it.second }!!
        val runnerUp = scores.filter { it.first != best.first }
            .maxOf { it.second }
        if (best.second <= 0.01f) return Verdict(Family.UNKNOWN, 0f,
            "nothing distinctive yet")

        // Confidence is how far clear of the next family it is, not the
        // raw score: two families both fitting is exactly the case where
        // the name should be allowed to decide.
        val conf = (best.second * (1f - runnerUp / max(best.second, 1e-6f)))
            .coerceIn(0f, 1f)

        val why = when (best.first) {
            Family.LOW_END -> "%.0f%% of it is under 200 Hz with no top"
                .format((sub + low) * 100)
            Family.HITS -> "struck: %.0f dB attacks, peaks %.0f dB over average"
                .format(attack, crest)
            Family.VOICELIKE -> ("%.0f%% in the 400 Hz-5 kHz band, moving " +
                "(flux %.2f)").format(voiceBand * 100, flux)
            Family.BED -> "wide and even, playing %.0f%% of the time"
                .format(duty * 100)
            Family.UNKNOWN -> "unclear"
        } + ", %.0f onsets/s".format(onsetRate)

        return Verdict(best.first, conf, why)
    }

    // ------------------------------------------------------------------
    /**
     * Settle a channel's role from its name and what it sounds like.
     *
     * The name proposes, the audio disposes. Returns null to leave the
     * role alone — which is the answer whenever there is not enough
     * evidence, or the two agree already.
     */
    fun resolve(ch: Int, name: String, current: Role): Resolution? {
        // Speech mics are never automated and never re-roled: that is a
        // safety property, not a classification.
        if (current == Role.TALK || inferRole(name) == Role.TALK) return null
        val v = verdict(ch) ?: return null
        if (v.family == Family.UNKNOWN) return null

        val named = namedRoles(name)
        val fits = named.filter { familyOf(it) == v.family }

        // 1. the name is ambiguous and the audio picks one of its readings
        if (named.size > 1 && fits.size == 1 && v.confidence >= settings.actConfidence)
            return Resolution(fits[0], v,
                "\"$name\" could be ${named.joinToString(" or ") { pretty(it) }} " +
                "— it sounds like ${pretty(fits[0])} (${v.why})")

        // 2. the name says nothing useful, so the audio names it
        if (named.isEmpty() && v.confidence >= settings.actConfidence) {
            val r = defaultRole(v.family)
            if (r != current) return Resolution(r, v,
                "\"$name\" says nothing about what it is — it sounds like " +
                "${pretty(r)} (${v.why})")
        }

        // 3. the name is confident and the audio flatly contradicts it.
        // The room can hear what is on the channel; the label cannot.
        if (named.isNotEmpty() && fits.isEmpty() &&
            v.confidence >= settings.overruleConfidence) {
            val r = defaultRole(v.family)
            if (r != current) return Resolution(r, v,
                "\"$name\" is labelled ${pretty(named[0])} but does not " +
                "sound like one — treating it as ${pretty(r)} (${v.why})")
        }
        return null
    }

    data class Resolution(val role: Role, val verdict: Verdict, val why: String)

    /**
     * Every role this name could plausibly mean, best first. More than
     * one means the label is ambiguous — "Congo / Vox 3" is a conga AND
     * a vocal as far as the words go, and only the audio can say which.
     */
    fun namedRoles(name: String): List<Role> {
        val n = name.lowercase()
        fun has(vararg keys: String) = keys.any { it in n }
        val out = ArrayList<Role>()
        if (has("talk", "tb ", "announce", "speech")) out.add(Role.TALK)
        if (has("harmonica", "blues harp", "sax", "horn", "trumpet",
                "flute", "tromb")) out.add(Role.COLOR)
        if (has("bgv", "bvox", "backing", "back ", "choir", "harmony",
                "harm ")) out.add(Role.BACKING_VOCAL)
        if (has("vox", "vocal", "sing", "voice", "lead v")) out.add(Role.VOCAL)
        if (has("conga", "congo", "bongo", "perc", "cajon", "shaker",
                "timbale", "tamb", "snare", "overhead", "oh ", "tom",
                "hat", "kit", "ride", "crash")) out.add(Role.PERCUSSION)
        if (has("kick", "bass", "sub", "808", "di 2", "di2"))
            out.add(Role.FOUNDATION)
        if (has("piano", "keys", "keyb", "rhodes", "organ", "synth",
                "pad")) out.add(Role.KEYS)
        if (has("solo", "lead g", "amp")) out.add(Role.SOLO_GTR)
        if (has("rhythm", "ac g", "acoustic", "gtr", "guitar"))
            out.add(Role.RHYTHM_GTR)
        return out
    }

    /** which family a role belongs to, for agreement testing */
    fun familyOf(role: Role): Family = when (role) {
        Role.FOUNDATION -> Family.LOW_END
        Role.PERCUSSION -> Family.HITS
        Role.VOCAL, Role.BACKING_VOCAL, Role.COLOR,
        Role.SOLO_GTR, Role.RHYTHM_GTR -> Family.VOICELIKE
        Role.KEYS -> Family.BED
        Role.INSTRUMENT, Role.TALK -> Family.UNKNOWN
    }

    /**
     * With nothing but the audio to go on, the safest reading of each
     * family. VOICELIKE defaults to VOCAL: putting a sax briefly in the
     * vocal group costs a couple of dB, while leaving a singer out of it
     * costs the show.
     */
    private fun defaultRole(f: Family): Role = when (f) {
        Family.LOW_END -> Role.FOUNDATION
        Family.HITS -> Role.PERCUSSION
        Family.VOICELIKE -> Role.VOCAL
        Family.BED -> Role.KEYS
        Family.UNKNOWN -> Role.INSTRUMENT
    }

    fun pretty(r: Role): String = when (r) {
        Role.FOUNDATION -> "low end"
        Role.PERCUSSION -> "percussion"
        Role.VOCAL -> "a lead vocal"
        Role.BACKING_VOCAL -> "a backing vocal"
        Role.KEYS -> "keys"
        Role.COLOR -> "a horn or harp"
        Role.SOLO_GTR -> "a lead guitar"
        Role.RHYTHM_GTR -> "a rhythm guitar"
        Role.INSTRUMENT -> "unclassified"
        Role.TALK -> "a talkback mic"
    }
}
