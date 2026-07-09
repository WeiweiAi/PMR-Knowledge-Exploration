import json
from graphviz import Digraph
import itertools
from typing import Dict, Optional

def clean_id(uri):
    return uri.split('/')[-1]

def clean_property(uri):
    if "#" in uri:
        return uri.split("#")[-1]
    return uri.split("/")[-1]

def get_comp_tuple(comp_list):
    return tuple(sorted([clean_id(c) for c in comp_list]))

def get_ontology_label(ontology_list):
    return "\n".join(sorted([clean_id(uri) for uri in ontology_list]))

def get_ontology_id(ontology_list):
    return "_".join(sorted([clean_id(uri) for uri in ontology_list]))

def build_bioprocess_graph(json_file_path: str | Dict,  output_file: Optional[str] = None) -> Digraph:
    """
    Builds a directed graph representing biological processes from a JSON file.

    Args:
        json_file_path (str): Path to the JSON file containing biological process data.
        output_file (str, optional): Path to save the GraphViz graph as a PNG file.
        If None, the graph is not saved.

    Returns:
        Digraph: The built GraphViz graph.
    
    """
    if isinstance(json_file_path, dict):
        json_data = json_file_path
    else:
        with open(json_file_path, "r") as f:
            json_data = json.load(f)

    dot = Digraph(name="Biological_Processes", format="png")
    
    NODE_SIZE = 1.5
    dot.attr(rankdir="LR", splines="spline", nodesep="0.3", ranksep="2.0", pad="0.5")

    species_node_palette = itertools.cycle(["#FFB3BA", "#BAE1FF", "#BAFFC9", "#FFFFBA", "#E0BBE4"])
    species_edge_palette = itertools.cycle(["#E60073", "#007ACC", "#009933", "#CCCC00", "#7A0099"])
    comp_palette = itertools.cycle(["#000080", "#006400", "#8B0000", "#4B0082", "#2F4F4F"])

    species_colors = {}
    comp_colors = {}

    for proc_name, proc_info in json_data.items():
        meds = proc_info.get("mediator", [])
        if not meds:
            continue
            
        med_id = get_ontology_id(meds[0]["ontology ID"])
        med_label = get_ontology_label(meds[0]["ontology ID"])
        
        proc_props = set(proc_info.get("properties", []))
        med_props = set(meds[0].get("properties", []))
        all_props = sorted(list(proc_props.union(med_props)))
        
        # 1. Build the Mediator Pillar
        med_text_id = f"text_{med_id}"
        m_props = [clean_property(p) for p in all_props]
        
        with dot.subgraph(name=f"same_{med_id}") as mcol:
            mcol.attr(rank="same")
            if m_props:
                mcol.node(med_text_id, label="\n".join(m_props), shape="plaintext", fontcolor="#555555", fontsize="10", margin="0.05")
            else:
                mcol.node(med_text_id, label="", shape="none", width="0", height="0", margin="0")
                
            mcol.node(med_id, label=med_label, shape="box", style="filled, rounded", fillcolor="#D1E8F7", height="0.6", width="1.5")
            
            # Text rests closely above the box
            mcol.edge(med_text_id, med_id, style="invis", weight="1000")
        
        physical_compartments = {}
        unique_edges = set() 

        # 2. Collect Species Data
        for src in proc_info.get("source", []):
            src_sp_id = get_ontology_id(src["ontology ID"])
            src_sp_label = get_ontology_label(src["ontology ID"])
            src_comps = get_comp_tuple(src.get("compartments", src.get("compartment", [])))
            src_props = src.get("properties", [])
            
            if src_sp_id not in physical_compartments.setdefault(src_comps, {}):
                physical_compartments[src_comps][src_sp_id] = {"label": src_sp_label, "properties": set(src_props)}
            else:
                physical_compartments[src_comps][src_sp_id]["properties"].update(src_props)
            
            if src_sp_id not in species_colors:
                species_colors[src_sp_id] = (next(species_node_palette), next(species_edge_palette))
            if src_comps not in comp_colors:
                comp_colors[src_comps] = next(comp_palette)
                
        for snk in proc_info.get("sink", []):
            snk_sp_id = get_ontology_id(snk["ontology ID"])
            snk_sp_label = get_ontology_label(snk["ontology ID"])
            snk_comps = get_comp_tuple(snk.get("compartments", snk.get("compartment", [])))
            snk_props = snk.get("properties", [])
            
            if snk_sp_id not in physical_compartments.setdefault(snk_comps, {}):
                physical_compartments[snk_comps][snk_sp_id] = {"label": snk_sp_label, "properties": set(snk_props)}
            else:
                physical_compartments[snk_comps][snk_sp_id]["properties"].update(snk_props)

            if snk_sp_id not in species_colors:
                species_colors[snk_sp_id] = (next(species_node_palette), next(species_edge_palette))
            if snk_comps not in comp_colors:
                comp_colors[snk_comps] = next(comp_palette)

        max_nodes_per_cluster = max((len(sp_dict) for sp_dict in physical_compartments.values()), default=1)
        comp_list = list(physical_compartments.keys())
        midpoint = len(comp_list) // 2
        left_comps = comp_list[:midpoint] if len(comp_list) > 1 else comp_list

        for src in proc_info.get("source", []):
            src_sp_id = get_ontology_id(src["ontology ID"])
            src_comps = get_comp_tuple(src.get("compartments", src.get("compartment", [])))
            src_node_id = f"node_{abs(hash(src_sp_id))}_{abs(hash(src_comps))}"
            if src_comps in left_comps:
                unique_edges.add((src_node_id, med_id, src_sp_id, "forward"))
            else:
                unique_edges.add((med_id, src_node_id, src_sp_id, "back"))

        for snk in proc_info.get("sink", []):
            snk_sp_id = get_ontology_id(snk["ontology ID"])
            snk_comps = get_comp_tuple(snk.get("compartments", snk.get("compartment", [])))
            snk_node_id = f"node_{abs(hash(snk_sp_id))}_{abs(hash(snk_comps))}"
            if snk_comps in left_comps:
                unique_edges.add((snk_node_id, med_id, snk_sp_id, "back"))
            else:
                unique_edges.add((med_id, snk_node_id, snk_sp_id, "forward"))

        # 3. Build Rigid Pillars 
        all_created_circles = {"left": [], "right": []}
        left_circle_anchors = []
        right_circle_anchors = []

        for comps, sp_dict in physical_compartments.items():
            is_left = comps in left_comps
            cluster_name = f"cluster_{abs(hash(comps))}"
            c_color = comp_colors[comps]
            
            with dot.subgraph(name=cluster_name) as comp_box:
                comp_box.attr(label="\n".join(comps), color=c_color, style="solid", penwidth="2", margin="12.0")
                
                ordered_species = sorted(sp_dict.items())
                chain_elements = []
                
                for i in range(max_nodes_per_cluster):
                    prop_id = f"prop_{abs(hash(comps))}_{i}"
                    
                    if i < len(ordered_species):
                        sp_id, sp_data = ordered_species[i]
                        circle_id = f"node_{abs(hash(sp_id))}_{abs(hash(comps))}" 
                        
                        p_props = [clean_property(p) for p in sorted(list(sp_data["properties"]))]
                        if p_props:
                            comp_box.node(prop_id, label="\n".join(p_props), shape="plaintext", fontcolor="#444444", fontsize="10", margin="0.05")
                        else:
                            comp_box.node(prop_id, label="", shape="none", width="0", height="0", margin="0")
                            
                        node_color, _ = species_colors[sp_id]
                        comp_box.node(circle_id, label=sp_data["label"], shape="circle", style="filled", fillcolor=node_color, width=str(NODE_SIZE), height=str(NODE_SIZE), fixedsize="true")
                    else:
                        circle_id = f"dummy_node_{abs(hash(comps))}_{i}"
                        comp_box.node(prop_id, label="", shape="none", width="0", height="0", margin="0")
                        comp_box.node(circle_id, label="", shape="circle", style="invis", width=str(NODE_SIZE), height=str(NODE_SIZE), fixedsize="true")
                        
                    chain_elements.extend([prop_id, circle_id])
                    
                    if is_left:
                        all_created_circles["left"].append(circle_id)
                    else:
                        all_created_circles["right"].append(circle_id)
                
                # THE FIX: Save the CIRCLE node (index 1), not the text node (index 0)
                if is_left:
                    left_circle_anchors.append(chain_elements[1])
                else:
                    right_circle_anchors.append(chain_elements[1])
                    
                # Link elements top-to-bottom sequentially
                for idx in range(len(chain_elements) - 1):
                    comp_box.edge(chain_elements[idx], chain_elements[idx+1], style="invis", weight="1000")
                    
                # Ensure local vertical stacking
                rank_str = "; ".join(chain_elements) + ";"
                comp_box.body.append(f'{{ rank=same; {rank_str} }}')
                
        # 4. The Invisible Horizontal Spine
        # Connects left-circle to mediator-box to right-circle with high weight.
        # This aligns the entities, letting the text float naturally on top.
        for l_node in left_circle_anchors:
            dot.edge(l_node, med_id, style="invis", weight="100")
        for r_node in right_circle_anchors:
            dot.edge(med_id, r_node, style="invis", weight="100")
                
        # 5. Apply Symmetrical Centering Springs
        for cid in all_created_circles["left"]:
            dot.edge(cid, med_id, style="invis", weight="10")
        for cid in all_created_circles["right"]:
            dot.edge(med_id, cid, style="invis", weight="10")

        # 6. Draw Visible Workflow Edges 
        for start_node, end_node, sp_id, direction in unique_edges:
            _, edge_color = species_colors[sp_id]
            dot.edge(start_node, end_node, constraint="false", color=edge_color, penwidth="1.5", dir=direction)
    if output_file:
        dot.render(output_file, view=True, format="png", cleanup=True)
    return dot


if __name__ == "__main__":
    # Example usage
    dot_graph = build_bioprocess_graph("./../process_rdf/Ostby_2009_NBC_simplified.json",
                                            output_file="Ostby_2009_NBC_graph.png")
