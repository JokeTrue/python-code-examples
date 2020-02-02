import logging

from bs4 import BeautifulSoup

from platforms.client.base import async_message_rate_limit
from platforms.client.sender import Sender
from platforms.client.vk import BaseVkClient
from platforms.utils import VK_MESSAGE_KEY
from platforms.utils.arguments import Argument

logger = logging.getLogger('django')
sentry_logger = logging.getLogger('sentry')


class VideoSaveMethod(BaseVkClient):
    METHOD = 'video.save'
    HTTP_METHOD = 'post'

    TOO_MUCH_REQUESTS_MSG = 'Too much requests'
    SERVICE_UNAVAILABLE = 'Page temporary unavailable'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'name': Argument(type=str, required=True),
        'link': Argument(type=str, required=True),
        'description': Argument(type=str, required=True),
        'group_id': Argument(type=int, default=None)
    }

    @staticmethod
    @async_message_rate_limit()
    async def toggle_upload_link(upload_url: str):
        try:
            response = await Sender.get(upload_url, {})
        except Exception as e:
            logger.error(e)
            if hasattr(e, 'doc'):
                msg = {
                    'url': upload_url,
                    'response': e.doc
                }
                if e.doc == VideoSaveMethod.TOO_MUCH_REQUESTS_MSG:
                    return e.doc
                elif bool(BeautifulSoup(e.doc, "html.parser").find()):
                    sentry_logger.error(msg=msg, extra={
                        'html': e.doc
                    })
                    return VideoSaveMethod.SERVICE_UNAVAILABLE
                else:
                    sentry_logger.error(msg=msg)

            return False

        return response.get(VK_MESSAGE_KEY.RESPONSE) == 1


class VideoDeleteMethod(BaseVkClient):
    METHOD = 'video.delete'
    HTTP_METHOD = 'post'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'video_id': Argument(type=int, required=True),
        'owner_id': Argument(type=int, required=True),
    }
