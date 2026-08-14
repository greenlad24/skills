// Voice analysis + caption writing, engine-agnostic (OpenAI or free Gemini).
const { chatJson } = require('./imagegen');

async function analyzeVoice(settings, captionsText) {
  return chatJson(settings, {
    temperature: 0.2,
    system:
      'You are a brand voice analyst. You will receive past social media captions from a live-music bar. ' +
      'Extract a precise, reusable style profile. Respond with JSON: ' +
      '{"tone": str, "structure": str (how captions are typically built, line by line), ' +
      '"emojiUsage": str (which emojis, how many, where), "hashtagStyle": str (typical tags, how many, placement), ' +
      '"language": str (languages/slang/quirks), "callToAction": str (typical CTA phrasings), ' +
      '"signaturePhrases": [str], "avgLengthWords": number, "thingsToAvoid": str}',
    user: captionsText,
  });
}

async function generateCaptions(settings, { voice, examples, day }) {
  const info = day.info || {};
  const dayName = day.day.charAt(0).toUpperCase() + day.day.slice(1);
  const profile = voice ? JSON.stringify(voice) : 'No profile yet — write warm, energetic, concise live-music-bar captions.';
  const sampleBlock = examples && examples.length
    ? `\n\nREAL PAST CAPTIONS (imitate this voice closely):\n${examples.slice(0, 6).map((c, i) => `--- example ${i + 1} ---\n${c}`).join('\n')}`
    : '';
  return chatJson(settings, {
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

module.exports = { analyzeVoice, generateCaptions };
