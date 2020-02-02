import json

from django.db.models import Prefetch

from core.models import (
    Post,
    Group
)
from platforms.utils import (
    split_list,
    format_post_ids,
    VK_MESSAGE_KEY)
from platforms.vk import sentry_logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import ExecuteMethod
from social_services.message import (
    SocialType,
    VkBulkCheckPostMessage
)
from social_services.social_service import SocialService


class BulkCheckPosts(VKBasePlatform):

    async def bulk_check_post(self, task_message: VkBulkCheckPostMessage):
        posts_queryset = Post.objects.filter(pk__in=task_message.post_ids)

        prefetch = Prefetch('posts', queryset=posts_queryset, to_attr='custom_prefetch_posts')
        group_id_list = posts_queryset.values_list('group_id', flat=True).distinct()
        groups = Group.objects.filter(pk__in=group_id_list).prefetch_related(prefetch)

        for group in groups:
            posts_chunks = split_list(group.custom_prefetch_posts, 100)

            vk_api_calls = []
            token = self._get_vk_credentials(group.custom_prefetch_posts[0].user)[1]

            for posts_chunk in posts_chunks:
                vk_api_calls.append(
                    ExecuteMethod.construct(
                        ExecuteMethod.WALL_ENTITY,
                        ExecuteMethod.GET_BY_ID,
                        json.dumps({
                            VK_MESSAGE_KEY.POSTS: format_post_ids(group.group_id, posts_chunk),

                        })
                    ))

            execute_request_calls = split_list(vk_api_calls, 25)
            posts_execute_chunks = split_list(posts_chunks, 25)

            for index_call, execute_code_data in enumerate(execute_request_calls):
                method = ExecuteMethod(
                    priority=task_message.priority,
                    access_token=token,
                    code=ExecuteMethod.construct_code(execute_code_data)
                )
                response_dict = await method.execute()
                response_list = response_dict.get(VK_MESSAGE_KEY.RESPONSE)

                if VK_MESSAGE_KEY.ERROR in response_dict or VK_MESSAGE_KEY.EXECUTE_ERRORS in response_dict:

                    sentry_error = {
                        'error': response_dict
                    }
                    sentry_logger.warning(msg=sentry_error)
                    continue
                else:
                    post_execute_chunk = posts_execute_chunks[index_call]
                    if not response_list:
                        for posts_chunk in post_execute_chunk:
                            for post in posts_chunk:
                                post.status = Post.DELETED_BY_VK
                                post.save()

                    for index, posts_chunk in enumerate(post_execute_chunk):
                        response_item_list = response_list[index]

                        if not response_item_list:
                            for post in posts_chunk:
                                post.status = Post.DELETED_BY_VK
                                post.save()

                        if response_item_list:

                            post_execute_id_list = list(map(lambda post: post.post_id, posts_chunk))
                            response_id_list = map(lambda item: item.get(VK_MESSAGE_KEY.ID), response_item_list)

                            result_post_vk_difference = list(set(post_execute_id_list) - set(response_id_list))

                            if result_post_vk_difference:
                                for result_vk_id in result_post_vk_difference:
                                    post = posts_queryset.get(post_id=result_vk_id, group=group)
                                    post.status = Post.DELETED_BY_VK
                                    post.save()

                            for response_item in response_item_list:
                                filtered_post = \
                                    list(filter(lambda post: post.post_id == response_item.get(VK_MESSAGE_KEY.ID),
                                                posts_chunk))[0]

                                if VK_MESSAGE_KEY.ATTACHMENT not in response_item:
                                    sentry_logger.error(msg={
                                        'post_pk': filtered_post.pk,
                                        'message': 'Нет видео у поста'
                                    })
                                    SocialService.delete_post(
                                        SocialType.VK,
                                        post_id=filtered_post.pk,
                                        delete_status=Post.WITHOUT_VIDEO
                                    )

        return True
