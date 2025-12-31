"""
Helper functions for determining if an alert should run based on frequency.
"""
from datetime import datetime, timedelta

def should_run_alert(last_run_str: str, frequency: str) -> bool:
    """
    Determine if an alert should run based on its frequency and last run time.
    
    Args:
        last_run_str: ISO format timestamp string of last run
        frequency: One of 'hourly', 'daily', 'weekly', 'biweekly', 'monthly'
    
    Returns:
        True if alert should run, False otherwise
    """
    if not last_run_str:
        return True  # Never run before
    
    try:
        last_run = datetime.fromisoformat(last_run_str)
    except:
        return True  # Invalid timestamp, run anyway
    
    now = datetime.now()
    time_since_last = now - last_run
    
    # Frequency thresholds
    if frequency == 'hourly':
        return time_since_last >= timedelta(hours=1)
    elif frequency == 'daily':
        return time_since_last >= timedelta(days=1)
    elif frequency == 'weekly':
        return time_since_last >= timedelta(weeks=1)
    elif frequency == 'biweekly':
        return time_since_last >= timedelta(weeks=2)
    elif frequency == 'monthly':
        return time_since_last >= timedelta(days=30)
    else:
        return time_since_last >= timedelta(days=1)  # Default to daily

def get_frequency_display(frequency: str) -> str:
    """Get human-readable frequency label."""
    labels = {
        'hourly': '⚡ Hourly',
        'daily': '📅 Daily',
        'weekly': '📆 Weekly',
        'biweekly': '📆 Bi-weekly',
        'monthly': '📆 Monthly'
    }
    return labels.get(frequency, frequency)
