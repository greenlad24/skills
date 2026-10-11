# Run Thai TikTok Studio as a website (free)

**Recommended: Oracle Cloud "Always Free".** You get a server that is on 24/7 with:
- 4 CPU cores (ARM)
- 24 GB RAM
- 200 GB disk
- 10 TB of traffic per month

It's free forever, not a trial. It is faster than a 2015 MacBook, and it runs Claude Code, so the "Your Claude account" mode works there even though your Mac is on macOS 12.

> Why not Netlify? Netlify only hosts static pages and short functions that run for seconds, with no disk. Video rendering takes minutes and needs gigabytes of storage.

The site is protected by a password you choose. Your Claude token and your videos stay on your server.

---

## 1. Create a free Oracle Cloud account (about 10 minutes)
1. Go to **https://www.oracle.com/cloud/free/** and click *Start for free*.
2. **Home region:** choose **Singapore** (closest to Thailand). This can't be changed later.
3. A credit/debit card is required **for identity verification only**. Always Free resources are never charged. Don't click "Upgrade to paid".

## 2. Create the server
1. In the Oracle console, go to **Compute → Instances → Create instance**.
2. Under **Image**, click *Change image* and pick **Canonical Ubuntu 24.04** (22.04 also works).
3. Under **Shape**, click *Change shape*, then **Ampere** → `VM.Standard.A1.Flex`. Set **4 OCPU** and **24 GB** memory. It shows the *Always Free-eligible* label.
   - If you get "Out of capacity", try another *Availability domain*, try 2 OCPU / 12 GB, or try again later.
4. Under **Boot volume**, tick *Specify a custom size* and enter **200 GB**.
5. Under **Add SSH keys**, choose *Generate a key pair for me* and **download the private key**.
6. Click **Create** and wait until it's *Running*. Copy the **Public IP address**.

## 3. Open the web ports (once)
1. On the instance page, click the **Subnet** link, then the **Default Security List**.
2. Click **Add Ingress Rules** and add two rules:
   - Source `0.0.0.0/0`, TCP, destination port **80**
   - Source `0.0.0.0/0`, TCP, destination port **443**

## 4. Install the app (one command)
1. Open **Cloud Shell**: the `>_` icon at the top right of the Oracle console.
2. Upload your private key (⚙ menu → Upload), then connect:
   ```bash
   chmod 600 ssh-key-*.key
   ssh -i ssh-key-*.key ubuntu@YOUR_PUBLIC_IP
   ```
3. On the server, download and run the setup script:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/greenlad24/skills/claude/wizardly-thompson-w6jjr8/thai-tiktok-studio/deploy/oracle-setup.sh
   sudo bash oracle-setup.sh
   ```
4. Choose a website password when it asks. Setup takes about 5–10 minutes.
5. At the end it prints your address, e.g. **https://152-67-1-2.sslip.io**. This is a free address with real HTTPS, so no domain is needed.

> **If the GitHub repo is private:** create a GitHub *fine-grained token* with read access to the repo, then run
> `sudo REPO_URL=https://YOUR_TOKEN@github.com/greenlad24/skills.git bash oracle-setup.sh`.
> To download the script itself, use `git clone` with the same URL instead of `curl`.

## 5. Connect your Claude account (once a year)
1. On the server, run:
   ```bash
   sudo -u studio /home/studio/.local/bin/claude setup-token
   ```
2. Open the link it shows, approve, and copy the token. It starts with `sk-ant-oat01-`.
3. On the website, go to **⚙ Settings → AI → "Your Claude account"**, paste the token and save.

The token lasts one year. Repeat this step when it expires; the app will tell you.

## 6. Use it
- Open your address on the Mac, a phone or any computer, and log in.
- Upload clips and narration straight from your phone's browser. Finished videos can be downloaded to the phone and posted.
- 200 GB holds a lot of footage. Delete old products in the app when you're done with them.

## Updating to the newest version
```bash
sudo bash /home/studio/app/thai-tiktok-studio/deploy/update.sh
```

## Useful commands
| What | Command |
|---|---|
| Is it running? | `systemctl status thai-tiktok-studio` |
| Live log | `journalctl -u thai-tiktok-studio -f` |
| Restart | `sudo systemctl restart thai-tiktok-studio` |
| Change password | edit `/etc/thai-tiktok-studio.env`, then restart |
| Disk space | `df -h /` |

---

## Alternative: Hugging Face Spaces (easiest, but storage is temporary)
A *Docker* Space on the free CPU tier (2 vCPU, 16 GB RAM) can run the included `Dockerfile`:
1. Create a new Space, choose **Docker**, and set it to **Private**.
2. Push this folder to the Space.
3. Add a secret **`TTS_STUDIO_PASSWORD`**.

**Caveat:** the free disk is wiped whenever the Space restarts or sleeps (after about 48 h idle). Download finished videos right away. For lasting storage, use Oracle.

---

## สรุปภาษาไทย (Thai summary)
- **Oracle Cloud Always Free:** เซิร์ฟเวอร์ฟรีตลอดไป · CPU 4 คอร์ · RAM 24 GB · พื้นที่ 200 GB
- สมัครที่ oracle.com/cloud/free (เลือกภูมิภาค **Singapore**) → สร้างเครื่อง Ubuntu แบบ Ampere 4 OCPU / 24 GB / ดิสก์ 200 GB → เปิดพอร์ต 80 และ 443
- เข้าเครื่องแล้วรัน `sudo bash oracle-setup.sh` ตั้งรหัสผ่าน รอประมาณ 10 นาที จะได้ลิงก์เว็บ https://…sslip.io
- เชื่อมบัญชี Claude: รัน `claude setup-token` บนเซิร์ฟเวอร์ แล้ววางโทเค็นที่ ⚙ Settings
- ใช้งานได้จากมือถือและคอมทุกเครื่อง อัปโหลดคลิปจากมือถือได้เลย
