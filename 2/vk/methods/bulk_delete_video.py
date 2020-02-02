import json

from core.models import User, Video
from platforms.utils import (
    split_list,
    VK_MESSAGE_KEY
)
from platforms.utils.error.error import DefaultError
from platforms.utils.error.error_code import ErrorCode
from platforms.vk import (
    logger,
    sentry_logger
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import ExecuteMethod
from social_services.message import BulkDeleteVideoTaskMessage
from utils import get_object_or_none


class BulkDeleteVideos(VKBasePlatform):

    async def bulk_delete_video(self, task_message: BulkDeleteVideoTaskMessage) -> bool:
        user = get_object_or_none(User, pk=task_message.user_id)
        if not user:
            logger.error('User not found {}'.format(task_message.user_id))
            return False

        social_uid, access_token = self._get_vk_credentials(user)
        videos_queryset = Video.objects.filter(pk__in=task_message.video_ids)
        video_list = list(videos_queryset)
        call_method_list = []

        video_splits = split_list(video_list, 25)

        for video_split in video_splits:
            for video in video_split:
                args = {
                    VK_MESSAGE_KEY.OWNER_ID: video.owner,
                    VK_MESSAGE_KEY.VIDEO_ID: video.vid
                }
                call = ExecuteMethod.construct(
                    ExecuteMethod.VIDEO_ENTITY,
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
                for video in video_list:
                    video.vk_response = error.to_json()
                    video.status = Video.DELETE_FAIL
                    video.save()
                return False

            if VK_MESSAGE_KEY.ERROR in response_dict:
                error_dict = response_dict.get(VK_MESSAGE_KEY.ERROR)
                error_msg = DefaultError.get_error_from_response(
                    error_dict=error_dict,
                    error_key=VK_MESSAGE_KEY.ERROR_CODE
                )

                sentry_logger.warning(msg="Error while deleting videos", extra={
                    'error': response_dict,
                    'error_msg': error_msg,
                    'user_id': user.pk,
                    'username': user.get_full_name()
                })

                for video in video_list:
                    video.vk_response = error_msg
                    video.status = Video.DELETE_FAIL
                    video.save()

                return False

            response_list = response_dict.get(VK_MESSAGE_KEY.RESPONSE)
            if VK_MESSAGE_KEY.EXECUTE_ERRORS in response_dict:
                error_list = response_dict.get(VK_MESSAGE_KEY.EXECUTE_ERRORS)
                false_response_videos = []

                # порядок постов в сплите совпадает с порядком постов в ответе
                for index, video in enumerate(video_split):
                    if not response_list[index]:
                        false_response_videos.append(video)

                if false_response_videos:
                    for index, video in enumerate(false_response_videos):
                        concrete_error = error_list[index]
                        concrete_error_msg = DefaultError.get_error_from_response(
                            error_dict=concrete_error,
                            error_key=VK_MESSAGE_KEY.ERROR_MSG
                        )

                        # error code 7, Access denied распознаем, как удаленные
                        error_message = concrete_error.get(VK_MESSAGE_KEY.ERROR_MSG)
                        if error_message == ErrorCode.ACCESS_DENIED_KEY:
                            video.status = Video.IS_DELETED
                        else:
                            video.status = Video.DELETE_FAIL

                        video.vk_response = concrete_error_msg

                        video.save()
                        self.log_to_sentry(video, concrete_error_msg, level='warning')
            else:
                for index, video in enumerate(video_split):
                    if response_list[index]:
                        video.status = Video.IS_DELETED
                        video.save()
            call_method_list[:] = []

        videos_queryset.update(status=Video.IS_DELETED)
        return True
