from core.models import Video
from platforms.vk import logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.video import VideoDeleteMethod
from social_services.message import DeleteVideoTaskMessage
from utils import get_object_or_none


class DeleteVideo(VKBasePlatform):

    async def delete_video(self, task_message: DeleteVideoTaskMessage) -> bool:
        video = get_object_or_none(Video, pk=task_message.video_id)
        if not video:
            logger.error('Video Not Found vid: {}'.format(task_message.video_id))
            return False

        social_uid, access_token = self._get_vk_credentials(video.user)

        method = VideoDeleteMethod(
            access_token=access_token,
            video_id=video.vid,
            owner_id=video.owner,
            priority=task_message.priority
        )

        response_dict = await method.execute()

        status = self.check_response(
            video,
            response_dict,
            fail_status=Video.DELETE_FAIL,
            delete_status=Video.IS_DELETED
        )

        if not status:
            return False

        video.status = Video.IS_DELETED
        video.save()
        return True
