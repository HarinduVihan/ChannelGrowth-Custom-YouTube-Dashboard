import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]
PAGE_SIZE = 500


def die(msg):
    print(msg)
    sys.exit(1)


def get_credentials(client_secret, token_path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret.exists():
                die(
                    f"Missing OAuth client file: {client_secret}\n"
                    "Download it from Google Cloud Console (OAuth client -> Desktop app) "
                    "and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_services(client_secret, token_path):
    from googleapiclient.discovery import build

    creds = get_credentials(client_secret, token_path)
    return (
        build("youtubeAnalytics", "v2", credentials=creds),
        build("youtube", "v3", credentials=creds),
    )


def get_service(client_secret, token_path):
    return get_services(client_secret, token_path)[0]


def list_uploads(yt):
    channels = yt.channels().list(mine=True, part="contentDetails").execute()
    items = channels.get("items", [])
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos = []
    token = None
    while True:
        resp = (
            yt.playlistItems()
            .list(
                playlistId=uploads,
                part="contentDetails,snippet",
                maxResults=50,
                pageToken=token,
            )
            .execute()
        )
        for item in resp.get("items", []):
            vid = item["contentDetails"]["videoId"]
            title = item["snippet"].get("title", vid)
            videos.append((vid, title))
        token = resp.get("nextPageToken")
        if not token:
            break
    return videos


def load_videos(path):
    videos = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vid = (row.get("Content") or "").strip()
            title = (row.get("Video title") or "").strip()
            if vid and vid != "Total" and not any(v == vid for v, _ in videos):
                videos.append((vid, title or vid))
    return videos


def fetch_video_daily(service, vid, start, end):
    rows = []
    idx = 1
    prev_first = None
    while True:
        resp = (
            service.reports()
            .query(
                ids="channel==MINE",
                startDate=start,
                endDate=end,
                metrics="views",
                dimensions="day,creatorContentType",
                filters=f"video=={vid}",
                sort="day",
                startIndex=idx,
                maxResults=PAGE_SIZE,
            )
            .execute()
        )
        chunk = resp.get("rows", [])
        if not chunk:
            break
        if prev_first is not None and chunk[0] == prev_first:
            break
        rows.extend(chunk)
        prev_first = chunk[0]
        if len(chunk) < PAGE_SIZE:
            break
        idx += len(chunk)
    return rows


def find_titles_file(base):
    for p in base.rglob("Table data.csv"):
        return p
    return None


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-08-07")
    ap.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--client-secret", default="secrets/client_secret.json")
    ap.add_argument("--token", default="secrets/token.json")
    ap.add_argument("--titles", default=None)
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent.parent
    client_secret = Path(args.client_secret)
    if not client_secret.is_absolute():
        client_secret = base / client_secret
    token_path = Path(args.token)
    if not token_path.is_absolute():
        token_path = base / token_path

    videos_path = Path(args.titles) if args.titles else find_titles_file(base)

    out_dir = base / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    (base / "output").mkdir(parents=True, exist_ok=True)
    daily_csv = out_dir / "per_video_daily_views.csv"

    titles = {}
    types = {}
    per_video = defaultdict(dict)
    all_dates = set()
    if args.reuse and daily_csv.exists():
        print(f"Reusing {daily_csv.name} ...")
        with daily_csv.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                vid = row["Video ID"]
                d = datetime.strptime(row["Date"], "%Y-%m-%d").date()
                per_video[vid][d] = per_video[vid].get(d, 0) + int(row["Views"])
                all_dates.add(d)
                if row.get("Video title"):
                    titles[vid] = row["Video title"]
                types[vid] = row.get("Type") or "unknown"
    else:
        analytics, yt = get_services(client_secret, token_path)
        try:
            videos = list_uploads(yt)
            print(f"Found {len(videos)} uploads (including Shorts) via YouTube Data API.")
        except Exception as e:
            print(f"YouTube Data API unavailable ({e}).")
            print("Falling back to Table data.csv (long-form only).")
            if not videos_path or not videos_path.exists():
                die("Could not find 'Table data.csv'. Pass it with --titles.")
            videos = load_videos(videos_path)
        titles = dict(videos)
        print(f"Fetching daily views for {len(videos)} videos {args.start} -> {args.end} ...")
        for i, (vid, title) in enumerate(videos, 1):
            try:
                rows = fetch_video_daily(analytics, vid, args.start, args.end)
            except Exception as e:
                print(f"  [{i}/{len(videos)}] skipped {vid}: {e}")
                continue
            for day, ctype, views in rows:
                d = datetime.strptime(day, "%Y-%m-%d").date()
                per_video[vid][d] = per_video[vid].get(d, 0) + int(views)
                all_dates.add(d)
                types[vid] = ctype
            safe_title = title.encode("ascii", "replace").decode("ascii")[:50]
            print(f"  [{i}/{len(videos)}] {len(rows):>5} days  {safe_title}")

    if not all_dates:
        die("No data returned. Check the date range or channel authorization.")

    dates = sorted(all_dates)
    full_dates = list(daterange(dates[0], dates[-1]))

    video_totals = {vid: sum(s.values()) for vid, s in per_video.items()}
    ranked = sorted(video_totals, key=video_totals.get, reverse=True)
    total_views = sum(video_totals.values())

    with daily_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Video ID", "Video title", "Type", "Views"])
        for vid in ranked:
            for d in sorted(per_video[vid]):
                w.writerow(
                    [
                        d.isoformat(),
                        vid,
                        titles.get(vid, vid),
                        types.get(vid, "unknown"),
                        per_video[vid][d],
                    ]
                )

    cum_csv = out_dir / "per_video_cumulative_views.csv"
    cum_by_video = {}
    for vid in ranked:
        running = 0
        series = []
        for d in full_dates:
            running += per_video[vid].get(d, 0)
            series.append(running)
        cum_by_video[vid] = series
    with cum_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date"] + [f"{titles.get(v, v)} [{v}]" for v in ranked])
        for i, d in enumerate(full_dates):
            w.writerow([d.isoformat()] + [cum_by_video[v][i] for v in ranked])

    top = ranked[: args.top]
    other = ranked[args.top:]
    groups = {}
    labels = []
    for vid in top:
        label = titles.get(vid, vid)
        if len(label) > 45:
            label = label[:42] + "..."
        groups[label] = cum_by_video[vid]
        labels.append(label)
    if other:
        other_series = [sum(cum_by_video[v][i] for v in other) for i in range(len(full_dates))]
        groups["Other (" + str(len(other)) + " videos)"] = other_series
        labels.append("Other (" + str(len(other)) + " videos)")

    order = (["Other (" + str(len(other)) + " videos)"] if other else []) + labels[: len(top)]
    colors = plt.get_cmap("tab20").colors
    color_map = {lab: colors[i % len(colors)] for i, lab in enumerate(order)}

    fig, ax = plt.subplots(figsize=(14, 7))
    for lab in order:
        ax.plot(
            full_dates,
            groups[lab],
            linewidth=1.8,
            label=lab,
            color=color_map[lab],
        )
    ax.set_title(
        f"Channel Growth by Video - Cumulative Views ({total_views:,} total)",
        fontsize=15,
        fontweight="bold",
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative views")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.autofmt_xdate()
    fig.tight_layout()
    stacked_png = base / "output" / "channel_growth_by_video.png"
    fig.savefig(stacked_png, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 7))
    for i, lab in enumerate(labels):
        ax.plot(full_dates, groups[lab], linewidth=1.8, label=lab, color=colors[i % len(colors)])
    ax.set_title("Cumulative Views per Video", fontsize=15, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative views")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.autofmt_xdate()
    fig.tight_layout()
    lines_png = base / "output" / "top_videos_cumulative.png"
    fig.savefig(lines_png, dpi=150)
    plt.close(fig)

    print(f"Videos: {len(ranked)}  Total views: {total_views:,}")
    print(f"Saved {stacked_png.name}, {lines_png.name}")
    print(f"Saved {daily_csv.name}, {cum_csv.name} in {out_dir.name}")
    print("Top videos:")
    for vid in ranked[:10]:
        safe_title = titles.get(vid, vid).encode("ascii", "replace").decode("ascii")
        print(f"  {video_totals[vid]:>7,}  {safe_title}")


if __name__ == "__main__":
    main()
