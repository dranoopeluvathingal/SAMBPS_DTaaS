# =============================================================================
# sambp / sambp_sync_oc
# config/study_cases.py
#
# Defines the set of simulation cases for batch studies.
# Each entry overrides the corresponding field in SYSTEM_CONFIG at run time.
# fault_type: "3PH" | "LL" | "SLG"
# =============================================================================

HIF_STUDY_CASES = [
    {"case_name": "hif_3ph_R050", "fault_type": "3PH", "fault_R_pu": 0.50, "fault_time": 0.10},
    {"case_name": "hif_3ph_R075", "fault_type": "3PH", "fault_R_pu": 0.75, "fault_time": 0.10},
    {"case_name": "hif_3ph_R100", "fault_type": "3PH", "fault_R_pu": 1.00, "fault_time": 0.10},
    {"case_name": "hif_3ph_R125", "fault_type": "3PH", "fault_R_pu": 1.25, "fault_time": 0.10},
    {"case_name": "hif_3ph_R150", "fault_type": "3PH", "fault_R_pu": 1.50, "fault_time": 0.10},
    {"case_name": "hif_slg_R050", "fault_type": "SLG", "fault_R_pu": 0.50, "fault_time": 0.10},
    {"case_name": "hif_slg_R075", "fault_type": "SLG", "fault_R_pu": 0.75, "fault_time": 0.10},
    {"case_name": "hif_slg_R100", "fault_type": "SLG", "fault_R_pu": 1.00, "fault_time": 0.10},
    {"case_name": "hif_slg_R125", "fault_type": "SLG", "fault_R_pu": 1.25, "fault_time": 0.10},
    {"case_name": "hif_slg_R150", "fault_type": "SLG", "fault_R_pu": 1.50, "fault_time": 0.10},
]

STUDY_CASES = [
    {
        "case_name":        "3ph_fault_low_R",
        "fault_type":  "3PH",
        "fault_R_pu":  0.01,
        "fault_time":  0.10,
    },
    {
        "case_name":        "ll_fault_mid_R",
        "fault_type":  "LL",
        "fault_R_pu":  0.05,
        "fault_time":  0.10,
    },
    {
        "case_name":        "slg_fault_high_R",
        "fault_type":  "SLG",
        "fault_R_pu":  0.15,
        "fault_time":  0.10,
    },
]
