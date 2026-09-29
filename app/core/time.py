import datetime


def utc_now_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def get_current_time() -> datetime.datetime:
    """Backward-compatible UTC clock used by the existing auth flow."""
    return utc_now_naive()
