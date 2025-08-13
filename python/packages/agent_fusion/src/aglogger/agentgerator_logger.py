import logging

from .logger import global_log_filterer


agentgenerator_logger = logging.getLogger("agentgenerator")

agentgenerator_logger.setLevel(logging.DEBUG)

agentgenerator_logger.addHandler(global_log_filterer)



