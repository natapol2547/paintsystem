from .nodetree_builder import NodeTreeBuilder, START, END, register, unregister, Add_Node
from .basic_layers import PSNodeTreeBuilder, get_alpha_over_nodetree
from .common import get_layer_blend_type, set_layer_blend_type


def create_layer_graph(layer, context):
	return PSNodeTreeBuilder.create_layer_graph(layer, context)