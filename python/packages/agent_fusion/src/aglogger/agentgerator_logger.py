import logging
from .logger import gobal_log_filterer

agentgenerator_logger = logging.getLogger("agentgenerator")
agentgenerator_logger.setLevel(logging.DEBUG)
agentgenerator_logger.addHandler(gobal_log_filterer)


