# Thai TikTok Shop Motion-Design Framework (v1)

**What the editor does.** It renders every element below itself, in code, using CapCut-like timings. The plan only says WHICH element, WHEN, WHERE, and WHAT TEXT. Keep all text inside the safe box: x 60–900, y 150–1400 of 1080x1920. TikTok's UI covers the right rail and the bottom 520 px.

## Ranked elements (rank = how common they are in viral Thai TikTok Shop videos)
| rank | overlay `type` | use it for | timing rule | notes |
|---|---|---|---|---|
| 1 | *(captions)* | every spoken line; each beat's `captions` chunks | automatic, synced to speech | ≤18 Thai characters per chunk, 0–2 `highlight` keywords (numbers, prices, benefits) |
| 2 | hook_title | the scroll-stopper text in the first beat | at 0, dur 2.5–3.5 | 3–8 Thai words; it can differ from the spoken hook (a curiosity/pain/price statement); top position |
| 3 | *(effect: punch_in)* | emphasis on key words and cuts | about every 2–4 s | use `punch_in` / `punch_shake` on price or shock beats |
| 4 | keyword_pop | a single shock word or phrase: "ถูกมาก!!" ("so cheap!!"), "นุ่มเด้ง" ("soft and bouncy"), "ปัง" ("wow") | 0.8–1.5 s | center or upper; pair with `boom` or `pop` sfx |
| 5 | cta_basket | the call to action pointing at the yellow basket (bottom-left) | final 2.5–4 s; optionally a 2 s flash mid-video | text like "กดตะกร้าเลย" ("tap the basket"); pair with `ding`/`cash` |
| 6 | price_tag | price reveal: `text` = new price digits, `sub_text` = old price digits | 2–4 s when the price is spoken | stamp animation; pair with `cash` + `punch_shake` |
| 6 | discount_badge | "ลด 50%" ("50% off"), "1 แถม 1" ("buy 1 get 1"), "ส่งฟรี" ("free shipping") starburst | 2–3 s | upper right; only if true |
| 7 | emoji_sticker | emotion: 😱🔥💯✨👍❤️ | 0.8–1.5 s | near the face or product, using the corner positions |
| 8 | arrow / circle_highlight | point at a product detail (`target_x`, `target_y` 0–1) | 1–2 s | `position: target` |
| 9 | checklist | 2–5 benefits with ✅, staggered | 3–6 s | `items` (each ≤ 14 characters); center_left |
| 10 | before_after_labels | "ก่อน" / "หลัง" ("before" / "after") tags | the whole before or after beat | `text` = "ก่อน" or "หลัง" |
| 11 | *(effect: flash)* | reveals, transitions | at the beat start | pair with `shutter` or `whoosh` |
| 12 | *(effect: shake)* | impact on a price or shock line | 0.3 s | |
| 13 | reaction_text | personality: "จริงดิ?!" ("for real?!"), "ของมันต้องมี" ("a must-have") | 1–1.5 s | cute rounded font; wiggles |
| 14 | speech_bubble | a short thought or quote | 1.5–3 s | |
| 14 | comment_reply | TikTok-style reply card, "ตอบกลับ @user" ("reply to @user") | first 3–5 s of the reply_to_comment format | `sub_text` = @username, `text` = the comment question |
| 15 | trust_badges | "ของแท้" ("genuine"), "มี อย." ("Thai FDA registered"), "ส่งฟรี" ("free shipping"), "เก็บเงินปลายทาง" ("cash on delivery") | 3–6 s | `items`; only true claims |
| 16 | stars_rating | social proof: `text` "4.9", `sub_text` "ขายแล้ว 10k+" ("10k+ sold") | 2–3 s | only real numbers |
| 17 | urgency_banner | "โปรวันนี้วันเดียว" ("today only") | final third | ONLY if the deal is real |
| 18 | number_badge | list formats: "1", "2", "3" + a short title in `sub_text` | start of each reason | top_left |
| 19 | lower_third | product name or model | 2–3 s at first reveal | lower_left |
| 20 | *(progress_bar)* | retention cue on long videos (40 s+) | whole video | `progress_bar: true` |
| 21 | vs_split | comparisons: `text` = left label, `sub_text` = right label | the comparison beat | |
| 22 | spec_card | dimensions and specs: `items` like "สูง: 150 ซม." ("height: 150 cm") | 3–5 s | furniture and appliances (specs did well in the dataset) |

## Density rules
- Something new on screen every **1.5–3 s**: a cut, punch-in, sticker or text.
- At most **2 overlays at once**, captions excluded. Never cover the product with text.
- About **1 sfx every 2–3 s**, synced to overlay entrances (`at` equal to the overlay's `at`).
- Hook beat: hook_title + punch_in or flash + `whoosh`/`ding`. Price beat: price_tag or discount_badge + `cash` + `punch_shake`. Last beat: cta_basket + `ding`.
- Theme by category:
  - Sale or price: sale_red_yellow
  - Beauty: beauty_pink
  - Health or supplements: trust_green
  - Gadgets: hot_orange_gold
  - Premium: clean_black_white
- Fonts:
  - kanit: the default punchy look
  - prompt: wide, clean
  - mitr / mali / itim: cute or beauty
  - chakra: tech or price
