# delivery/base.py
import abc
from typing import Optional

class BaseNotificationGateway(abc.ABC):
    """
    Abstract interface guaranteeing that any free, open-source delivery method
    implements a standardized asynchronous routing protocol.
    """
    
    @abc.abstractmethod
    async def send_notification(
        self, 
        recipient: str, 
        text: str, 
        media_url: Optional[str] = None
    ) -> bool:
        """
        Dispatches structured text or media updates to a targeted endpoint.
        """
        pass