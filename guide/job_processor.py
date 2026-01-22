"""
Background job processor for guide generation.
Handles the async workflow: logo retrieval → instruction extraction → PDF generation → email.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def process_guide_request(request_id: str, db_connection=None):
    """
    Main job processor for guide requests.
    
    Steps:
    1. Update status to "processing"
    2. Retrieve logo (if website provided)
    3. Get instructions for each utility
    4. Compile guide data
    5. Generate PDF
    6. Create shareable link
    7. Send email
    8. Update status to "completed"
    
    Args:
        request_id: UUID of the guide request
        db_connection: Database connection
    """
    from .logo_retrieval import retrieve_logo, download_and_store_logo
    from .instruction_extraction import get_utility_instructions
    from .deregulated_explainers import get_deregulated_explainer, is_deregulated_state
    from .pdf_generator import generate_guide_pdf, save_pdf_to_storage
    from .guide_api import generate_short_code
    
    logger.info(f"Processing guide request: {request_id}")
    
    try:
        cursor = db_connection.cursor()
        
        # Step 1: Get request data and update status
        cursor.execute("""
            UPDATE guide_requests SET status = 'processing', processed_at = NOW()
            WHERE id = %s
            RETURNING address, address_components, utility_results, email, company_name, website
        """, (request_id,))
        
        row = cursor.fetchone()
        if not row:
            logger.error(f"Guide request not found: {request_id}")
            return
        
        address, address_components, utility_results, email, company_name, website = row
        db_connection.commit()
        
        # Parse JSON if needed
        if isinstance(address_components, str):
            address_components = json.loads(address_components)
        if isinstance(utility_results, str):
            utility_results = json.loads(utility_results)
        
        state = address_components.get("state", "")
        zip_code = address_components.get("zip", "")
        
        logger.info(f"Processing guide for {address}, company: {company_name}")
        
        # Step 2: Retrieve logo
        logo_url = None
        if website:
            logger.info(f"Retrieving logo from {website}")
            raw_logo_url = retrieve_logo(website, company_name)
            if raw_logo_url:
                logo_url = download_and_store_logo(raw_logo_url, str(request_id))
                
                # Update request with logo URL
                cursor.execute("""
                    UPDATE guide_requests SET logo_url = %s WHERE id = %s
                """, (logo_url, request_id))
                db_connection.commit()
        
        # Step 3: Get instructions for each utility
        compiled_utilities = {}
        
        utilities_data = utility_results.get("utilities", {})
        
        # Process electric
        electric = utilities_data.get("electric")
        if electric:
            electric_list = electric if isinstance(electric, list) else [electric]
            primary_electric = electric_list[0]
            
            is_deregulated = primary_electric.get("_is_deregulated", False)
            
            # Generate utility ID from name
            utility_id = primary_electric.get("name", "").lower().replace(" ", "_")
            
            instructions = get_utility_instructions(
                utility_id=utility_id,
                utility_name=primary_electric.get("name", "Unknown"),
                utility_type="electric",
                website_url=primary_electric.get("website"),
                state=state,
                is_deregulated=is_deregulated,
                db_connection=db_connection
            )
            
            compiled_utilities["electric"] = {
                "name": primary_electric.get("name", "Unknown"),
                "phone": primary_electric.get("phone"),
                "website": primary_electric.get("website"),
                "instructions": instructions
            }
        
        # Process gas
        gas = utilities_data.get("gas")
        if gas:
            gas_list = gas if isinstance(gas, list) else [gas]
            primary_gas = gas_list[0]
            
            utility_id = primary_gas.get("name", "").lower().replace(" ", "_")
            
            instructions = get_utility_instructions(
                utility_id=utility_id,
                utility_name=primary_gas.get("name", "Unknown"),
                utility_type="gas",
                website_url=primary_gas.get("website"),
                state=state,
                db_connection=db_connection
            )
            
            compiled_utilities["gas"] = {
                "name": primary_gas.get("name", "Unknown"),
                "phone": primary_gas.get("phone"),
                "website": primary_gas.get("website"),
                "instructions": instructions
            }
        
        # Process water
        water = utilities_data.get("water")
        if water:
            water_list = water if isinstance(water, list) else [water]
            primary_water = water_list[0]
            
            # Check if MUD/special district
            water_name = primary_water.get("name", "").lower()
            is_mud = "mud" in water_name or "municipal utility district" in water_name
            
            utility_id = primary_water.get("name", "").lower().replace(" ", "_")
            
            instructions = get_utility_instructions(
                utility_id=utility_id,
                utility_name=primary_water.get("name", "Unknown"),
                utility_type="water",
                website_url=primary_water.get("website"),
                state=state,
                is_mud=is_mud,
                db_connection=db_connection
            )
            
            compiled_utilities["water"] = {
                "name": primary_water.get("name", "Unknown"),
                "phone": primary_water.get("phone"),
                "website": primary_water.get("website"),
                "instructions": instructions
            }
        
        # Process internet (may have multiple providers)
        internet = utilities_data.get("internet", {})
        providers = internet.get("providers", [])
        if providers:
            compiled_utilities["internet"] = []
            for provider in providers[:3]:  # Limit to top 3
                utility_id = provider.get("name", "").lower().replace(" ", "_")
                
                instructions = get_utility_instructions(
                    utility_id=utility_id,
                    utility_name=provider.get("name", "Unknown"),
                    utility_type="internet",
                    website_url=provider.get("website"),
                    state=state,
                    db_connection=db_connection
                )
                
                compiled_utilities["internet"].append({
                    "name": provider.get("name", "Unknown"),
                    "phone": provider.get("phone"),
                    "website": provider.get("website"),
                    "technology": provider.get("technology"),
                    "max_download_mbps": provider.get("max_download_mbps"),
                    "instructions": instructions
                })
        
        # Step 4: Get deregulated market explainer if applicable
        deregulated_explainer = None
        if compiled_utilities.get("electric"):
            electric_data = utilities_data.get("electric")
            if electric_data:
                electric_list = electric_data if isinstance(electric_data, list) else [electric_data]
                is_deregulated = electric_list[0].get("_is_deregulated", False)
                
                if is_deregulated or is_deregulated_state(state):
                    utility_name = compiled_utilities["electric"]["name"]
                    deregulated_explainer = get_deregulated_explainer(
                        state=state,
                        utility_name=utility_name,
                        zip_code=zip_code
                    )
        
        # Step 5: Compile full guide data
        guide_data = {
            "address": address,
            "address_components": address_components,
            "company_name": company_name,
            "logo_url": logo_url,
            "utilities": compiled_utilities,
            "deregulated_explainer": deregulated_explainer,
            "generated_at": datetime.now().isoformat()
        }
        
        # Step 6: Generate PDF
        logger.info("Generating PDF")
        pdf_bytes = generate_guide_pdf(
            address=address,
            company_name=company_name,
            logo_url=logo_url,
            company_website=website,
            utilities=compiled_utilities,
            deregulated_explainer=deregulated_explainer
        )
        
        # Save PDF
        street = address_components.get("street", "address").replace(" ", "-").replace(",", "")
        pdf_filename = f"Utility-Guide-{street}-{request_id}.pdf"
        pdf_url = save_pdf_to_storage(pdf_bytes, pdf_filename)
        
        # Step 7: Create shareable link
        short_code = generate_short_code()
        
        cursor.execute("""
            INSERT INTO guide_outputs (guide_request_id, short_code, pdf_url, guide_data)
            VALUES (%s, %s, %s, %s)
        """, (request_id, short_code, pdf_url, json.dumps(guide_data)))
        db_connection.commit()
        
        base_url = os.getenv('BASE_URL', 'https://utilityprofit.com')
        shareable_url = f"{base_url}/u/{short_code}"
        
        logger.info(f"Guide created: {shareable_url}")
        
        # Step 8: Send email
        logger.info(f"Sending email to {email}")
        send_guide_email(
            to_email=email,
            address=address,
            pdf_url=pdf_url,
            pdf_bytes=pdf_bytes,
            shareable_url=shareable_url,
            company_name=company_name
        )
        
        # Update status to completed
        cursor.execute("""
            UPDATE guide_requests 
            SET status = 'completed', emailed_at = NOW()
            WHERE id = %s
        """, (request_id,))
        db_connection.commit()
        
        logger.info(f"Guide request completed: {request_id}")
        
    except Exception as e:
        logger.error(f"Guide processing failed: {e}", exc_info=True)
        
        # Update status to failed
        if db_connection:
            try:
                cursor = db_connection.cursor()
                cursor.execute("""
                    UPDATE guide_requests 
                    SET status = 'failed', error_message = %s
                    WHERE id = %s
                """, (str(e), request_id))
                db_connection.commit()
            except:
                pass


def send_guide_email(
    to_email: str,
    address: str,
    pdf_url: str,
    pdf_bytes: bytes,
    shareable_url: str,
    company_name: str
):
    """
    Send the guide email via Customer.io.
    
    Args:
        to_email: Recipient email
        address: Property address
        pdf_url: URL to the PDF
        pdf_bytes: PDF content for attachment
        shareable_url: Shareable link URL
        company_name: PM's company name
    """
    import requests
    import base64
    
    CUSTOMERIO_API_KEY = os.getenv("CUSTOMERIO_API_KEY")
    CUSTOMERIO_SITE_ID = os.getenv("CUSTOMERIO_SITE_ID")
    
    if not CUSTOMERIO_API_KEY:
        logger.warning("CUSTOMERIO_API_KEY not set - skipping email")
        return
    
    # Customer.io Transactional API
    # https://customer.io/docs/api/#tag/Transactional
    
    # Extract street for filename
    street = address.split(",")[0].replace(" ", "-") if "," in address else "address"
    
    try:
        # Encode PDF as base64 for attachment
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        payload = {
            "transactional_message_id": "resident_guide_ready",  # Create this template in Customer.io
            "to": to_email,
            "identifiers": {
                "email": to_email
            },
            "message_data": {
                "address": address,
                "shareable_url": shareable_url,
                "pdf_url": pdf_url,
                "company_name": company_name
            },
            "attachments": [
                {
                    "name": f"Utility-Guide-{street}.pdf",
                    "data": pdf_base64
                }
            ]
        }
        
        response = requests.post(
            "https://api.customer.io/v1/send/email",
            headers={
                "Authorization": f"Bearer {CUSTOMERIO_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"Email sent successfully to {to_email}")
        else:
            logger.error(f"Email send failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        # Don't raise - email failure shouldn't fail the whole job


def setup_redis_worker():
    """
    Set up Redis/RQ worker for background job processing.
    Run this as a separate process: python -m guide.job_processor worker
    """
    from redis import Redis
    from rq import Worker, Queue
    
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("guide_jobs", connection=redis_conn)
    
    worker = Worker([queue], connection=redis_conn)
    worker.work()


def enqueue_guide_job(request_id: str, db_connection):
    """
    Enqueue a guide processing job.
    
    Args:
        request_id: UUID of the guide request
        db_connection: Database connection to pass to worker
    """
    REDIS_URL = os.getenv("REDIS_URL")
    
    if REDIS_URL:
        from redis import Redis
        from rq import Queue
        
        redis_conn = Redis.from_url(REDIS_URL)
        queue = Queue("guide_jobs", connection=redis_conn)
        
        job = queue.enqueue(
            process_guide_request,
            request_id,
            job_timeout=300  # 5 minute timeout
        )
        logger.info(f"Enqueued guide job: {job.id}")
        return job.id
    else:
        # No Redis - process synchronously (for development)
        logger.warning("REDIS_URL not set - processing synchronously")
        process_guide_request(request_id, db_connection)
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        print("Starting RQ worker...")
        setup_redis_worker()
    else:
        print("Usage: python -m guide.job_processor worker")
