# Handoff: create the VibeNation DigitalOcean API token

You are Claude in Chrome, working in the user's DigitalOcean account (already logged in).
Your job: create ONE personal access token with only the permissions VibeNation needs, then leave it on screen for the user to copy. You never handle the token value yourself.

## Hard rules
- Never copy, type, paste, repeat or summarise the token value: not in chat, not in another tab or website, not in a file. Once it appears on screen, stop and hand over to the user.
- Do NOT create droplets, firewalls, Spaces, databases or anything else. One token only.
- Do NOT open, view or change billing or payment details.
- Do NOT delete or regenerate existing tokens. If a token named `vibenation-build` already exists, stop and ask the user what to do.
- If a scope listed below is missing or named differently, stop and report what you see; don't guess a wider scope. Never pick **Full Access**.

## Steps
1. Go to https://cloud.digitalocean.com/account/api/tokens (or **API** in the left menu → **Tokens** tab).
2. Click **Generate New Token**.
3. **Token name:** `vibenation-build`
4. **Expiration:** **1 year**.
5. **Scopes:** choose **Custom Scopes**, then tick only:
   - **droplet**: create, read, delete
   - **ssh_key**: create, read
   - **sizes**: read
   - **regions**: read
   - **tag**: create, read

   DigitalOcean may add the scopes these depend on automatically (for example `image: read`, `vpc: read`). Accept them, and note which ones it added.
6. STOP before clicking **Generate Token** and report to the user:
   - name, expiration,
   - the full list of scopes now ticked (including any that were added automatically).

   Wait for the user to say "generate it", then click **Generate Token**.
7. The token appears once, in a green box. **Do not copy or read it out.** Tell the user:
   > "Your token is on screen now. Click the copy icon next to it yourself, then paste it into your server using the command in the handoff (step 8). DigitalOcean will never show it again, so do this before leaving the page."
8. Show the user this command to run in their SSH window (it hides what they paste and saves it privately, readable only by `vibe`):
   ```
   sudo -iu vibe bash -c 'read -rsp "Paste the DigitalOcean token, then Enter: " t; echo; f=~/vibenation/vibenation/.env; sed -i "/^DIGITALOCEAN_TOKEN=/d" "$f"; printf "DIGITALOCEAN_TOKEN=%s\n" "$t" >> "$f"; chmod 600 "$f"; echo Saved.'
   ```
   Then tell the user to tell Claude on the build server: "the DigitalOcean token is in .env".

## Context (for your understanding only)
VibeNation's build server (`vibenation-build`) uses this token to create a GPU show server (RTX 4000 Ada, TOR1, about $0.76/hour) for each show and to destroy it afterwards (`infra/showserver/showserver.py`). It only creates and deletes droplets tagged `vibenation-show`, registers its own SSH key, and reads sizes and regions to check the price. Nothing is created when the token is made; the first test server is started later, after the user approves the cost.
