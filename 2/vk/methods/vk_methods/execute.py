from platforms.client.vk import BaseVkClient
from platforms.utils.arguments import Argument


class ExecuteMethod(BaseVkClient):
    METHOD = 'execute'
    HTTP_METHOD = 'post'
    API_PREFIX = 'API'

    WALL_ENTITY = 'wall'
    VIDEO_ENTITY = 'video'
    STATS_ENTITY = 'stats'
    DELETE_METHOD = 'delete'
    GET_METHOD = 'get'
    POST_REACH = 'getPostReach'
    GET_BY_ID = 'getById'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'code': Argument(type=str, required=True),
    }

    @staticmethod
    def prepare_execute(call_list: str):
        return "return [{}];".format(call_list)

    @staticmethod
    def construct(entity: str, method: str, args_string: str) -> str:
        return "{0}.{1}.{2}({3})".format(
            ExecuteMethod.API_PREFIX,
            entity, method,
            args_string
        )

    @staticmethod
    def construct_code(call_method_list: list):
        call_method_list_str = ",".join(call_method_list)
        code = ExecuteMethod.prepare_execute(call_method_list_str)
        return code


class VideoExecuteMethod(ExecuteMethod):
    API_VERSION = 3.0
