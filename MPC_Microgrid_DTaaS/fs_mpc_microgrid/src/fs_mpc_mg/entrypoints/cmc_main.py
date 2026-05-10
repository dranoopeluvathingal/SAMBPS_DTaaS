"""Long-running CMC process."""

from __future__ import annotations

import argparse
import time

from ..comm.mqtt_pubsub import MQTTPubSub
from ..cmc import (
    Topology, BusNode, ICANode, LoadNode, Controller, ControllerConfig,
)
from ..cmc.topology import SwitchEdge


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--icas", required=True, help="comma-separated ICA ids")
    p.add_argument("--tick-period", type=float, default=0.5,
                   help="Dispatch period in seconds")
    p.add_argument("--q-target", type=float, default=0.0,
                   help="Q_total_target (VAr)")
    p.add_argument("--v-dc-ref", type=float, default=900.0)
    args = p.parse_args()

    ica_ids = [s.strip() for s in args.icas.split(",") if s.strip()]
    print(f"[cmc] connecting to mqtt://{args.broker}:{args.port}")
    pubsub = MQTTPubSub(broker_host=args.broker, broker_port=args.port,
                       client_id="cmc")
    pubsub.connect(timeout=10.0)

    topo = Topology()
    topo.add_bus(BusNode("grid", is_grid=True))
    topo.add_bus(BusNode("pcc"))
    topo.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for iid in ica_ids:
        topo.add_ica(ICANode(iid, "pcc", s_max=80e3))
    topo.add_load(LoadNode("aggregate", "pcc", p_nominal=40e3, nonlinear=True))

    cfg = ControllerConfig(
        tick_period_s=args.tick_period,
        v_dc_ref_default=args.v_dc_ref,
        q_total_target=args.q_target,
    )
    ctrl = Controller(topo, pubsub, cfg)
    ctrl.start()

    print(f"[cmc] running with {len(ica_ids)} ICAs, period {args.tick_period}s")
    while True:
        ctrl.tick()
        rec = ctrl.log[-1]
        print(f"[cmc] t={rec['ts']:.2f}  mode={rec['sys_mode']}  "
              f"active={rec['n_active']}  Q_total={rec['q_total_target']:.0f}")
        time.sleep(args.tick_period)


if __name__ == "__main__":
    main()
