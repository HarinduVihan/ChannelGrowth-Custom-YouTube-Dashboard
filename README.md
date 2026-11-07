# Custom YouTube Dashboard

A local dashboard for exploring how individual YouTube videos contribute to a channel's growth over time. It pulls daily views from the **YouTube Analytics API**, builds cumulative view charts per video, and serves an interactive web dashboard with filters for **All / Videos / Shorts**.

<img width="1738" height="1185" alt="image" src="https://github.com/user-attachments/assets/c70e1716-e114-4bad-bc1f-a6392c39c069" />

<img width="1145" height="757" alt="image" src="https://github.com/user-attachments/assets/eb763fd2-9bf0-4c51-84fa-03bc2387d5b0" />

<img width="1505" height="1115" alt="image" src="https://github.com/user-attachments/assets/cd202122-970e-4d12-8f8b-d82886e0eca4" />


## Features

- Cumulative views line chart for each video (no fills)
- Channel-total cumulative views chart
- Daily views bar chart
- Filter by content type: All, Videos, Shorts
- Date-range and Top-N controls
- Live refresh from the YouTube Analytics API (cached locally)
- Exports PNG charts and CSV data
- Optional Matplotlib charts for offline use

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

On first load it uses cached data from `data/generated/`. Click **Refresh from YouTube** to fetch the latest data (may take about a minute).

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

## Project structure

```text
.
├── scripts/
│   ├── dashboard_server.py    # local web server + API endpoint
│   ├── per_video_growth.py    # API fetching + per-video charts
│   └── plot_growth.py         # channel-total cumulative chart
├── web/
│   └── dashboard.html         # dashboard UI (Chart.js)
├── data/
│   ├── raw/                   # YouTube Studio CSV export (local only)
│   └── generated/             # derived CSVs (local only)
├── output/                    # generated PNG charts (local only)
├── secrets/                   # OAuth credentials (local only)
├── requirements.txt
└── .gitignore
```

`secrets/`, `data/`, and `output/` are git-ignored because they contain credentials and personal channel data.

## Data notes

- The YouTube Analytics API typically lags about **2 days**, so the most recent days may be missing.
- Views are attributed per day and per video using `creatorContentType` (`shorts` or `videoOnDemand`).
- Video titles and the offline fallback list come from the Studio export (`Table data.csv`) in `data/raw/`.
- If the YouTube Data API is not enabled, the dashboard falls back to long-form videos only and shows a notice.

## Troubleshooting

- **`The query is not supported`** — the Analytics API does not support all dimension combinations. This project queries each video separately with a `video==ID` filter, which is supported.
- **No Shorts appear** — enable **YouTube Data API v3**, then click **Refresh from YouTube**.
- **`Missing OAuth client file`** — make sure `secrets/client_secret.json` exists.
- **Auth expired** — delete `secrets/token.json` and run a script again to re-authorize.

## License

No license has been specified for this project.
