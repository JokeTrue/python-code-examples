from core.models import AdvertisingCampaign
from core.models.vk import (
    DelayedPost,
    Post
)
from platforms.vk.methods.create_post import CreatePost
from platforms.vk.methods.repost import Repost
from platforms.vk.methods.video_post import VideoPost
from social_services.message import (
    DelayedPostTaskMessage,
    PostTaskMessage,
    SocialType,
    RepostTaskMessage,
    VideoPostTaskMessage
)
from social_services.task_priorities import TaskPriority


class DelayPost(Repost, CreatePost, VideoPost):

    async def delay_post(self, task_message: DelayedPostTaskMessage) -> bool:
        delay_obj = DelayedPost.objects.get(pk=task_message.delay_pk)
        campaign = AdvertisingCampaign.objects.get(pk=task_message.campaign_id)

        if delay_obj.status == DelayedPost.IDLE:
            if delay_obj.post.campaign.is_active:
                func, new_task_message = None, None

                if campaign.campaign_type == AdvertisingCampaign.YOUTUBE_VIDEO_POST:
                    new_task_message = PostTaskMessage(
                        social_type=SocialType.VK.value,
                        priority=TaskPriority.POST.value,
                        post_id=task_message.post_id,
                        target_group_id=task_message.target_group_id,
                        campaign_id=task_message.campaign_id,
                        user_id=task_message.user_id,
                        target_video_upload=task_message.target_video_upload,
                        text=task_message.text,
                        method=task_message.method,
                        message_type=task_message.message_type
                    )
                    func = self.create_post

                elif campaign.campaign_type == AdvertisingCampaign.VK_REPOST:
                    new_task_message = RepostTaskMessage(
                        social_type=SocialType.VK.value,
                        priority=TaskPriority.POST.value,
                        post_id=task_message.post_id,
                        target_group_id=task_message.target_group_id,
                        campaign_id=task_message.campaign_id,
                        user_id=task_message.user_id,
                        method=task_message.method,
                        message_type=task_message.message_type
                    )
                    func = self.repost

                elif campaign.campaign_type == AdvertisingCampaign.VK_VIDEO_POST:
                    new_task_message = VideoPostTaskMessage(
                        social_type=SocialType.VK.value,
                        priority=TaskPriority.POST.value,
                        post_id=task_message.post_id,
                        target_group_id=task_message.target_group_id,
                        campaign_id=task_message.campaign_id,
                        user_id=task_message.user_id,
                        method=task_message.method,
                        message_type=task_message.message_type
                    )
                    func = self.video_post

                if func and new_task_message:
                    create_status = await func(new_task_message)
                    if create_status:
                        delay_obj.status = DelayedPost.SUCCESS
                        delay_obj.save()
                    else:
                        post = Post.objects.get(pk=delay_obj.post_id)
                        post.status = Post.FAILED
                        post.save()
                        delay_obj.status = DelayedPost.FAILED
                        delay_obj.save()

        return True
