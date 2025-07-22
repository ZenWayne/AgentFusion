this is a cli interface for agent fusion

#design pattern
first, the created agent will plan what to do, and then execute the plan
we need a orchestrator to manage the agent's plan and execution, and update the plan
once the agent finish the task, the executed agent will return the result to the orchestrator
then executed