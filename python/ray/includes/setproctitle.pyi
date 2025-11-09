# source: setproctitle.pxi
import threading
from typing import Optional

_current_proctitle:Optional[str]
_current_proctitle_lock:threading.Lock

def setproctitle(title:str)->None: ...
def getproctitle()->str: ...
