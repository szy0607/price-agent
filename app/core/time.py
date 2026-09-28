from datetime import datetime, timezone


def get_current_time()->datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
