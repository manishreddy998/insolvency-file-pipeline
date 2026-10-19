"""Same parsing and checks as layout-v2; the page text comes from Azure AI Document Intelligence."""
from .base import register
from .local import LayoutV2


@register
class AzureLayout(LayoutV2):
    name = "azure-di-layout"
    ocr = "azure"
