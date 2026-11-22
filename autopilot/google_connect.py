"""One-time Google Business Profile connection.

Run:  python -m autopilot.google_connect "C:\\path\\to\\client_secret_....json"

It opens Google's sign-in in your browser (you approve "See, edit, create and delete your Google
business listings"), then saves the client ID, client secret and long-lived refresh token straight
into the repo's GitHub secrets with `gh`. Secret values are never printed or written to disk.
It also finds your Business Profile account and location IDs and saves them for each brand.
"""
import http.server, json, secrets, subprocess, sys, threading, urllib.parse, webbrowser
import requests

REPO = "a1nabob1/social-autopilot"
SCOPE = "https://www.googleapis.com/auth/business.manage"
# Which listing belongs to which brand (matched against the listing name, case-insensitive)
BRANDS = {"HOINOW": "alabama coastal insurance", "FINEHOMELOAN": "weber mortgage"}


def gh_secret(name, value):
    r = subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value, text=True, capture_output=True)
    if r.returncode != 0:
        sys.exit(f"Could not save {name}: {r.stderr.strip()}")
    print(f"  saved {name}")


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m autopilot.google_connect path\\to\\client_secret.json")
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    client = cfg.get("installed") or cfg.get("web") or {}
    cid, csecret = client.get("client_id"), client.get("client_secret")
    if not (cid and csecret):
        sys.exit("That file doesn't look like a Google OAuth client file.")

    result = {}
    state = secrets.token_urlsafe(16)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                result["code"] = q.get("code", [""])[0]
                result["error"] = q.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = "Done - you can close this tab and go back to the terminal." if result.get("code") else "Sign-in did not finish."
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})
    print("Opening Google sign-in in your browser. Choose the Google account that manages your Business Profiles.")
    print("If it doesn't open, paste this address into your browser:\n" + url + "\n")
    webbrowser.open(url)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    t.join(timeout=600)
    srv.server_close()
    if not result.get("code"):
        sys.exit(f"Google sign-in did not complete ({result.get('error') or 'timed out'}).")

    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "code": result["code"], "client_id": cid, "client_secret": csecret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30).json()
    if "refresh_token" not in tok:
        sys.exit(f"Google did not return a long-lived key: {tok.get('error_description') or tok.get('error')}")

    print("\nSaving to GitHub (values are not shown):")
    gh_secret("GOOGLE_CLIENT_ID", cid)
    gh_secret("GOOGLE_CLIENT_SECRET", csecret)
    gh_secret("GOOGLE_REFRESH_TOKEN", tok["refresh_token"])

    h = {"Authorization": f"Bearer {tok['access_token']}"}
    accounts = requests.get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", headers=h, timeout=30).json()
    found = {}
    print("\nYour Business Profile listings:")
    for acct in accounts.get("accounts", []):
        locs = requests.get(f"https://mybusinessbusinessinformation.googleapis.com/v1/{acct['name']}/locations",
                            params={"readMask": "name,title", "pageSize": 100}, headers=h, timeout=30).json()
        for loc in locs.get("locations", []):
            title = loc.get("title", "")
            print(f"  {title}  ({acct['name']}/{loc['name']})")
            for brand, needle in BRANDS.items():
                if needle in title.lower() and brand not in found:
                    found[brand] = (acct["name"].split("/")[-1], loc["name"].split("/")[-1], title)
    print()
    for brand in BRANDS:
        if brand in found:
            a, l, title = found[brand]
            gh_secret(f"{brand}_GBP_ACCOUNT_ID", a)
            gh_secret(f"{brand}_GBP_LOCATION_ID", l)
            print(f"  {brand.lower()} -> {title}")
        else:
            print(f"  {brand.lower()}: no matching listing found (looked for '{BRANDS[brand]}')")
    print("\nGoogle Business Profile is connected. Tell Claude 'done'.")


if __name__ == "__main__":
    main()
