from platforms.client.vk import BaseVkClient
from platforms.utils.arguments import Argument


class GroupsGetMethod(BaseVkClient):
    METHOD = 'groups.get'
    API_VERSION = '5.71'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'user_id': Argument(type=str, required=True),
        'extended': Argument(type=int, required=True),
        'filter': Argument(type=str, required=True),
        'fields': Argument(type=str, required=True),
    }
