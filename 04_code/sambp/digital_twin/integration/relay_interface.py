# =============================================================================
# sambp / digital_twin / integration / relay_interface.py
#
# Generic relay adapter — hooks the DT into existing SAMBP relay modules.
#
# Each relay family (87L, 87T, 87B, OC) exposes a trip_event() or similar
# call.  RelayInterface wraps these with a standard event dict so the DT
# validation layer can consume events from any relay without knowing its
# internal structure.
#
# Design principles
# -----------------
#   • Non-invasive: relay code is NOT modified.  The adapter wraps outputs.
#   • One adapter instance per relay module.
#   • Relay modules may be absent (not yet imported) — adapters degrade
#     gracefully to 'UNKNOWN' events.
#   • GOOSE events from the IEC 61850 layer can be injected directly via
#     inject_goose_event() as if they came from a relay module.
#
# Event dict schema (canonical relay event)
# -----------------------------------------
#   {
#     'relay_id':   str   — e.g. 'LINE_87L_A', 'BUS_87B_1'
#     'element':    str   — protection element ('87L', '87T', '87B', 'OC', ...)
#     'action':     str   — 'TRIP' or 'BLOCK'
#     'fault_type': str   — 'SLG', 'LL', 'LLG', '3PH', 'HIF', 'UNKNOWN'
#     'k_ibr':      float — DT-estimated k_ibr at event time
#     'alpha':      float — DT-estimated alpha at event time
#     'kappa_n':    float — EKF condition number at event time
#     'residual':   float — EKF residual at event time
#     't_event':    float — event timestamp [s]
#   }
#
# Public API
# ----------
# iface = RelayInterface(relay_modules=[...])
# iface.attach(relay_id, relay_module)
# event = iface.wrap_87L_result(relay_id, result_dict, dt_state)
# event = iface.wrap_87T_result(relay_id, result_dict, dt_state)
# event = iface.wrap_87B_result(relay_id, result_dict, dt_state)
# event = iface.wrap_OC_result(relay_id, result_dict, dt_state)
# iface.inject_goose_event(goose_dict, dt_state)  → event dict
# =============================================================================


class RelayInterface:
    """
    Adapter between SAMBP relay module outputs and the DT event dict schema.

    Parameters
    ----------
    relay_modules : list
        Initial list of relay module instances.  Can be empty; attach()
        adds modules later.
    """

    def __init__(self, relay_modules=None):
        self._modules = {}   # relay_id → module instance
        for mod in (relay_modules or []):
            self.attach(getattr(mod, 'relay_id', repr(mod)), mod)

    # ------------------------------------------------------------------
    def attach(self, relay_id, module):
        """Attach a relay module under a given identifier."""
        self._modules[relay_id] = module

    # ------------------------------------------------------------------
    # 87L line differential
    # ------------------------------------------------------------------
    def wrap_87L_result(self, relay_id, result, dt_state, t_event=0.0):
        """
        Wrap line differential relay output into a DT event dict.

        Parameters
        ----------
        relay_id  : str
        result    : dict — from line_diff_baseline.py evaluate_differential()
                    Expected keys: tripped (bool), mode (str), i_op, i_rst
        dt_state  : dict — from EKFEstimator.update()
        t_event   : float — event timestamp [s]
        """
        tripped = result.get('tripped', False)
        mode    = result.get('mode', 'UNKNOWN')
        return self._build_event(
            relay_id  = relay_id,
            element   = '87L',
            action    = 'TRIP' if tripped else 'BLOCK',
            fault_type = result.get('fault_type', 'UNKNOWN'),
            dt_state  = dt_state,
            t_event   = t_event,
            extra     = {'mode': mode,
                         'i_op': result.get('i_op', 0.0),
                         'i_rst': result.get('i_rst', 0.0)},
        )

    # ------------------------------------------------------------------
    # 87T transformer differential
    # ------------------------------------------------------------------
    def wrap_87T_result(self, relay_id, result, dt_state, t_event=0.0):
        """
        Wrap transformer differential relay output.

        result keys: tripped (bool), block_reason (str or None),
                     i_diff_fund, k2_ratio, k5_ratio
        """
        tripped = result.get('tripped', False)
        block   = result.get('block_reason')
        return self._build_event(
            relay_id  = relay_id,
            element   = '87T',
            action    = 'TRIP' if tripped else 'BLOCK',
            fault_type = result.get('fault_type', 'UNKNOWN'),
            dt_state  = dt_state,
            t_event   = t_event,
            extra     = {'block_reason': block,
                         'i_diff':  result.get('i_diff_fund', 0.0),
                         'k2':      result.get('k2_ratio', 0.0),
                         'k5':      result.get('k5_ratio', 0.0)},
        )

    # ------------------------------------------------------------------
    # 87B bus differential
    # ------------------------------------------------------------------
    def wrap_87B_result(self, relay_id, result, dt_state, t_event=0.0):
        """
        Wrap bus differential relay output.

        result keys: tripped (bool), i_diff, eps_ct
        """
        tripped = result.get('tripped', False)
        return self._build_event(
            relay_id  = relay_id,
            element   = '87B',
            action    = 'TRIP' if tripped else 'BLOCK',
            fault_type = result.get('fault_type', 'UNKNOWN'),
            dt_state  = dt_state,
            t_event   = t_event,
            extra     = {'i_diff': result.get('i_diff', 0.0),
                         'eps_ct': result.get('eps_ct', 0.0)},
        )

    # ------------------------------------------------------------------
    # OC overcurrent
    # ------------------------------------------------------------------
    def wrap_OC_result(self, relay_id, result, dt_state, t_event=0.0):
        """
        Wrap overcurrent relay output.

        result keys: tripped (bool), t_op (float), element ('INST'/'TIME')
        """
        tripped = result.get('tripped', False)
        return self._build_event(
            relay_id  = relay_id,
            element   = 'OC',
            action    = 'TRIP' if tripped else 'BLOCK',
            fault_type = result.get('fault_type', 'UNKNOWN'),
            dt_state  = dt_state,
            t_event   = t_event,
            extra     = {'t_op':       result.get('t_op', None),
                         'oc_element': result.get('element', 'UNKNOWN')},
        )

    # ------------------------------------------------------------------
    # GOOSE injection
    # ------------------------------------------------------------------
    def inject_goose_event(self, goose_dict, dt_state, t_event=0.0):
        """
        Inject a raw IEC 61850 GOOSE event directly as a relay event.

        Parameters
        ----------
        goose_dict : dict — from goose_engine.py; must contain 'CSWI_Pos'
                     or similar trip indication, and 'LD' (logical device).
        dt_state   : dict
        """
        trip_bit = goose_dict.get('CSWI_Pos', goose_dict.get('trip', False))
        ld       = goose_dict.get('LD', 'UNKNOWN')
        element  = self._infer_element_from_ld(ld)
        return self._build_event(
            relay_id  = f'GOOSE:{ld}',
            element   = element,
            action    = 'TRIP' if trip_bit else 'BLOCK',
            fault_type = goose_dict.get('fault_type', 'UNKNOWN'),
            dt_state  = dt_state,
            t_event   = t_event,
            extra     = {'source': 'GOOSE', 'ld': ld},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_event(relay_id, element, action, fault_type,
                     dt_state, t_event, extra=None):
        event = {
            'relay_id':   relay_id,
            'element':    element,
            'action':     action,
            'fault_type': fault_type,
            'k_ibr':      dt_state.get('k_ibr',   0.0),
            'alpha':      dt_state.get('alpha',    0.5),
            'kappa_n':    dt_state.get('kappa_n',  1.0),
            'residual':   dt_state.get('residual', 0.0),
            't_event':    t_event,
        }
        if extra:
            event.update(extra)
        return event

    @staticmethod
    def _infer_element_from_ld(ld):
        """Infer relay element from IEC 61850 logical device name."""
        ld_upper = str(ld).upper()
        if '87L' in ld_upper or 'LINE' in ld_upper:
            return '87L'
        if '87T' in ld_upper or 'XFMR' in ld_upper or 'TRAFO' in ld_upper:
            return '87T'
        if '87B' in ld_upper or 'BUS' in ld_upper:
            return '87B'
        if 'OC' in ld_upper or '51' in ld_upper or '50' in ld_upper:
            return 'OC'
        return 'UNKNOWN'

    # ------------------------------------------------------------------
    def __repr__(self):
        return f"RelayInterface(attached={list(self._modules.keys())})"
