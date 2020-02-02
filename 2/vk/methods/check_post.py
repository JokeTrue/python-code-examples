from core.models import Post
from platforms.utils import VK_MESSAGE_KEY
from platforms.vk import sentry_logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.wall import WallGetByIdMethod
from social_services.message import (
    VkCheckPostMessage,
    SocialType
)
from social_services.social_service import SocialService


class CheckPost(VKBasePlatform):

    async def check_post(self, task_message: VkCheckPostMessage):
        post = Post.objects.get(pk=task_message.post_id)
        user = post.user
        social_uid, access_token = self._get_vk_credentials(user)

        result = await self._wall_get_by_id(
            post=post,
            priority=task_message.priority,
            access_token=access_token
        )
        response = result.get(VK_MESSAGE_KEY.RESPONSE)

        if not response:
            post.status = Post.DELETED_BY_VK
            post.save()
            return True

        if VK_MESSAGE_KEY.ATTACHMENT not in response[0]:
            sentry_logger.error(msg={
                'post_pk': post.pk,
                'message': 'Нет видео у поста'
            })
            SocialService.delete_post(SocialType.VK, post_id=post.pk, delete_status=Post.WITHOUT_VIDEO)

        return True

    async def _wall_get_by_id(self, post, priority, access_token):
        post_string = "-{}_{}".format(post.group.group_id, post.post_id)

        method = WallGetByIdMethod(
            access_token=access_token,
            posts=post_string,
            priority=priority
        )

        return await method.execute()
