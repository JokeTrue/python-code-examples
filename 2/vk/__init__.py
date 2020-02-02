import logging

from raven.handlers.logging import SentryHandler

sentry_logger = logging.getLogger('sentry')
sentry_logger.addHandler(SentryHandler())

logger = logging.getLogger('django')



