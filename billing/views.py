"""
Klientský portál - přehled historických vyúčtování.

Čte výhradně z BillingLine (nikdy nic nepřepočítává) - jakmile je
Období uzavřené, tady zobrazené hodnoty se už nezmění, viz
billing/engine.py (BillingPeriodClosedError).
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from accounts.models import User
from core.models import BillingLine, Client, Period
from billing.statement_generator import build_statement_data


def _resolve_client(request):
    """Klient vidí jen sebe. Admin/správce si může přes ?client=<id> zobrazit
    kteréhokoli klienta (podpora/kontrola) - bez parametru nevybere nikoho."""
    user = request.user
    if user.role == User.Role.KLIENT:
        return user.client

    client_id = request.GET.get("client")
    if client_id:
        return get_object_or_404(Client, pk=client_id)
    return None


@login_required
def periods_list(request):
    client = _resolve_client(request)

    all_clients = None
    if request.user.role != User.Role.KLIENT:
        all_clients = Client.objects.filter(is_active=True).order_by("name")

    periods = []
    if client is not None:
        periods = (
            Period.objects.filter(billing_lines__client_card__client=client)
            .distinct()
            .order_by("-year", "-month")
        )

    return render(request, "billing/periods_list.html", {
        "client": client,
        "all_clients": all_clients,
        "periods": periods,
    })


@login_required
def period_detail(request, period_id):
    client = _resolve_client(request)
    if client is None:
        raise PermissionDenied("Není vybraný klient.")

    period = get_object_or_404(Period, pk=period_id)

    has_data = BillingLine.objects.filter(period=period, client_card__client=client).exists()
    if not has_data:
        raise PermissionDenied("Pro tohoto klienta a období nejsou k dispozici žádná data.")

    data = build_statement_data(client, period)
    all_cards = {line["card"] for cls in data["classes"] for line in cls["lines"]}

    return render(request, "billing/period_detail.html", {
        "client": client,
        "period": period,
        "classes": data["classes"],
        "grand_total": data["grand_total"],
        "show_card_column": len(all_cards) > 1,
    })
