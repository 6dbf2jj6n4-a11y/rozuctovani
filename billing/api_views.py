from rest_framework import viewsets

from accounts.models import User
from core.models import BillingLine
from .serializers import BillingLineSerializer


class BillingLineViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/billing-lines/  - vyuctovane polozky.

    - klient: pouze radky tykajici se jeho karet
    - spravce / admin: vse (lze filtrovat ?period=, ?client_card=)
    """

    serializer_class = BillingLineSerializer

    def get_queryset(self):
        user = self.request.user
        qs = BillingLine.objects.select_related("service_item", "period", "client_card", "client_card__unit")

        if user.role == User.Role.KLIENT:
            qs = qs.filter(client_card__client=user.client)

        period_id = self.request.query_params.get("period")
        if period_id:
            qs = qs.filter(period_id=period_id)

        client_card_id = self.request.query_params.get("client_card")
        if client_card_id:
            qs = qs.filter(client_card_id=client_card_id)

        return qs
