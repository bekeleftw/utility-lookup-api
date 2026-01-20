"""
Phase 0: Monitoring and Metrics Module

Provides metrics tracking for utility lookups:
- Lookup latency by utility type
- Source usage tracking
- Confidence score distribution
- Error rate monitoring

Usage:
    from monitoring.metrics import track_lookup, get_metrics_summary

    # Track a lookup
    track_lookup('gas', result, latency_ms=1234)

    # Get summary
    summary = get_metrics_summary()
"""

import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetricsBucket:
    """Holds metrics for a time window."""
    window_start: str
    window_end: str
    
    # Counts
    total_lookups: int = 0
    successful_lookups: int = 0
    failed_lookups: int = 0
    
    # By utility type
    lookups_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # By source
    lookups_by_source: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Latency (in ms)
    latencies: List[float] = field(default_factory=list)
    
    # Confidence scores
    confidence_scores: List[int] = field(default_factory=list)
    
    # Errors
    errors: List[Dict] = field(default_factory=list)


class MetricsCollector:
    """
    Collects and aggregates metrics for utility lookups.
    
    Thread-safe singleton that accumulates metrics in memory
    and periodically flushes to disk.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._metrics_lock = threading.Lock()
        self._current_bucket = self._create_bucket()
        self._historical_buckets: List[MetricsBucket] = []
        
        # Configuration
        self._bucket_duration_minutes = 5
        self._max_historical_buckets = 288  # 24 hours at 5-min intervals
        self._metrics_dir = Path(__file__).parent.parent / 'data' / 'metrics'
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
    
    def _create_bucket(self) -> MetricsBucket:
        """Create a new metrics bucket for the current time window."""
        now = datetime.now()
        window_start = now.replace(second=0, microsecond=0)
        window_end = window_start + timedelta(minutes=self._bucket_duration_minutes)
        
        return MetricsBucket(
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat()
        )
    
    def _maybe_rotate_bucket(self):
        """Rotate to a new bucket if the current one has expired."""
        now = datetime.now()
        window_end = datetime.fromisoformat(self._current_bucket.window_end)
        
        if now >= window_end:
            # Archive current bucket
            self._historical_buckets.append(self._current_bucket)
            
            # Trim old buckets
            if len(self._historical_buckets) > self._max_historical_buckets:
                self._historical_buckets = self._historical_buckets[-self._max_historical_buckets:]
            
            # Create new bucket
            self._current_bucket = self._create_bucket()
    
    def track_lookup(
        self,
        utility_type: str,
        result: Optional[Dict],
        latency_ms: float,
        source: Optional[str] = None,
        error: Optional[str] = None
    ):
        """
        Track a utility lookup.
        
        Args:
            utility_type: 'electric', 'gas', or 'water'
            result: The lookup result dict
            latency_ms: Time taken in milliseconds
            source: The data source that provided the result
            error: Error message if lookup failed
        """
        with self._metrics_lock:
            self._maybe_rotate_bucket()
            bucket = self._current_bucket
            
            bucket.total_lookups += 1
            bucket.lookups_by_type[utility_type] += 1
            bucket.latencies.append(latency_ms)
            
            if result and result.get('NAME'):
                bucket.successful_lookups += 1
                
                # Track source
                src = source or result.get('_source', 'unknown')
                bucket.lookups_by_source[src] += 1
                
                # Track confidence
                conf = result.get('_confidence_score')
                if conf is not None:
                    bucket.confidence_scores.append(conf)
            else:
                bucket.failed_lookups += 1
                
                if error:
                    bucket.errors.append({
                        'utility_type': utility_type,
                        'error': error,
                        'timestamp': datetime.now().isoformat()
                    })
    
    def get_current_metrics(self) -> Dict:
        """Get metrics for the current time window."""
        with self._metrics_lock:
            self._maybe_rotate_bucket()
            return self._bucket_to_dict(self._current_bucket)
    
    def get_historical_metrics(self, hours: int = 1) -> List[Dict]:
        """Get historical metrics for the specified number of hours."""
        with self._metrics_lock:
            cutoff = datetime.now() - timedelta(hours=hours)
            
            result = []
            for bucket in self._historical_buckets:
                window_start = datetime.fromisoformat(bucket.window_start)
                if window_start >= cutoff:
                    result.append(self._bucket_to_dict(bucket))
            
            return result
    
    def _bucket_to_dict(self, bucket: MetricsBucket) -> Dict:
        """Convert a bucket to a dictionary with computed statistics."""
        latencies = bucket.latencies
        confidences = bucket.confidence_scores
        
        return {
            'window_start': bucket.window_start,
            'window_end': bucket.window_end,
            'total_lookups': bucket.total_lookups,
            'successful_lookups': bucket.successful_lookups,
            'failed_lookups': bucket.failed_lookups,
            'success_rate': (
                bucket.successful_lookups / bucket.total_lookups * 100
                if bucket.total_lookups > 0 else 0
            ),
            'lookups_by_type': dict(bucket.lookups_by_type),
            'lookups_by_source': dict(bucket.lookups_by_source),
            'latency': {
                'avg_ms': sum(latencies) / len(latencies) if latencies else 0,
                'p50_ms': sorted(latencies)[len(latencies) // 2] if latencies else 0,
                'p95_ms': sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else 0,
                'max_ms': max(latencies) if latencies else 0,
            },
            'confidence': {
                'avg': sum(confidences) / len(confidences) if confidences else 0,
                'min': min(confidences) if confidences else 0,
                'max': max(confidences) if confidences else 0,
            },
            'error_count': len(bucket.errors),
            'recent_errors': bucket.errors[-5:] if bucket.errors else [],
        }
    
    def get_summary(self) -> Dict:
        """Get a summary of all metrics."""
        current = self.get_current_metrics()
        historical = self.get_historical_metrics(hours=1)
        
        # Aggregate historical
        total_lookups = sum(h['total_lookups'] for h in historical) + current['total_lookups']
        total_success = sum(h['successful_lookups'] for h in historical) + current['successful_lookups']
        
        all_latencies = []
        for h in historical:
            # We don't have raw latencies in historical, so use averages
            if h['latency']['avg_ms'] > 0:
                all_latencies.append(h['latency']['avg_ms'])
        
        return {
            'current_window': current,
            'last_hour': {
                'total_lookups': total_lookups,
                'successful_lookups': total_success,
                'success_rate': total_success / total_lookups * 100 if total_lookups > 0 else 0,
                'avg_latency_ms': sum(all_latencies) / len(all_latencies) if all_latencies else 0,
            },
            'buckets_count': len(historical) + 1,
        }
    
    def flush_to_disk(self):
        """Flush current metrics to disk."""
        with self._metrics_lock:
            metrics_file = self._metrics_dir / f"metrics_{datetime.now().strftime('%Y%m%d')}.json"
            
            # Load existing data
            existing = []
            if metrics_file.exists():
                try:
                    with open(metrics_file, 'r') as f:
                        existing = json.load(f)
                except:
                    pass
            
            # Add current bucket
            existing.append(self._bucket_to_dict(self._current_bucket))
            
            # Write back
            with open(metrics_file, 'w') as f:
                json.dump(existing, f, indent=2)
            
            logger.info(f"Flushed metrics to {metrics_file}")


# Global collector instance
_collector = MetricsCollector()


def track_lookup(
    utility_type: str,
    result: Optional[Dict],
    latency_ms: float,
    source: Optional[str] = None,
    error: Optional[str] = None
):
    """
    Track a utility lookup.
    
    Args:
        utility_type: 'electric', 'gas', or 'water'
        result: The lookup result dict
        latency_ms: Time taken in milliseconds
        source: The data source that provided the result
        error: Error message if lookup failed
    
    Example:
        start = time.time()
        result = lookup_gas(...)
        track_lookup('gas', result, (time.time() - start) * 1000)
    """
    _collector.track_lookup(utility_type, result, latency_ms, source, error)


def get_metrics_summary() -> Dict:
    """Get a summary of current metrics."""
    return _collector.get_summary()


def get_current_metrics() -> Dict:
    """Get metrics for the current time window."""
    return _collector.get_current_metrics()


def flush_metrics():
    """Flush metrics to disk."""
    _collector.flush_to_disk()


# Context manager for timing lookups
class LookupTimer:
    """
    Context manager for timing and tracking lookups.
    
    Example:
        with LookupTimer('gas') as timer:
            result = lookup_gas(...)
            timer.set_result(result)
    """
    
    def __init__(self, utility_type: str):
        self.utility_type = utility_type
        self.start_time = None
        self.result = None
        self.source = None
        self.error = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = (time.time() - self.start_time) * 1000
        
        if exc_type is not None:
            self.error = str(exc_val)
        
        track_lookup(
            self.utility_type,
            self.result,
            latency_ms,
            self.source,
            self.error
        )
        
        return False  # Don't suppress exceptions
    
    def set_result(self, result: Optional[Dict], source: Optional[str] = None):
        """Set the lookup result."""
        self.result = result
        self.source = source or (result.get('_source') if result else None)


if __name__ == "__main__":
    # Demo/test
    print("Testing metrics collection...")
    
    # Simulate some lookups
    for i in range(10):
        track_lookup(
            'electric',
            {'NAME': 'Test Utility', '_confidence_score': 85, '_source': 'test'},
            latency_ms=100 + i * 10
        )
    
    for i in range(5):
        track_lookup(
            'gas',
            {'NAME': 'Gas Utility', '_confidence_score': 75, '_source': 'hifld'},
            latency_ms=200 + i * 20
        )
    
    # Track a failure
    track_lookup('water', None, latency_ms=50, error='No water utility found')
    
    # Print summary
    summary = get_metrics_summary()
    print(json.dumps(summary, indent=2))
