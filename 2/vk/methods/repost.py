import traceback

from application.settings import ENABLED_POSTING_SCREENSHOT
from core.models import (
    Post,
    User,
    AdvertisingCampaign,
    Group,
    CustomCampaign,
    GroupPostImgs
)
from platforms.utils import VK_MESSAGE_KEY
from platforms.vk import sentry_logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.wall import WallRepost
from social_services.message import RepostTaskMessage
from social_services.social_service import SocialService


class Repost(VKBasePlatform):

    async def repost(self, task_message: RepostTaskMessage):
        post = Post.objects.get(pk=task_message.post_id)

        user = User.objects.get(pk=task_message.user_id)
        campaign = AdvertisingCampaign.objects.get(pk=task_message.campaign_id)
        group = Group.objects.get(pk=task_message.target_group_id)

        custom_campaign = CustomCampaign.objects.filter(user=user, campaign=campaign)
        text = campaign.text if not custom_campaign else custom_campaign.first().text

        social_uid, access_token = self._get_vk_credentials(user=user)
        post_link = campaign.link.split('=')[1]

        method = WallRepost(
            access_token=access_token,
            priority=task_message.priority,
            object=post_link,
            message=text,
            group_id=str(group.group_id)
        )

        response_dict = await method.execute()
        response = response_dict.get(VK_MESSAGE_KEY.RESPONSE, {})

        try:
            if response.get("success"):
                post.status = Post.IS_ACTIVE
                post.post_id = response.get("post_id")
                post.save()

                post_screen_exists = GroupPostImgs.objects.filter(group__group_id=post.group.group_id,
                                                                  campaign__pk=post.campaign.pk).first()

                if not post_screen_exists and ENABLED_POSTING_SCREENSHOT:
                    SocialService.post_vk_screenshot(
                        post_id=post.post_id,
                        group_id=post.group.group_id,
                        campaign_pk=post.campaign.pk
                    )
            else:
                post.status = Post.FAILED
                post.vk_response = response
                post.save()

                return False
        except Exception as e:
            traceback_log = traceback.format_exc()
            sentry_logger.error(msg=e, extra={
                'trace': traceback_log,
                'locals': locals()
            })
        return True
