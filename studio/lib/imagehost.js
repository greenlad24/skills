// Free public hosting for the finished posters — needed because Buffer (and
// Instagram itself) fetch images from a URL rather than accepting uploads
// from a local app. Uses a free Cloudinary account with an UNSIGNED upload
// preset, so only two non-secret values are required (cloud name + preset).
//
// Setup (one time, free, no card):
//   1. Create an account at https://cloudinary.com
//   2. Settings → Upload → Upload presets → Add upload preset
//      → Signing Mode: "Unsigned" → Save; note the preset name
//   3. Put your cloud name + preset name in the app's Settings.

/** file: {buffer, mime, name}. Returns a public https URL. */
async function uploadPublicImage(settings, file) {
  const cloud = (settings.cloudinaryCloudName || '').trim();
  const preset = (settings.cloudinaryUploadPreset || '').trim();
  if (!cloud || !preset) {
    throw new Error(
      'Image hosting is not configured — Buffer needs a public image URL. ' +
      'Add your Cloudinary cloud name + unsigned upload preset in Settings (free account, see README).'
    );
  }

  const form = new FormData();
  form.append('file', `data:${file.mime};base64,${file.buffer.toString('base64')}`);
  form.append('upload_preset', preset);

  const res = await fetch(`https://api.cloudinary.com/v1_1/${encodeURIComponent(cloud)}/image/upload`, {
    method: 'POST',
    body: form,
  });
  const json = await res.json().catch(() => null);
  if (!res.ok || !json?.secure_url) {
    throw new Error(`Cloudinary upload failed: ${json?.error?.message || `HTTP ${res.status}`}`);
  }
  return json.secure_url;
}

module.exports = { uploadPublicImage };
