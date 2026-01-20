"""
Data source implementations for the utility lookup pipeline.
"""

from .electric import (
    StateGISElectricSource,
    MunicipalElectricSource,
    CoopSource,
    EIASource,
    HIFLDElectricSource,
    CountyDefaultElectricSource,
)

from .gas import (
    StateGISGasSource,
    MunicipalGasSource,
    ZIPMappingGasSource,
    HIFLDGasSource,
    CountyDefaultGasSource,
)

from .corrections import UserCorrectionSource

__all__ = [
    # Corrections (highest priority)
    'UserCorrectionSource',
    # Electric
    'StateGISElectricSource',
    'MunicipalElectricSource',
    'CoopSource',
    'EIASource',
    'HIFLDElectricSource',
    'CountyDefaultElectricSource',
    # Gas
    'StateGISGasSource',
    'MunicipalGasSource',
    'ZIPMappingGasSource',
    'HIFLDGasSource',
    'CountyDefaultGasSource',
]
