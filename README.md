# The Gametime Guru · Apple Podcasts Chart Tracker

Checks every Apple Podcasts storefront (~175 countries) once a day:

- **Rank** of The Gametime Guru (Apple ID `1195653965`) in the **Basketball Top 200**
- **Star rating + rating count** in each country

Then it saves the history, refreshes the dashboard (GitHub Pages), and emails a daily report.

## Setup (one time, ~5 minutes)

1. **Gmail app password** — go to https://myaccount.google.com/apppasswords (needs 2-Step Verification on),
   create one named "Chart tracker", copy the 16-character password.
2. **Add secrets** — in this repo: Settings → Secrets and variables → Actions → New repository secret:
   - `GMAIL_USER` = `shane.g.larson@gmail.com`
   - `GMAIL_APP_PASSWORD` = the 16-character password
   - `REPORT_TO` = `shane.g.larson@gmail.com` (comma-separate to add more people)
3. **Turn on the dashboard** — Settings → Pages → Source: *Deploy from a branch* → Branch `main`, folder `/docs` → Save.
   Dashboard: https://shaneglarson.github.io/podcast-charts/
4. **First run** — Actions tab → *Daily chart check* → *Run workflow*. After that it runs every morning automatically.

## Changing things

Edit `config.json`:

- Track more charts: add e.g. `{ "genre_id": "1545", "name": "Sports" }` or `{ "genre_id": "1547", "name": "Football" }`
- `priority_countries`: countries pinned in their own section of the email
- `track_ratings`: set to `false` to skip ratings

Change the send time in `.github/workflows/daily.yml` (`cron` is in UTC).

## Notes

- Apple only publishes the Top 200 of each chart, so outside that a country shows as "not charting."
- GitHub may start scheduled runs 5–30 minutes late at busy times. GitHub pauses schedules after 60 days with no repo activity; the daily data commit counts as activity, so it keeps itself alive.
