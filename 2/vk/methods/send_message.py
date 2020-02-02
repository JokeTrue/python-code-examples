from application.settings import VK_GROUP_TOKEN
from core.models.messages import VKMessagesLog
from platforms.utils import VK_MESSAGE_KEY
from platforms.vk.methods.vk_methods.wall import SendMessage as VKSendMessage
from social_services.message import SendMessageTaskMessage


class SendMessage:

    async def send_message(self, task_message: SendMessageTaskMessage):
        method = VKSendMessage(
            priority=task_message.priority,
            access_token=VK_GROUP_TOKEN,
            user_id=str(task_message.user_id),
            message=task_message.message
        )

        response_dict = await method.execute()

        if response_dict.get(VK_MESSAGE_KEY.RESPONSE):
            VKMessagesLog.objects.create(
                type=task_message.vk_message_type,
                message=task_message.message,
                recipient=task_message.user_id
            )

        return True
