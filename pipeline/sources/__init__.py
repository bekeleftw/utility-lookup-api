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

from .water import (
    MunicipalWaterSource,
    StateGISWaterSource,
    SpecialDistrictWaterSource,
    EPAWaterSource,
    CountyDefaultWaterSource,
)

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
    # Water
    'MunicipalWaterSource',
    'StateGISWaterSource',
    'SpecialDistrictWaterSource',
    'EPAWaterSource',
    'CountyDefaultWaterSource',
]
