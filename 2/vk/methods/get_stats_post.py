import json
import traceback
from datetime import datetime

from django.db.models import Prefetch
from django.utils import timezone
from transliterate import translit

from application.settings import StatsClient
from core.models import (
    Post,
    User,
    PostStats,
    AdvertisingCampaign
)
from core.models.stats import ViewsStat
from core.models.vk import (
    UnitedPostsStat,
    SuspiciousUser
)
from platforms.utils import (
    VK_MESSAGE_KEY,
    format_group_id,
    split_list
)
from platforms.vk import (
    logger,
    sentry_logger
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import ExecuteMethod
from social_services.message import (
    GetStatsPostMessage,
    SocialType
)
from social_services.social_service import SocialService


class GetStatsPosts(VKBasePlatform):

    async def get_stats_post(self, task_message: GetStatsPostMessage):
        posts_queryset = Post.objects.filter(pk__in=task_message.post_ids, group__members__gt=5000)
        prefetch = Prefetch(
            'posts',
            queryset=posts_queryset,
            to_attr='custom_prefetch_posts'
        )
        user_id_list = posts_queryset.values_list('user_id', flat=True).distinct()
        users = User.objects.filter(pk__in=user_id_list).prefetch_related(prefetch)

        try:
            if not posts_queryset:
                logger.error('Posts are empty {}'.format(task_message.post_ids))
                return False

            posts_queryset.update(is_stat_fetching=True)

            for user in users:
                posts = user.custom_prefetch_posts
                social_uid, access_token = self._get_vk_credentials(user)
                api_calls = [
                    ExecuteMethod.construct(
                        ExecuteMethod.STATS_ENTITY,
                        ExecuteMethod.POST_REACH,
                        json.dumps({
                            VK_MESSAGE_KEY.OWNER_ID: format_group_id(post.group.group_id),
                            VK_MESSAGE_KEY.POST_ID: post.post_id
                        })
                    ) for post in posts
                ]

                execute_parts = split_list(api_calls, 25)
                posts_parts = split_list(posts, 25)

                for index_part, execute_part in enumerate(execute_parts):
                    post_part = posts_parts[index_part]
                    method = ExecuteMethod(
                        priority=task_message.priority,
                        access_token=access_token,
                        code=ExecuteMethod.construct_code(execute_part)
                    )

                    response_dict = await method.execute()
                    if not response_dict:
                        traceback_log = traceback.format_exc()
                        sentry_logger.error(msg="False response on get stat Post", extra={
                            'trace': traceback_log,
                            'locals': locals()
                        })
                        continue
                    response_list = response_dict.get(VK_MESSAGE_KEY.RESPONSE)
                    if VK_MESSAGE_KEY.ERROR in response_dict:
                        sentry_error = {
                            'error': response_dict
                        }
                        sentry_logger.warning(msg=sentry_error)
                        continue

                    if VK_MESSAGE_KEY.EXECUTE_ERRORS in response_dict:
                        false_response_list = []

                        for index, post_api_call in enumerate(execute_part):
                            if not response_list[index]:
                                post = post_part[index]
                                false_response_list.append(post)

                        errors = response_dict.get(VK_MESSAGE_KEY.EXECUTE_ERRORS)

                        if errors and false_response_list:
                            for index, post in enumerate(false_response_list):
                                error = errors[index]
                                post_stats, is_created = PostStats.objects.get_or_create(post=post)
                                post_stats.vk_response = error
                                post_stats.save()
                                sentry_logger.warning(
                                    msg='False response get_stat for post pk {}'.format(post.pk),
                                    extra={
                                        'post_id_in_vk': post.post_id,
                                        'group': post.group.name,
                                        'user_pk': post.user_id,
                                        'username': post.user.get_full_name(),
                                        'error': error,
                                        'link': 'https://vk.com/wall-{}_{}'.format(
                                            post.group.group_id,
                                            post.post_id
                                        )
                                    }
                                )
                                SocialService.vk_check_post(SocialType.VK, post_id=post.pk)

                    for index, post_api_call in enumerate(execute_part):
                        if response_list[index]:
                            posts_array = response_list[index]
                            post = post_part[index]
                            post_stats, is_created = PostStats.objects.get_or_create(post=post)

                            u_stat, _ = UnitedPostsStat.objects.get_or_create(
                                user=post.user,
                                group=post.group,
                                campaign=post.campaign
                            )

                            if 'reach_subscribers' in posts_array[0] and 'reach_total' in posts_array[0]:
                                if post.campaign.campaign_type in [AdvertisingCampaign.VK_VIDEO_POST,
                                                                   AdvertisingCampaign.VK_REPOST]:
                                    last_views = int(
                                        post_stats.reach.split('/')[1].replace('-', '0')) if post_stats.reach else 0
                                    diff = posts_array[0]['reach_total'] - last_views
                                    today = timezone.make_aware(
                                        datetime.now(),
                                        timezone.get_default_timezone()
                                    ).date()

                                    views_stat, _ = ViewsStat.objects.get_or_create(
                                        group=post.group,
                                        campaign=post.campaign,
                                        date__contains=today,
                                        user=post.user
                                    )
                                    if diff:
                                        views_stat.views += diff
                                        views_stat.save()

                                post_stats.reach = '{}/{}'.format(
                                    str(posts_array[0]['reach_subscribers']),
                                    str(posts_array[0]['reach_total'])
                                )
                                post_stats.save()
                            try:
                                if len(SuspiciousUser.objects.filter(user=post.user, campaign=post.campaign)) > 0:
                                    reach_tags = {
                                        'type': 'reach',
                                        'campaign_pk': post.campaign.pk,
                                        'user_pk': post.user.pk,
                                        'user': translit(str(post.user), 'ru', reversed=True),
                                        'group_pk': post.group.pk,
                                        'group_name': translit(post.group.name, 'ru', reversed=True)
                                    }
                                    StatsClient.event('video-seed__suspicious_users',
                                                      value=posts_array[0]['reach_total'],
                                                      tags=reach_tags)
                            except Exception as e:
                                sentry_logger.error(msg=e)

                for post in posts:
                    post.is_stat_fetching = False
                    post.last_stat_fetch_date = timezone.make_aware(datetime.now(), timezone.get_default_timezone())
                    post.save()

        except Exception as e:
            traceback_log = traceback.format_exc()
            sentry_logger.error(msg=e, extra={
                'trace': traceback_log,
                'locals': locals()
            })

        posts_queryset.update(is_stat_fetching=False,
                              last_stat_fetch_date=timezone.make_aware(datetime.now(), timezone.get_default_timezone()))

        return True
