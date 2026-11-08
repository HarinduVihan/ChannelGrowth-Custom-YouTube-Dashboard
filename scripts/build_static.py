import bisect
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GEN = BASE / "data" / "generated"
DIST = BASE / "dist"


def load_meta():
    path = GEN / "fetch_meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_videos():
    path = GEN / "per_video_daily_views.csv"
    if not path.exists():
        raise SystemExit("Missing per_video_daily_views.csv; run per_video_growth.py first.")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("No rows in per_video_daily_views.csv.")

    dates = sorted({datetime.strptime(r["Date"], "%Y-%m-%d").date() for r in rows})
    start = dates[0]
    count = (dates[-1] - start).days + 1
    date_list = [(start + timedelta(days=i)).isoformat() for i in range(count)]
    index = {d: i for i, d in enumerate(date_list)}

    videos = {}
    for row in rows:
        vid = row["Video ID"]
        i = index[row["Date"]]
        video = videos.get(vid)
        if video is None:
            video = videos[vid] = {
                "id": vid,
                "title": row.get("Video title") or vid,
                "type": row.get("Type") or "unknown",
                "views": [0] * count,
                "minutes": [0.0] * count,
            }
        video["views"][i] += int(row["Views"])
        video["minutes"][i] = round(
            video["minutes"][i] + float(row.get("Minutes") or 0), 2
        )

    ordered = sorted(videos.values(), key=lambda v: sum(v["views"]), reverse=True)
    return date_list, ordered


def load_subscribers(date_list):
    path = GEN / "subscribers.json"
    raw = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}

    current = raw.get("current")
    sub_daily = {}
    for row in raw.get("daily") or []:
        day = row["date"]
        gained = int(row.get("gained", 0))
        lost = int(row.get("lost", 0))
        prev = sub_daily.get(day, (0, 0))
        sub_daily[day] = (prev[0] + gained, prev[1] + lost)

    sub_dates = sorted(sub_daily)
    total_net = 0
    cum_map = {}
    for day in sub_dates:
        gained, lost = sub_daily[day]
        total_net += gained - lost
        cum_map[day] = total_net

    def cum_through(day):
        pos = bisect.bisect_right(sub_dates, day)
        return cum_map[sub_dates[pos - 1]] if pos else 0

    gained_arr = []
    lost_arr = []
    total_arr = []
    for day in date_list:
        gained, lost = sub_daily.get(day, (0, 0))
        gained_arr.append(gained)
        lost_arr.append(lost)
        if current is not None:
            total_arr.append(int(current - (total_net - cum_through(day))))
        else:
            total_arr.append(int(cum_through(day)))

    return {
        "current": current,
        "total": total_arr,
        "gained": gained_arr,
        "lost": lost_arr,
        "updated": raw.get("updated"),
    }


def main():
    date_list, videos = load_videos()
    subscribers = load_subscribers(date_list)
    meta = load_meta()

    payload = {
        "updated": meta.get("updated") or datetime.now().isoformat(timespec="seconds"),
        "dates": date_list,
        "videos": videos,
        "subscribers": subscribers,
        "videoSource": meta.get("videoSource") or "cache",
    }

    DIST.mkdir(parents=True, exist_ok=True)
    data_path = DIST / "data.json"
    with data_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    html = (BASE / "web" / "dashboard.html").read_text(encoding="utf-8")
    marker = "window.DASHBOARD_STATIC = false;"
    if marker not in html:
        raise SystemExit("Static flag marker not found in web/dashboard.html.")
    (DIST / "index.html").write_text(
        html.replace(marker, "window.DASHBOARD_STATIC = true;"), encoding="utf-8"
    )
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    size_mb = data_path.stat().st_size / (1024 * 1024)
    print(
        f"Built {DIST} - {len(date_list)} days, {len(videos)} videos, "
        f"data.json {size_mb:.2f} MB"
    )


if __name__ == "__main__":
    main()
