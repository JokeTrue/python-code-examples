from application.settings import ENABLED_POSTING_SCREENSHOT
from core.models import (
    Post,
    User,
    AdvertisingCampaign,
    Group,
    CustomCampaign,
    GroupPostImgs
)
from platforms.utils import (
    format_group_id,
    VK_MESSAGE_KEY
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.wall import WallPostMethod
from social_services.message import VideoPostTaskMessage
from social_services.social_service import SocialService


class VideoPost(VKBasePlatform):

    async def video_post(self, task_message: VideoPostTaskMessage):
        post = Post.objects.get(pk=task_message.post_id)

        user = User.objects.get(pk=task_message.user_id)
        campaign = AdvertisingCampaign.objects.get(pk=task_message.campaign_id)
        group = Group.objects.get(pk=task_message.target_group_id)

        custom_campaign = CustomCampaign.objects.filter(user=user, campaign=campaign)
        text = campaign.text if not custom_campaign else custom_campaign.first().text

        social_uid, access_token = self._get_vk_credentials(user=user)
        video_owner, video_vid = campaign.link.split('video-')[1].split('_')

        method = WallPostMethod(
            access_token=access_token,
            owner_id=format_group_id(group.group_id),
            attachments=[{
                'type': VK_MESSAGE_KEY.ATTACHMENT_TYPE,
                'owner_id': format_group_id(video_owner),
                'id': video_vid
            }],
            priority=task_message.priority,
            message=text
        )

        response_dict = await method.execute()

        if not self.check_response(
                post,
                response_dict,
                fail_status=Post.FAILED,
                delete_status=Post.IS_DELETED
        ):
            return False

        response = response_dict.get(VK_MESSAGE_KEY.RESPONSE)
        post.status = Post.IS_ACTIVE
        post.post_id = response.get(VK_MESSAGE_KEY.POST_ID)
        post.save()

        post_screen_exists = GroupPostImgs.objects.filter(group__group_id=post.group.group_id,
                                                          campaign__pk=post.campaign.pk).first()

        if not post_screen_exists and ENABLED_POSTING_SCREENSHOT:
            SocialService.post_vk_screenshot(
                post_id=post.post_id,
                group_id=post.group.group_id,
                campaign_pk=post.campaign.pk
            )

        return True
