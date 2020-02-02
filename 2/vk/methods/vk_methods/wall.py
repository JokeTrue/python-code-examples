from platforms.client.vk import BaseVkClient
from platforms.utils.arguments import Argument
from platforms.utils.argumentslib import ListOfArgument


class WallPostMethod(BaseVkClient):
    METHOD = 'wall.post'
    HTTP_METHOD = 'post'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'owner_id': Argument(type=str, required=True),
        'attachments': ListOfArgument(argument_inst=Argument(type=dict, required=True)),
        'message': Argument(type=str, required=True)
    }

    def get_arguments(self):
        arguments = super(WallPostMethod, self).get_arguments()
        attachments = arguments['attachments']
        arguments['attachments'] = ','.join(
            self.create_attachment(item['owner_id'], item['type'], item['id']) for item in attachments
        )
        return arguments

    def create_attachment(self, owner_id, object_type, object_id):
        return "{0}{1}_{2}".format(object_type, owner_id, object_id)


class WallDeleteMethod(BaseVkClient):
    METHOD = 'wall.delete'
    HTTP_METHOD = 'post'
    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'owner_id': Argument(type=str, required=True),
        'post_id': Argument(type=int, required=True)
    }


class WallGetByIdMethod(BaseVkClient):
    METHOD = 'wall.getById'
    HTTP_METHOD = 'post'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'posts': Argument(type=str, required=True)
    }


class SendMessage(BaseVkClient):
    METHOD = 'messages.send'
    HTTP_METHOD = 'post'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'user_id': Argument(type=str, required=True),
        'message': Argument(type=str, required=True)
    }


class WallRepost(BaseVkClient):
    METHOD = 'wall.repost'
    HTTP_METHOD = 'post'

    ARGUMENTS = {
        'access_token': Argument(type=str, required=True),
        'object': Argument(type=str, required=True),
        'message': Argument(type=str, required=True),
        'group_id': Argument(type=str, required=True)
    }
