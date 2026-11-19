import os
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"
DIST = BASE / "dist"

REQUIRED = (
    "dashboard.html",
    "privacy.html",
    "terms.html",
    "config.js",
    "vendor/chart.umd.min.js",
)

PLACEHOLDER = "REPLACE_WITH_WEB_CLIENT_ID"


def custom_domain():
    domain = os.environ.get("CUSTOM_DOMAIN", "").strip()
    if not domain:
        cname_path = WEB / "CNAME"
        if cname_path.exists():
            domain = cname_path.read_text(encoding="utf-8").strip()
    return domain.replace("https://", "").replace("http://", "").strip("/")


def main():
    missing = [name for name in REQUIRED if not (WEB / name).is_file()]
    if missing:
        raise SystemExit("Missing web files: " + ", ".join(missing))

    config_text = (WEB / "config.js").read_text(encoding="utf-8")
    if PLACEHOLDER in config_text and os.environ.get("ALLOW_PLACEHOLDER") != "1":
        raise SystemExit(
            "web/config.js still contains the placeholder client ID. "
            "Add the Web application OAuth client ID from Google Cloud, "
            "or set ALLOW_PLACEHOLDER=1 to build a preview anyway."
        )

    if DIST.exists():
        if DIST.name != "dist" or DIST.parent != BASE:
            raise SystemExit("Refusing to clean unexpected dist path: " + str(DIST))
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copy2(WEB / "dashboard.html", DIST / "index.html")
    shutil.copy2(WEB / "dashboard.html", DIST / "dashboard.html")
    shutil.copy2(WEB / "privacy.html", DIST / "privacy.html")
    shutil.copy2(WEB / "terms.html", DIST / "terms.html")
    shutil.copy2(WEB / "config.js", DIST / "config.js")
    shutil.copytree(WEB / "vendor", DIST / "vendor")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    domain = custom_domain()
    if domain:
        (DIST / "CNAME").write_text(domain + "\n", encoding="utf-8")

    files = sorted(
        str(path.relative_to(DIST)).replace("\\", "/")
        for path in DIST.rglob("*")
        if path.is_file()
    )
    extra = ", CNAME " + domain if domain else ""
    print("Built " + str(DIST) + " - " + str(len(files)) + " files" + extra)
    for name in files:
        print("  " + name)


if __name__ == "__main__":
    main()
