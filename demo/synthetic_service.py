"""Synthetic workload for the local stack, standard library only.

Exposes /metrics in the Prometheus text format with the three series the example
SLOs read. Behaviour is driven by environment variables so an incident can be
simulated without touching code:

    CHECKOUT_ERROR_RATIO   share of checkout requests that fail with a 500 (0.0005)
    SEARCH_SLOW_RATIO      share of search queries slower than 400 ms     (0.02)
    INGESTION_STALLED      "1" stops the ingestion pipeline from succeeding (0)
"""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHECKOUT_RPS = 50.0
SEARCH_RPS = 80.0
INGESTION_EVERY_SECONDS = 300
# Upper bounds of the search latency histogram and how fast traffic is spread across them.
BUCKETS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
FAST_SHARE = (0.30, 0.35, 0.25, 0.10)  # of fast requests, buckets up to 0.4
SLOW_SHARE = (0.70, 0.30)  # of slow requests, buckets 0.8 and 1.6


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.checkout = {"200": 0.0, "500": 0.0}
        self.search_buckets = [0.0] * len(BUCKETS)
        self.search_count = 0.0
        self.search_sum = 0.0
        self.last_success = time.time()

    def tick(self, error_ratio: float, slow_ratio: float, stalled: bool) -> None:
        with self.lock:
            self.checkout["500"] += CHECKOUT_RPS * error_ratio
            self.checkout["200"] += CHECKOUT_RPS * (1 - error_ratio)
            fast = SEARCH_RPS * (1 - slow_ratio)
            slow = SEARCH_RPS * slow_ratio
            per_bucket = [fast * s for s in FAST_SHARE] + [slow * s for s in SLOW_SHARE]
            for i, n in enumerate(per_bucket):
                self.search_buckets[i] += n
                self.search_sum += n * BUCKETS[i] * 0.75
            self.search_count += SEARCH_RPS
            now = time.time()
            if not stalled and now - self.last_success >= INGESTION_EVERY_SECONDS:
                self.last_success = now

    def render(self) -> str:
        with self.lock:
            lines = [
                "# TYPE http_server_requests_total counter",
                *(
                    f'http_server_requests_total{{service="checkout-api",code="{code}"}} {value}'
                    for code, value in self.checkout.items()
                ),
                "# TYPE http_server_request_duration_seconds histogram",
            ]
            labels = 'service="search",route="/api/search"'
            cumulative = 0.0
            for bound, n in zip(BUCKETS, self.search_buckets, strict=True):
                cumulative += n
                lines.append(
                    f'http_server_request_duration_seconds_bucket{{{labels},le="{bound}"}} '
                    f"{cumulative}"
                )
            lines += [
                f'http_server_request_duration_seconds_bucket{{{labels},le="+Inf"}} '
                f"{self.search_count}",
                f"http_server_request_duration_seconds_count{{{labels}}} {self.search_count}",
                f"http_server_request_duration_seconds_sum{{{labels}}} {self.search_sum}",
                "# TYPE ingestion_last_success_timestamp_seconds gauge",
                'ingestion_last_success_timestamp_seconds{pipeline="events"} '
                f"{self.last_success}",
            ]
        return "\n".join(lines) + "\n"


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/metrics":
            self.send_error(404)
            return
        body = STATE.render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _loop() -> None:
    error_ratio = float(os.environ.get("CHECKOUT_ERROR_RATIO", "0.0005"))
    slow_ratio = float(os.environ.get("SEARCH_SLOW_RATIO", "0.02"))
    stalled = os.environ.get("INGESTION_STALLED", "0") == "1"
    while True:
        STATE.tick(error_ratio, slow_ratio, stalled)
        time.sleep(1)


def main() -> None:
    threading.Thread(target=_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
