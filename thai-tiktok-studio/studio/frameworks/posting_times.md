# When to post (Thai TikTok Shop, Bangkok time)
> **In use:** the creator chose 18:00 as the daily default (extra posts 12:15 and 21:00). The research below is kept for reference.

Built into `studio/scheduler.py` (`SLOTS`). Evidence was gathered on 2026-10-11:
- **BigSeller 2025.** Weekdays: 06–09, 12:00–13:30, 18–21. Weekends: 08–10, 12–14, 17–20. https://www.bigseller.com/blog/articleDetails/2828/best-times-tiktok-2025.htm
- **Southern Whale 2026.** Thai TikTok Shop buying peaks are 12:00–13:30 (lunch) and 19:30–22:30 (before bed). https://southernwhale.com/blog/best-time-to-post-tiktok-2026/
- **Everyday Marketing.** 18–22 is strongest; Tue–Thu are the most consistent days. https://everydaymarketing.co/
- **Primal.** 20:00–21:00 is the core slot; Tue–Thu are the best days. https://www.primal.co.th/th/social/time-to-post-on-tiktok/
- **TikTok Thailand.** Live is most popular 20:00–24:00. https://www.naewna.com/business/916768
- **Buffer, 11.4M posts.** Posting more often gives more views per post: 2–5 a week gives +17%, 6–10 gives +29%, and 11+ gives +34%. https://buffer.com/resources/how-often-should-you-post-on-tiktok/

| Day | #1 | #2 | #3 |
|---|---|---|---|
| Mon | 20:00 | 12:15 | 18:30 |
| Tue | 20:00 | 12:15 | 18:30 |
| Wed | 20:00 | 12:15 | 21:00 |
| Thu | 20:00 | 12:15 | 07:30 |
| Fri | 20:30 | 12:15 | 18:30 |
| Sat | 19:00 | 10:00 | 13:00 |
| Sun | 20:00 | 10:00 | 13:00 |

How the scheduler uses this:
- **1 post a day** uses slot #1, **2 a day** uses #1 and #2, and **3 a day** uses all three.
- Posts are at least 3 hours apart.
- An A/B version of the same video waits at least 2 days.
- After 2–4 weeks, your own TikTok Analytics (follower activity) should beat this table.

Caption rules:
- The hook comes first. Put the product name and category words near the start, because TikTok's search reads them.
- Keep it to about 150 characters or less.
- Use one call to action that points to the basket (ตะกร้า).
- Never include prices.
- Use 3–5 hashtags: 1–2 broad, 1–2 niche, and 1 product tag.
- Avoid #นายหน้า tags, which reach other affiliates rather than buyers.
