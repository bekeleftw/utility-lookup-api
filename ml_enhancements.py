#!/usr/bin/env python3
"""
Machine learning enhancements for utility lookups.
Includes active learning, ensemble predictions, and anomaly detection.
"""

import json
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import math


SOURCE_WEIGHTS = {
    "special_district": 0.95,
    "municipal_utility": 0.92,
    "user_confirmed": 0.90,
    "utility_direct_api": 0.90,
    "parcel_data": 0.88,
    "state_puc_map": 0.85,
    "serp_verified": 0.85,
    "eia_861": 0.75,
    "hifld": 0.70,
    "epa_sdwis": 0.65,
    "heuristic": 0.50,
    "inference": 0.60,
    "unknown": 0.40
}

LOOKUP_HISTORY_FILE = Path(__file__).parent / "data" / "lookup_history.json"
ANOMALY_LOG_FILE = Path(__file__).parent / "data" / "anomaly_log.json"

_lookup_history = None


def load_lookup_history() -> Dict:
    global _lookup_history
    if _lookup_history is not None:
        return _lookup_history
    if LOOKUP_HISTORY_FILE.exists():
        try:
            with open(LOOKUP_HISTORY_FILE, 'r') as f:
                _lookup_history = json.load(f)
        except:
            _lookup_history = {"lookups": [], "stats": {}}
    else:
        _lookup_history = {"lookups": [], "stats": {}}
    return _lookup_history


def save_lookup_history(history: Dict) -> None:
    try:
        LOOKUP_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOOKUP_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except IOError:
        pass


def get_typical_utilities(zip_code: str) -> Dict:
    history = load_lookup_history()
    stats = history.get("stats", {}).get(zip_code)
    if not stats or stats.get("count", 0) < 3:
        return {}
    
    result = {}
    for utility_type in ["electric", "gas", "water"]:
        type_stats = stats.get(utility_type, {})
        if type_stats and isinstance(type_stats, dict):
            most_common = max(type_stats.items(), key=lambda x: x[1], default=(None, 0))
            if most_common[0]:
                result[utility_type] = most_common[0]
    return result


def ensemble_prediction(sources_results: Dict) -> Dict:
    """Combine predictions from multiple sources using learned weights."""
    predictions = defaultdict(float)
    source_details = []
    
    for source, result in sources_results.items():
        if result and result.get("utility"):
            weight = SOURCE_WEIGHTS.get(source, 0.5)
            utility = result["utility"]
            predictions[utility] += weight
            source_details.append({
                "source": source,
                "utility": utility,
                "weight": weight
            })
    
    if not predictions:
        return {"utility": None, "confidence": 0, "method": "ensemble_no_data"}
    
    best = max(predictions.items(), key=lambda x: x[1])
    total_weight = sum(predictions.values())
    
    return {
        "utility": best[0],
        "ensemble_score": best[1],
        "confidence": best[1] / total_weight if total_weight > 0 else 0,
        "method": "ensemble_model",
        "sources_used": source_details
    }


def calculate_verification_value(
    confidence: float,
    source_reliability: float,
    is_unique_area: bool,
    lookup_count: int
) -> float:
    """Calculate value of verifying an address (for active learning)."""
    uncertainty = 1.0 - confidence
    source_uncertainty = 1.0 - source_reliability
    uniqueness_bonus = 1.5 if is_unique_area else 1.0
    traffic_factor = math.log(lookup_count + 1) / 10.0
    
    value = (uncertainty * 0.4 + source_uncertainty * 0.3 + traffic_factor * 0.3) * uniqueness_bonus
    return min(value, 1.0)


def prioritize_verification_queue(pending_lookups: List[Dict]) -> List[Tuple[float, Dict]]:
    """Build queue of addresses most needing verification."""
    scored = []
    for lookup in pending_lookups:
        score = calculate_verification_value(
            confidence=lookup.get("confidence_score", 0.5),
            source_reliability=SOURCE_WEIGHTS.get(lookup.get("source", "unknown"), 0.5),
            is_unique_area=lookup.get("is_unique_area", False),
            lookup_count=lookup.get("lookup_count", 1)
        )
        scored.append((score, lookup))
    return sorted(scored, key=lambda x: x[0], reverse=True)


def detect_anomalies(result: Dict, zip_code: str) -> List[Dict]:
    """Flag results that seem anomalous based on patterns."""
    anomalies = []
    typical = get_typical_utilities(zip_code)
    
    if not typical:
        return anomalies
    
    for utility_type in ["electric", "gas", "water"]:
        returned = None
        if utility_type in result and isinstance(result[utility_type], dict):
            returned = result[utility_type].get("name")
        
        expected = typical.get(utility_type)
        
        if returned and expected and returned.lower() != expected.lower():
            anomalies.append({
                "type": "atypical_utility",
                "utility_type": utility_type,
                "returned": returned,
                "typical_for_zip": expected,
                "zip_code": zip_code,
                "action": "flag_for_review",
                "severity": "medium"
            })
    
    return anomalies


def log_anomaly(anomaly: Dict) -> None:
    """Log an anomaly for review."""
    try:
        anomalies = []
        if ANOMALY_LOG_FILE.exists():
            with open(ANOMALY_LOG_FILE, 'r') as f:
                anomalies = json.load(f)
        
        anomaly["timestamp"] = datetime.now().isoformat()
        anomalies.append(anomaly)
        
        if len(anomalies) > 1000:
            anomalies = anomalies[-1000:]
        
        ANOMALY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ANOMALY_LOG_FILE, 'w') as f:
            json.dump(anomalies, f, indent=2)
    except:
        pass


def get_source_weight(source: str) -> float:
    """Get the reliability weight for a source."""
    return SOURCE_WEIGHTS.get(source.lower().replace(" ", "_"), 0.5)


def update_source_weight(source: str, was_correct: bool, learning_rate: float = 0.01) -> None:
    """Update source weight based on feedback (online learning)."""
    source_key = source.lower().replace(" ", "_")
    current = SOURCE_WEIGHTS.get(source_key, 0.5)
    
    if was_correct:
        SOURCE_WEIGHTS[source_key] = min(current + learning_rate, 0.99)
    else:
        SOURCE_WEIGHTS[source_key] = max(current - learning_rate, 0.1)


if __name__ == "__main__":
    print("ML Enhancements Tests:")
    print("=" * 60)
    
    print("\n1. Ensemble Prediction Test:")
    test_sources = {
        "municipal_utility": {"utility": "Austin Energy"},
        "eia_861": {"utility": "Austin Energy"},
        "heuristic": {"utility": "Pedernales Electric"},
    }
    result = ensemble_prediction(test_sources)
    print(f"   Winner: {result['utility']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    
    print("\n2. Verification Priority Test:")
    test_lookups = [
        {"confidence_score": 0.9, "source": "municipal_utility", "lookup_count": 100},
        {"confidence_score": 0.5, "source": "heuristic", "lookup_count": 5},
        {"confidence_score": 0.7, "source": "eia_861", "lookup_count": 50},
    ]
    prioritized = prioritize_verification_queue(test_lookups)
    print("   Priority order:")
    for score, lookup in prioritized:
        print(f"     Score {score:.3f}: conf={lookup['confidence_score']}, src={lookup['source']}")
    
    print("\n3. Source Weights:")
    for source, weight in sorted(SOURCE_WEIGHTS.items(), key=lambda x: -x[1]):
        print(f"   {source}: {weight:.2f}")
