from core.models import (
    User,
    Group,
    UserGroup
)
from platforms.utils import VK_MESSAGE_KEY
from platforms.vk import sentry_logger
from platforms.vk.methods import VKBasePlatform
from platforms.vk.methods.vk_methods.groups import GroupsGetMethod
from social_services.message import GetUserGroupsMessage


class GetUserGroups(VKBasePlatform):

    async def get_user_groups(self, task_message: GetUserGroupsMessage):
        user = User.objects.get(pk=task_message.user_pk)
        social_uid, access_token = self._get_vk_credentials(user)
        method = GroupsGetMethod(
            access_token=access_token,
            user_id=social_uid,
            extended=1,
            fields='members_count,can_post',
            filter='admin,editor,moder',
            priority=task_message.priority
        )
        response_dict = await method.execute()

        if VK_MESSAGE_KEY.ERROR in response_dict:
            sentry_logger.error(msg='Authorization Failed: User - {}'.format(user.get_full_name()))
            return False

        if not response_dict:
            sentry_logger.error('No response on get_user_groups: User - {}'.format(user.get_full_name()))
            return False

        response = response_dict.get(VK_MESSAGE_KEY.RESPONSE)

        if not response or len(response) < 2:
            sentry_logger.error('No vk response key in get_user_groups response, {} User - {}'.format(
                response,
                user.get_full_name()
            ))
            return False

        group_items = response.get(VK_MESSAGE_KEY.ITEMS)

        for group_item in group_items:
            try:
                group = Group.objects.get(group_id=group_item["id"])
            except Group.DoesNotExist:
                group = Group(
                    group_id=group_item["id"],
                    name=group_item["name"],
                    members=group_item.get("members_count", 0)
                )
                group.save()

            group.name = group_item["name"] if group.name != group_item["name"] else group.name

            if VK_MESSAGE_KEY.DEACTIVATED in group_item:
                sentry_logger.warning(msg={
                    'group': group,
                    'reason': 'Группа забанена ВК'
                })
                continue

            try:
                group.members = group_item["members_count"] \
                    if group.members != group_item["members_count"] else group.members
            except Exception as e:
                sentry_logger.error(msg=e)
            group.is_closed = bool(group_item['is_closed']) \
                if group.is_closed != bool(group_item['is_closed']) else group.is_closed

            group.groups_img = group_item.get("photo_50") \
                if group.groups_img != group_item.get("photo_50") else group.groups_img
            group.save()

            user_group, created = UserGroup.objects.get_or_create(user=user, group=group)

            user_group.is_admin = bool(group_item.get('is_admin')) \
                if user_group.is_admin != bool(group_item.get('is_admin')) else user_group.is_admin

            user_group.admin_level = group_item.get('admin_level', UserGroup.ADMIN) \
                if user_group.admin_level != group_item.get('admin_level', UserGroup.ADMIN) else user_group.admin_level

            user_group.save()

        return True
