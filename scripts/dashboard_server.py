import csv
import json
import sys
import threading
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
BASE = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import per_video_growth as pvg

LIVE_START = "2023-08-07"
SUBS_JSON = BASE / "data" / "generated" / "subscribers.json"
STATE = {
    "per_video": None,
    "per_minutes": None,
    "titles": {},
    "types": {},
    "subscribers": None,
    "updated": None,
    "source": None,
    "videoSource": None,
}
LOCK = threading.Lock()


def load_from_csv():
    path = BASE / "data" / "generated" / "per_video_daily_views.csv"
    if not path.exists():
        return False
    per_video = defaultdict(dict)
    per_minutes = defaultdict(dict)
    titles = {}
    types = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row["Video ID"]
            d = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            per_video[vid][d] = per_video[vid].get(d, 0) + int(row["Views"])
            per_minutes[vid][d] = per_minutes[vid].get(d, 0.0) + float(
                row.get("Minutes") or 0
            )
            titles.setdefault(vid, row["Video title"])
            types[vid] = row.get("Type") or "unknown"
    if not per_video:
        return False
    STATE.update(
        per_video=dict(per_video),
        per_minutes=dict(per_minutes),
        titles=titles,
        types=types,
        updated=datetime.now().isoformat(timespec="seconds"),
        source="cache",
        videoSource="cache",
    )
    return True


def load_subscribers_cache():
    data = pvg.load_subscribers(SUBS_JSON)
    if data is None:
        return False
    STATE["subscribers"] = data
    return True


def fetch_live():
    end = datetime.now().strftime("%Y-%m-%d")
    analytics, yt = pvg.get_services(
        BASE / "secrets" / "client_secret.json", BASE / "secrets" / "token.json"
    )
    try:
        videos = pvg.list_uploads(yt)
        video_source = "data-api"
        print(f"  Found {len(videos)} uploads including Shorts via YouTube Data API.")
    except Exception as e:
        print(f"  YouTube Data API unavailable: {e}")
        print("  Falling back to Table data.csv (long-form only).")
        videos_path = pvg.find_titles_file(BASE)
        if not videos_path:
            raise RuntimeError("Table data.csv not found and Data API unavailable")
        videos = pvg.load_videos(videos_path)
        video_source = "csv"

    per_video = defaultdict(dict)
    per_minutes = defaultdict(dict)
    titles = dict(videos)
    types = {}
    for i, (vid, title) in enumerate(videos, 1):
        safe = title.encode("ascii", "replace").decode("ascii")[:50]
        print(f"  [{i}/{len(videos)}] {safe}")
        try:
            rows = pvg.fetch_video_daily(analytics, vid, LIVE_START, end)
        except Exception as e:
            print(f"    skipped {vid}: {e}")
            continue
        for day, ctype, views, minutes in rows:
            d = datetime.strptime(day, "%Y-%m-%d").date()
            per_video[vid][d] = per_video[vid].get(d, 0) + int(views)
            per_minutes[vid][d] = per_minutes[vid].get(d, 0.0) + float(minutes)
            types[vid] = ctype
    try:
        sub_rows = pvg.fetch_channel_subscribers(analytics, pvg.HISTORY_START, end)
        try:
            current = pvg.fetch_current_subscribers(yt)
        except Exception as e:
            print(f"  Could not read current subscriber count: {e}")
            current = None
        pvg.save_subscribers(SUBS_JSON, sub_rows, current)
        STATE["subscribers"] = pvg.load_subscribers(SUBS_JSON)
        print(f"  Subscribers: {current} current, {len(sub_rows)} days.")
    except Exception as e:
        print(f"  Could not fetch subscriber data: {e}")
    STATE.update(
        per_video=dict(per_video),
        per_minutes=dict(per_minutes),
        titles=titles,
        types=types,
        updated=datetime.now().isoformat(timespec="seconds"),
        source="live",
        videoSource=video_source,
    )


def count_types():
    types = STATE.get("types") or {}
    counts = {"all": len(types), "video": 0, "shorts": 0, "unknown": 0}
    for t in types.values():
        if t == "shorts":
            counts["shorts"] += 1
        elif t == "videoOnDemand":
            counts["video"] += 1
        else:
            counts["unknown"] += 1
    return counts


def build_subscribers(full, sdate):
    data = STATE.get("subscribers") or {}
    daily = data.get("daily") or []
    current = data.get("current")
    gained_map = {}
    lost_map = {}
    for row in daily:
        d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        gained_map[d] = int(row.get("gained", 0))
        lost_map[d] = int(row.get("lost", 0))

    subs_dates = sorted(gained_map)
    cum_map = {}
    total_net = 0
    if subs_dates:
        for d in pvg.daterange(subs_dates[0], subs_dates[-1]):
            total_net += gained_map.get(d, 0) - lost_map.get(d, 0)
            cum_map[d] = total_net

    def cum_through(d):
        if not subs_dates or d < subs_dates[0]:
            return 0
        if d > subs_dates[-1]:
            return total_net
        return cum_map.get(d, 0)

    before = cum_through(sdate - timedelta(days=1)) if full and sdate else 0
    totals, gained, lost, net = [], [], [], []
    g_total = l_total = 0
    for d in full:
        g = gained_map.get(d, 0)
        l = lost_map.get(d, 0)
        g_total += g
        l_total += l
        if current is not None:
            totals.append(int(current - (total_net - cum_through(d))))
        else:
            totals.append(int(cum_through(d) - before))
        gained.append(g)
        lost.append(l)
        net.append(g - l)

    return {
        "dates": [d.isoformat() for d in full],
        "total": totals,
        "gained": gained,
        "lost": lost,
        "net": net,
        "current": current,
        "netChange": g_total - l_total,
        "gainedTotal": g_total,
        "lostTotal": l_total,
        "anchored": current is not None,
        "updated": data.get("updated"),
    }


def build_response(start, end, top, kind, metric="views"):
    source = STATE["per_minutes"] if metric == "watch" else STATE["per_video"]
    per_video = source or {}
    titles = STATE["titles"]
    types = STATE.get("types") or {}

    if kind == "video":
        per_video = {v: s for v, s in per_video.items() if types.get(v) == "videoOnDemand"}
    elif kind == "shorts":
        per_video = {v: s for v, s in per_video.items() if types.get(v) == "shorts"}

    unit = "hours" if metric == "watch" else "views"

    def conv(x):
        return round(x / 60.0, 2) if metric == "watch" else int(x)

    all_dates = sorted({d for s in per_video.values() for d in s})
    base_resp = {
        "dates": [],
        "series": [],
        "total": 0,
        "videoCount": 0,
        "counts": count_types(),
        "updated": STATE["updated"] or datetime.now().isoformat(timespec="seconds"),
        "source": STATE["source"] or "cache",
        "videoSource": STATE["videoSource"] or "cache",
        "filter": kind,
        "metric": metric,
        "unit": unit,
    }
    if not all_dates:
        base_resp["subscribers"] = build_subscribers([], None)
        return base_resp

    sdate = datetime.strptime(start, "%Y-%m-%d").date() if start else all_dates[0]
    edate = datetime.strptime(end, "%Y-%m-%d").date() if end else all_dates[-1]
    sdate = max(sdate, all_dates[0])
    edate = min(edate, all_dates[-1])
    if edate < sdate:
        sdate, edate = all_dates[0], all_dates[-1]

    full = list(pvg.daterange(sdate, edate))
    subs_payload = build_subscribers(full, sdate)
    cumulative = {}
    totals = {}
    for vid, series in per_video.items():
        running = 0
        arr = []
        for d in full:
            running += series.get(d, 0)
            arr.append(running)
        cumulative[vid] = arr
        totals[vid] = running

    ranked = sorted(totals, key=totals.get, reverse=True)
    chosen = ranked[:top]
    series = []
    for vid in chosen:
        series.append(
            {
                "label": titles.get(vid, vid),
                "videoId": vid,
                "type": types.get(vid, "unknown"),
                "data": [conv(x) for x in cumulative[vid]],
                "total": conv(totals[vid]),
                "other": False,
            }
        )
    rest = ranked[top:]
    if rest:
        other = [sum(cumulative[v][i] for v in rest) for i in range(len(full))]
        series.append(
            {
                "label": f"Other ({len(rest)} videos)",
                "videoId": "",
                "type": "",
                "data": [conv(x) for x in other],
                "total": conv(sum(totals[v] for v in rest)),
                "other": True,
            }
        )

    base_resp.update(
        dates=[d.isoformat() for d in full],
        series=series,
        total=conv(sum(totals.values())),
        videoCount=len(per_video),
        subscribers=subs_payload,
    )
    return base_resp


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = (BASE / "web" / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path == "/api/data":
            qs = parse_qs(parsed.query)
            get = lambda k, d="": qs.get(k, [d])[0]
            refresh = get("refresh", "0") in ("1", "true")
            start, end = get("start"), get("end")
            kind = get("type", "all")
            if kind not in ("all", "video", "shorts"):
                kind = "all"
            metric = get("metric", "views")
            if metric not in ("views", "watch"):
                metric = "views"
            try:
                top = max(1, min(int(get("top", "10") or 10), 40))
            except ValueError:
                top = 10
            try:
                with LOCK:
                    if refresh or STATE["per_video"] is None:
                        print("Fetching live data from YouTube Analytics...")
                        fetch_live()
                        print("Done.")
                payload = build_response(start, end, top, kind, metric)
                self.send_json(payload)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
        self.send_response(404)
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if load_from_csv():
        print("Seeded dashboard from cached CSV.")
    else:
        print("No cache found; first page load will fetch from YouTube.")
    if load_subscribers_cache():
        print("Seeded subscribers from cached JSON.")
    url = f"http://127.0.0.1:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard running at {url}  (Ctrl+C to stop)")
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
