"""Long-running Digital-Twin process."""

from __future__ import annotations

import argparse
import time

from ..comm.mqtt_pubsub import MQTTPubSub
from ..dt import MicrogridDigitalTwin, TwinConfig


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--icas", required=True, help="comma-separated ICA ids")
    p.add_argument("--tick-period", type=float, default=0.01)
    args = p.parse_args()

    ica_ids = [s.strip() for s in args.icas.split(",") if s.strip()]
    print(f"[dt] connecting to mqtt://{args.broker}:{args.port}")
    pubsub = MQTTPubSub(broker_host=args.broker, broker_port=args.port, client_id="dt")
    pubsub.connect(timeout=10.0)

    twin = MicrogridDigitalTwin(ica_ids, pubsub, TwinConfig())
    print(f"[dt] running for {ica_ids}, period {args.tick_period}s")
    t = 0.0
    while True:
        twin.tick(t=t)
        if int(t * 100) % 100 == 0:
            s = twin.summary()
            print(f"[dt] t={t:.2f}  ticks={s['n_ticks']}  "
                  f"anomalies={s['n_anomaly_events']}  cyber={s['n_cyber_alerts']}")
        time.sleep(args.tick_period)
        t += args.tick_period


if __name__ == "__main__":
    main()
