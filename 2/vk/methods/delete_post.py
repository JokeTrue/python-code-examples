from core.models import Post
from platforms.utils import format_group_id
from platforms.vk import logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.wall import WallDeleteMethod
from social_services.message import DeletePostTaskMessage
from utils import get_object_or_none


class DeletePost(VKBasePlatform):

    async def delete_post(self, task_message: DeletePostTaskMessage) -> bool:
        post = get_object_or_none(Post, pk=task_message.post_id)

        if not post:
            logger.error('Post Not Found Post id {}'.format(task_message.post_id))
            return False

        social_uid, access_token = self._get_vk_credentials(post.user)

        method = WallDeleteMethod(
            priority=task_message.priority,
            access_token=access_token,
            owner_id=format_group_id(post.group.group_id),
            post_id=post.post_id
        )

        response_dict = await method.execute()

        status = self.check_response(
            post,
            response_dict,
            fail_status=Post.FAILED_DELETE,
            delete_status=Post.IS_DELETED
        )

        if not status:
            return False

        post.status = Post.IS_DELETED if task_message.delete_status == Post.IS_DELETED else task_message.delete_status
        post.save()
        return True
