from platforms.utils import vk_post_screenshot
from social_services.message import PostVKScreenshotMessage


class PostVKScreenshot:

    async def post_vk_screenshot(self, task_message: PostVKScreenshotMessage):
        await vk_post_screenshot(
            post_id=task_message.post_id,
            group_id=task_message.group_id,
            campaign_pk=task_message.campaign_pk
        )
        return True
