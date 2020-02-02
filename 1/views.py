from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response

from backoffice.views.internal_transfers.serializers import (
    InternalTransferListFilter,
)
from common.filters import RelatedOrderingFilter
from internal_transfers.exceptions import (
    InternalTransferError,
    RecipientAccountCollisionError,
)
from internal_transfers.models import InternalTransfer
from internal_transfers.perm_plus_filter import (
    InternalTransferAccountsEnabled,
    InternalTransferTradersEnabled,
    UserInternalTransferFilter,
)
from internal_transfers.serializers import (
    InnerTransferAccountSerializer,
    InternalTransferInfoSerializer,
    InternalTransferInnerSerializer,
    InternalTransferListSerializer,
    InternalTransferTradersSerializer,
)
from money import Money
from money.currencies import USD
from platforms.models import Account
from turku.strings import (
    blockedAccountError,
    recipientAccountNotFound,
    tradersAccountRestriction,
)
from users.perm_plus_filter import IsAuthenticated
from utils.paginator import PageSizePaginator
from utils.perm_plus_filter import BrokerFilterBackend, SearchFilter


class InternalTransferMixin:
    serializer_class = None
    setting = None
    type = None

    def get_recipient_account(self, pk):
        raise NotImplementedError()

    def get_transfer_details(self, sender_account, recipient_account):
        settings = sender_account.broker.get_value(self.setting)
        data = {}

        data['transfer_type'] = self.type
        data['min_amount_for_approve'] = settings['min_amount_for_approve']
        data['min_commission'] = Money(settings['commissions']['min_commission'], USD).to(sender_account.currency)
        data['max_commission'] = Money(settings['commissions']['max_commission'], USD).to(sender_account.currency)

        if sender_account.currency == recipient_account.currency:
            data['commission'] = settings['commissions']['same_currencies']
        else:
            data['commission'] = settings['commissions']['different_currencies']

            exchange_string, exchange_coefficient = InternalTransfer.get_exchange_rate(
                sender_account.currency,
                recipient_account.currency,
            )
            data['exchange_rate'] = exchange_string
            data['exchange_coefficient'] = exchange_coefficient

        data['exchange_coefficient_for_fix'] = Money(1, USD).to(sender_account.currency).amount
        return data

    @staticmethod
    def calculate_receive_amount(transfer_details, sender_account, send_amount, receive_currency) -> [Money, Money]:
        percentage = transfer_details['commission']['percentage']
        fix = transfer_details['commission']['fix']

        send_amount = Money(send_amount, sender_account.currency)
        commission = InternalTransfer.calculate_commission(
            send_amount,
            percentage,
            fix,
            transfer_details['min_commission'],
            transfer_details['max_commission'],
        )
        receive_amount = (send_amount - commission).to(receive_currency)
        if receive_amount.amount < 0:
            receive_amount = Money(0, receive_currency)

        return receive_amount, commission

    def get(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.GET)
        serializer.is_valid(raise_exception=True)

        sender_account = Account.objects.get(pk=serializer.validated_data['sender_account'], is_demo=False)
        recipient_account = self.get_recipient_account(serializer.validated_data['recipient_account'])

        if not recipient_account:
            return Response(status=status.HTTP_404_NOT_FOUND, data=recipientAccountNotFound())

        if sender_account.is_blocked or recipient_account.is_blocked:
            return Response(status=status.HTTP_409_CONFLICT, data=blockedAccountError())

        if self.type == InternalTransfer.TO_TRADER and sender_account.user == recipient_account.user:
            return Response(status=status.HTTP_409_CONFLICT, data=tradersAccountRestriction())

        data = {
            'details': self.get_transfer_details(sender_account, recipient_account),
            'max_amount': sender_account.balance.amount,
        }

        return Response(status=status.HTTP_200_OK, data=InternalTransferInfoSerializer(instance=data).data)

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        sender_account = Account.objects.get(pk=serializer.validated_data['sender_account'], is_demo=False)
        recipient_account = self.get_recipient_account(serializer.validated_data['recipient_account'])

        if sender_account.is_blocked or recipient_account.is_blocked:
            return Response(status=status.HTTP_409_CONFLICT, data=blockedAccountError())

        if self.type == InternalTransfer.TO_TRADER and sender_account.user == recipient_account.user:
            return Response(status=status.HTTP_409_CONFLICT, data=tradersAccountRestriction())

        send_amount = Money(serializer.validated_data['send_amount'], sender_account.currency)
        if send_amount > sender_account.balance:
            return Response(status=status.HTTP_409_CONFLICT, data='Not enough money to perform transfer')

        transfer_details = self.get_transfer_details(sender_account, recipient_account)
        receive_amount, commission = self.calculate_receive_amount(
            transfer_details,
            sender_account,
            send_amount.amount,
            recipient_account.currency,
        )

        if receive_amount.amount <= 0:
            return Response(status=status.HTTP_409_CONFLICT, data='Receive amount is less or equal 0.00')

        commission_info = {
            **transfer_details['commission'],
            'commissionValue': {'amount': float(commission.amount), 'currency': str(commission.currency)},
        }
        transfer = InternalTransfer.objects.create(
            broker=request.broker,
            sender_account=sender_account,
            recipient_account=recipient_account,
            send_amount=send_amount,
            receive_amount=receive_amount,
            transfer_type=self.type,
            _commissions=commission_info,
            exchange_rate=transfer_details.get('exchange_coefficient', 1.00),
        )

        transfer.event_notify(request, transfer.sender_account.user)

        ready_for_transfer = True

        # Manual Approve Check
        if transfer.send_amount.to(USD).amount >= transfer_details['min_amount_for_approve']:
            transfer.status = InternalTransfer.WAITING_FOR_APPROVAL
            ready_for_transfer = False

        if ready_for_transfer:
            try:
                transfer.execute()
                transfer.status = InternalTransfer.COMPLETED
                transfer.status_notify()

            except InternalTransferError:
                transfer.status = InternalTransfer.FAILED
                transfer.status_notify()

        transfer.save()

        transfer.event_notify(request, transfer.sender_account.user)

        return Response(status=status.HTTP_201_CREATED)


class InternalTransferInner(generics.GenericAPIView, InternalTransferMixin):
    permission_classes = [IsAuthenticated, InternalTransferAccountsEnabled]
    serializer_class = InternalTransferInnerSerializer
    setting = 'InternalTransfersAccountsSetting'
    type = InternalTransfer.INNER

    def get_recipient_account(self, pk):
        return Account.objects.filter(pk=pk, is_demo=False).first()


class InternalTransferTraders(InternalTransferInner):
    permission_classes = [IsAuthenticated, InternalTransferTradersEnabled]
    serializer_class = InternalTransferTradersSerializer
    setting = 'InternalTransfersTradersSetting'
    type = InternalTransfer.TO_TRADER

    def get_recipient_account(self, login: str) -> Account:
        login_q = Q()
        if login.isdigit():
            login_q &= Q(mt4_login=login)
            login_q &= Q(mt5_login=login)
        else:
            login_q &= Q(ramm_login=login)

        accounts = Account.objects.filter(
            broker=self.request.broker,
            is_archived=False,
            is_demo=False,
        ).get_real().filter(login_q)

        if accounts.count() > 1:
            raise RecipientAccountCollisionError()
        else:
            return accounts.first()


class UserAccountsForTransfer(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InnerTransferAccountSerializer

    def get(self, request, *args, **kwargs):
        user_accounts = Account.objects.filter(
            broker=request.broker,
            user=request.user,
            is_archived=False,
            is_demo=False,
        ).get_real()

        if 'senderAccount' in request.GET:
            user_accounts = user_accounts.exclude(id=request.GET['senderAccount'])

        return Response(status=status.HTTP_200_OK, data=self.serializer_class(instance=user_accounts, many=True).data)


class InternalTransferList(generics.ListAPIView):
    queryset = InternalTransfer.objects.all().order_by('-id')
    serializer_class = InternalTransferListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        BrokerFilterBackend,
        UserInternalTransferFilter,
        SearchFilter,
        DjangoFilterBackend,
        RelatedOrderingFilter,
    ]
    pagination_class = PageSizePaginator
    ordering_fields = '__all__'
    search_fields = (
        'id',
        'sender_account__user__email',
    )

    def get_queryset(self):
        qr = self.filter_queryset(super().get_queryset())
        q = Q()

        filters_serializer = InternalTransferListFilter(data=self.request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        parsed_filters = filters_serializer.validated_data

        status = parsed_filters.get('status')
        transfer_type = parsed_filters.get('transfer_type')

        if status:
            q &= Q(status=status)
        if transfer_type:
            q &= Q(transfer_type=transfer_type)

        return qr.filter(q)


class InternalTransferRetrieve(generics.RetrieveAPIView):
    queryset = InternalTransfer.objects.all()
    serializer_class = InternalTransferListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [BrokerFilterBackend, UserInternalTransferFilter]
