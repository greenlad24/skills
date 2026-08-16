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
    /**
     * Half-minute windows of the night before a voice and a horn are
     * worth trying to tell apart. Over one song they are the same
     * thing; the difference is that one of them is in most songs.
     */
    val minWindows: Int = 6,
    /** confidence before an instrument reading is acted on */
    val recogniseConfidence: Float = 0.45f,
)

class InstrumentId(val settings: IdSettings = IdSettings()) {

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
     * WHAT INSTRUMENT IS THIS? — from the audio, with no name involved.
     *
     * [verdict] answers "what family", which is as far as one channel's
     * own numbers go. This answers "what instrument", and it can only
     * do that because [Ensemble] supplies what a channel is doing
     * relative to the other fifteen. Each test below names the physical
     * fact it stands on, because a classifier whose thresholds are
     * folklore cannot be argued with when it is wrong:
     *
     *  · KICK vs BASS. Both are energy under 200 Hz with no top, and
     *    nothing in one channel's spectrum separates them. What does is
     *    the ENVELOPE: a kick is a hit and then nothing — a hard rise
     *    and a peak far above its own average — while a bass sustains
     *    between notes. A kick also fires with the rest of the kit; a
     *    bass locks to the kick but not to the cymbals.
     *  · CYMBALS vs SNARE vs HAND DRUM. Overheads are the only channel
     *    that hears the WHOLE kit, so they coincide with everything and
     *    are mostly air. A snare has a body around 200 Hz and a burst
     *    of noise above 2 kHz. Congas and toms are the mid-low ones
     *    with no top and a much denser stream of hits.
     *  · KEYS. Wide, even, always there — and very often two channels
     *    whose envelopes are the same curve twice, which no two
     *    separate instruments ever are.
     *  · VOICE vs HORN. These are the same thing to a spectrum, and
     *    saying so is more useful than pretending otherwise. What
     *    separates them is the SET: a singer sings in most songs, a
     *    saxophone plays in a few and in bursts. That needs more than
     *    one song to see, and until it has been seen this returns
     *    UNKNOWN rather than guessing.
     */
    fun recognise(ch: Int, ens: Ensemble): Reading? {
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
        val bottom = sub + low
        val top = pres + air
        val voiceBand = mid + upMid + pres

        val duty = p.duty; val sustain = p.sustain
        val attack = p.attack; val crest = p.crest
        val flux = p.flux; val onsets = p.onsetRate

        val kit = ens.kitAffinity(ch)
        val mate = ens.stereoMate(ch)
        val setDuty = ens.setDuty(ch)
        val burst = ens.burstiness(ch)
        val windows = ens.windows(ch)

        fun ramp(v: Float, at0: Float, at1: Float): Float =
            ((v - at0) / (at1 - at0)).coerceIn(0f, 1f)

        val scores = HashMap<Instrument, Float>()
        val why = HashMap<Instrument, String>()

        // --- the low end ------------------------------------------------
        val isLow = ramp(bottom, 0.35f, 0.62f) * ramp(air, 0.14f, 0.03f) *
            ramp(sub, 0.06f, 0.25f)
        if (isLow > 0.05f) {
            val struck = ramp(attack, 2f, 7f) * ramp(crest, 7f, 14f) *
                ramp(1f - sustain, 0.2f, 0.5f)
            scores[Instrument.KICK] = isLow * struck *
                ramp(kit, 0.15f, 0.45f)
            why[Instrument.KICK] = ("all underneath and struck: %.0f dB " +
                "attacks, peaks %.0f dB over average, firing with the kit")
                .format(attack, crest)
            // A BASS DOES NOT FIRE WITH THE CYMBALS.
            //
            // The kit term was in the comment above and missing from the
            // arithmetic, and it cost exactly what it was there to
            // prevent: on a real night the OVERHEADS were declared a
            // bass — "60 % under 200 Hz and it sustains" — and the
            // engine then moved them into the low-end group and put a
            // kick's chain on them. A channel that lands with every
            // other drum is part of the kit whatever its spectrum says,
            // and a bass locks to the KICK and to nothing else.
            scores[Instrument.BASS] = isLow * ramp(sustain, 0.25f, 0.6f) *
                ramp(crest, 12f, 6f) * ramp(kit, 0.55f, 0.25f)
            why[Instrument.BASS] = ("%.0f%% under 200 Hz, it sustains " +
                "between notes rather than being struck, and it does not " +
                "land with the kit").format(bottom * 100)
        }

        // --- the kit ----------------------------------------------------
        if (kit > 0.2f) {
            scores[Instrument.CYMBALS] = ramp(air, 0.20f, 0.45f) *
                ramp(bottom, 0.30f, 0.08f) * ramp(kit, 0.35f, 0.7f)
            why[Instrument.CYMBALS] = ("%.0f%% of it is above 5 kHz and it " +
                "fires with every other drum — that is a pair of overheads")
                .format(air * 100)
            scores[Instrument.SNARE] = ramp(loMid + mid, 0.20f, 0.45f) *
                ramp(top, 0.12f, 0.35f) * ramp(crest, 8f, 16f) *
                ramp(kit, 0.25f, 0.55f) * ramp(onsets, 0.3f, 1.2f)
            why[Instrument.SNARE] = ("a body around 200 Hz with a burst of " +
                "noise on top, peaks %.0f dB over average, on the grid")
                .format(crest)
            // AND IT HAS TO STOP. Every other term here is satisfied by
            // a singer through a stage mic: plenty of low-mid, no air to
            // speak of once a PA has had its way with it, a healthy
            // crest, and three or four onsets a second because that is
            // what singing to a beat looks like on a meter. This was
            // the runaway of the night — seven channels identified,
            // every one of them "congas / toms", including both singers
            // and both pianos. A conga is over a quarter-second after
            // it is hit. Nothing else here is.
            // AND IT IS NEITHER THE KICK NOR ANYTHING WITH A TUNE IN IT.
            //
            // Two terms that were missing, and both cost a channel on
            // the next real night. A kick is low, struck, over before
            // the next one and lands with the kit — every test above,
            // passed perfectly — so the kick was declared a conga and
            // taken out of FOUNDATION, which is the one channel the
            // whole pyramid is measured from. A conga has its body
            // around 200 Hz and almost nothing underneath, so being
            // low-end at all now argues against it.
            //
            // The second is the mirror of the singer problem. Making
            // `kit` mean "struck, alongside other struck things" also
            // made a strummed guitar DI score highly on it — strummed
            // chords do stop — which zeroed its melodic score and left
            // congas the only candidate standing. A drum has no tune:
            // energy in the voice band is a line being played, and
            // hands on a skin do not play lines.
            scores[Instrument.HAND_DRUM] = ramp(low + loMid, 0.25f, 0.55f) *
                ramp(air, 0.12f, 0.02f) * ramp(crest, 7f, 14f) *
                ramp(onsets, 0.8f, 2.5f) * ramp(kit, 0.2f, 0.5f) *
                ramp(1f - sustain, 0.30f, 0.60f) *
                ramp(isLow, 0.45f, 0.10f) *
                ramp(voiceBand, 0.45f, 0.20f)
            why[Instrument.HAND_DRUM] = ("mid-low, no top, %.1f hits a " +
                "second, and each one is over before the next — hands " +
                "rather than sticks").format(onsets)
        }

        // --- the bed ----------------------------------------------------
        val widest = maxOf(sub, low, loMid, mid, upMid, pres, air)
        val even = ramp(widest, 0.60f, 0.30f)
        scores[Instrument.KEYS] = even * ramp(duty, 0.35f, 0.75f) *
            ramp(sustain, 0.35f, 0.75f) * ramp(flux, 0.25f, 0.08f) *
            ramp(sub, 0.20f, 0.04f) *
            // two channels that are the same curve twice are one
            // instrument, and on a stage that instrument is a keyboard
            (if (mate != null) 1f else 0.55f)
        why[Instrument.KEYS] = (if (mate != null)
            "wide and even, and channel %02d is the same curve twice — " +
            "one instrument on two channels".format(mate + 1)
            else "wide and even, playing %.0f%% of the time".format(duty * 100))

        // --- things that carry a line -----------------------------------
        // A SINGER SINGS IN TIME WITH THE BAND.
        //
        // `kit` used to be a timing measurement, so this last term —
        // meant to read "and it is not a drum" — actually read "and it
        // is not playing along with anyone", which zeroed the voice
        // score for every singer in every band there has ever been. Two
        // vocal channels went a whole night unrecognised because of it,
        // were called percussion instead, lost the protection that
        // holds a singer's fader still, and sat twelve dB down for two
        // and a half hours. `kit` now means "is struck, alongside other
        // things that are struck", which is what this always wanted to
        // ask, so the term can stay — and can be gentler, because it
        // now separates what it is aimed at.
        val melodic = ramp(voiceBand, 0.40f, 0.70f) * ramp(sub, 0.12f, 0.02f) *
            ramp(flux, 0.05f, 0.22f) * ramp(kit, 0.50f, 0.20f)
        if (melodic > 0.05f) {
            // A singer is in most of the night; a horn is in a few songs
            // of it, and in bursts. Below `minWindows` there has not
            // been enough night to tell, and neither score is offered.
            val enough = windows >= settings.minWindows
            if (enough) {
                scores[Instrument.VOICE] = melodic *
                    ramp(setDuty, 0.18f, 0.45f) * ramp(burst, 0.75f, 0.35f)
                why[Instrument.VOICE] = ("carries a line in the voice band " +
                    "and is in %.0f%% of the night — a singer, not a guest")
                    .format(setDuty * 100)
                scores[Instrument.HORN] = melodic *
                    ramp(setDuty, 0.40f, 0.12f) * ramp(burst, 0.35f, 0.75f)
                why[Instrument.HORN] = ("carries a line but only in %.0f%% " +
                    "of the night, in bursts — a horn or a reed, playing " +
                    "its parts").format(setDuty * 100)
            }
            // A picked string has attacks a throat and a reed do not.
            val picked = ramp(attack, 2f, 6f) * ramp(crest, 6f, 13f)
            scores[Instrument.GUITAR] = melodic * picked *
                ramp(setDuty, 0.20f, 0.55f) * ramp(burst, 0.6f, 0.25f)
            why[Instrument.GUITAR] = ("a picked string: %.0f dB attacks, " +
                "playing under the song most of the time").format(attack)
            scores[Instrument.LEAD_GUITAR] = melodic * picked *
                ramp(burst, 0.3f, 0.7f) * ramp(setDuty, 0.55f, 0.15f)
            why[Instrument.LEAD_GUITAR] = ("a picked string that plays in " +
                "bursts rather than under the song — lead, not rhythm")
        }

        val best = scores.entries.maxByOrNull { it.value }
            ?: return Reading(Instrument.UNKNOWN, 0f, "nothing distinctive yet")
        if (best.value <= 0.02f)
            return Reading(Instrument.UNKNOWN, 0f, "nothing distinctive yet")
        val runnerUp = scores.entries.filter { it.key != best.key }
            .maxOfOrNull { it.value } ?: 0f
        // Confidence is how far clear of the next candidate it is, not
        // the raw score: two instruments both fitting is exactly the
        // case where an autopilot should keep its opinion to itself.
        val conf = (best.value * (1f - runnerUp / max(best.value, 1e-6f)))
            .coerceIn(0f, 1f)
        return Reading(best.key, conf, why[best.key] ?: "")
    }

    data class Reading(
        val instrument: Instrument,
        val confidence: Float,
        val why: String,
    )

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
        // `fits[0] != current` for the same reason the other two
        // branches check it: this function answers "what should this
        // channel become", and "what it already is" is not an answer.
        // It started mattering when the name vocabulary learned that a
        // console truncates to eight characters — "Kick Drum" now reads
        // as both a drum and a kick, which is correct and ambiguous.
        if (named.size > 1 && fits.size == 1 && fits[0] != current &&
            v.confidence >= settings.actConfidence)
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
        // A CONSOLE TRUNCATES NAMES TO EIGHT CHARACTERS, so the words
        // an engineer types are not the words that arrive. This rig's
        // desk says "DRUM OVRH", "DRUM SNAR", "DRUM KICK" — and
        // "overhead" never matched "OVRH", so the overheads counted as
        // a channel whose name says nothing, the family classifier
        // called their 400 Hz-5 kHz content a lead vocal, and over
        // three nights they were re-roled between percussion and VOCAL
        // eight times. A vocal role is one the engine promises not to
        // move, so a drum microphone kept being handed that promise.
        if (has("conga", "congo", "bongo", "perc", "cajon", "shaker",
                "timbale", "tamb", "snare", "snar", "snr", "overhead",
                "ovrh", "ovhd", "ovh", "oh ", "tom", "hat", "hh", "kit",
                "ride", "crash", "cym", "drum", "drm")) out.add(Role.PERCUSSION)
        if (has("kick", "kik", "bd ", "bass", "sub", "808", "di 2", "di2"))
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
