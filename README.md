# Custom YouTube Dashboard

A local dashboard for exploring how individual YouTube videos contribute to a channel's growth over time. It pulls daily views, watch time, and subscriber activity from the **YouTube APIs**, builds cumulative charts per video, and serves an interactive web dashboard with filters for **All / Videos / Shorts**.

## Problem Statement

YouTube Studio shows aggregate channel numbers, but it does not clearly answer **what is driving growth over time**. This project was built to answer questions like:

- Which individual videos contribute most to cumulative views and watch time?
- Are **Shorts** or **long-form videos** driving growth?
- How is the channel's subscriber count growing, and when do spikes happen?
- Can all of this be explored locally, with filters and live data?

### The obstacle faced

- The Analytics API rejects `dimensions=day,video`, and `dimensions=video` alone. Per-video data only works by querying **one video at a time** with `filters=video==<id>` and `dimensions=day,creatorContentType`.
- `creatorContentType` is what makes it possible to classify each video as `shorts` or `videoOnDemand`.
- Enumerating uploads **including Shorts** requires the **YouTube Data API v3**. Without it, the fallback is the Studio `Table data.csv`, which only contains long-form videos.
- The Analytics API lags about **2 days**, so recent data is always slightly behind.
- "Watch time" is Google's `estimatedMinutesWatched` (the same value as Studio's *Watch time hours*); it is converted to hours for display.
- The API has **no historical subscriber total** — only `subscribersGained` and `subscribersLost` per day. The subscriber curve must therefore be reconstructed backwards and anchored to the current `subscriberCount` from the Data API.

## How We Solved It

1. **Fetch layer** (`scripts/per_video_growth.py`) — walks every upload, fetches daily views, watch minutes, and content type in a single call per video, and fetches subscriber gains/losses in date chunks (avoiding the API's broken `startIndex` pagination). Results are cached locally.
2. **Server layer** (`scripts/dashboard_server.py`) — seeds from the cache, serves JSON, and can refresh live. Handles date range, content type, metric, and Top-N filters, plus subscriber aggregation.
3. **UI layer** (`web/dashboard.html`) — a local web dashboard with a Views/Watch time toggle, All/Videos/Shorts filter, Top-N ranking, and a dedicated subscriber section (current KPI, reconstructed total line, daily gained/lost bars).
4. **Reliability** — cache-based startup keeps the dashboard instant, refresh is optional, long-form fallback works without the Data API, and credentials/personal data stay out of Git.

In short: the project turns a fragmented and restrictive API surface into a cached, queryable dataset and a dashboard that explains **which videos and content types actually drive views, watch time, and subscriber growth over time** — not just a single total number.

## Features

- Cumulative line chart for each video (no fills)
- Channel-total cumulative chart
- Daily activity bar chart
- Switch the metric between **Views** and **Watch time (hours)**
- Filter by content type: All, Videos, Shorts
- **Subscribers** KPI with current total and net change in the selected range
- **Subscriber total** line chart (reconstructed from daily gains/losses)
- **Subscribers gained / lost per day** bar chart
- Date-range and Top-N controls
- Live refresh from the YouTube Analytics API (cached locally)
- **Download CSV** of the current filtered dataset from the dashboard
- **Download PNG** of any chart from the dashboard
- Exports PNG charts and CSV data from the CLI
- Optional Matplotlib charts for offline use
- Static GitHub Pages build with daily scheduled data updates

<img width="1485" height="1238" alt="image" src="https://github.com/user-attachments/assets/3c794cf6-3a58-4906-b2ba-c920fcefd793" />

<img width="1472" height="1228" alt="image" src="https://github.com/user-attachments/assets/423d1b1f-e437-4710-80d6-675d96e13e6e" />

<img width="1155" height="1118" alt="image" src="https://github.com/user-attachments/assets/0635ca58-92bd-497a-9305-6df2c9e2fc5a" />


## Requirements

- Python 3.9+
- A Google account with access to the channel
- A Google Cloud project with these APIs enabled:
  - **YouTube Analytics API** (required)
  - **YouTube Data API v3** (required to list Shorts; without it only long-form videos are found)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Google Cloud setup (one time)

1. Create or select a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **YouTube Analytics API** and **YouTube Data API v3** under **APIs & Services → Library**.
3. Configure **Google Auth Platform / OAuth consent screen** (External) and add your Google account as a **Test user**.
4. Create an OAuth client ID of type **Desktop app**.
5. Download the JSON and save it as:

```text
secrets/client_secret.json
```

On the first run, a browser window opens for sign-in. The resulting token is stored at `secrets/token.json` and reused afterward.

## Usage

### Web dashboard

```bash
python scripts/dashboard_server.py
```

This opens <http://127.0.0.1:8000>. Pass a port to change it:

```bash
python scripts/dashboard_server.py 8080
```

On first load it uses cached data from `data/generated/`. Click **Refresh from YouTube** to fetch the latest data (may take about a minute). Use **Download CSV** to export the currently filtered data, and the **PNG** button on any chart to save it as an image.

### Per-video charts (Matplotlib)

```bash
python scripts/per_video_growth.py
```

Useful flags:

```bash
python scripts/per_video_growth.py --top 15
python scripts/per_video_growth.py --start 2024-01-01 --end 2026-11-06
python scripts/per_video_growth.py --reuse   # redraw from cached CSV, no API calls
```

### Channel-total cumulative chart

```bash
python scripts/plot_growth.py
python scripts/plot_growth.py "path/to/Totals.csv" --show
```

## Hosting on GitHub Pages

The dashboard can be published as a static site. A GitHub Actions workflow (`.github/workflows/pages.yml`) runs daily, fetches the latest data, builds `dist/`, and deploys it to GitHub Pages.

### One-time setup

1. **Publish the OAuth app.** In Google Cloud Console → OAuth consent screen, set the publishing status to **In production**. Refresh tokens issued while the app is in *Testing* expire after about 7 days, which would break scheduled updates.
2. **Add repository secrets.** In GitHub → Settings → Secrets and variables → Actions, add:
   - `GOOGLE_CLIENT_SECRET` — contents of `secrets/client_secret.json`
   - `GOOGLE_TOKEN` — contents of `secrets/token.json` after the first local sign-in
3. **Enable Pages.** Settings → Pages → Build and deployment → Source: **GitHub Actions**.
4. **Run the workflow.** Actions → *Update and deploy dashboard* → *Run workflow*. When it finishes, the site is available at `https://<username>.github.io/<repo>/`.

The workflow also runs daily at 03:00 UTC and on pushes to `main`, `master`, or `branch2`. Scheduled workflows are disabled after 60 days of repository inactivity.

### Privacy note

GitHub Pages sites are public on free and Pro plans; private Pages requires GitHub Enterprise. If you need access control, deploy the generated `dist/` folder to Cloudflare Pages and put **Cloudflare Access** in front of it.

### Build the static site locally

```bash
python scripts/per_video_growth.py
python scripts/build_static.py
```

Then open `dist/index.html`, or serve the folder:

```bash
python -m http.server 8080 --directory dist
```

The static build writes `dist/data.json` and a copy of the dashboard that loads it and applies the date, content, metric, and Top-N filters in the browser.

## Project structure

```text
.
├── .github/
│   └── workflows/pages.yml    # scheduled fetch + GitHub Pages deploy
├── scripts/
│   ├── dashboard_server.py    # local web server + API endpoint
│   ├── per_video_growth.py    # API fetching + per-video charts
│   ├── build_static.py        # builds dist/ for GitHub Pages
│   └── plot_growth.py         # channel-total cumulative chart
├── web/
│   └── dashboard.html         # dashboard UI (Chart.js, local + static)
├── data/
│   ├── raw/                   # YouTube Studio CSV export (local only)
│   └── generated/             # derived CSVs + subscribers.json (local only)
├── output/                    # generated PNG charts (local only)
├── dist/                      # generated static site (local only)
├── secrets/                   # OAuth credentials (local only)
├── requirements.txt
└── .gitignore
```

`secrets/`, `data/`, `output/`, and `dist/` are git-ignored because they contain credentials, personal channel data, or generated output.

## Data notes

- The YouTube Analytics API typically lags about **2 days**, so the most recent days may be missing.
- Views and watch time are fetched in a single call using `metrics=views,estimatedMinutesWatched`.
- Watch time is displayed in **hours** (`estimatedMinutesWatched / 60`), which matches YouTube Studio's **Watch time (hours)**.
- Daily activity is attributed per video using `creatorContentType` (`shorts` or `videoOnDemand`).
- Subscribers come from `subscribersGained` / `subscribersLost` per day. The absolute total is anchored to the current `subscriberCount` from the YouTube Data API, so history is reconstructed backwards.
- Subscriber data is channel-level only; the API cannot attribute subscribers to individual videos.
- Video titles and the offline fallback list come from the Studio export (`Table data.csv`) in `data/raw/`.
- If the YouTube Data API is not enabled, the dashboard falls back to long-form videos only and shows a notice.

## Troubleshooting

- **`The query is not supported`** — the Analytics API does not support all dimension combinations. This project queries each video separately with a `video==ID` filter, which is supported.
- **No Shorts appear** — enable **YouTube Data API v3**, then click **Refresh from YouTube**.
- **`Missing OAuth client file`** — make sure `secrets/client_secret.json` exists.
- **Auth expired** — delete `secrets/token.json` and run a script again to re-authorize.

## License

No license has been specified for this project.
