# ABS Dunk Bot 🤦

Posts the most embarrassing **overturned ABS challenge** of the day/week to
Bluesky — the "SMH ump" call, ranked by how badly the pitch missed the zone.

A strike-zone graphic shows the pitch dot sitting clearly outside the box, with
the miss distance in inches, plus a link to the play on Baseball Savant.

---

## What it does

- **Daily** (~10am ET): finds yesterday's worst overturned challenge, posts it.
- **Weekly** (Mondays ~11am ET): finds the worst of the trailing 7 days.
- On a day with **no** overturned challenges, it posts nothing and exits quietly.

Ranking = pure miss distance (inches outside the nearest zone edge). The data
layer is structured so stakes-weighting or a "should've challenged but didn't"
post type can be added later without touching the core.

---

## One-time setup

### 1. Create the Bluesky account + app password
- Make the account yourself at bsky.app (I can't create accounts for you).
- Settings → **App Passwords** → create one. Use the **app password**, never
  your real password.

### 2. Make a new GitHub repo
- Use your normal GitHub account. A **private** repo is fine — this runs Actions,
  it's not a Pages site.
- Push these files to it.

### 3. Add repo secrets
Repo → Settings → Secrets and variables → **Actions** → New repository secret:
- `BLUESKY_HANDLE` — e.g. `abs-dunk.bsky.social`
- `BLUESKY_APP_PASSWORD` — the app password from step 1

### 4. ⚠️ Confirm the 2026 challenge columns (important, ~5 min)
The exact column names Savant uses for challenge data in 2026 couldn't be
verified offline. Before trusting auto-posts, run the inspector once:

```bash
pip install -r requirements.txt
python main.py --inspect --date 2026-05-21   # any date with games
```

It prints the challenge-related columns and the list of `description` values.
If they don't match the defaults in `fetch.py` (`CHALLENGE_FLAG_COLS`,
`CHALLENGE_RESULT_COLS`, `OVERTURN_VALUES`), adjust those lists — they're at the
top of the file and clearly labeled. This is the one place the build makes an
assumption it couldn't test.

### 5. Test before going live
```bash
python main.py --window day --date 2026-05-21 --dry-run
```
Builds the card (`card.png`) and prints the caption **without posting**. Open the
PNG, read the caption, confirm it looks right. Then drop `--dry-run` to post for
real, or just let the schedule take over.

You can also trigger manually anytime from the **Actions** tab
(workflow_dispatch) with a window choice and a dry-run toggle.

---

## Files
- `fetch.py` — pulls Statcast, finds the worst overturned call, scores miss in inches
- `graphic.py` — renders the strike-zone card (Mike's design DNA, accent `#e8234a`)
- `post.py` — composes caption, posts text+image to Bluesky
- `main.py` — orchestrates fetch → graphic → post (`--window`, `--dry-run`, `--inspect`)
- `.github/workflows/post.yml` — daily + weekly cron, plus manual trigger

---

## Known constraints (by design)
- **No broadcast clip** — zone graphic only. Auto-scraping MLB video is fragile
  and legally murky, so it's out.
- **Link goes to Savant's gamefeed** for the play, not a guaranteed mlb.com video
  URL (those aren't reliably constructable).
- **Fully automated = no human glance.** It posts whatever the data says is worst.
  On a slow day that might be a mild call. To add a review step, flip the
  workflow to `--dry-run` and post manually, or have it open a PR/issue instead.
- **First run verifies columns** (see step 4).
