from rest_framework import serializers

from money.serializers import MoneyField


class InnerTransferAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    login = serializers.CharField()
    balance = MoneyField()


class InternalTransferInnerSerializer(serializers.Serializer):
    sender_account = serializers.IntegerField()
    recipient_account = serializers.IntegerField()
    send_amount = serializers.FloatField(required=False)


class InternalTransferTradersSerializer(InternalTransferInnerSerializer):
    recipient_account = serializers.CharField()


class InternalTransferListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender_account = serializers.CharField(source='sender_account.login')
    recipient_account = serializers.CharField(source='recipient_account.login')
    send_amount = MoneyField()
    transfer_type = serializers.CharField()
    status = serializers.CharField()
    created = serializers.DateTimeField()
    email = serializers.CharField(source='sender_account.user.email')
    commission_info = serializers.DictField(source='_commissions')


class InternalTransferInfoDetailsField(serializers.Serializer):
    min_commission = MoneyField()
    max_commission = MoneyField()
    transfer_type = serializers.CharField()
    commission = serializers.DictField()
    exchange_rate = serializers.CharField(required=False)
    exchange_coefficient = serializers.FloatField(required=False)
    exchange_coefficient_for_fix = serializers.FloatField()


class InternalTransferInfoSerializer(serializers.Serializer):
    details = InternalTransferInfoDetailsField()
    max_amount = serializers.FloatField()
