from django.urls import path

from . import views

urlpatterns = [
    path("", views.readings_entry, name="odecty"),
    path("ulozit/", views.readings_save, name="odecty-ulozit"),
    path("uzavrit/", views.readings_close, name="odecty-uzavrit"),
    path("foto/", views.readings_photo, name="odecty-foto"),
    path("foto/smazat/", views.readings_photo_delete, name="odecty-foto-smazat"),
    path("preradit/", views.readings_reorder, name="odecty-preradit"),
]
