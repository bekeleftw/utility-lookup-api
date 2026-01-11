# User Feedback System

## Context

Users who actually live at an address are the most reliable source of utility provider data. When our system returns the wrong provider, users should be able to submit corrections. After multiple users confirm the same correction, it should automatically update our data.

## Goal

- Accept user corrections via API endpoint
- Track pending corrections
- Auto-confirm when multiple users agree
- Provide dashboard to review feedback

## Implementation

### Step 1: Create Feedback Storage

Create file: `/data/feedback/pending.json`
```json
{}
```

Create file: `/data/feedback/confirmed.json`
```json
{}
```

### Step 2: Add Feedback Endpoint to api.py

```python
from datetime import datetime
import json
import os

FEEDBACK_DIR = os.path.join(os.path.dirname(__file__), 'data', 'feedback')

def load_feedback(filename):
    filepath = os.path.join(FEEDBACK_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}

def save_feedback(filename, data):
    filepath = os.path.join(FEEDBACK_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """
    Accept user corrections for utility providers.
    
    Request body:
    {
        "address": "301 Treasure Trove Path, Kyle, TX 78640",
        "zip_code": "78640",
        "utility_type": "gas",
        "returned_provider": "Texas Gas Service",
        "correct_provider": "CenterPoint Energy",
        "source": "resident",
        "email": null
    }
    """
    data = request.get_json()
    
    # Validate required fields
    required = ['address', 'utility_type', 'returned_provider', 'correct_provider']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Validate utility type
    valid_types = ['electric', 'gas', 'water', 'internet']
    if data['utility_type'] not in valid_types:
        return jsonify({"error": f"Invalid utility_type. Must be one of: {valid_types}"}), 400
    
    # Generate feedback ID
    import hashlib
    feedback_id = 'fb_' + hashlib.md5(
        f"{data['address']}_{data['utility_type']}_{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    
    # Create feedback record
    feedback_record = {
        "feedback_id": feedback_id,
        "address": data['address'],
        "zip_code": data.get('zip_code', extract_zip(data['address'])),
        "utility_type": data['utility_type'],
        "returned_provider": data['returned_provider'],
        "correct_provider": data['correct_provider'],
        "source": data.get('source', 'unknown'),
        "email": data.get('email'),
        "submitted_at": datetime.now().isoformat(),
        "status": "pending",
        "confirmation_count": 1
    }
    
    # Load pending feedback
    pending = load_feedback('pending.json')
    
    # Check if similar feedback already exists (same ZIP + utility + correction)
    correction_key = f"{feedback_record['zip_code']}_{data['utility_type']}_{data['correct_provider']}"
    
    existing = None
    for fid, record in pending.items():
        existing_key = f"{record['zip_code']}_{record['utility_type']}_{record['correct_provider']}"
        if existing_key == correction_key:
            existing = fid
            break
    
    if existing:
        # Increment confirmation count
        pending[existing]['confirmation_count'] += 1
        pending[existing]['addresses'] = pending[existing].get('addresses', [])
        pending[existing]['addresses'].append(data['address'])
        
        # Auto-confirm if threshold reached
        if pending[existing]['confirmation_count'] >= 3:
            auto_confirm_feedback(existing, pending[existing])
            del pending[existing]
            save_feedback('pending.json', pending)
            return jsonify({
                "status": "auto_confirmed",
                "feedback_id": existing,
                "message": "Correction confirmed by multiple users and applied."
            })
        
        save_feedback('pending.json', pending)
        return jsonify({
            "status": "confirmation_added",
            "feedback_id": existing,
            "confirmation_count": pending[existing]['confirmation_count'],
            "message": f"Thanks! {pending[existing]['confirmation_count']}/3 confirmations for this correction."
        })
    
    # New feedback
    pending[feedback_id] = feedback_record
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "received",
        "feedback_id": feedback_id,
        "message": "Thank you. This correction will be reviewed."
    })


def auto_confirm_feedback(feedback_id, feedback_record):
    """
    When 3+ users confirm same correction, auto-apply it.
    """
    # Load confirmed feedback
    confirmed = load_feedback('confirmed.json')
    
    # Add to confirmed
    feedback_record['status'] = 'auto_confirmed'
    feedback_record['confirmed_at'] = datetime.now().isoformat()
    confirmed[feedback_id] = feedback_record
    save_feedback('confirmed.json', confirmed)
    
    # Add to override table based on utility type
    zip_code = feedback_record['zip_code']
    utility_type = feedback_record['utility_type']
    correct_provider = feedback_record['correct_provider']
    
    if utility_type == 'gas':
        add_gas_zip_override(zip_code, correct_provider, f"User feedback ({feedback_record['confirmation_count']} confirmations)")
    elif utility_type == 'electric':
        add_electric_zip_override(zip_code, correct_provider, f"User feedback ({feedback_record['confirmation_count']} confirmations)")
    elif utility_type == 'water':
        add_water_override(feedback_record.get('city'), feedback_record.get('state'), correct_provider)
    
    print(f"Auto-confirmed feedback {feedback_id}: {zip_code} {utility_type} → {correct_provider}")


def extract_zip(address):
    """Extract ZIP code from address string."""
    import re
    match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
    return match.group(1) if match else None


@app.route('/api/feedback/dashboard', methods=['GET'])
def feedback_dashboard():
    """
    Internal dashboard showing feedback status.
    """
    pending = load_feedback('pending.json')
    confirmed = load_feedback('confirmed.json')
    
    # Sort pending by confirmation count (highest first)
    pending_sorted = sorted(
        pending.values(),
        key=lambda x: x.get('confirmation_count', 0),
        reverse=True
    )
    
    # Recent confirmed
    confirmed_sorted = sorted(
        confirmed.values(),
        key=lambda x: x.get('confirmed_at', ''),
        reverse=True
    )[:20]
    
    # Stats by ZIP
    zip_stats = {}
    for record in list(pending.values()) + list(confirmed.values()):
        zip_code = record.get('zip_code', 'unknown')
        if zip_code not in zip_stats:
            zip_stats[zip_code] = {'pending': 0, 'confirmed': 0}
        if record.get('status') == 'pending':
            zip_stats[zip_code]['pending'] += 1
        else:
            zip_stats[zip_code]['confirmed'] += 1
    
    # Top problem ZIPs
    problem_zips = sorted(
        zip_stats.items(),
        key=lambda x: x[1]['pending'] + x[1]['confirmed'],
        reverse=True
    )[:10]
    
    return jsonify({
        "summary": {
            "pending_count": len(pending),
            "confirmed_count": len(confirmed),
            "total_feedback": len(pending) + len(confirmed)
        },
        "pending": pending_sorted[:20],
        "recent_confirmed": confirmed_sorted,
        "problem_zips": problem_zips
    })


@app.route('/api/feedback/<feedback_id>/confirm', methods=['POST'])
def manually_confirm_feedback(feedback_id):
    """
    Manually confirm a pending feedback item (admin action).
    """
    pending = load_feedback('pending.json')
    
    if feedback_id not in pending:
        return jsonify({"error": "Feedback not found"}), 404
    
    record = pending[feedback_id]
    auto_confirm_feedback(feedback_id, record)
    del pending[feedback_id]
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "confirmed",
        "feedback_id": feedback_id,
        "message": "Feedback confirmed and override applied."
    })


@app.route('/api/feedback/<feedback_id>/reject', methods=['POST'])
def reject_feedback(feedback_id):
    """
    Reject a pending feedback item (admin action).
    """
    pending = load_feedback('pending.json')
    
    if feedback_id not in pending:
        return jsonify({"error": "Feedback not found"}), 404
    
    record = pending[feedback_id]
    record['status'] = 'rejected'
    record['rejected_at'] = datetime.now().isoformat()
    
    # Move to confirmed file (for record keeping)
    confirmed = load_feedback('confirmed.json')
    confirmed[feedback_id] = record
    save_feedback('confirmed.json', confirmed)
    
    del pending[feedback_id]
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "rejected",
        "feedback_id": feedback_id
    })
```

### Step 3: Add Override Helper Functions

Add to `state_utility_verification.py`:

```python
def add_gas_zip_override(zip_code, provider_name, source):
    """Add a ZIP code override for gas utility."""
    # Load existing overrides
    overrides = load_gas_zip_overrides()
    
    overrides[zip_code] = {
        "provider": provider_name,
        "source": source,
        "added_at": datetime.now().isoformat()
    }
    
    save_gas_zip_overrides(overrides)
    print(f"Added gas override: {zip_code} → {provider_name}")


def add_electric_zip_override(zip_code, provider_name, source):
    """Add a ZIP code override for electric utility."""
    overrides = load_electric_zip_overrides()
    
    overrides[zip_code] = {
        "provider": provider_name,
        "source": source,
        "added_at": datetime.now().isoformat()
    }
    
    save_electric_zip_overrides(overrides)
    print(f"Added electric override: {zip_code} → {provider_name}")


def add_water_override(city, state, provider_name):
    """Add a city-level override for water utility."""
    # Load supplemental water file
    filepath = 'water_utilities_supplemental.json'
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    key = f"{state}|{city}".upper()
    data[key] = {
        "name": provider_name,
        "source": "user_feedback",
        "added_at": datetime.now().isoformat()
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Added water override: {city}, {state} → {provider_name}")
```

### Step 4: Create Data Directory

```bash
mkdir -p data/feedback
echo '{}' > data/feedback/pending.json
echo '{}' > data/feedback/confirmed.json
```

## Testing

### Test 1: Submit New Feedback
```bash
curl -X POST https://web-production-9acc6.up.railway.app/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "address": "301 Treasure Trove Path, Kyle, TX 78640",
    "zip_code": "78640",
    "utility_type": "gas",
    "returned_provider": "Texas Gas Service",
    "correct_provider": "CenterPoint Energy",
    "source": "resident"
  }'
```

Expected: `{"status": "received", "feedback_id": "fb_xxx", ...}`

### Test 2: Submit Duplicate (Should Increment Count)
```bash
curl -X POST https://web-production-9acc6.up.railway.app/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "address": "123 Other St, Kyle, TX 78640",
    "zip_code": "78640",
    "utility_type": "gas",
    "returned_provider": "Texas Gas Service",
    "correct_provider": "CenterPoint Energy",
    "source": "resident"
  }'
```

Expected: `{"status": "confirmation_added", "confirmation_count": 2, ...}`

### Test 3: View Dashboard
```bash
curl https://web-production-9acc6.up.railway.app/api/feedback/dashboard
```

### Test 4: Manually Confirm
```bash
curl -X POST https://web-production-9acc6.up.railway.app/api/feedback/fb_xxx/confirm
```

## Commit Message

```
Add user feedback system for utility corrections

- POST /api/feedback - submit corrections
- GET /api/feedback/dashboard - view pending/confirmed
- POST /api/feedback/:id/confirm - manual confirmation
- POST /api/feedback/:id/reject - reject feedback
- Auto-confirm when 3+ users submit same correction
- Auto-apply confirmed corrections to override tables
```
