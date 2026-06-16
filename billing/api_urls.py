from rest_framework.routers import DefaultRouter

from .api_views import BillingLineViewSet

router = DefaultRouter()
router.register("billing-lines", BillingLineViewSet, basename="billing-line")

urlpatterns = router.urls
