from core.models import User
from platforms.base import BasePlatform
from platforms.utils import VK_MESSAGE_KEY
from platforms.utils.error.error import DefaultError
from platforms.utils.error.error_code import ErrorCode

from platforms.vk import sentry_logger


class VKBasePlatform(BasePlatform):
    PREFIX = 'vk'
    AUTH_PROVIDER = 'vk-oauth2'

    @staticmethod
    def _get_vk_credentials(user: User):
        social_auth = user.social_auth.get(provider=VKBasePlatform.AUTH_PROVIDER)
        access_token = social_auth.extra_data['access_token']
        social_uid = social_auth.uid

        return social_uid, access_token

    def log_to_sentry(self, entity, error, level='error'):
        if level == 'warning':
            sentry_logger.warning(msg=error, extra={
                'error': error,
                'video_id': entity.pk,
                'campaign_name': entity.campaign.name,
                'campaign_id': entity.campaign_id,
                'group_id': entity.group_id,
                'groupname': entity.group.name,
                'username': entity.user.get_full_name(),
                'user_id': entity.user_id
            })
        else:
            sentry_logger.error(msg=error, extra={
                'error': error,
                'video_id': entity.pk,
                'campaign_name': entity.campaign.name,
                'campaign_id': entity.campaign_id,
                'group_id': entity.group_id,
                'groupname': entity.group.name,
                'username': entity.user.get_full_name(),
                'user_id': entity.user_id
            })

    def check_response(self, entity, response_dict, fail_status, delete_status=None) -> bool:
        if not response_dict:
            entity.status = fail_status
            error = DefaultError(
                error_key=ErrorCode.RESPONSE_IS_EMPTY_KEY,
                text=ErrorCode.RESPONSE_IS_EMPTY_TEXT
            )
            entity.vk_response = error.to_json()
            entity.save()

            self.log_to_sentry(entity, error.to_json())
            return False

        if VK_MESSAGE_KEY.ERROR in response_dict:
            error_dict = response_dict.get(VK_MESSAGE_KEY.ERROR)
            error = DefaultError.get_error_from_response(
                error_dict=error_dict,
                error_key=VK_MESSAGE_KEY.ERROR_MSG
            )
            entity.vk_response = error

            # Access denied распознаем, как удаленные
            error_message = error_dict.get(VK_MESSAGE_KEY.ERROR_MSG)
            if error_message == ErrorCode.WALL_DELETE_ACCESS_DENIED_KEY or error_message == ErrorCode.ACCESS_DENIED_KEY and delete_status:
                entity.status = delete_status
            else:
                entity.status = fail_status

            entity.save()
            self.log_to_sentry(entity, error, level='warning')
            return False

        if VK_MESSAGE_KEY.RESPONSE not in response_dict:
            entity.status = fail_status
            error = DefaultError.response_not_correct_error()
            entity.vk_response = error
            entity.save()

            self.log_to_sentry(entity, error)
            return False

        return True
