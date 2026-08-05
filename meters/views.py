"""
Obrazovka pro spravce na zadavani odectu meridel - jedno meridlo na
obrazovku, navigace sipkami/swipem, kontrola odchylky proti historii.
Viz core/models.py Meter.consumption_for pro vypocet spotreby.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Meter, MeterReading, Period


def _require_spravce(user):
    if not user.is_spravce_role:
        raise PermissionDenied("Zadávání odečtů je jen pro správce.")


@login_required
def readings_entry(request):
    user = request.user
    _require_spravce(user)

    sites = user.get_accessible_sites().order_by("name")
    site_id = request.GET.get("site")
    site = sites.filter(pk=site_id).first() if site_id else sites.first()

    periods = Period.objects.order_by("-year", "-month")[:24]
    period_id = request.GET.get("period")
    period = periods.filter(pk=period_id).first() if period_id else None
    if period is None:
        period = Period.objects.filter(status=Period.Status.OPEN).first() or Period.objects.first()

    meters_data = []
    if site and period:
        meters = (
            Meter.objects.filter(site=site, is_virtual=False)
            .order_by("display_order", "meter_type", "code")
        )
        prev_period = period.previous_period()
        yoy_period = Period.objects.filter(year=period.year - 1, month=period.month).first()
        earlier_periods = list(
            Period.objects.filter(
                Q(year__lt=period.year) | Q(year=period.year, month__lt=period.month)
            ).order_by("-year", "-month")[:6]
        )

        for m in meters:
            existing = m.readings.filter(period=period).first()
            previous = m.readings.filter(period=prev_period).first() if prev_period else None

            hist = []
            for p in earlier_periods:
                c = m.consumption_for(p)
                if c is not None:
                    hist.append({"label": str(p), "value": float(c)})
            hist.reverse()

            yoy_value = m.consumption_for(yoy_period) if yoy_period else None

            meters_data.append({
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "meter_type_label": m.get_meter_type_display(),
                "unit": m.unit_of_measure,
                "reading_mode": m.reading_mode,
                "parent_id": m.parent_meter_id,
                "prev_value": float(previous.value) if previous else None,
                "prev_date": previous.reading_date.strftime("%d. %m. %Y") if previous else None,
                "yoy_value": float(yoy_value) if yoy_value is not None else None,
                "yoy_label": str(yoy_period) if yoy_period else None,
                "hist": hist,
                "existing": {
                    "value": float(existing.value) if existing else None,
                    "note": existing.note if existing else "",
                    "reset_from_value": (
                        float(existing.reset_from_value)
                        if existing and existing.reset_from_value is not None else None
                    ),
                } if existing else None,
            })

    return render(request, "meters/readings_entry.html", {
        "sites": sites,
        "site": site,
        "periods": periods,
        "period": period,
        "meters_data": meters_data,
        "period_closed": bool(period and period.status == Period.Status.CLOSED),
    })


@login_required
@require_POST
def readings_save(request):
    user = request.user
    _require_spravce(user)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)

    meter = get_object_or_404(Meter, pk=payload.get("meter_id"))
    if not user.get_accessible_sites().filter(pk=meter.site_id).exists():
        raise PermissionDenied("K tomuto areálu nemáš přístup.")

    period = get_object_or_404(Period, pk=payload.get("period_id"))
    if period.status == Period.Status.CLOSED:
        return JsonResponse(
            {"ok": False, "error": "Období je uzavřené, odečet nejde upravit."}, status=400
        )

    try:
        value = Decimal(str(payload.get("value")))
    except (InvalidOperation, TypeError):
        return JsonResponse({"ok": False, "error": "Zadej číselnou hodnotu."}, status=400)

    reset_raw = payload.get("reset_from_value")
    reset_from_value = None
    if reset_raw not in (None, ""):
        try:
            reset_from_value = Decimal(str(reset_raw))
        except InvalidOperation:
            return JsonResponse({"ok": False, "error": "Neplatný počáteční stav."}, status=400)

    if meter.reading_mode == Meter.ReadingMode.CONSUMPTION:
        consumption = value
    elif reset_from_value is not None:
        consumption = value - reset_from_value
    else:
        prev_period = period.previous_period()
        previous = meter.readings.filter(period=prev_period).first() if prev_period else None
        consumption = (value - previous.value) if previous else None

    if consumption is not None and consumption < 0:
        return JsonResponse({
            "ok": False,
            "error": (
                "Spotřeba nemůže být záporná. Pokud bylo měřidlo vyměněno, "
                "zadej počáteční stav nového měřidla."
            ),
        }, status=400)

    MeterReading.objects.update_or_create(
        meter=meter, period=period,
        defaults={
            "value": value,
            "reset_from_value": reset_from_value,
            "note": (payload.get("note") or "")[:300],
            "reading_date": timezone.localdate(),
        },
    )
    return JsonResponse({
        "ok": True,
        "consumption": float(consumption) if consumption is not None else None,
    })
