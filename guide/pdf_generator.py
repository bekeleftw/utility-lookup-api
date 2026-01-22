"""
PDF generation service for resident utility guides.
Uses WeasyPrint to generate branded PDFs.
"""

import os
from typing import Dict, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Utility Profit brand color
BRAND_GREEN = "#7AC143"

PDF_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: letter;
            margin: 0.75in;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
        }}
        
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid {brand_color};
        }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .company-logo {{
            max-height: 50px;
            max-width: 180px;
        }}
        
        .company-name {{
            font-size: 18pt;
            font-weight: 600;
            color: #333;
        }}
        
        .header-right {{
            text-align: right;
            color: #666;
            font-size: 10pt;
        }}
        
        .address-block {{
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
        }}
        
        .address-label {{
            font-size: 9pt;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }}
        
        .address {{
            font-size: 14pt;
            font-weight: 500;
        }}
        
        .utility-section {{
            margin-bottom: 25px;
            page-break-inside: avoid;
        }}
        
        .utility-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 15px;
            background: {brand_color};
            color: white;
            border-radius: 6px 6px 0 0;
        }}
        
        .utility-icon {{
            font-size: 18pt;
        }}
        
        .utility-type {{
            font-size: 12pt;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .utility-body {{
            border: 1px solid #ddd;
            border-top: none;
            border-radius: 0 0 6px 6px;
            padding: 15px;
        }}
        
        .utility-name {{
            font-size: 14pt;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        
        .utility-contact {{
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            font-size: 10pt;
            color: #555;
        }}
        
        .utility-contact span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        
        .section-title {{
            font-size: 10pt;
            font-weight: 600;
            color: #333;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 15px 0 8px 0;
            padding-bottom: 5px;
            border-bottom: 1px solid #eee;
        }}
        
        .steps {{
            margin: 0;
            padding-left: 20px;
        }}
        
        .steps li {{
            margin-bottom: 5px;
        }}
        
        .requirements {{
            margin: 0;
            padding-left: 20px;
            list-style-type: disc;
        }}
        
        .requirements li {{
            margin-bottom: 3px;
        }}
        
        .info-row {{
            display: flex;
            gap: 30px;
            margin-top: 10px;
        }}
        
        .info-item {{
            flex: 1;
        }}
        
        .info-label {{
            font-size: 9pt;
            color: #666;
            text-transform: uppercase;
        }}
        
        .info-value {{
            font-size: 10pt;
            font-weight: 500;
        }}
        
        .signup-link {{
            display: inline-block;
            margin-top: 10px;
            padding: 8px 15px;
            background: {brand_color};
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 10pt;
            font-weight: 500;
        }}
        
        .deregulated-section {{
            background: #fff8e6;
            border: 1px solid #ffd966;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        
        .deregulated-title {{
            font-size: 12pt;
            font-weight: 600;
            color: #b8860b;
            margin-bottom: 10px;
        }}
        
        .deregulated-content {{
            font-size: 10pt;
        }}
        
        .deregulated-content h4 {{
            font-size: 10pt;
            font-weight: 600;
            margin: 12px 0 5px 0;
        }}
        
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            font-size: 9pt;
            color: #666;
            text-align: center;
        }}
        
        .footer-brand {{
            margin-top: 10px;
            font-size: 8pt;
            color: #999;
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""


def generate_utility_section(
    utility_type: str,
    utility_name: str,
    phone: Optional[str],
    website: Optional[str],
    instructions: Dict
) -> str:
    """Generate HTML for a single utility section."""
    
    icons = {
        "electric": "⚡",
        "gas": "🔥",
        "water": "💧",
        "internet": "📶"
    }
    
    icon = icons.get(utility_type, "📋")
    
    # Build contact info
    contact_parts = []
    if phone:
        contact_parts.append(f'<span>📞 {phone}</span>')
    if website:
        contact_parts.append(f'<span>🌐 {website}</span>')
    contact_html = ''.join(contact_parts) if contact_parts else ''
    
    # Build steps
    steps = instructions.get("steps", [])
    steps_html = ""
    if steps:
        steps_items = ''.join(f'<li>{step}</li>' for step in steps)
        steps_html = f'''
        <div class="section-title">How to Start Service</div>
        <ol class="steps">{steps_items}</ol>
        '''
    
    # Build requirements
    requirements = instructions.get("required_documents", [])
    requirements_html = ""
    if requirements:
        req_items = ''.join(f'<li>{req}</li>' for req in requirements)
        requirements_html = f'''
        <div class="section-title">What You'll Need</div>
        <ul class="requirements">{req_items}</ul>
        '''
    
    # Build deposit and timeline info
    deposit = instructions.get("deposit", {})
    deposit_text = ""
    if deposit:
        if deposit.get("required") == True:
            deposit_text = f"Required: {deposit.get('amount', 'Amount varies')}"
        elif deposit.get("required") == False:
            deposit_text = "Not required"
        else:
            deposit_text = deposit.get("amount", "May be required")
    
    timeline = instructions.get("timeline", "")
    
    info_html = ""
    if deposit_text or timeline:
        info_html = '<div class="info-row">'
        if deposit_text:
            info_html += f'''
            <div class="info-item">
                <div class="info-label">Deposit</div>
                <div class="info-value">{deposit_text}</div>
            </div>
            '''
        if timeline:
            info_html += f'''
            <div class="info-item">
                <div class="info-label">Timeline</div>
                <div class="info-value">{timeline}</div>
            </div>
            '''
        info_html += '</div>'
    
    # Signup link
    signup_url = instructions.get("online_signup_url")
    signup_html = ""
    if signup_url:
        signup_html = f'<a href="{signup_url}" class="signup-link">Start Service Online →</a>'
    
    return f'''
    <div class="utility-section">
        <div class="utility-header">
            <span class="utility-icon">{icon}</span>
            <span class="utility-type">{utility_type.upper()}</span>
        </div>
        <div class="utility-body">
            <div class="utility-name">{utility_name}</div>
            <div class="utility-contact">{contact_html}</div>
            {steps_html}
            {requirements_html}
            {info_html}
            {signup_html}
        </div>
    </div>
    '''


def generate_deregulated_section(explainer: Dict) -> str:
    """Generate HTML for deregulated market explainer."""
    
    sections_html = ""
    for section in explainer.get("sections", []):
        heading = section.get("heading", "")
        content = section.get("content", "")
        steps = section.get("steps", [])
        items = section.get("items", [])
        
        section_html = f'<h4>{heading}</h4>'
        
        if content:
            # Convert newlines to <br> and bullet points
            content = content.replace('\n• ', '<br>• ')
            content = content.replace('\n', '<br>')
            section_html += f'<p>{content}</p>'
        
        if steps:
            steps_items = ''.join(f'<li>{step}</li>' for step in steps)
            section_html += f'<ol>{steps_items}</ol>'
        
        if items:
            items_list = ''.join(f'<li>{item}</li>' for item in items)
            section_html += f'<ul>{items_list}</ul>'
        
        sections_html += section_html
    
    comparison = explainer.get("comparison_site", {})
    comparison_html = ""
    if comparison:
        comparison_html = f'<p><strong>Compare plans at:</strong> <a href="{comparison.get("url")}">{comparison.get("name")}</a></p>'
    
    return f'''
    <div class="deregulated-section">
        <div class="deregulated-title">{explainer.get("title", "About Your Electric Service")}</div>
        <div class="deregulated-content">
            <p>{explainer.get("intro", "")}</p>
            {sections_html}
            {comparison_html}
        </div>
    </div>
    '''


def generate_guide_pdf(
    address: str,
    company_name: str,
    logo_url: Optional[str],
    company_website: Optional[str],
    utilities: Dict,
    deregulated_explainer: Optional[Dict] = None
) -> bytes:
    """
    Generate a PDF guide.
    
    Args:
        address: Full property address
        company_name: PM's company name
        logo_url: URL to PM's logo (optional)
        company_website: PM's website (optional)
        utilities: Dict of utility data with instructions
            {
                "electric": {"name": "...", "phone": "...", "website": "...", "instructions": {...}},
                "gas": {...},
                "water": {...},
                "internet": {...}
            }
        deregulated_explainer: Deregulated market explainer content (optional)
    
    Returns:
        PDF bytes
    """
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        logger.error("WeasyPrint not installed. Run: pip install weasyprint")
        raise
    
    # Build header
    if logo_url:
        header_left = f'''
        <div class="header-left">
            <img src="{logo_url}" class="company-logo" alt="{company_name}">
        </div>
        '''
    else:
        header_left = f'''
        <div class="header-left">
            <span class="company-name">{company_name}</span>
        </div>
        '''
    
    header = f'''
    <div class="header">
        {header_left}
        <div class="header-right">
            Utility Setup Guide
        </div>
    </div>
    '''
    
    # Address block
    address_block = f'''
    <div class="address-block">
        <div class="address-label">Property Address</div>
        <div class="address">{address}</div>
    </div>
    '''
    
    # Utility sections
    utility_sections = ""
    utility_order = ["electric", "gas", "water", "internet"]
    
    for utility_type in utility_order:
        utility_data = utilities.get(utility_type)
        if not utility_data:
            continue
        
        # Handle multiple providers (internet)
        if isinstance(utility_data, list):
            for provider in utility_data:
                utility_sections += generate_utility_section(
                    utility_type=utility_type,
                    utility_name=provider.get("name", "Unknown"),
                    phone=provider.get("phone"),
                    website=provider.get("website"),
                    instructions=provider.get("instructions", {})
                )
        else:
            utility_sections += generate_utility_section(
                utility_type=utility_type,
                utility_name=utility_data.get("name", "Unknown"),
                phone=utility_data.get("phone"),
                website=utility_data.get("website"),
                instructions=utility_data.get("instructions", {})
            )
        
        # Add deregulated explainer after electric section
        if utility_type == "electric" and deregulated_explainer:
            utility_sections += generate_deregulated_section(deregulated_explainer)
    
    # Footer
    generated_date = datetime.now().strftime("%B %d, %Y")
    footer_contact = f'<br>{company_website}' if company_website else ''
    
    footer = f'''
    <div class="footer">
        Generated {generated_date}<br>
        Questions? Contact {company_name}{footer_contact}
        <div class="footer-brand">
            ━━━<br>
            Powered by Utility Profit<br>
            utilityprofit.com
        </div>
    </div>
    '''
    
    # Combine all content
    content = header + address_block + utility_sections + footer
    
    # Generate PDF
    html = PDF_TEMPLATE.format(content=content, brand_color=BRAND_GREEN)
    pdf_bytes = HTML(string=html).write_pdf()
    
    return pdf_bytes


def save_pdf_to_storage(pdf_bytes: bytes, filename: str) -> str:
    """
    Save PDF to cloud storage.
    
    Args:
        pdf_bytes: PDF content
        filename: Desired filename
    
    Returns:
        URL to stored PDF
    """
    # TODO: Implement R2/S3 storage
    # For now, save locally and return a placeholder URL
    
    local_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'guides', filename)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    
    with open(local_path, 'wb') as f:
        f.write(pdf_bytes)
    
    logger.info(f"PDF saved locally to {local_path}")
    
    # In production, return the R2/S3 URL
    return f"file://{local_path}"
