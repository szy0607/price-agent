import logging
from app.core.trace import get_trace_id
_FORMAT = "%(asctime)s %(levelname)-8s [%(trace_id)s] %(name)s: %(message)s"
class TraceIdFilter(logging.Filter):
    def filter(self, record:logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        return True
def setup_logging(level:int = logging.INFO) -> None:
    #输出到控制台
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(TraceIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
