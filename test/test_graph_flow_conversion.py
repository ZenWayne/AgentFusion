import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.dataclass.graph_flow import GraphFlowConfig, GraphFlowNode, GraphFlowEdge

def test_tuple_conversion():
    """Test converting from tuple format to GraphFlowNode objects"""
    
    # Test data similar to metadata.json
    test_data = {
        "name": "prompt_specialize_flow",
        "description": "A workflow for prompt specialization",
        "labels": ["prompt", "prompt_specialization", "group_chat", "graph_flow"],
        "type": "graph_flow",
        "participants": ["template_extractor", "prompt_specialization", "file_system", "human_proxy"],
        "nodes": [
            ["template_extractor", "prompt_specialization"],
            ["prompt_specialization", {"": "human_proxy", "<EOF>": "file_system"}],
            ["human_proxy", "prompt_specialization"]
        ]
    }
    
    # Create GraphFlowConfig from test data
    config = GraphFlowConfig(**test_data)
    
    # Verify the conversion worked correctly
    assert len(config.nodes) == 3
    
    # Check first node
    assert config.nodes[0].name == "template_extractor"
    assert len(config.nodes[0].edges) == 1
    assert config.nodes[0].edges[0].target == "prompt_specialization"
    assert config.nodes[0].edges[0].condition == ""
    
    # Check second node (with conditional edges)
    assert config.nodes[1].name == "prompt_specialization"
    assert len(config.nodes[1].edges) == 2
    
    # Find edges by condition
    empty_condition_edge = next(edge for edge in config.nodes[1].edges if edge.condition == "")
    eof_condition_edge = next(edge for edge in config.nodes[1].edges if edge.condition == "<EOF>")
    
    assert empty_condition_edge.target == "human_proxy"
    assert eof_condition_edge.target == "file_system"
    
    # Check third node
    assert config.nodes[2].name == "human_proxy"
    assert len(config.nodes[2].edges) == 1
    assert config.nodes[2].edges[0].target == "prompt_specialization"
    assert config.nodes[2].edges[0].condition == ""
    
    print("✅ All tuple conversion tests passed!")

def test_from_tuple_method():
    """Test the from_tuple class method directly"""
    
    # Test simple edge
    node = GraphFlowNode.from_tuple(["node1", "node2"])
    assert node.name == "node1"
    assert len(node.edges) == 1
    assert node.edges[0].target == "node2"
    assert node.edges[0].condition == ""
    
    # Test conditional edge
    node = GraphFlowNode.from_tuple(["node1", {"condition1": "node2"}])
    assert node.name == "node1"
    assert len(node.edges) == 1
    assert node.edges[0].target == "node2"
    assert node.edges[0].condition == "condition1"
    
    # Test multiple conditional edges
    node = GraphFlowNode.from_tuple(["node1", {"": "node2", "end": "node3"}])
    assert node.name == "node1"
    assert len(node.edges) == 2
    
    empty_edge = next(edge for edge in node.edges if edge.condition == "")
    end_edge = next(edge for edge in node.edges if edge.condition == "end")
    
    assert empty_edge.target == "node2"
    assert end_edge.target == "node3"
    
    print("✅ All from_tuple method tests passed!")

def test_complex_tuple_with_activation_groups():
    """Test the new complex tuple format with activation groups"""
    
    # Test complex edge with activation groups
    node = GraphFlowNode.from_tuple(["node1", {"target1": ["activation_group1", "all"], "target2": ["activation_group2", "any"]}])
    assert node.name == "node1"
    assert len(node.edges) == 2
    
    # Find edges by condition
    target1_edge = next(edge for edge in node.edges if edge.condition == "target1")
    target2_edge = next(edge for edge in node.edges if edge.condition == "target2")
    
    # Check first edge
    assert target1_edge.target == "activation_group1"
    assert target1_edge.condition == "target1"
    assert target1_edge.activation_group == "activation_group1"
    assert target1_edge.activation_condition == "all"
    
    # Check second edge
    assert target2_edge.target == "activation_group2"
    assert target2_edge.condition == "target2"
    assert target2_edge.activation_group == "activation_group2"
    assert target2_edge.activation_condition == "any"
    
    print("✅ All complex tuple with activation groups tests passed!")

def test_mixed_tuple_formats():
    """Test mixed tuple formats in the same configuration"""
    
    test_data = {
        "name": "mixed_flow",
        "description": "A workflow with mixed tuple formats",
        "labels": ["test", "graph_flow"],
        "type": "graph_flow",
        "participants": ["node1", "node2", "node3", "group1", "group2"],
        "nodes": [
            ["node1", "node2"],
            ["node2", {"": "node3", "complex": ["group1", "all"]}],
            ["node3", {"simple": "node1", "group": ["group2", "any"]}]
        ]
    }
    
    config = GraphFlowConfig(**test_data)
    assert len(config.nodes) == 3
    
    # Check mixed formats work correctly
    assert config.nodes[1].name == "node2"
    assert len(config.nodes[1].edges) == 2
    
    # Simple edge
    simple_edge = next(edge for edge in config.nodes[1].edges if edge.condition == "")
    assert simple_edge.target == "node3"
    assert simple_edge.activation_group is None
    
    # Complex edge
    complex_edge = next(edge for edge in config.nodes[1].edges if edge.condition == "complex")
    assert complex_edge.target == "group1"
    assert complex_edge.activation_group == "group1"
    assert complex_edge.activation_condition == "all"
    
    print("✅ All mixed tuple formats tests passed!")

if __name__ == "__main__":
    test_from_tuple_method()
    test_tuple_conversion()
    test_complex_tuple_with_activation_groups()
    test_mixed_tuple_formats()
    print("\n🎉 All tests completed successfully!") 