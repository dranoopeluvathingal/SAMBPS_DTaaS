# =============================================================================
# sambp / digital_twin
#
# SAMBP Digital Twin Lab — core package
#
# Architecture (5-layer, mirrors relay families):
#   1. models/          — state-space model, scenario library, protection mirror
#   2. estimation/      — RLS (TR-43) and EKF (TR-44) state estimators
#   3. validation/      — decision comparator + flag engine (TR-45)
#   4. integration/     — relay adapter hooks (87L / 87T / 87B / OC)
#   5. run_dt_lab.py    — unified study runner
#
# Public API (import from here)
# -----------------------------
# from sambp.digital_twin import DTEngine
#
# engine = DTEngine(relay_modules=[line_diff, transformer_diff, bus_diff])
# engine.update(t, v_abc, i_abc)        # call at 1 kHz
# result = engine.validate(relay_event) # call after each relay trip/block
# =============================================================================

from .models.state_space_model  import IBRStateSpaceModel
from .models.scenario_library   import ScenarioLibrary
from .models.protection_mirror  import ProtectionMirror
from .estimation.rls_estimator  import RLSEstimator
from .estimation.ekf_estimator  import EKFEstimator
from .validation.decision_comparator import DecisionComparator
from .validation.flag_engine    import FlagEngine
from .integration.relay_interface import RelayInterface


class DTEngine:
    """
    Top-level Digital Twin engine.

    Wraps all sub-modules into a single object suitable for use in study
    runners and (eventually) real-time relay integration.

    Parameters
    ----------
    dt_rate_hz : float
        Update rate in Hz. Default 1000 (1 kHz, TR-43 §2.1).
    n_scenarios : int
        Size of pre-computed scenario library. Default 1000.
    estimator : {'rls', 'ekf'}
        Which state estimator to use. 'rls' is lighter (TR-43);
        'ekf' is multi-parameter (TR-44).
    relay_modules : list, optional
        List of relay module instances to attach via RelayInterface.
    """

    def __init__(self, dt_rate_hz=1000, n_scenarios=1000,
                 estimator='ekf', relay_modules=None):
        self.dt_rate_hz = dt_rate_hz
        self.dt_period  = 1.0 / dt_rate_hz

        # Sub-modules
        self.model    = IBRStateSpaceModel()
        self.library  = ScenarioLibrary(n_scenarios=n_scenarios)
        self.mirror   = ProtectionMirror()

        if estimator == 'rls':
            self.estimator = RLSEstimator()
        else:
            self.estimator = EKFEstimator()

        self.comparator = DecisionComparator(self.mirror)
        self.flags      = FlagEngine()
        self.interface  = RelayInterface(relay_modules or [])

        self._t = 0.0

    # ------------------------------------------------------------------
    def update(self, t, v_abc, i_abc):
        """
        Run one DT cycle (call at dt_rate_hz).

        Parameters
        ----------
        t     : float  — current time [s]
        v_abc : array  — three-phase voltage measurements [pu]
        i_abc : array  — three-phase current measurements [pu]

        Returns
        -------
        state : dict with keys k_ibr, z_line, alpha, f_gfm (estimated values)
        """
        self._t = t
        state = self.estimator.update(t, v_abc, i_abc)
        self.model.push(state)
        return state

    # ------------------------------------------------------------------
    def validate(self, relay_event):
        """
        Compare relay decision against DT expectation.

        Parameters
        ----------
        relay_event : dict
            Must contain keys: 'element' (str), 'action' ('TRIP'/'BLOCK'),
            'k_ibr' (float), 'alpha' (float), 'fault_type' (str).

        Returns
        -------
        result : dict with keys: verdict ('AGREE'/'FLAG'), reason, flag_type
        """
        dt_expected = self.library.nearest(
            relay_event['k_ibr'], relay_event.get('alpha', 0.5))
        result = self.comparator.compare(relay_event, dt_expected)
        self.flags.record(result)
        return result

    # ------------------------------------------------------------------
    @property
    def flag_summary(self):
        return self.flags.summary()
