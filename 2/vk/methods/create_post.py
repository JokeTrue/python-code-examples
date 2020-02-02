from application import settings
from application.settings import ENABLED_POSTING_SCREENSHOT
from core.models import (
    Post,
    GroupPostImgs,
    Payment,
    User,
    Group,
    AdvertisingCampaign,
    Video
)
from platforms.utils import (
    format_group_id,
    VK_MESSAGE_KEY,
    get_object_or_none
)
from platforms.utils.error.error import DefaultError
from platforms.utils.error.error_code import ErrorCode
from platforms.vk import logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.video import VideoSaveMethod
from platforms.vk.methods.vk_methods.wall import WallPostMethod
from social_services.message import (
    PostTaskMessage,
    TargetVideoUpload
)
from social_services.social_service import SocialService
from utils.time_to_influx import time_result


class CreatePost(VKBasePlatform):

    @time_result
    async def create_post(self, task_message: PostTaskMessage) -> bool:
        post = get_object_or_none(Post, pk=task_message.post_id)
        if not post:
            logger.error('Post Not Found Post id {}'.format(task_message.post_id))
            return False

        user = User.objects.get(pk=task_message.user_id)
        group = Group.objects.get(pk=task_message.target_group_id)
        campaign = AdvertisingCampaign.objects.get(pk=task_message.campaign_id)

        description = task_message.text
        target_video_upload = task_message.target_video_upload

        social_uid, access_token = self._get_vk_credentials(user=user)

        video = Video.objects.filter(group=group, campaign=campaign, user=user, status=Video.IS_ACTIVE).first()

        if not video:
            video = Video(
                group=group,
                campaign=campaign,
                user=user,
                status=Video.IN_PROGRESS,
                factor=settings.KOFF
            )
            video.save()

            to_group = target_video_upload == TargetVideoUpload.GROUP.value
            status_ok = await self._video_save(
                post=post,
                video=video,
                access_token=access_token,
                campaign=campaign,
                description=description,
                priority=task_message.priority,
                group=group,
                to_group=to_group
            )

            if not status_ok:
                post.status = Post.FAILED
                post.vk_response = video.vk_response
                post.save()
                return False

            if status_ok == VideoSaveMethod.TOO_MUCH_REQUESTS_MSG:
                return False

        return await self._wall_post(
            access_token=access_token,
            group=group,
            video=video,
            priority=task_message.priority,
            description=description,
            post=post,
            campaign_pk=campaign.pk
        )

    async def _wall_post(self, access_token, group, video, priority, description, post, campaign_pk):
        method = WallPostMethod(
            access_token=access_token,
            owner_id=format_group_id(group.group_id),
            attachments=[{
                'type': VK_MESSAGE_KEY.ATTACHMENT_TYPE,
                'owner_id': video.owner,
                'id': video.vid
            }],
            priority=priority,
            message=description
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

        post_screen_exists = GroupPostImgs.objects.filter(
            group__group_id=post.group.group_id,
            campaign__pk=campaign_pk
        ).first()
        if not post_screen_exists and ENABLED_POSTING_SCREENSHOT:
            SocialService.post_vk_screenshot(
                post_id=post.post_id,
                group_id=post.group.group_id,
                campaign_pk=campaign_pk
            )

        payment, create_ = Payment.objects.get_or_create(campaign_id=campaign_pk, user=post.user)

        if payment.is_Payment:
            payment.is_Payment = False
            payment.save()

        return True

    async def _video_save(self, post, video, access_token, campaign, description, priority, group, to_group) -> bool:
        method = VideoSaveMethod(
            access_token=access_token,
            name=campaign.name,
            link=campaign.link,
            description=description,
            priority=priority,
            group_id=group.group_id if to_group else None
        )

        response_dict = await method.execute()

        if not self.check_response(video, response_dict, Video.UPLOAD_FAIL):
            return False

        response = response_dict.get(VK_MESSAGE_KEY.RESPONSE)

        upload_url = response.get(VK_MESSAGE_KEY.UPLOAD_URL)

        toggle_ok = await VideoSaveMethod.toggle_upload_link(upload_url=upload_url)

        if toggle_ok and toggle_ok == VideoSaveMethod.TOO_MUCH_REQUESTS_MSG:
            SocialService.toggle_upload_link(
                upload_url=upload_url,
                video_pk=video.pk,
                video_id=response.get(VK_MESSAGE_KEY.VIDEO_ID),
                owner_id=response.get(VK_MESSAGE_KEY.OWNER_ID),
                post_pk=post.pk,
                description=description
            )
            return toggle_ok

        elif toggle_ok and toggle_ok == VideoSaveMethod.SERVICE_UNAVAILABLE:
            video_error = DefaultError(
                error_key=ErrorCode.VIDEO_UPLOAD_SERVICE_UNAVAILABLE_KEY,
                text=ErrorCode.VIDEO_UPLOAD_SERVICE_UNAVAILABLE_TEXT,
                error_code=1101
            )

            video.status = Video.UPLOAD_FAIL
            video.vk_response = video_error.to_json()
            video.save()
            return False

        if not toggle_ok:
            video_error = DefaultError(
                error_key=ErrorCode.VIDEO_UPLOAD_CHECK_KEY,
                text=ErrorCode.VIDEO_UPLOAD_CHECK_TEXT,
                error_code=1100
            )
            self.log_to_sentry(video, video_error.to_json())
            video.status = Video.UPLOAD_FAIL
            video.vk_response = video_error.to_json()
            video.save()
            return False
        else:
            video.status = Video.IS_ACTIVE
            video.vid = response.get(VK_MESSAGE_KEY.VIDEO_ID)
            video.owner = response.get(VK_MESSAGE_KEY.OWNER_ID)
            video.save()
            return True
