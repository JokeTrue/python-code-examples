import json
import traceback
from datetime import datetime
from itertools import groupby

from dateutil.tz import tzlocal
from django.utils import timezone
from transliterate import translit

from application.settings import StatsClient
from core.models import Video
from core.models.stats import ViewsStat
from core.models.vk import SuspiciousUser
from platforms.utils import (
    split_list,
    VK_MESSAGE_KEY,
    format_videos_ids
)
from platforms.vk import (
    logger,
    sentry_logger
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import (
    ExecuteMethod,
    VideoExecuteMethod
)
from social_services.message import GetStatsVideoMessage


class GetStatsVideo(VKBasePlatform):

    async def get_stats_video(self, task_message: GetStatsVideoMessage) -> bool:
        videos = Video.objects.all().filter(pk__in=task_message.video_ids)
        if not videos:
            logger.error('Videos is empty {}'.format(task_message.video_ids))
            return False

        videos.update(is_stat_fetching=True)
        try:
            for owner, user_videos in groupby(
                    videos,
                    lambda video: video.owner if video.owner else video.user.social_auth.get(provider='vk-oauth2').uid
            ):
                user_videos = list(user_videos)
                user = user_videos[0].user
                social_uid, access_token = self._get_vk_credentials(user)

                video_parts = split_list(user_videos, 200)

                execute_calls = [
                    ExecuteMethod.construct(
                        ExecuteMethod.VIDEO_ENTITY,
                        ExecuteMethod.GET_METHOD,
                        json.dumps({
                            VK_MESSAGE_KEY.OWNER_ID: owner,
                            VK_MESSAGE_KEY.COUNT: len(video_part),
                            VK_MESSAGE_KEY.VIDEOS: format_videos_ids(owner, video_part)
                        })
                    ) for video_part in video_parts
                ]

                execute_parts = split_list(execute_calls, 25)
                video_execute_parts = split_list(video_parts, 25)

                for index_part, execute_part in enumerate(execute_parts):
                    method = VideoExecuteMethod(
                        priority=task_message.priority,
                        access_token=access_token,
                        code=ExecuteMethod.construct_code(execute_part)
                    )

                    response_dict = await method.execute()

                    if not response_dict:
                        traceback_log = traceback.format_exc()
                        sentry_logger.error(msg="False response on get stat Video", extra={
                            'trace': traceback_log,
                            'locals': locals()
                        })
                        continue

                    response_list = response_dict.get(VK_MESSAGE_KEY.RESPONSE)
                    if VK_MESSAGE_KEY.ERROR in response_dict or VK_MESSAGE_KEY.EXECUTE_ERRORS in response_dict:

                        sentry_error = {
                            'error': response_dict
                        }
                        sentry_logger.warning(msg=sentry_error)

                        for index, videos_err in enumerate(video_execute_parts[index_part]):
                            for video in videos_err:
                                video.is_stat_fetching = False
                                video.last_stat_fetch_date = datetime.now(tzlocal())
                                video.save()
                    else:
                        video_execute_part = video_execute_parts[index_part]
                        for index, video_part in enumerate(video_execute_part):
                            if response_list[index]:
                                video_get_array = response_list[index]
                                # первый элемент - количество видео в одном видео гет
                                video_get_array.pop(0)

                                for video_part_index, video in enumerate(video_part):
                                    video.is_stat_fetching = False
                                    video_array = []

                                    if video_get_array:
                                        video_array = list(filter(lambda vid_dict: vid_dict.get('vid') == video.vid,
                                                                  video_get_array))

                                    if len(video_array):
                                        video_dict = video_array[0]

                                        diff = video_dict["views"] - video.views
                                        try:
                                            if SuspiciousUser.objects.filter(user=video.user,
                                                                             campaign=video.campaign
                                                                             ).count() > 0:
                                                views_tags = {
                                                    'type': 'views',
                                                    'campaign_pk': video.campaign.pk,
                                                    'user_pk': video.user.pk,
                                                    'user': translit(str(video.user), 'ru', reversed=True),
                                                    'group_pk': video.group.pk,
                                                    'group_name': translit(video.group.name, 'ru', reversed=True)
                                                }
                                                StatsClient.event('video-seed__suspicious_users', value=diff,
                                                                  tags=views_tags)
                                        except Exception as e:
                                            sentry_logger.error(msg=e)

                                        views = video_dict["views"]
                                        video.views = views
                                        video.is_stat_fetching = False
                                        video.last_stat_fetch_date = datetime.now(tzlocal())
                                        video.save()

                                        today = timezone.make_aware(
                                            datetime.now(),
                                            timezone.get_default_timezone()
                                        ).date()

                                        views_stat, _ = ViewsStat.objects.get_or_create(
                                            group=video.group,
                                            campaign=video.campaign,
                                            date__contains=today,
                                            user=video.user
                                        )
                                        if diff:
                                            views_stat.views += diff
                                            views_stat.save()
        except Exception as e:
            traceback_log = traceback.format_exc()
            sentry_logger.error(msg=e, extra={
                'trace': traceback_log,
                'locals': locals()
            })

        videos.update(is_stat_fetching=False,
                      last_stat_fetch_date=timezone.make_aware(datetime.now(), timezone.get_default_timezone()))
        return True
