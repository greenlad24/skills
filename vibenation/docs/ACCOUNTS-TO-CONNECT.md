# Accounts and keys only you can create

VibeNation is built to use these, but each one needs you to sign in or create a key. Paste every key into the server's private settings file `/root/vibenation/vibenation/.env` (never committed), or send it to Claude in the chat and Claude will put it there.

| # | What | Why | Where | What to paste |
|---|---|---|---|---|
| 1 | DigitalOcean API token | Creates and destroys the GPU show server for each show (~$0.76/h) | cloud.digitalocean.com → API → Tokens → Generate (scopes: droplet, ssh_key, reserved_ip: read+write) | `DIGITALOCEAN_TOKEN=` |
| 2 | Google OAuth client (YouTube) | Go live on @MusicLiveLove, set title/description/tags/thumbnail, read chat | console.cloud.google.com → new project "VibeNation" → enable "YouTube Data API v3" → OAuth consent screen (External, add your Google account as test user) → Credentials → OAuth client ID → Web application → redirect URI `https://app.jeeznews.com/api/oauth/youtube/callback` | `YOUTUBE_CLIENT_ID=` and `YOUTUBE_CLIENT_SECRET=` — then press "Connect YouTube" in the app |
| 3 | Custom thumbnails on YouTube | Thumbnail upload needs a verified channel | youtube.com/verify (phone verification) | nothing to paste |
| 4 | OpenAI API key | Thumbnail images (GPT Image) from a live camera frame | platform.openai.com → API keys (needs API billing; a ChatGPT plan doesn't cover the API) | `OPENAI_API_KEY=` |
| 5 | Gemini API key | The "listener" that hears the mix every few seconds (cheapest option, ~$1–2 per show) | aistudio.google.com → Get API key | `GEMINI_API_KEY=` |
| 6 | Twitch app | Multistream to Twitch | dev.twitch.tv/console/apps → Register (redirect `https://app.jeeznews.com/api/oauth/twitch/callback`) | `TWITCH_CLIENT_ID=` and `TWITCH_CLIENT_SECRET=` |
| 7 | Facebook app | Multistream to your Facebook Page | developers.facebook.com → Create app (Business) → Facebook Login + Live Video API (redirect `https://app.jeeznews.com/api/oauth/facebook/callback`) | `FACEBOOK_APP_ID=` and `FACEBOOK_APP_SECRET=` |
| 8 | TikTok LIVE stream key | Vertical stream to TikTok (needs LIVE access, ~1,000 followers) | TikTok LIVE Studio / creator tools → stream key | paste in the Go Live screen each show |
| 9 | Instagram stream key | Vertical stream to Instagram (professional account) | Instagram → Live → Streaming software → key (new key every show) | paste in the Go Live screen each show |

Only #1 is needed to test the GPU show server; #2 is needed for the first real YouTube stream. Everything else can come later.
