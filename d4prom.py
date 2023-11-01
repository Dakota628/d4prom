#!/usr/bin/env python3

import logging
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter, Retry
from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram, push_to_gateway

PROM_PUSH_GATEWAY_ENDPOINT = "localhost:9091"

LIVE_EVENT_ENDPOINT = "https://d4armory.io/api/liveevent"
WORLD_STATE_ENDPOINT = "https://d4armory.io/api/worldstate"
STATUS_ENDPOINT = "https://d4armory.io/status"


def get_endpoint(s: requests.Session, url: str, req_counter: Counter, req_histogram: Histogram) -> any:
    status = -1
    method = "GET"
    parsed_url = urlparse(url)

    with req_histogram.time() as t:
        try:
            resp = s.get(url)
            status = resp.status_code
            return resp.json()
        except Exception:
            status = -1
        finally:
            labels = dict(
                status=status,
                method=method,
                scheme=parsed_url.scheme,
                host=parsed_url.hostname,
                port=parsed_url.port,
                path=parsed_url.path
            )
            t.labels(**labels)
            req_counter.labels(**labels).inc(1)


def d4armory_health_check(s: requests.Session, g: Gauge, req_counter: Counter, req_histogram: Histogram):
    try:
        data = get_endpoint(s, STATUS_ENDPOINT, req_counter, req_histogram)
    except Exception:
        data = {}

    for service in ["character_service", "event_service"]:
        value = data.get(service, False) is True
        g.labels(service=service).set(1 if value else 0)


def live_event(
    s: requests.Session,
    sno_g: Gauge,
    start_g: Gauge,
    end_g: Gauge,
    req_counter: Counter,
    req_histogram: Histogram,
):
    try:
        data = get_endpoint(s, LIVE_EVENT_ENDPOINT, req_counter, req_histogram)

        if "liveEventSno" in data:
            sno_g.set(data["liveEventSno"])
        else:
            logging.warning(f"Missing liveEventSno: {data}")

        if "liveEventStartTime" in data:
            start_g.set(data["liveEventStartTime"])
        else:
            logging.warning(f"Missing liveEventStartTime: {data}")

        if "liveEventEndTime" in data:
            end_g.set(data["liveEventEndTime"])
        else:
            logging.warning(f"Missing liveEventEndTime: {data}")
    except Exception:
        logging.exception("Failed to get live event!")


def world_state(s: requests.Session, g: Gauge, req_counter: Counter, req_histogram: Histogram,):
    try:
        data = get_endpoint(s, WORLD_STATE_ENDPOINT, req_counter, req_histogram)

        for info in (data or []):
            if "worldState" in info and "nValue" in info:
                g.labels(world_state=info["worldState"]).set(info["nValue"])
            else:
                logging.warning(f"Invalid world state info: {info}")
    except Exception:
        logging.exception("Failed to get world state!")


def main():
    logging.basicConfig(level=logging.DEBUG)

    retry = Retry(total=5, backoff_factor=1)
    session = requests.Session()
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))

    registry = CollectorRegistry()
    req_counter = Counter(
        "req_counter",
        "HTTP request counter",
        labelnames=["status", "method", "scheme", "host", "port", "path"],
        registry=registry
    )
    req_histogram = Histogram(
        "req_latency",
        "HTTP request latency",
        labelnames=["status", "method", "scheme", "host", "port", "path"],
        registry=registry
    )
    d4armory_status_gauge = Gauge(
        "d4armory_status",
        "D4Armory API status by service",
        labelnames=["service"],
        registry=registry,
    )
    world_state_gauge = Gauge(
        "world_state",
        "Current Diablo 4 World States",
        labelnames=["world_state"],
        registry=registry,
    )
    live_event_sno_gauge = Gauge(
        "live_event_sno",
        "Current Diablo 4 live event SNO",
        registry=registry,
    )
    live_event_start_time_gauge = Gauge(
        "live_event_start_time",
        "Current Diablo 4 live event start timestamp",
        registry=registry,
    )
    live_event_end_time_gauge = Gauge(
        "live_event_end_time",
        "Current Diablo 4 live event end timestamp",
        registry=registry,
    )

    d4armory_health_check(session, d4armory_status_gauge, req_counter, req_histogram)
    world_state(session, world_state_gauge, req_counter, req_histogram)
    live_event(
        session,
        live_event_sno_gauge,
        live_event_start_time_gauge,
        live_event_end_time_gauge,
        req_counter,
        req_histogram,
    )

    push_to_gateway(PROM_PUSH_GATEWAY_ENDPOINT, job="d4prom", registry=registry)


if __name__ == "__main__":
    main()
