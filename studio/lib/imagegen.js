// Image-engine dispatcher + caption/voice text generation.
// Engines: cloudflare (free), gemini (~$0.04/img), segmind (~$0.04/img), openai (premium).
const cloudflare = require('./cloudflare');
const gemini = require('./gemini');
const vertex = require('./vertex');
const segmind = require('./segmind');
const openai = require('./openaiClient');

/** Generate one poster (Buffer) with the configured engine. images: [{buffer, mime, name}] */
async function generatePoster(settings, { prompt, images }) {
  const engine = settings.imageEngine || 'cloudflare';
  if (engine === 'cloudflare') {
    return cloudflare.generateImage({
      accountId: settings.cfAccountId || process.env.CF_ACCOUNT_ID,
      apiToken: settings.cfApiToken || process.env.CF_API_TOKEN,
      model: settings.cfModel,
      prompt,
      images,
    });
  }
  if (engine === 'openai') {
    return openai.generateImage({
      apiKey: settings.openaiApiKey || process.env.OPENAI_API_KEY,
      model: settings.openaiImageModel || 'gpt-image-2',
      prompt,
      images,
      quality: settings.imageQuality,
      size: '1024x1536',
    });
  }
  if (engine === 'vertex') {
    return vertex.generateImage({ settings, prompt, images, aspectRatio: '2:3' });
  }
  if (engine === 'segmind') {
    return segmind.generateImage({
      apiKey: settings.segmindApiKey || process.env.SEGMIND_API_KEY,
      model: settings.segmindModel,
      prompt,
      images,
      aspectRatio: '2:3',
    });
  }
  return gemini.generateImage({
    apiKey: settings.geminiApiKey || process.env.GEMINI_API_KEY,
    model: settings.geminiModel,
    prompt,
    images,
    aspectRatio: '2:3',
  });
}

/**
 * JSON text generation for captions/voice: OpenAI when a key is set,
 * otherwise the (free) Gemini key — so the whole tool can run without OpenAI.
 */
async function chatJson(settings, { system, user, temperature }) {
  const openaiKey = settings.openaiApiKey || process.env.OPENAI_API_KEY;
  if (openaiKey) {
    return openai.chatJson({ apiKey: openaiKey, model: settings.captionModel, system, user, temperature });
  }
  const geminiKey = settings.geminiApiKey || process.env.GEMINI_API_KEY;
  if (geminiKey) {
    return gemini.chatJson({ apiKey: geminiKey, system, user });
  }
  throw new Error('No text model available — add a Gemini (free) or OpenAI API key in Settings.');
}

module.exports = { generatePoster, chatJson };
