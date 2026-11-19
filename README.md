# Channel Growth

A local dashboard for exploring how individual YouTube videos contribute to a channel's growth over time. It pulls daily views, watch time, and subscriber activity from the **YouTube APIs**, builds cumulative charts per video, and serves an interactive web dashboard with filters for **All / Videos / Shorts**.

A browser-only analytics dashboard for viewing private analytics for a YouTube channel. Any Google account that manages a channel can connect it and see views, watch time, subscriber changes, and top videos for that channel. There is no backend: analytics are fetched directly from Google into the browser tab, and the site stores nothing on a server.

Live site: <https://channelgrowth.me/>

<img width="1586" height="1296" alt="image" src="https://github.com/user-attachments/assets/6afaacb9-aff7-461e-bbe3-d499f37d47a9" />

<img width="1124" height="1126" alt="image" src="https://github.com/user-attachments/assets/2470fc02-2bff-45b2-9438-8e73561cedb8" />

<img width="1104" height="677" alt="image" src="https://github.com/user-attachments/assets/bf00709c-388a-4e27-be6c-1dfc3860d4a4" />

## Problem Statement

YouTube Studio shows aggregate channel numbers, but it does not clearly answer **what is driving growth over time**. This project was built to answer questions like:

- Which individual videos contribute most to cumulative views and watch time?
- Are **Shorts** or **long-form videos** driving growth?
- How is the channel's subscriber count growing, and when do spikes happen?
- Can all of this be explored locally, with filters and live data?

## How it works

1. The site is a static app hosted on GitHub Pages.
2. The user clicks **Continue with Google**. Google Identity Services returns a short-lived OAuth access token (about one hour, no refresh token) using read-only scopes.
3. The browser calls the YouTube Analytics API and YouTube Data API v3 directly with that token and renders the results with Chart.js.
4. The token is kept in the tab's `sessionStorage`. It is cleared on sign-out, expiry, or tab close. The site operator never sees or stores it.
5. No analytics data is written to disk or sent to the site operator. CSV and PNG exports happen locally in the browser.

## Features

- Google sign-in with read-only access to the user's own channel (`channel==MINE`)
- Branch 2 dashboard layout with KPI cards for total views/watch time, videos tracked, days, data through, and subscribers
- Global Views/Watch time metric, All/Videos/Shorts content filter, and Top 5/10/15/20 video selector
- Regular videos reported as `UNSPECIFIED` by Google are included in the Videos filter
- Per-video cumulative views or watch time with an "Other videos" residual line
- Channel total cumulative views or watch time
- Daily views or watch time
- Subscriber total over time, estimated from daily gains/losses, anchored to the current count, and clamped at zero
- Daily subscribers gained/lost chart
- Top-videos sidebar with type badges, IDs, totals, and progress bars
- PNG download for every chart
- Start/end date controls; the initial range starts at the channel creation date
- CSV export of the current range
- Channel avatar and name in the header, with sign-out; logo/title refreshes the dashboard
- Clear loading, empty, quota, permission, and expired-session states

## Google Cloud setup (one time)

Use the same Cloud project for the site and the optional local scripts.

1. Enable **YouTube Analytics API** and **YouTube Data API v3** in [Google Cloud Console](https://console.cloud.google.com/) under **APIs & Services > Library**.
2. Configure the **Google Auth Platform / OAuth consent screen** as **External**.
3. Add the two read-only scopes under **Data access**:
   - `https://www.googleapis.com/auth/yt-analytics.readonly`
   - `https://www.googleapis.com/auth/youtube.readonly`
4. Create an OAuth client ID of type **Web application**:
   - Authorized JavaScript origin: `https://channelgrowth.me`
   - Authorized JavaScript origin for the `www` host: `https://www.channelgrowth.me`
   - Authorized JavaScript origin for local testing: `http://localhost:8080`
5. Copy the client ID (it ends in `.apps.googleusercontent.com`) into `web/config.js`:

```js
window.CHANNEL_GROWTH_CONFIG = {
  clientId: "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com",
  scopes: [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly"
  ],
  siteUrl: "https://channelgrowth.me/"
};
```

The client ID is public and is expected to be visible in the page. Do not put a client secret in this file or anywhere in the repository.

6. Under **Branding**, set:
   - App name: `Channel Growth`
   - Authorized domain: `channelgrowth.me`
   - Homepage: `https://channelgrowth.me/`
   - Privacy policy: `https://channelgrowth.me/privacy.html`
   - Terms of service: `https://channelgrowth.me/terms.html`
7. After the site is live and the branding URLs return `200`, publish the app under **Audience > Publish app**.

While the app is in **Testing**, only listed test users can connect, and Google shows an unverified-app warning for sensitive scopes. Publishing removes that warning for approved use. Verification is required for broader public use.

The original Desktop OAuth client and `secrets/` credentials are only for the optional local Python scripts. They are not used by the deployed site.

## Hosting on GitHub Pages

The workflow at `.github/workflows/pages.yml` builds the app shell and deploys `dist/` on every push to `main`, or when run manually from **Actions > Build and deploy dashboard > Run workflow**. There is no scheduled data job because data is fetched live in each visitor's browser.

### Custom domain

1. In Namecheap (or your DNS provider), set:
   - `A` records for `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - `CNAME` for `www`: `harinduvihan.github.io.`
2. In GitHub, open **Settings > Pages**, set the custom domain to `channelgrowth.me`, and enable **Enforce HTTPS** once the certificate is ready.
3. Verify the domain in [Google Search Console](https://search.google.com/search-console) as a **Domain** property using the DNS TXT record. Google OAuth branding requires a verified domain property.

`web/CNAME` contains `channelgrowth.me` and is copied into the build. The build also honors a `CUSTOM_DOMAIN` environment variable if you need to override it.

## Local development

Serve the site over HTTP rather than opening the HTML file directly; OAuth authorized origins do not work with `file://`.

The built site has the correct `index.html` entry point, so building first is the simplest option:

```bash
python scripts/build_static.py
python -m http.server 8080 --directory dist
```

Open <http://localhost:8080>. Add `http://localhost:8080` as an authorized JavaScript origin on the Web OAuth client. `http://127.0.0.1:8080` may be treated as a different origin, so use the same host you added.

To preview unbuilt source from `web/`, open <http://localhost:8080/dashboard.html> instead of the directory root.

## Build the static site

```bash
python scripts/build_static.py
```

The build cleans `dist/` and copies:

- `dashboard.html` -> `index.html` and `dashboard.html`
- `privacy.html`, `terms.html`, `config.js`
- `vendor/chart.umd.min.js` and its license
- `.nojekyll`
- `CNAME` when a domain is configured

It does **not** write `data.json` or include cached analytics. If `web/config.js` still contains the placeholder client ID, the build stops with an error; set `ALLOW_PLACEHOLDER=1` to build a preview anyway:

```powershell
$env:ALLOW_PLACEHOLDER = "1"
python scripts/build_static.py
```

Then preview the build:

```bash
python -m http.server 8080 --directory dist
```

## API usage

Each dashboard load makes a mix of channel-level and bounded per-video requests:

- `reports.query` with `dimensions=day` for daily views, watch minutes, subscribers gained, and subscribers lost
- `reports.query` with `dimensions=day,creatorContentType` for content-filter totals
- `reports.query` for top videos: first tries `dimensions=video,creatorContentType`; if unsupported, it tries a `creatorContentType==SHORTS|VIDEO_ON_DEMAND` filter, then falls back to an unfiltered top 2,000 ranking classified by a playback-details query (`dimensions=video,creatorContentType` plus `filters=video==ID,...`)
- One paginated `reports.query` per selected top video with `dimensions=day` and `filters=video==VIDEO_ID` for cumulative history
- `videos.list` for titles of the selected top videos
- `channels.list?mine=true` for the channel name, avatar, and current subscriber count

Per-video history is deliberately bounded to the selected top 5/10/15/20 videos rather than fanning out over every upload. Larger Top-N values, long date ranges, and changing the metric/type controls use additional API quota. Successful per-video daily responses are cached for the current date range while the tab is open. If the top-videos content-type report is unsupported, the app first tries a per-type top-videos filter, then classifies up to 2,000 ranked videos via a playback-details query (or per-video fallback) before showing a notice. Google may report regular videos as `UNSPECIFIED`; those are treated as `VIDEO_ON_DEMAND` for the Videos filter.

YouTube Analytics data typically lags one to two days. All visitors share the Cloud project's API quota; there is no server-side rate limiting because there is no server. If the project runs out of quota, the app shows a quota message and users can retry later.

## Legacy local tooling

The original per-video Python pipeline is still in the repository for local exploration and is not part of the deployed site:

- `scripts/per_video_growth.py` fetches per-video daily data and builds Matplotlib charts.
- `scripts/dashboard_server.py` serves a local dashboard from cached data with `/api/data` and `/api/export.csv`.
- `scripts/plot_growth.py` draws a channel-total cumulative chart from a Studio CSV export.
- `secrets/client_secret.json` and `secrets/token.json` are Desktop OAuth credentials for those local scripts and are git-ignored.

Install Python dependencies only if you use these scripts:

```bash
pip install -r requirements.txt
```

The GitHub Actions workflow no longer uses `GOOGLE_CLIENT_SECRET`, `GOOGLE_TOKEN`, or `CUSTOM_DOMAIN` repository secrets/variables. They can be removed from repository settings.

## Project structure

```text
.
├── .github/
│   └── workflows/pages.yml    # builds the app shell and deploys to Pages
├── scripts/
│   ├── build_static.py        # copies web/ to dist/ (no data)
│   ├── dashboard_server.py    # legacy local server
│   ├── per_video_growth.py    # legacy local per-video fetcher/charts
│   └── plot_growth.py         # legacy channel-total chart
├── web/
│   ├── dashboard.html         # sign-in, live API fetches, charts, top videos
│   ├── config.js              # public Web OAuth client ID + scopes
│   ├── privacy.html           # privacy policy
│   ├── terms.html             # terms of service
│   ├── CNAME                  # channelgrowth.me
│   └── vendor/
│       ├── chart.umd.min.js   # Chart.js 4.4.1 (MIT)
│       └── CHARTJS-LICENSE.md
├── data/                      # legacy local caches (git-ignored)
├── output/                    # legacy chart output (git-ignored)
├── dist/                      # generated static site (git-ignored)
├── secrets/                   # local OAuth credentials (git-ignored)
├── requirements.txt
└── .gitignore
```

## Troubleshooting

- **"This deployment is not configured yet"** — `web/config.js` still has the placeholder client ID. Create the Web OAuth client and paste its ID.
- **`redirect_uri_mismatch` or `origin_mismatch`** — add the exact origin (`https://channelgrowth.me`, `https://www.channelgrowth.me`, or `http://localhost:8080`) to the Web OAuth client's authorized JavaScript origins.
- **"Access blocked" / unverified app** — add your Google account as a test user while the app is in Testing, or publish the app after branding and domain verification.
- **No channel analytics** — use an account that owns or manages the channel, and confirm the YouTube Analytics API is enabled for the project.
- **Videos filter looks empty but Shorts works** — Google may label regular videos as `UNSPECIFIED`; the app treats those as Videos. If the notice still appears, check `window.__lastTypeError` in DevTools.
- **Top videos show IDs only** — the YouTube Data API v3 may be disabled or the quota may be exhausted; titles and thumbnails fall back to IDs and static thumbnail URLs.
- **No recent days** — normal. YouTube Analytics usually reports with a one- to two-day delay.
- **Session expired** — sign in again. Browser token-client sessions last about an hour and do not use refresh tokens.
- **Charts do not render** — confirm `web/vendor/chart.umd.min.js` was copied into `dist/vendor/` and that JavaScript is enabled.

## Privacy and terms

The deployed policy pages are `web/privacy.html` and `web/terms.html`. They describe browser-only processing, the two read-only scopes, `sessionStorage` token handling, local CSV export, and Google API Limited Use.

## License

No license has been specified for this project. Chart.js is distributed under the MIT License; see `web/vendor/CHARTJS-LICENSE.md`.
