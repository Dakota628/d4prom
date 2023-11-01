#!/usr/bin/env python3

import logging
import requests
from requests.adapters import HTTPAdapter, Retry
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

PROM_PUSH_GATEWAY_ENDPOINT = "localhost:9091"

LIVE_EVENT_ENDPOINT = "https://d4armory.io/api/liveevent"
WORLD_STATE_ENDPOINT = "https://d4armory.io/api/worldstate"


def live_event(
    s: requests.Session,
    sno_g: Gauge,
    start_g: Gauge,
    end_g: Gauge,
):
    try:
        resp = s.get(LIVE_EVENT_ENDPOINT)
        data = resp.json()

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


def world_state(s: requests.Session, g: Gauge):
    try:
        resp = s.get(WORLD_STATE_ENDPOINT)
        data = resp.json()

        for info in data or []:
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

    world_state(session, world_state_gauge)
    live_event(
        session,
        live_event_sno_gauge,
        live_event_start_time_gauge,
        live_event_end_time_gauge,
    )

    push_to_gateway(PROM_PUSH_GATEWAY_ENDPOINT, job="d4prom", registry=registry)


if __name__ == "__main__":
    main()
