"""Inner FS-MPC unit tests."""

import numpy as np

from fs_mpc_mg.inner_fsmpc import FSMPCController, FSMPCParams
from fs_mpc_mg.plant import Plant, PlantParams, SWITCHING_VECTORS


def test_picks_a_valid_switching_vector():
    ctrl = FSMPCController(FSMPCParams())
    s = ctrl.update(
        i_m=np.zeros(3),
        v_dc=900.0,
        v_s=np.array([310.0, -155.0, -155.0]),
        i_s_ref=np.array([100.0, -50.0, -50.0]),
        i_l=np.zeros(3),
    )
    assert s.shape == (3,)
    # output must be one of the 8 switching vectors
    assert any(np.allclose(s, sv) for sv in SWITCHING_VECTORS)


def test_step_response_no_load():
    """Closed-loop FS-MPC drives plant current toward step reference."""
    plant_p = PlantParams(L=1e-3, r=50e-3, v_dc_init=900.0)
    plant = Plant(plant_p)
    ctrl_p = FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6, use_delay_compensation=True)
    ctrl = FSMPCController(ctrl_p)

    # Constant grid voltage (frozen for deterministic test)
    v_s = np.array([310.0, -155.0, -155.0])
    # Step reference
    i_s_ref = np.array([50.0, -25.0, -25.0])

    T_s = ctrl_p.T_s
    N = 200  # 200 ticks = 4 ms — well past expected settle
    err = []
    for k in range(N):
        s = ctrl.update(plant.i_m, plant.v_dc, v_s, i_s_ref, np.zeros(3))
        # Sub-step the plant 5x for stability
        for _ in range(5):
            plant.step(s, v_s, i_dc=0.0, dt=T_s / 5)
        err.append(np.linalg.norm(plant.i_m - i_s_ref))

    # Average error in last 50 samples should be small relative to ref magnitude
    mean_err_tail = float(np.mean(err[-50:]))
    ref_mag = float(np.linalg.norm(i_s_ref))
    assert mean_err_tail / ref_mag < 0.25, (
        f"FS-MPC failed to track: tail-mean-err={mean_err_tail:.2f}, ref_mag={ref_mag:.2f}"
    )
