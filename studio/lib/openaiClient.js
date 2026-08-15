// OpenAI client: gpt-image-1 for posters (premium option), chat completions
// for captions/voice. Uses Node 18+ global fetch/FormData/Blob.
const API = 'https://api.openai.com/v1';

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
 * Generate one poster image. images: [{buffer, mime, name}]. With images we
 * use the edits endpoint (input_fidelity=high keeps faces); without, plain
 * generation. Returns a Buffer.
 */
async function generateImage({ apiKey, model = 'gpt-image-2', prompt, images = [], quality = 'high', size = '1024x1536' }) {
  if (!apiKey) throw new Error('OpenAI API key is missing — add it in Settings.');

  if (images.length === 0) {
    const json = await openaiFetch(apiKey, `${API}/images/generations`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, prompt, size, quality, n: 1 }),
    });
    return Buffer.from(json.data[0].b64_json, 'base64');
  }

  // input_fidelity exists only on gpt-image-1/1.5; gpt-image-2 always runs
  // high-fidelity inputs and rejects the parameter with a 400.
  const fidelityParamSupported = /^gpt-image-1/.test(model);
  const edit = (withFidelity) => {
    const form = new FormData();
    form.append('model', model);
    form.append('prompt', prompt);
    form.append('size', size);
    form.append('quality', quality);
    if (withFidelity) form.append('input_fidelity', 'high');
    form.append('n', '1');
    images.slice(0, 16).forEach((img, i) => {
      form.append('image[]', new Blob([img.buffer], { type: img.mime }), img.name || `image-${i}.png`);
    });
    return openaiFetch(apiKey, `${API}/images/edits`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}` },
      body: form,
    });
  };

  let json;
  try {
    json = await edit(fidelityParamSupported);
  } catch (e) {
    // Safety net for parameter drift across model snapshots.
    if (/input_fidelity|unknown parameter|unsupported/i.test(e.message)) json = await edit(!fidelityParamSupported);
    else throw e;
  }
  return Buffer.from(json.data[0].b64_json, 'base64');
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

module.exports = { generateImage, chatJson };
