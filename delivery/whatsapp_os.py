# delivery/whatsapp_os.py
import logging
import re
import httpx
from typing import Optional
from .base import BaseNotificationGateway

logger = logging.getLogger("OpenClaw.Delivery")

class WhatsAppOSGateway(BaseNotificationGateway):
    """
    Harness for self-hosted open-source WhatsApp Gateways running on your local Docker network
    or private server to bypass official Meta API premium conversation charges.
    """
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, instance_name: str = "openclaw"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.instance_name = instance_name
        self.headers = {"Content-Type": "application/json"}
        
        if self.api_key:
            # Evolution API defaults to using an 'apikey' header token for access security
            self.headers["apikey"] = self.api_key

    def _convert_markdown_to_whatsapp(self, markdown_text: str) -> str:
        """
        Converts typical RAG markdown structures to clean formatting syntax tolerated by WhatsApp:
        - **Bold text** -> *Bold text*
        - *Italic text* -> _Italic text_
        - Custom cleaner sweeps for clean line-breaks
        """
        # Swap bold indicators
        whatsapp_text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', markdown_text)
        # Swap basic italic indicators
        whatsapp_text = re.sub(r'\*(.*?)\*', r'_\1_', whatsapp_text)
        return whatsapp_text

    async def send_notification(
        self, 
        recipient: str, 
        text: str, 
        media_url: Optional[str] = None
    ) -> bool:
        """
        Sends an unauthenticated/self-hosted message or rich media message via HTTP POST.
        """
        formatted_message = self._convert_markdown_to_whatsapp(text)
        
        # Decide if we are performing a text stream or a rich-media distribution (Game charts, injury graphs)
        if media_url:
            endpoint = f"{self.base_url}/message/sendMedia/{self.instance_name}"
            payload = {
                "number": recipient,
                "mediaMessage": {
                    "mediatype": "image",
                    "caption": formatted_message,
                    "media": media_url
                }
            }
        else:
            endpoint = f"{self.base_url}/message/sendText/{self.instance_name}"
            payload = {
                "number": recipient,
                "options": {
                    "delay": 1000,          # Built-in delay simulation to look human
                    "presence": "composing"  # Triggers a realistic typing status 
                },
                "textMessage": {
                    "text": formatted_message
                }
            }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    endpoint, 
                    json=payload, 
                    headers=self.headers, 
                    timeout=15.0
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"Successfully routed sports update to recipient: {recipient}")
                    return True
                else:
                    logger.error(f"OS WhatsApp Gateway rejected request ({response.status_code}): {response.text}")
                    return False
                    
            except httpx.RequestError as exc:
                logger.error(f"Connection timeout/error communicating with WhatsApp gateway: {exc}")
                return False