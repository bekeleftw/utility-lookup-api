"""
Fallback templates for utility signup instructions.
Used when AI extraction fails or returns extraction_failed: true.
"""

FALLBACK_TEMPLATES = {
    "municipal_electric": {
        "signup_method": "multiple",
        "steps": [
            "Visit the utility's website or call their customer service number",
            "Provide your move-in address and desired start date",
            "Provide valid ID (driver's license or state ID)",
            "Social Security Number may be required for credit check",
            "Pay deposit if required"
        ],
        "required_documents": [
            "Government-issued ID",
            "Move-in date",
            "Lease agreement (sometimes required)"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Typically $50-200, may be waived with good credit",
            "waiver_conditions": "Good credit history or letter of credit from previous utility"
        },
        "timeline": "Usually 1-3 business days",
        "is_generic": True
    },
    
    "deregulated_electric_texas": {
        "signup_method": "online",
        "steps": [
            "Go to PowerToChoose.org (official state comparison site)",
            "Enter your ZIP code to see available plans",
            "Compare rates, contract terms, and customer reviews",
            "Select a plan and sign up directly with that retail provider",
            "The delivery utility will connect service automatically"
        ],
        "required_documents": [
            "Move-in address and date",
            "Government-issued ID",
            "Social Security Number (for credit check)"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Depends on provider and credit history",
            "waiver_conditions": None
        },
        "timeline": "Usually 1-2 business days after signup",
        "is_generic": True,
        "comparison_site": "https://powertochoose.org"
    },
    
    "deregulated_electric_pennsylvania": {
        "signup_method": "online",
        "steps": [
            "Go to PAPowerSwitch.com (official state comparison site)",
            "Enter your ZIP code to see available suppliers",
            "Compare rates and contract terms",
            "Select a supplier and sign up, or stay with default utility rate",
            "Your delivery utility handles the physical connection"
        ],
        "required_documents": [
            "Move-in address and date",
            "Government-issued ID",
            "Account number (if switching suppliers)"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Depends on supplier and credit history",
            "waiver_conditions": None
        },
        "timeline": "Usually 1-2 billing cycles to switch suppliers",
        "is_generic": True,
        "comparison_site": "https://www.papowerswitch.com"
    },
    
    "deregulated_electric_ohio": {
        "signup_method": "online",
        "steps": [
            "Go to EnergizeOhio.gov (official state comparison site)",
            "Enter your ZIP code to see available suppliers",
            "Compare rates and contract terms",
            "Select a supplier and sign up, or stay with default utility rate",
            "Your delivery utility handles the physical connection"
        ],
        "required_documents": [
            "Move-in address and date",
            "Government-issued ID",
            "Account number (if switching suppliers)"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Depends on supplier and credit history",
            "waiver_conditions": None
        },
        "timeline": "Usually 1-2 billing cycles to switch suppliers",
        "is_generic": True,
        "comparison_site": "https://energizeohio.gov"
    },
    
    "mud_water": {
        "signup_method": "phone",
        "steps": [
            "Call the MUD office during business hours",
            "Provide your move-in address and date",
            "Provide a copy of your signed lease",
            "Pay the required deposit"
        ],
        "required_documents": [
            "Signed lease agreement",
            "Government-issued ID",
            "Move-in date"
        ],
        "deposit": {
            "required": True,
            "amount": "Typically $100-200 (refundable)",
            "waiver_conditions": None
        },
        "timeline": "Usually 1-3 business days",
        "is_generic": True
    },
    
    "municipal_water": {
        "signup_method": "multiple",
        "steps": [
            "Visit the city utilities website or call customer service",
            "Provide your move-in address and desired start date",
            "Provide valid ID",
            "Pay deposit if required"
        ],
        "required_documents": [
            "Government-issued ID",
            "Move-in date"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Typically $50-150",
            "waiver_conditions": None
        },
        "timeline": "Usually 1-3 business days",
        "is_generic": True
    },
    
    "gas": {
        "signup_method": "multiple",
        "steps": [
            "Visit the utility's website or call customer service",
            "Provide your move-in address and desired start date",
            "Provide valid ID (driver's license or state ID)",
            "Schedule appointment if meter access is required",
            "Pay deposit if required"
        ],
        "required_documents": [
            "Government-issued ID",
            "Move-in date",
            "Social Security Number (sometimes required)"
        ],
        "deposit": {
            "required": "varies",
            "amount": "Typically $50-150, may be waived with good credit",
            "waiver_conditions": "Good credit history"
        },
        "timeline": "1-5 business days (may require technician visit)",
        "is_generic": True
    },
    
    "internet": {
        "signup_method": "online",
        "steps": [
            "Visit the provider's website",
            "Enter your address to check availability and see plans",
            "Select a plan and complete signup",
            "Schedule installation appointment",
            "Be present for technician visit (if required)"
        ],
        "required_documents": [
            "Move-in address",
            "Payment method"
        ],
        "deposit": {
            "required": False,
            "amount": "Typically no deposit, may have installation fee",
            "waiver_conditions": None
        },
        "timeline": "Installation typically scheduled within 3-7 days",
        "is_generic": True
    }
}


def get_fallback_template(utility_type: str, state: str = None, is_mud: bool = False, is_deregulated: bool = False) -> dict:
    """
    Get the appropriate fallback template based on utility type and context.
    
    Args:
        utility_type: electric, gas, water, internet
        state: Two-letter state code (for deregulated market detection)
        is_mud: True if this is a MUD/special district (for water)
        is_deregulated: True if in a deregulated electricity market
    
    Returns:
        Fallback template dict with signup instructions
    """
    if utility_type == "electric":
        if is_deregulated:
            if state == "TX":
                return FALLBACK_TEMPLATES["deregulated_electric_texas"].copy()
            elif state == "PA":
                return FALLBACK_TEMPLATES["deregulated_electric_pennsylvania"].copy()
            elif state == "OH":
                return FALLBACK_TEMPLATES["deregulated_electric_ohio"].copy()
            else:
                # Generic deregulated - use Texas as base
                return FALLBACK_TEMPLATES["deregulated_electric_texas"].copy()
        else:
            return FALLBACK_TEMPLATES["municipal_electric"].copy()
    
    elif utility_type == "water":
        if is_mud:
            return FALLBACK_TEMPLATES["mud_water"].copy()
        else:
            return FALLBACK_TEMPLATES["municipal_water"].copy()
    
    elif utility_type == "gas":
        return FALLBACK_TEMPLATES["gas"].copy()
    
    elif utility_type == "internet":
        return FALLBACK_TEMPLATES["internet"].copy()
    
    else:
        # Unknown type - return generic electric template
        return FALLBACK_TEMPLATES["municipal_electric"].copy()
