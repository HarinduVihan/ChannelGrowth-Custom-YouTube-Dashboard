import csv
import json
import sys
import threading
import webbrowser
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
BASE = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import per_video_growth as pvg

LIVE_START = "2023-08-07"
STATE = {
    "per_video": None,
    "titles": {},
    "types": {},
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
    titles = {}
    types = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row["Video ID"]
            d = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            per_video[vid][d] = per_video[vid].get(d, 0) + int(row["Views"])
            titles.setdefault(vid, row["Video title"])
            types[vid] = row.get("Type") or "unknown"
    if not per_video:
        return False
    STATE.update(
        per_video=dict(per_video),
        titles=titles,
        types=types,
        updated=datetime.now().isoformat(timespec="seconds"),
        source="cache",
        videoSource="cache",
    )
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
        for day, ctype, views in rows:
            d = datetime.strptime(day, "%Y-%m-%d").date()
            per_video[vid][d] = per_video[vid].get(d, 0) + int(views)
            types[vid] = ctype
    STATE.update(
        per_video=dict(per_video),
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


def build_response(start, end, top, kind):
    per_video = STATE["per_video"] or {}
    titles = STATE["titles"]
    types = STATE.get("types") or {}

    if kind == "video":
        per_video = {v: s for v, s in per_video.items() if types.get(v) == "videoOnDemand"}
    elif kind == "shorts":
        per_video = {v: s for v, s in per_video.items() if types.get(v) == "shorts"}

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
    }
    if not all_dates:
        return base_resp

    sdate = datetime.strptime(start, "%Y-%m-%d").date() if start else all_dates[0]
    edate = datetime.strptime(end, "%Y-%m-%d").date() if end else all_dates[-1]
    sdate = max(sdate, all_dates[0])
    edate = min(edate, all_dates[-1])
    if edate < sdate:
        sdate, edate = all_dates[0], all_dates[-1]

    full = list(pvg.daterange(sdate, edate))
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
                "data": cumulative[vid],
                "total": totals[vid],
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
                "data": other,
                "total": sum(totals[v] for v in rest),
                "other": True,
            }
        )

    base_resp.update(
        dates=[d.isoformat() for d in full],
        series=series,
        total=sum(totals.values()),
        videoCount=len(per_video),
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
                payload = build_response(start, end, top, kind)
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
