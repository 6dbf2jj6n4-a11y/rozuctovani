from django.urls import path

from . import views

urlpatterns = [
    path("", views.readings_entry, name="odecty"),
    path("ulozit/", views.readings_save, name="odecty-ulozit"),
    path("foto/", views.readings_photo, name="odecty-foto"),
    path("preradit/", views.readings_reorder, name="odecty-preradit"),
]
