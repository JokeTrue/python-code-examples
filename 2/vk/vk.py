from platforms.base import BasePlatformException
from platforms.vk.methods.bulk_delete_post import BulkDeletePosts
from platforms.vk.methods.bulk_delete_video import BulkDeleteVideos
from platforms.vk.methods.check_post import CheckPost
from platforms.vk.methods.delay_post import DelayPost
from platforms.vk.methods.delete_post import DeletePost
from platforms.vk.methods.delete_video import DeleteVideo
from platforms.vk.methods.get_likes_reposts import GetLikesReposts
from platforms.vk.methods.get_stats_group import GetStatsGroup
from platforms.vk.methods.get_stats_post import GetStatsPosts
from platforms.vk.methods.get_stats_video import GetStatsVideo
from platforms.vk.methods.get_user_groups import GetUserGroups
from platforms.vk.methods.post_vk_screenshot import PostVKScreenshot
from platforms.vk.methods.send_message import SendMessage


class VkPlatformException(BasePlatformException):
    def __init__(self, reason):
        super(VkPlatformException, self).__init__(VKPlatform.PREFIX, reason=reason)


class VKPlatform(
    DeletePost,
    DeleteVideo,
    SendMessage,
    PostVKScreenshot,
    BulkDeletePosts,
    BulkDeleteVideos,
    GetStatsVideo,
    GetUserGroups,
    GetStatsGroup,
    GetStatsPosts,
    GetLikesReposts,
    DelayPost,
    CheckPost,
):
    pass
