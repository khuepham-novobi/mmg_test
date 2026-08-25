from backend.config import EnvironmentConfig

from .base import OdooAdapter, OdooRPC, OdooRPCError, QA_MARKER
from .odoo15 import Odoo15Adapter
from .odoo19 import Odoo19Adapter

_BY_VERSION = {"15": Odoo15Adapter, "19": Odoo19Adapter}


def get_adapter(env: EnvironmentConfig) -> OdooAdapter:
    try:
        return _BY_VERSION[str(env.version)](env)
    except KeyError:
        raise ValueError(
            f"No adapter for Odoo version '{env.version}'. "
            f"Known versions: {sorted(_BY_VERSION)}")


__all__ = ["get_adapter", "OdooAdapter", "OdooRPC", "OdooRPCError",
           "QA_MARKER", "Odoo15Adapter", "Odoo19Adapter"]
