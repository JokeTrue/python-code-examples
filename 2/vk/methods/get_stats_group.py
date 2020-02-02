import json
import traceback
from datetime import datetime

from django.db.models import Prefetch
from django.utils import timezone

from core.models import (
    AdvertisingCampaign,
    Group, UserGroup,
    User,
    Post,
    PostStats
)
from core.models.vk import UnitedPostsStat
from platforms.utils import (
    VK_MESSAGE_KEY,
    split_list
)
from platforms.vk import (
    logger,
    sentry_logger
)
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.execute import ExecuteMethod
from social_services.message import GetStatsGroupMessage


class GetStatsGroup(VKBasePlatform):

    async def get_stats_group(self, task_message: GetStatsGroupMessage):
        campaign = AdvertisingCampaign.objects.get(pk=task_message.campaign_id)
        groups = Group.objects.filter(pk__in=task_message.group_ids)
        user_groups_queryset = UserGroup.objects.filter(group_id__in=task_message.group_ids)

        prefetch = Prefetch(
            'user_groups_m2m',
            queryset=user_groups_queryset,
            to_attr='custom_user_groups'
        )

        users = User.objects.filter(pk__in=user_groups_queryset.values_list('user_id', flat=True).distinct()) \
            .prefetch_related(prefetch)

        if not groups:
            logger.error('Groups is empty {}'.format(task_message.group_ids))
            return False
        try:
            date_to = datetime.now().strftime('%Y-%m-%d')

            for user in users:
                token = self._get_vk_credentials(user)[1]
                user_groups = user.custom_user_groups
                execute_calls = []

                for user_group in user_groups:
                    execute_calls.append(ExecuteMethod.construct(
                        ExecuteMethod.STATS_ENTITY,
                        ExecuteMethod.GET_METHOD,
                        json.dumps({
                            VK_MESSAGE_KEY.GROUPD_ID: user_group.group.group_id,
                            VK_MESSAGE_KEY.DATE_FROM: campaign.date_created.strftime('%Y-%m-%d'),
                            VK_MESSAGE_KEY.DATE_TO: date_to

                        })
                    ))
                    user_group.group.is_stat_fetching = True
                    user_group.group.save()

                execute_parts = split_list(execute_calls, 25)
                group_parts = split_list(user_groups, 25)

                for index_part, execute_part in enumerate(execute_parts):
                    group_part = group_parts[index_part]
                    method = ExecuteMethod(
                        priority=task_message.priority,
                        access_token=token,
                        code=ExecuteMethod.construct_code(execute_part)
                    )
                    response_dict = await method.execute()
                    if not response_dict:
                        traceback_log = traceback.format_exc()
                        sentry_logger.error(msg="False response on get stat Group", extra={
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

                    for index, group_api_call in enumerate(execute_part):
                        if response_list[index]:
                            posts = Post.objects.all().filter(
                                group=group_part[index].group,
                                campaign__pk=task_message.campaign_id,
                                status=Post.IS_ACTIVE
                            )
                            male, female = 0, 0

                            for stat_item in response_list[index]:
                                if 'sex' in stat_item:
                                    m = list(filter(lambda sexes: 'm' in sexes.values(), stat_item['sex']))
                                    if len(m) == 1:
                                        male += int(m[0]['visitors'])

                                    f = list(filter(lambda sexes: 'f' in sexes.values(), stat_item['sex']))
                                    if len(f) == 1:
                                        female += int(f[0]['visitors'])

                            for post in posts:
                                post_stats = PostStats.objects.get_or_create(post=post)[0]
                                u_stat, _ = UnitedPostsStat.objects.get_or_create(
                                    user=post.user,
                                    group=post.group,
                                    campaign=post.campaign
                                )

                                if not female and not male:
                                    post_stats.sex_m = 0
                                    post_stats.sex_f = 0
                                else:
                                    sex_m = round(male / (male + female) * 100, 1)
                                    sex_f = round(female / (male + female) * 100, 1)
                                    post_stats.sex_m = sex_m
                                    post_stats.sex_f = sex_f
                                post_stats.save()

                        else:
                            group = group_part[index].group
                            sentry_error = {
                                'error': response_dict.get(VK_MESSAGE_KEY.EXECUTE_ERRORS),
                                'group': group.name
                            }
                            sentry_logger.warning(msg=sentry_error, extra={
                                'response': response_dict,
                                'execute_part': execute_part,
                                'group_part': group_part,
                                'execute_parts': execute_parts,
                                'group_parts': group_parts
                            })

        except Exception as e:
            traceback_log = traceback.format_exc()
            sentry_logger.error(msg=e, extra={
                'trace': traceback_log,
                'locals': locals()
            })

        Group \
            .objects \
            .filter(pk__in=task_message.group_ids) \
            .update(is_stat_fetching=False,
                    last_stat_fetch_date=timezone.make_aware(datetime.now(), timezone.get_default_timezone()))

        return True
