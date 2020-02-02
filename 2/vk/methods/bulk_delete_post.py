import json

from core.models import Post, User
from platforms.utils import (
    split_list,
    VK_MESSAGE_KEY,
    format_group_id
)
from platforms.utils.error.error import DefaultError
from platforms.utils.error.error_code import ErrorCode
from platforms.vk import (
    logger,
    sentry_logger
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import ExecuteMethod
from social_services.message import BulkDeletePostTaskMessage
from utils import get_object_or_none


class BulkDeletePosts(VKBasePlatform):

    async def bulk_delete_post(self, task_message: BulkDeletePostTaskMessage) -> bool:
        user = get_object_or_none(User, pk=task_message.user_id)
        if not user:
            logger.error('User not found {}'.format(task_message.user_id))
            return False

        social_uid, access_token = self._get_vk_credentials(user)
        posts_queryset = Post.objects.filter(pk__in=task_message.post_ids)
        posts_list = list(posts_queryset)
        call_method_list = []

        post_splits = split_list(posts_list, 25)

        for post_split in post_splits:
            for post in post_split:
                args = {
                    VK_MESSAGE_KEY.OWNER_ID: format_group_id(post.group.group_id),
                    VK_MESSAGE_KEY.POST_ID: post.post_id
                }
                call = ExecuteMethod.construct(
                    ExecuteMethod.WALL_ENTITY,
                    ExecuteMethod.DELETE_METHOD,
                    json.dumps(args)
                )
                call_method_list.append(call)

            method = ExecuteMethod(
                priority=task_message.priority,
                access_token=access_token,
                code=ExecuteMethod.construct_code(call_method_list)
            )

            response_dict = await method.execute()

            if not response_dict:
                error = DefaultError(
                    error_key=ErrorCode.RESPONSE_IS_EMPTY_KEY,
                    text=ErrorCode.RESPONSE_IS_EMPTY_TEXT
                )
                for post in posts_list:
                    post.vk_response = error.to_json()
                    post.status = Post.FAILED_DELETE
                    post.save()
                return False

            if VK_MESSAGE_KEY.ERROR in response_dict:
                # берем ошибку по коду ответа (только в execute)
                error_dict = response_dict.get(VK_MESSAGE_KEY.ERROR)
                error = DefaultError.get_error_from_response(
                    error_dict=error_dict,
                    error_key=VK_MESSAGE_KEY.ERROR_CODE
                )

                sentry_error = {
                    'error': response_dict,
                    'error_msg': error,
                    'user_id': user.pk,
                    'username': user.get_full_name()
                }
                sentry_logger.error(msg=sentry_error)

                for post in posts_list:
                    post.vk_response = error
                    post.status = Post.FAILED_DELETE
                    post.save()

                return False

            response_list = response_dict.get(VK_MESSAGE_KEY.RESPONSE)

            if VK_MESSAGE_KEY.EXECUTE_ERRORS in response_dict:
                error_list = response_dict.get(VK_MESSAGE_KEY.EXECUTE_ERRORS)

                sentry_logger.warning(msg="Execute errors while post deleting", extra={
                    'error': response_dict,
                    'user_id': user.pk,
                    'username': user.get_full_name()
                })

                false_response_posts = []

                # порядок постов в сплите совпадает с порядко постов в ответе
                for index, post in enumerate(post_split):
                    if not response_list[index]:
                        false_response_posts.append(post)

                if false_response_posts:
                    for index, post in enumerate(false_response_posts):
                        concrete_error = error_list[index]
                        concrete_error_msg = DefaultError.get_error_from_response(
                            error_dict=concrete_error,
                            error_key=VK_MESSAGE_KEY.ERROR_MSG
                        )

                        # error code 7, Access denied распознаем, как удаленные
                        error_message = concrete_error.get(VK_MESSAGE_KEY.ERROR_MSG)
                        if error_message == ErrorCode.WALL_DELETE_ACCESS_DENIED_KEY:
                            post.status = Post.IS_DELETED
                        else:
                            post.status = Post.FAILED_DELETE

                        post.vk_response = concrete_error_msg

                        post.save()
                        self.log_to_sentry(post, concrete_error_msg, level='warning')
            else:
                for index, post in enumerate(post_split):
                    if response_list[index]:
                        post.status = Post.IS_DELETED
                        post.save()
            call_method_list[:] = []

        posts_queryset.update(status=Post.IS_DELETED)
        return True
