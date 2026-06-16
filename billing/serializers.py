from rest_framework import serializers

from .models import BillingLine


class BillingLineSerializer(serializers.ModelSerializer):
    service_item_name = serializers.CharField(source="service_item.name")
    invoice_class = serializers.CharField(source="service_item.invoice_class")
    invoice_class_label = serializers.CharField(source="service_item.get_invoice_class_display")
    period_label = serializers.CharField(source="period.__str__")
    unit_name = serializers.CharField(source="client_card.unit.name")

    class Meta:
        model = BillingLine
        fields = [
            "id",
            "period",
            "period_label",
            "service_item",
            "service_item_name",
            "invoice_class",
            "invoice_class_label",
            "unit_name",
            "amount",
            "share",
        ]
