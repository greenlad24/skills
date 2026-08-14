// Google Gemini API client — image generation/editing (gemini-2.5-flash-image,
// "nano banana") and JSON text generation for captions. The Gemini API has a
// genuinely free tier: create a key at https://aistudio.google.com/apikey
const API = 'https://generativelanguage.googleapis.com/v1beta';

async function call(apiKey, model, body, timeoutMs = 180000) {
  if (!apiKey) throw new Error('Gemini API key is missing — add it in Settings (free at aistudio.google.com/apikey).');
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}/models/${model}:generateContent`, {
      method: 'POST',
      headers: { 'x-goog-api-key': apiKey, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = null; }
    if (!res.ok) {
      throw new Error(`Gemini: ${json?.error?.message || text.slice(0, 300) || `HTTP ${res.status}`}`);
    }
    return json;
  } finally {
    clearTimeout(t);
  }
}

/**
 * Generate one poster. images: [{buffer, mime}]. Returns a PNG/JPEG Buffer.
 */
async function generateImage({ apiKey, model, prompt, images = [], aspectRatio = '2:3' }) {
  const parts = [{ text: prompt }];
  for (const img of images.slice(0, 10)) {
    parts.push({ inline_data: { mime_type: img.mime, data: img.buffer.toString('base64') } });
  }
  const json = await call(apiKey, model || 'gemini-2.5-flash-image', {
    contents: [{ parts }],
    generationConfig: {
      responseModalities: ['IMAGE'],
      imageConfig: { aspectRatio },
    },
  });
  const outParts = json?.candidates?.[0]?.content?.parts || [];
  const imgPart = outParts.find((p) => p.inlineData?.data || p.inline_data?.data);
  if (!imgPart) {
    const reason = json?.candidates?.[0]?.finishReason || json?.promptFeedback?.blockReason || 'no image in response';
    const textOut = outParts.find((p) => p.text)?.text;
    throw new Error(`Gemini returned no image (${reason})${textOut ? `: ${textOut.slice(0, 200)}` : ''}`);
  }
  const data = imgPart.inlineData?.data || imgPart.inline_data?.data;
  return Buffer.from(data, 'base64');
}

/** JSON-mode text generation (used for captions/voice when there is no OpenAI key). */
async function chatJson({ apiKey, system, user, model = 'gemini-2.5-flash' }) {
  const json = await call(apiKey, model, {
    system_instruction: { parts: [{ text: system }] },
    contents: [{ parts: [{ text: user }] }],
    generationConfig: { responseMimeType: 'application/json', temperature: 0.8 },
  }, 60000);
  const text = json?.candidates?.[0]?.content?.parts?.map((p) => p.text).join('') || '';
  try {
    return JSON.parse(text);
  } catch {
    throw new Error('Gemini returned invalid JSON for captions — try again.');
  }
}

module.exports = { generateImage, chatJson };
