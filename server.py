import json
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


HOST = "127.0.0.1"
PORT = 8182
CACHE = {}


def fetch_upstream(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 MarketsWatch/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(req, timeout=15) as response:
        return response.read()


def cached_fetch(url, ttl=10):
    now = time.time()
    item = CACHE.get(url)
    if item and now - item["time"] < ttl:
      return item["body"]
    body = fetch_upstream(url)
    CACHE[url] = {"time": now, "body": body}
    return body


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        safe = str(message).replace("\\", "\\\\").replace('"', '\\"')
        self.send_json(status, f'{{"error":"{safe}"}}'.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/health":
                self.send_json(200, b'{"ok":true}')
                return

            if parsed.path == "/api/crypto/spot":
                out = {}
                for sym, key in (("BTC-USD", "BTCUSD"), ("ETH-USD", "ETHUSD")):
                    body = cached_fetch(f"https://api.coinbase.com/v2/prices/{sym}/spot", ttl=8)
                    data = json.loads(body.decode("utf-8"))
                    out[key] = float(data["data"]["amount"])
                self.send_json(200, json.dumps(out).encode("utf-8"))
                return

            if parsed.path == "/api/yahoo/quote":
                symbols = qs.get("symbols", [""])[0]
                fields = qs.get("fields", ["regularMarketPrice,regularMarketChangePercent"])[0]
                if not symbols:
                    self.send_error_json(400, "missing symbols")
                    return
                url = (
                    "https://query1.finance.yahoo.com/v7/finance/quote"
                    f"?symbols={quote(symbols, safe=',=^.-')}"
                    f"&fields={quote(fields, safe=',')}"
                )
                self.send_json(200, cached_fetch(url, ttl=15))
                return

            if parsed.path.startswith("/api/yahoo/chart/"):
                symbol = unquote(parsed.path.rsplit("/", 1)[-1])
                interval = qs.get("interval", ["1d"])[0]
                range_ = qs.get("range", ["1mo"])[0]
                url = (
                    "https://query1.finance.yahoo.com/v8/finance/chart/"
                    f"{quote(symbol, safe='=^.-')}"
                    f"?interval={quote(interval)}&range={quote(range_)}"
                )
                self.send_json(200, cached_fetch(url, ttl=15))
                return

            if parsed.path == "/api/coingecko/simple":
                ids = qs.get("ids", ["bitcoin,ethereum"])[0]
                vs = qs.get("vs_currencies", ["usd"])[0]
                change = qs.get("include_24hr_change", ["true"])[0]
                url = (
                    "https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={quote(ids, safe=',')}"
                    f"&vs_currencies={quote(vs, safe=',')}"
                    f"&include_24hr_change={quote(change)}"
                )
                self.send_json(200, cached_fetch(url, ttl=60))
                return

        except HTTPError as e:
            self.send_error_json(e.code, f"upstream returned {e.code}")
            return
        except URLError as e:
            self.send_error_json(502, e.reason)
            return
        except Exception as e:
            self.send_error_json(500, e)
            return

        super().do_GET()


if __name__ == "__main__":
    print(f"Starting Markets Watch on http://localhost:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
