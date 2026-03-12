import logging
import os

logging.basicConfig(
    filename="/tmp/agent-console.log",
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from src.tui.app import AgentConsoleApp

AgentConsoleApp(project_path=os.getcwd()).run()
