from pydantic import BaseModel, field_validator
from typing import Literal, Union, Any

class GraphFlowEdge(BaseModel):
    target: str
    condition: str | None = None
    activation_group: str | None = None
    activation_condition: Literal["all", "any"] = "all"

class GraphFlowNode(BaseModel):
    name: str
    edges: list[GraphFlowEdge]

    @classmethod
    def from_tuple(cls, node_tuple: Union[list, tuple]) -> "GraphFlowNode":
        """
        Convert from tuple format to GraphFlowNode.
        
        Tuple formats supported:
        - ["node_name", "target_node"] -> simple edge
        - ["node_name", {"condition": "target"}] -> conditional edge
        - ["node_name", {"condition1": "target1", "condition2": "target2"}] -> multiple conditional edges
        - ["node_name", {"condition": ["target", "activation_group", "activation_condition"]}] -> edge with activation group
        - ["node_name", {"condition": ["target", "activation_group"]}] -> edge with activation group (default activation_condition="all")
        """
        if not isinstance(node_tuple, (list, tuple)) or len(node_tuple) < 2:
            raise ValueError(f"Invalid node tuple format: {node_tuple}")
        
        node_name = node_tuple[0]
        edges_data = node_tuple[1]
        edges = []
        
        if isinstance(edges_data, str):
            # Simple edge: ["node_name", "target_node"]
            edges.append(GraphFlowEdge(target=edges_data, condition="", activation_group=edges_data))
        elif isinstance(edges_data, dict):
            # Conditional edges: ["node_name", {"condition": "target"}]
            # or ["node_name", {"condition": ["target", "activation_group", "activation_condition"]}]
            for condition, target_data in edges_data.items():
                if isinstance(target_data, str):
                    # Simple target: {"condition": "target"}
                    edges.append(GraphFlowEdge(target=target_data, condition=condition, activation_group=target_data))
                elif isinstance(target_data, (list, tuple)) and 1 <= len(target_data) <= 3:
                    # Complex target with activation group: 
                    # {"condition": ["target", "activation_group", "activation_condition"]}
                    # {"condition": ["target", "activation_group"]}
                    # {"condition": ["target"]}
                    
                    # Extract values with defaults for missing elements
                    target = target_data[0] if len(target_data) >= 1 else ""
                    activation_group = target_data[1] if len(target_data) >= 2 else target
                    activation_condition = target_data[2] if len(target_data) >= 3 else "all"
                    
                    # Validate activation_condition if provided
                    if activation_condition not in ["all", "any"]:
                        raise ValueError(f"Invalid activation_condition: {activation_condition}. Must be 'all' or 'any'")
                    
                    edges.append(GraphFlowEdge(
                        target=target,
                        condition=condition,
                        activation_group=activation_group,
                        activation_condition=activation_condition
                    ))
                else:
                    raise ValueError(f"Invalid target format in edges: {target_data}")
        else:
            raise ValueError(f"Invalid edges format in tuple: {edges_data}")
        
        return cls(name=node_name, edges=edges)

class GraphFlowConfig(BaseModel):
    name: str
    description: str
    labels: list[str]
    type: str
    participants: list[str]
    nodes: list[GraphFlowNode]

    @field_validator('nodes', mode='before')
    @classmethod
    def convert_nodes_from_tuples(cls, v: Any) -> list[GraphFlowNode]:
        """
        Convert nodes from tuple format to GraphFlowNode objects.
        This allows the metadata.json to use the simpler tuple format.
        """
        if not isinstance(v, list):
            return v
        
        converted_nodes = []
        for node_data in v:
            if isinstance(node_data, (list, tuple)):
                # Convert from tuple format
                converted_nodes.append(GraphFlowNode.from_tuple(node_data))
            elif isinstance(node_data, dict):
                # Already in proper format
                converted_nodes.append(GraphFlowNode(**node_data))
            else:
                raise ValueError(f"Invalid node format: {node_data}")
        
        return converted_nodes

ComponentInfo = GraphFlowConfig
