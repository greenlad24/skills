// The "listener": a hosted audio model hears a few seconds of the master mix and answers
// specific questions (vocal intelligible? anything harsh? bass audible on a phone? solo?).
// Claude's mixer reads these verdicts alongside the meters. Off until GEMINI_API_KEY is set
// (Keys screen; picked up live, no restart).

const key = () => process.env.GEMINI_API_KEY ?? '';
const MODEL = process.env.GEMINI_MODEL ?? 'gemini-2.5-flash';
const AUDIO = process.env.VN_AUDIO_URL ?? 'http://127.0.0.1:8091';

export interface Verdict {
  t: number;
  vocal: 'clear' | 'buried' | 'too loud' | 'no vocal';
  harsh: string; // 'none' or what is harsh
  low_end: 'good on phones' | 'thin' | 'boomy';
  solo: string; // 'none' or the instrument
  balance: string; // one short sentence
}

const PROMPT = `You are listening to ${'~'}6 seconds of a live funk/soul/R&B band's broadcast mix (it will mostly be heard on phones).
Answer JSON only: {"vocal": "clear"|"buried"|"too loud"|"no vocal", "harsh": "none" or the source that sounds harsh/piercing, "low_end": "good on phones"|"thin"|"boomy", "solo": "none" or the instrument soloing, "balance": "<one short sentence on the overall balance>"}`;

export class Listener {
  verdicts: Verdict[] = [];
  lastError = '';
  get enabled() { return Boolean(key()); }

  constructor(private playing: () => boolean) {
    setInterval(() => void this.listen(), 20_000);
  }

  status() {
    if (!this.enabled) return 'off (no Gemini key)';
    if (this.lastError) return 'error';
    return this.verdicts.length ? `every 20 s · ${this.verdicts[this.verdicts.length - 1].vocal}` : 'starting';
  }

  async listen() {
    if (!this.enabled || !this.playing()) return;
    try {
      const wav = Buffer.from(await (await fetch(`${AUDIO}/clip.wav?seconds=6`)).arrayBuffer());
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-goog-api-key': key() },
        body: JSON.stringify({
          contents: [{ parts: [{ text: PROMPT }, { inline_data: { mime_type: 'audio/wav', data: wav.toString('base64') } }] }],
          generationConfig: { responseMimeType: 'application/json', temperature: 0.2 },
        }),
        signal: AbortSignal.timeout(30_000),
      });
      const j = (await r.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[]; error?: { message: string } };
      if (!r.ok) throw new Error(j.error?.message ?? `HTTP ${r.status}`);
      const text = j.candidates?.[0]?.content?.parts?.[0]?.text ?? '{}';
      const v = JSON.parse(text) as Omit<Verdict, 't'>;
      this.verdicts.push({ t: Date.now(), ...v });
      if (this.verdicts.length > 12) this.verdicts.shift();
      this.lastError = '';
    } catch (e) {
      this.lastError = (e as Error).message.slice(0, 160);
    }
  }

  /** Lines for Claude's mixer report. */
  summary(): string | null {
    const recent = this.verdicts.filter((v) => Date.now() - v.t < 180_000);
    if (!recent.length) return null;
    return `Listener (hosted audio model, last ${recent.length} checks, newest last): ${recent.map((v) => `[vocal ${v.vocal}; harsh: ${v.harsh}; low end ${v.low_end}; solo: ${v.solo}; ${v.balance}]`).join(' ')}`;
  }
}
