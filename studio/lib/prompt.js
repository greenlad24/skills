// Poster art direction. This is the heart of "looks like a real designer made it":
// a strict brand system + per-style art direction + three distinct creative takes.

const STYLE_PRESETS = {
  'golden-stage': {
    name: 'Golden Stage',
    file: 'golden-stage.jpg',
    direction:
      'Warm amber concert stage: soft golden spotlights from above, a live band silhhouetted in warm bokeh behind the hero, purple-and-gold draped curtains, cinematic haze. Elegant metallic-gold sans/serif display type with generous letter-spacing. Mood: intimate, premium, alive.',
  },
  'golden-portrait': {
    name: 'Golden Portrait',
    file: 'golden-portrait.jpg',
    direction:
      'Dark luxurious lounge at night, city lights bokeh in the far background, deep browns and golds, thin ornate gold frame inset from the poster edges, engraved-gold beveled serif capitals for the artist name, delicate gold script for the day. Mood: seductive, upscale, editorial.',
  },
  'white-gold-luxe': {
    name: 'White & Gold Luxe',
    file: 'white-gold-luxe.jpg',
    direction:
      'Bright white luxury interior flooded with light, golden sparkle particles sweeping in an arc, thin double gold frame, polished 3D gold serif capitals with strong bevel for the artist name, gold script accents. Mood: glamorous, champagne, five-star.',
  },
  'smoky-stage': {
    name: 'Smoky Rock Stage',
    file: 'smoky-stage.jpg',
    direction:
      'Dark moody rock stage with warm tungsten backlight and smoke, deep blacks and burnt oranges, subtle film grain and vignette, thin retro border frame. Artist name in huge distressed white brush-script, supporting lines in cream condensed sans, a hand-drawn gold script flourish for genres. Mood: raw, soulful, vintage rock.',
  },
  'vintage-rock': {
    name: 'Vintage Rock Poster',
    file: 'vintage-rock.jpg',
    direction:
      'Illustrated vintage rock-poster: textured paper, ink spatter, halftone shading, sun-bleached palette with reds and creams, ragged label boxes for day/time, aggressive white brush lettering with red accent words. The hero is rendered as a detailed retro illustration, not a photo. Mood: gritty, collectible gig poster.',
  },
  'retro-funk': {
    name: 'Retro 70s Funk',
    file: 'retro-funk.jpg',
    direction:
      "1970s funk aesthetic: warm oranges and browns, psychedelic wallpaper shapes, disco ball glinting, vintage backline (amps, drums) on stage, chunky groovy 70s bubble lettering with deep drop shadow for the headline, rounded serif for details. Mood: playful, nostalgic, let's jam.",
  },
  'sunset-beach': {
    name: 'Sunset Beach',
    file: 'sunset-beach.jpg',
    direction:
      'Golden-hour beach: pastel pink-and-peach sky, soft sun glow behind the hero, rocks and gentle surf, airy composition. Clean modern geometric sans in deep teal for the headline plus an elegant script word pair, minimal furniture. Mood: breezy, feel-good, holiday.',
  },
};

// Three deliberately different creative takes so the 3 variations feel like
// three comps from a design studio, not three dice rolls.
const VARIANT_TAKES = [
  {
    label: 'Faithful',
    twist:
      'TAKE 1 — FAITHFUL: Follow the style reference image(s) as closely as possible — same lighting recipe, same typographic voice, same mood — executed perfectly for this artist and this copy.',
  },
  {
    label: 'Recomposed',
    twist:
      'TAKE 2 — RECOMPOSED: Keep the same style family, but change the composition: different hero crop or angle (e.g. closer portrait, off-center rule-of-thirds placement, or dramatic low angle), different placement of the type blocks, fresh background depth. It must still read instantly as the same brand.',
  },
  {
    label: 'Type-forward',
    twist:
      'TAKE 3 — TYPE-FORWARD: A bolder, more editorial layout: the artist name becomes a huge expressive typographic centerpiece (it may overlap the hero slightly), more negative space, fewer background details, stronger color-blocked contrast. Confident, gallery-grade poster design.',
  },
];

function line(label, value) {
  return value && String(value).trim() ? `- ${label}: ${String(value).trim()}\n` : '';
}

/**
 * Build the generation prompt for one variant.
 * imageManifest describes the images attached to the API call, in order.
 */
function buildPosterPrompt({ day, settings, preset, variantIndex, imageManifest }) {
  const info = day.info || {};
  const dayName = day.day.charAt(0).toUpperCase() + day.day.slice(1);
  const take = VARIANT_TAKES[variantIndex % VARIANT_TAKES.length];

  const attached = imageManifest.length
    ? 'ATTACHED IMAGES, IN ORDER:\n' +
      imageManifest.map((m, i) => `${i + 1}. ${m}`).join('\n') +
      '\n\n'
    : '';

  const styleBlock = preset
    ? `ART DIRECTION — "${preset.name}":\n${preset.direction}\n\n`
    : 'ART DIRECTION: Derive the art direction from the attached style reference image(s): match their palette, lighting, texture and typographic voice while keeping the brand system below.\n\n';

  const mustWords = (info.mustWords || '').trim();

  return (
    `Design a premium promotional poster for "${(settings.venueName || 'Vibration').toUpperCase()}", a live-music bar. ` +
    `This must look like the work of a top-tier poster designer: intentional composition, flawless typography, cohesive color grading.\n\n` +
    attached +
    styleBlock +
    `BRAND SYSTEM (always):\n` +
    `- Portrait poster, full-bleed artwork.\n` +
    `- Top center: the circular "V" monogram logo of the venue${imageManifest.some((m) => m.includes('logo')) ? ' — reproduce the attached logo exactly, do not redesign it —' : ' (a perforated metal disc with a large letter V),'} with the word "VIBRATION" beneath it in the poster's display style.\n` +
    `- Clear typographic hierarchy: (1) day of week, (2) the artist/event name as the dominant element, (3) genre or tagline, (4) time line near the bottom.\n` +
    `- Keep every text element inside comfortable margins and inside the central 4:5 safe area (top and bottom 10% of the canvas must stay free of critical text) so the poster survives Instagram cropping.\n` +
    `- Typography must be immaculate: real letterforms, perfect spelling, consistent kerning, no gibberish, no fake glyphs, no watermark, no borders cut off.\n\n` +
    `POSTER COPY — render this text EXACTLY, letter-for-letter, and nothing else:\n` +
    `- Venue wordmark: "VIBRATION"\n` +
    line('Day line', dayName) +
    line('Headline (dominant)', info.artistName) +
    line('Genre / tagline line', info.genres) +
    line('Time line', info.showTime) +
    (mustWords ? `- Must also appear on the poster, verbatim: "${mustWords}"\n` : '') +
    `\n` +
    (imageManifest.some((m) => m.startsWith('PERFORMER'))
      ? `HERO SUBJECT: Use the attached performer photo(s) as the hero of the poster. Preserve their exact facial identity, hair, skin tone and distinguishing features — a person who knows them must recognize them instantly. Integrate them into the scene with matching lighting, grade and grain; re-light and re-pose subtly if the composition needs it, never change who they are.\n\n`
      : `HERO SUBJECT: No performer photo is attached — build the hero from the scene itself (instruments, stage, atmosphere) as described by the art direction and event details.\n\n`) +
    (info.special || info.notes
      ? `EVENT CONTEXT (for mood and supporting visual details, not extra text): ${[info.special, info.notes].filter(Boolean).join(' — ')}\n\n`
      : '') +
    `${take.twist}\n\n` +
    `Final check: exact spelling of every word above, believable premium design, no additional text anywhere.`
  );
}

module.exports = { STYLE_PRESETS, VARIANT_TAKES, buildPosterPrompt };
