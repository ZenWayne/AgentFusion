import logging
from .logger import handler

agentgenerator_logger = logging.getLogger("agentgenerator")
agentgenerator_logger.setLevel(logging.DEBUG)
agentgenerator_logger.addHandler(handler)


