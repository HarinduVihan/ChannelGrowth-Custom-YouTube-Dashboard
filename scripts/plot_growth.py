import csv
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent
if len(sys.argv) > 1:
    CSV_PATH = Path(sys.argv[1])
else:
    candidates = sorted(
        (BASE / "data" / "raw").glob("*/Totals.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("No Totals.csv found under data/raw; pass a CSV path as an argument.")
    CSV_PATH = candidates[0]

dates, views = [], []
with CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if not row.get("Date") or not row.get("Views"):
            continue
        dates.append(datetime.strptime(row["Date"], "%Y-%m-%d"))
        views.append(int(row["Views"]))

cumulative = []
running = 0
for v in views:
    running += v
    cumulative.append(running)

fig, ax = plt.subplots(figsize=(13, 6))
ax.plot(dates, cumulative, color="#ff0033", linewidth=2)

ax.set_title(f"Cumulative Channel Views - {cumulative[-1]:,} total", fontsize=15, fontweight="bold")
ax.set_xlabel("Date")
ax.set_ylabel("Total views")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.grid(True, alpha=0.3)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

ax.annotate(f"{cumulative[-1]:,}", xy=(dates[-1], cumulative[-1]),
            xytext=(-10, 12), textcoords="offset points",
            ha="right", fontweight="bold", color="#ff0033")

fig.autofmt_xdate()
fig.tight_layout()
out = BASE / "output" / "channel_view_growth.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=150)
print(f"Saved {out}")
print(f"Days: {len(dates)}  Total views: {cumulative[-1]:,}")
if "--show" in sys.argv:
    plt.show()
