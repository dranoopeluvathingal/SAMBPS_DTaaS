"""Long-running ICA process.

Connects to the MQTT broker, instantiates a Plant + ICAAgent + HarmonicLoad,
and runs the closed loop forever.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from ..plant import Plant, PlantParams
from ..load_model import HarmonicLoad, HarmonicLoadParams
from ..pll import SOGIPLL, SOGIPLLParams
from ..inner_fsmpc import FSMPCController, FSMPCParams
from ..outer_energy_pi import EnergyPI, EnergyPIParams
from ..ica_agent import ICAAgent
from ..comm.mqtt_pubsub import MQTTPubSub


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True, help="ICA agent id, e.g. ica1")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--T-s", type=float, default=20e-6)
    p.add_argument("--N-sub", type=int, default=5)
    p.add_argument("--load-kw", type=float, default=10.0,
                   help="Harmonic load active power per ICA (kW)")
    args = p.parse_args()

    print(f"[{args.id}] connecting to mqtt://{args.broker}:{args.port}")
    pubsub = MQTTPubSub(broker_host=args.broker, broker_port=args.port,
                       client_id=args.id)
    pubsub.connect(timeout=10.0)

    plant_p = PlantParams()
    inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=args.T_s))
    outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
    pll = SOGIPLL(SOGIPLLParams(T_s=args.T_s))
    plant = Plant(plant_p)
    load = HarmonicLoad(HarmonicLoadParams(P_fund=args.load_kw * 1e3))
    agent = ICAAgent(args.id, inner, outer, pll, pubsub, telemetry_decim=100)

    print(f"[{args.id}] running")
    t = 0.0
    last_print = 0.0
    while True:
        v_s = load.v_s(t)
        i_l = load.i_l(t)
        s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l)
        for _ in range(args.N_sub):
            plant.step(s, v_s, i_dc=0.0, dt=args.T_s / args.N_sub)
        t += args.T_s

        # Real-time pacing — keep simulation time loosely tied to wall-clock
        if int(t * 1e3) % 200 == 0 and t - last_print >= 0.2:
            last_print = t
            print(f"[{args.id}] t={t:.2f}s v_dc={plant.v_dc:.1f}V")
            time.sleep(0.001)


if __name__ == "__main__":
    main()
