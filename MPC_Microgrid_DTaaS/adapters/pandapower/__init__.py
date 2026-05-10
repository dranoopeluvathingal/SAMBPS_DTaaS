"""Adapters between fs_mpc_mg.cmc.Topology and pandapower."""

from .topology_to_pp import topology_to_pandapower

__all__ = ["topology_to_pandapower"]
