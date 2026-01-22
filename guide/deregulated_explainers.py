"""
Deregulated market explainer content for resident guides.
Included when the address is in a deregulated electricity market.
"""

# Texas ERCOT delivery utilities with phone numbers
TEXAS_DELIVERY_UTILITIES = {
    "oncor": {
        "name": "Oncor",
        "phone": "(888) 313-4747",
        "website": "https://www.oncor.com"
    },
    "centerpoint": {
        "name": "CenterPoint Energy",
        "phone": "(800) 332-7143",
        "website": "https://www.centerpointenergy.com"
    },
    "aep_texas": {
        "name": "AEP Texas",
        "phone": "(866) 223-8508",
        "website": "https://www.aeptexas.com"
    },
    "tnmp": {
        "name": "Texas-New Mexico Power (TNMP)",
        "phone": "(888) 866-7456",
        "website": "https://www.tnmp.com"
    }
}


def get_texas_ercot_explainer(delivery_utility_name: str, delivery_utility_phone: str, zip_code: str) -> dict:
    """
    Generate Texas ERCOT deregulated market explainer content.
    
    Args:
        delivery_utility_name: Name of the transmission/delivery utility (e.g., "Oncor")
        delivery_utility_phone: Phone number for the delivery utility
        zip_code: ZIP code for the address
    
    Returns:
        Dict with explainer content sections
    """
    return {
        "title": "ABOUT YOUR ELECTRIC SERVICE",
        "intro": "This property is in a deregulated electricity market. Here's what that means:",
        "sections": [
            {
                "heading": "DELIVERY vs. RETAIL - TWO SEPARATE COMPANIES",
                "content": f"{delivery_utility_name} delivers electricity to your home through the power lines. You don't choose this company - they're assigned based on your location. Contact them for outages or emergencies.\n\nYou choose your Retail Electric Provider (REP). This is the company that sets your rate, sends your bill, and handles your account. Dozens of REPs compete for your business, which typically means lower rates."
            },
            {
                "heading": "HOW TO SET UP ELECTRIC SERVICE",
                "steps": [
                    "Go to PowerToChoose.org (official state comparison site)",
                    f"Enter your ZIP code: {zip_code}",
                    "Compare plans by rate, contract length, and customer reviews",
                    "Select a plan and sign up directly with that REP",
                    f"The REP notifies {delivery_utility_name}, who connects your service",
                    "Service typically starts within 1-2 business days"
                ]
            },
            {
                "heading": "WHAT YOU'LL NEED",
                "items": [
                    "Move-in address and date",
                    "Government-issued ID",
                    "Social Security Number (for credit check)",
                    "Payment method"
                ]
            },
            {
                "heading": "TIPS",
                "items": [
                    "Fixed-rate plans lock in your price; variable rates can change monthly",
                    "Check the \"Electricity Facts Label\" for true all-in cost",
                    "Avoid plans with high minimum usage charges if you have a small unit"
                ]
            },
            {
                "heading": "WHAT IF YOU DON'T CHOOSE?",
                "content": "If you don't select a REP, you'll be assigned a \"Provider of Last Resort\" at a higher rate. Always choose your own provider to save money."
            },
            {
                "heading": "OUTAGES & EMERGENCIES",
                "content": f"Power outage? Contact {delivery_utility_name} at {delivery_utility_phone}. Your REP cannot restore power - only the delivery utility handles the physical infrastructure."
            }
        ],
        "comparison_site": {
            "name": "PowerToChoose.org",
            "url": "https://powertochoose.org"
        }
    }


def get_pennsylvania_explainer(utility_name: str) -> dict:
    """
    Generate Pennsylvania deregulated market explainer content.
    
    Args:
        utility_name: Name of the default/delivery utility
    
    Returns:
        Dict with explainer content sections
    """
    return {
        "title": "ABOUT YOUR ELECTRIC SERVICE",
        "intro": "Pennsylvania has electric choice. You have a default utility that delivers power, but you can shop for a competitive supplier for potentially lower rates.",
        "sections": [
            {
                "heading": "YOUR DEFAULT UTILITY",
                "content": f"{utility_name} delivers electricity and will serve you automatically if you don't choose a supplier."
            },
            {
                "heading": "YOUR CHOICE",
                "content": f"Shop for competitive suppliers at PAPowerSwitch.com\n\nYou can:\n• Stay with {utility_name}'s default rate (no action needed)\n• Choose a competitive supplier for a potentially lower rate\n\nService is seamless either way - {utility_name} still delivers the power and handles outages."
            }
        ],
        "comparison_site": {
            "name": "PAPowerSwitch.com",
            "url": "https://www.papowerswitch.com"
        }
    }


def get_ohio_explainer(utility_name: str) -> dict:
    """
    Generate Ohio deregulated market explainer content.
    
    Args:
        utility_name: Name of the default/delivery utility
    
    Returns:
        Dict with explainer content sections
    """
    return {
        "title": "ABOUT YOUR ELECTRIC SERVICE",
        "intro": "Ohio has electric choice. You have a default utility that delivers power, but you can shop for a competitive supplier.",
        "sections": [
            {
                "heading": "YOUR DEFAULT UTILITY",
                "content": f"{utility_name} delivers electricity and will serve you automatically if you don't choose a supplier."
            },
            {
                "heading": "YOUR CHOICE",
                "content": f"Shop for competitive suppliers at EnergizeOhio.gov\n\nYou can:\n• Stay with {utility_name}'s default rate (no action needed)\n• Choose a competitive supplier for a potentially lower rate"
            }
        ],
        "comparison_site": {
            "name": "EnergizeOhio.gov",
            "url": "https://energizeohio.gov"
        }
    }


def get_deregulated_explainer(state: str, utility_name: str, delivery_utility_key: str = None, zip_code: str = None) -> dict:
    """
    Get the appropriate deregulated market explainer based on state.
    
    Args:
        state: Two-letter state code
        utility_name: Name of the utility from lookup results
        delivery_utility_key: For Texas, the key to look up delivery utility info
        zip_code: ZIP code for the address (used in Texas explainer)
    
    Returns:
        Dict with explainer content, or None if not a deregulated state
    """
    if state == "TX":
        # Try to match delivery utility
        delivery_info = None
        utility_lower = utility_name.lower() if utility_name else ""
        
        for key, info in TEXAS_DELIVERY_UTILITIES.items():
            if key in utility_lower or info["name"].lower() in utility_lower:
                delivery_info = info
                break
        
        if not delivery_info:
            # Default to Oncor (most common in Texas)
            delivery_info = TEXAS_DELIVERY_UTILITIES["oncor"]
        
        return get_texas_ercot_explainer(
            delivery_utility_name=delivery_info["name"],
            delivery_utility_phone=delivery_info["phone"],
            zip_code=zip_code or "your ZIP code"
        )
    
    elif state == "PA":
        return get_pennsylvania_explainer(utility_name or "Your local utility")
    
    elif state == "OH":
        return get_ohio_explainer(utility_name or "Your local utility")
    
    else:
        return None


def is_deregulated_state(state: str) -> bool:
    """Check if a state has deregulated electricity markets."""
    # States with significant retail choice
    # Note: Some states have partial deregulation or only commercial choice
    DEREGULATED_STATES = {"TX", "PA", "OH", "IL", "NY", "NJ", "MD", "CT", "MA", "ME", "NH", "RI"}
    return state in DEREGULATED_STATES
