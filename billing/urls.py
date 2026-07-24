from django.urls import path

from . import views

urlpatterns = [
    path("", views.periods_list, name="moje-vyuctovani"),
    path("<int:period_id>/", views.period_detail, name="moje-vyuctovani-detail"),
]
