# Handoff: create the Google sign-in for YouTube (VibeNation)

You are Claude in Chrome, in the user's Google account (already logged in, the account that owns the YouTube channel @MusicLiveLove).
Your job: create a Google Cloud OAuth client so VibeNation can go live on the channel. Then let the user copy the Client ID and Client secret themselves.

## Hard rules
- Never copy, type, repeat or summarise the **Client secret**, in chat or anywhere else. When it's on screen, stop and hand over to the user. (The Client ID is not secret, but let the user copy both.)
- Do NOT enable billing, buy anything, or touch any other project, API or setting.
- Do NOT click **Publish app**. Leave the app in **Testing**.
- Do NOT delete or change existing projects or OAuth clients. If a project named `VibeNation` already exists, use it and tell the user.
- Never mention any location in any field.
- If a screen differs from these steps (Google renames menus often), describe what you see and pick the obvious equivalent. If unsure, stop and ask.

## Steps
1. Go to https://console.cloud.google.com/. Use the project picker at the top → **New project** → name `VibeNation` → **Create**. Select it.
2. **Enable the API:** https://console.cloud.google.com/apis/library/youtube.googleapis.com → **Enable** (YouTube Data API v3).
3. **Consent screen:** go to **Google Auth Platform** (or **APIs & Services → OAuth consent screen**) → **Get started**:
   - App name: `VibeNation`
   - User support email: the user's email (pick from the list)
   - Audience: **External**
   - Contact email: the same email
   - Agree to the policy → **Create**.
4. **Test users:** under **Audience** → **Test users** → **Add users** → add the Google account email that owns the YouTube channel → **Save**. (Ask the user which email if unsure. In Testing only test users can sign in.)
5. **Client:** **Clients** (or **Credentials → Create credentials → OAuth client ID**) → **Create client**:
   - Application type: **Web application**
   - Name: `VibeNation web`
   - **Authorized redirect URIs → Add URI:** `https://app.jeeznews.com/api/oauth/youtube/callback` (exactly this, no trailing slash)
   - **Create**.
6. A box shows the **Client ID** and **Client secret**. STOP. Tell the user:
   > "Your Google sign-in is created. Copy the Client ID and the Client secret yourself (use the copy icons; if there's a Download JSON option, that works too). Then in VibeNation open **Keys** and paste the Client ID into 'YouTube — Client ID' and press Save, then the Client secret into 'YouTube — Client secret' and press Save. Both get tested. Then go to **Go Live** and press **Connect YouTube**."
7. **Check live streaming is switched on for the channel** (it can take 24 hours to activate the first time, which would block tonight):
   open https://studio.youtube.com → **Create** (camera icon) → **Go live**. Report exactly what it shows:
   - the live control room / stream settings = ✅ ready;
   - "Live streaming is available in 24 hours" or a phone verification request = ⚠️ tell the user right away (verification needs their phone).
   Do not start a stream, change stream settings or copy the stream key.

## Context (for your understanding only)
VibeNation is a web app that runs the band's live show. With this sign-in it creates the YouTube broadcast, sets the title, description, tags and thumbnail, and starts and ends the stream. Unverified apps in Testing show a "Google hasn't verified this app" warning when the user connects. That's expected for their own app: click **Continue**. Refresh tokens in Testing expire after 7 days, so they reconnect weekly until the app is published (later).
