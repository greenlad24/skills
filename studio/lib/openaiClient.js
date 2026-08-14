// OpenAI client: gpt-image-1 for posters, chat completions for captions/voice.
// Zero dependencies — uses Node 18+ global fetch/FormData/Blob.
const fs = require('fs');
const path = require('path');

const API = 'https://api.openai.com/v1';

function mimeFor(file) {
  const ext = path.extname(file).toLowerCase();
  return { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' }[ext] || 'image/png';
}

async function openaiFetch(apiKey, url, options, timeoutMs = 300000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = null; }
    if (!res.ok) {
      const msg = json?.error?.message || text.slice(0, 400) || `HTTP ${res.status}`;
      throw new Error(`OpenAI: ${msg}`);
    }
    return json;
  } finally {
    clearTimeout(t);
  }
}

/**
 * Generate one poster image. If inputImages (absolute paths) are provided we use
 * the edits endpoint (image-to-image, keeps faces with input_fidelity=high),
 * otherwise plain generation.
 * Returns base64 PNG data.
 */
async function generatePoster({ apiKey, prompt, inputImages = [], quality = 'high', size = '1024x1536' }) {
  if (!apiKey) throw new Error('OpenAI API key is missing — add it in Settings.');

  if (inputImages.length === 0) {
    const json = await openaiFetch(apiKey, `${API}/images/generations`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'gpt-image-1', prompt, size, quality, n: 1 }),
    });
    return json.data[0].b64_json;
  }

  const form = new FormData();
  form.append('model', 'gpt-image-1');
  form.append('prompt', prompt);
  form.append('size', size);
  form.append('quality', quality);
  form.append('input_fidelity', 'high');
  form.append('n', '1');
  for (const file of inputImages.slice(0, 16)) {
    const buf = fs.readFileSync(file);
    form.append('image[]', new Blob([buf], { type: mimeFor(file) }), path.basename(file));
  }
  const json = await openaiFetch(apiKey, `${API}/images/edits`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  return json.data[0].b64_json;
}

async function chatJson({ apiKey, model, system, user, temperature = 0.8 }) {
  if (!apiKey) throw new Error('OpenAI API key is missing — add it in Settings.');
  const json = await openaiFetch(apiKey, `${API}/chat/completions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: model || 'gpt-4.1',
      temperature,
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
    }),
  }, 120000);
  return JSON.parse(json.choices[0].message.content);
}

/** Analyze pasted past captions into a reusable voice profile. */
async function analyzeVoice({ apiKey, model, captions }) {
  return chatJson({
    apiKey,
    model,
    temperature: 0.2,
    system:
      'You are a brand voice analyst. You will receive past social media captions from a live-music bar. ' +
      'Extract a precise, reusable style profile. Respond with JSON: ' +
      '{"tone": str, "structure": str (how captions are typically built, line by line), ' +
      '"emojiUsage": str (which emojis, how many, where), "hashtagStyle": str (typical tags, how many, placement), ' +
      '"language": str (languages/slang/quirks), "callToAction": str (typical CTA phrasings), ' +
      '"signaturePhrases": [str], "avgLengthWords": number, "thingsToAvoid": str}',
    user: captions,
  });
}

/** Generate IG + FB captions for one day's poster in the learned voice. */
async function generateCaptions({ apiKey, model, voice, examples, day, settings }) {
  const info = day.info || {};
  const dayName = day.day.charAt(0).toUpperCase() + day.day.slice(1);
  const profile = voice ? JSON.stringify(voice) : 'No profile yet — write warm, energetic, concise live-music-bar captions.';
  const sampleBlock = examples && examples.length
    ? `\n\nREAL PAST CAPTIONS (imitate this voice closely):\n${examples.slice(0, 6).map((c, i) => `--- example ${i + 1} ---\n${c}`).join('\n')}`
    : '';
  return chatJson({
    apiKey,
    model,
    system:
      `You write social captions for "${settings.venueName || 'Vibration'}", a live music bar. ` +
      `Match the owner's voice profile exactly: ${profile}${sampleBlock}\n\n` +
      'Respond with JSON: {"instagram": str (caption INCLUDING hashtags at the end), "facebook": str (slightly longer, max 3 hashtags)}. ' +
      'Never invent facts (prices, guest lists) that were not provided.',
    user:
      `Write the Instagram and Facebook captions for this event:\n` +
      `- Day: ${dayName} ${day.date}\n` +
      `- Artist/event: ${info.artistName || '(untitled)'}\n` +
      `- Genres: ${info.genres || '-'}\n` +
      `- Time: ${info.showTime || '-'}\n` +
      `- What is special: ${info.special || '-'}\n` +
      `- Extra notes: ${info.notes || '-'}`,
  });
}

module.exports = { generatePoster, analyzeVoice, generateCaptions };
