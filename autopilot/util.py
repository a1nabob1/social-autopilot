import json, os, sys, time, tomllib, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

def load_env():
    """Load secrets: a local .env file, and/or the AUTOPILOT_SECRETS JSON that GitHub Actions passes in."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    blob = os.environ.get("AUTOPILOT_SECRETS")
    if blob:
        try:
            for k, v in json.loads(blob).items():
                if isinstance(v, str):
                    os.environ.setdefault(k, v)
        except json.JSONDecodeError:
            pass

def config():
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)

def tz():
    return ZoneInfo(config()["settings"].get("timezone", "America/Chicago"))

def now():
    return dt.datetime.now(tz())

def load_json(path, default):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default

def save_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

_session = None
def http():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = "SocialAutopilot/1.0 (+self-hosted social scheduler)"
    return _session

def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(DATA / "run.log", "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {line}\n")

def env(brand_id, key):
    """Secrets are named like HOINOW_FB_TOKEN or FINEHOMELOAN_IG_USER_ID."""
    return os.environ.get(f"{brand_id.upper()}_{key}", "").strip()
