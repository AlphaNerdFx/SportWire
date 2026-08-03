# delivery/router.py
from typing import Dict, Any, Optional
from .whatsapp_os import WhatsAppOSGateway

class DeliveryOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.whatsapp = WhatsAppOSGateway(
            base_url=config.get("WHATSAPP_GATEWAY_URL", "http://localhost:8080"),
            api_key=config.get("WHATSAPP_API_KEY"),
            instance_name=config.get("WHATSAPP_INSTANCE", "openclaw")
        )
        
    async def dispatch(self, platform: str, recipient_id: str, content: str, media: Optional[str] = None) -> bool:
        """
        Dynamically handles multi-channel routing between WhatsApp or Messenger targets.
        """
        normalized_platform = platform.strip().lower()
        if normalized_platform == "whatsapp":
            return await self.whatsapp.send_notification(recipient_id, content, media)
        elif normalized_platform == "messenger":
            # Direct routing pointer to self-hosted/Free tier Page Hook logic
            pass 
        return False