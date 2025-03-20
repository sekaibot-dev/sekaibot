import structlog

logger = structlog.get_logger()

try:
    1 / 0
except ZeroDivisionError as exc:
    logger.error("Error occurred", exc_info=exc, a="a")  # ✅ 详细异常信息
    logger.exception("Exception occurred")        # ✅ 详细异常信息
