# Aino Money: 2-minute demo video

**The story:** Aino is an AI coach inside S-mobiili. It talks with your own transactions,
decides which data to look at, draws the chart that fits the question, and turns advice into
an experiment you can track. **Our differentiator:** real Prisma receipts, downloaded and with every
line classified into product categories, so Aino can see *what* was bought, not just *where*. All numbers come from tools that query the ledger. The model
picks the analysis and writes the explanation. It never makes up amounts.

Persona: **Sofia, 35**, saving €15,000 for an apartment deposit (synthetic data).

---

## Before recording (5 min)

1. Start the app with the AI provider on:
   ```bash
   cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
   ```
   ```bash
   cd frontend && npm run dev
   ```
   `http://localhost:5173/api/health` must show `"provider": "anthropic"`.
2. **Reset Sofia's simulated spending.** Earlier experiments change her totals:
   ```bash
   curl -X DELETE "http://localhost:8000/simulate?customer_id=DEMO-SETUKORTTI"
   ```
3. **Warm up.** Ask one question in the chat, then **refresh** the page. The first model call
   is slower, and refreshing empties the chat.
4. Use a phone viewport (Chrome DevTools → iPhone 14 Pro, 393×852). Hide the bookmarks bar.
   Zoom to 110–125% so the text is readable on video.
5. Refresh: the app opens on the **Aino Money** start screen. Tap **Sofia, 35** (top card, marked *Demo*) to land on Home with the **Aino noticed something** card.

Answers take 5–10 s. Let the first one play in real time so viewers see the live steps,
then speed up the waits 2–4× in editing.

---

## Script (2:00)

| Time | Do this | Say this (voice-over) |
| --- | --- | --- |
| **0:00–0:10** | Start on the persona screen and tap **Sofia**. The familiar S-Pankki home screen opens: bonus banner, accounts. Point to the **✦ Aino noticed something** card at the top (*€587 on everyday things in 2 weeks…*) and tap it. | “This is the S-Pankki app with Aino built in, an AI money coach that talks with your own transactions. It has already noticed something in Sofia’s last two weeks.” |
| **0:10–0:28** | The chat opens with Aino’s greeting. Tap the suggestion **✦ What kind of spender am I?** Let the live steps tick off. The **three money baskets** donut appears, then the answer. | “Watch it work. Aino picks the data it needs, sorts her spending into S-Bank’s three baskets and draws the chart. The chart is computed from her ledger, so the AI can’t invent a number.” |
| **0:28–0:42** | Tap **Koti** → **S-Tili**. The second row is a **Prisma Herttoniemi €27.15** purchase with **🧾 Itemised receipt**. Tap **View itemised receipt**: *10 items · classified into 10 product categories*. | “Here’s what makes us different. A bank only sees ‘€27 at Prisma’. We downloaded real Prisma receipts and classified every line, from chocolate to kitchen roll.” |
| **0:42–1:02** | Tap **✦ See more: Aino’s insight on this receipt**. The receipt card appears at once: a colour bar of what she bought, then each category with what she spent this month, a marker for her usual, and an evaluation badge (*On your usual pace*, *45% above usual*…). Tap one category to show its items. Aino’s explanation streams in below. | “Aino groups the receipt into everyday categories. For each one it checks this month against her usual and gives a verdict. Then it explains what stands out, what’s going well, and one small, kind idea.” |
| **1:02–1:12** | Tap the follow-up **Show all my grocery categories this month**. If it isn’t offered, type it. The chart shows all grocery categories, this month vs usual. | “One more tap and she sees every grocery category this month, straight from her receipts.” |
| **1:12–1:32** | Type **What if I ate out 20% less? How would that help my apartment deposit?** Show the chart *Actual vs 20% less* with **Could free up €85/mo · €1,020/yr**. | “She can ask ‘what if’ in plain language. Aino runs it on her real dining history and connects it to her apartment goal. That’s about a thousand euros a year.” |
| **1:32–1:50** | Tap **Try 20% less on restaurants for 14 days**. Goals opens with **Aino’s suggested experiment** prefilled → **Start this experiment** → **Fast-forward 7 days**. | “Advice becomes a two-week experiment with a daily budget. We fast-forward a week. She’s on track.” |
| **1:50–2:00** | Scroll back in the chat and open **How Aino worked this out**. End on the steps list. | “Every answer shows how it was worked out. Aino reads her data, never moves money, and helps her save for what matters.” |

## Key messages to land

- **Conversational, not a dashboard:** you ask in your own words and get a chart chosen for that question (MyData spirit).
- **Agentic and transparent:** the live steps show which data Aino checks. **How Aino worked this out** keeps the record.
- **Receipts are the differentiator:** real Prisma receipts, every line classified into product categories and grouped (fruit & veg, snacks & sweets, household…). Each group is evaluated against the user's usual for the same point in the month.
- **Grounded:** charts and amounts come from deterministic tools over the user's ledger, not from the language model.
- **Pedagogy:** the three baskets, peer benchmarks, what-if simulations and safe-to-spend.
- **From insight to action:** suggestion → prefilled experiment → progress → back to the coach.

## Alternates if something goes wrong

- **A slow answer:** cut the wait in editing. Each step appears live, so the screen never looks frozen.
- **A different follow-up:** type the question from the script. All of them are free-form.
- **Cut for time, still worth showing:** the peers follow-up (*Am I spending more than people my age?*)
  and **✦ Ask Aino how it’s going** on the running experiment.
- **Shortcut:** **✦ Ask Aino about this purchase** on any row opens the same AI flow. Receipt purchases show
  the receipt card; other purchases get a category chart and a comparison with similar purchases.
- **A different receipt:** the Nov 2 Prisma receipt (17 items) flags **Extras** (yarn) as 510% above
  usual, which shows a "slips through your fingers" verdict.
- **Extra B-roll (MyData):** type **Show my taxi spending over the last 6 months** to show that
  you can ask for any view, not only the charts the bank picked.
- **No AI provider:** the suggestion buttons fall back to the built-in coach answers
  (spending split, weekly budget, dining what-if). Free-form chat and live steps need the provider.
