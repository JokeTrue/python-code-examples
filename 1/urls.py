from django.conf.urls import url

from internal_transfers.views import (
    InternalTransferInner,
    InternalTransferList,
    InternalTransferRetrieve,
    InternalTransferTraders,
    UserAccountsForTransfer,
)

urlpatterns = [
    url(
        r'^transfer/inner/$',
        InternalTransferInner.as_view(),
    ),
    url(
        r'^transfer/traders/$',
        InternalTransferTraders.as_view(),
    ),
    url(
        r'transfer/accounts_options/$',
        UserAccountsForTransfer.as_view(),
    ),
    url(
        r'transfer/list/$',
        InternalTransferList.as_view(),
    ),
    url(
        r'transfer/(?P<pk>\d+)/$',
        InternalTransferRetrieve.as_view(),
    ),
]
