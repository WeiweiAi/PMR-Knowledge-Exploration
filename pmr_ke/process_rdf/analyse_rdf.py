import os
from rdflib import Graph, URIRef, Literal
from typing import Dict, Optional, List, Tuple, Any
from utilities import  qualifier_term, cellml_term, sedml_term, ontology_term_bio,local_id
from extract_rdf import read_rdf_file
from qdrant_client import QdrantClient, models
from collections import deque
import json
import logging
import copy

logging.basicConfig(
    filename="rdf_process.log",
    filemode="w",          # Overwrite the log file
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# Suppress the messy Windows symlink warning
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
# Initialize in-memory Qdrant
qdrant_client = QdrantClient(":memory:")
COLLECTION_NAME = "schema_targets"
# Define and set the active model
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
qdrant_client.set_model(MODEL_NAME)
# Define target concepts with phrase variants for better semantic matching
# Each concept can have multiple phrases that all map to the same schema_key
TARGET_CONCEPTS_PHRASES = {
    "source": ["has source participant"],
    "sink": ["has sink participant"],
    "mediator": ["has mediator participant"],
    "isProperty": ["is property of"],
    "hasProperty": ["has property"],
    "multiplier": ["has multiplier", "has coefficient"],
    "part": ["has part", "is part of", 'compartment of', 'is compartment of','located in'],
    "is": [
        "is",
        "is version of",
        "has version",
        "has physical definition",
        "is computational component for",
        "has physical entity reference"
    ]
}

def setup_qdrant():
    """
    Automatically sets up the Qdrant collection, generates embeddings, and inserts target concepts.
    Handles extraction of FastEmbed parameters, collection creation, and document vectorization.
    """
    try:
        # Extract configuration from the active FastEmbed model
        # For in-memory configuration, extracts base parameters (size, distance metric)
        vector_params = qdrant_client.get_fastembed_vector_params()
        if not vector_params:
            raise ValueError("Could not retrieve FastEmbed vector parameters")
        
        base_params = list(vector_params.values())[0]  # Extract first config: size=384, distance=COSINE
        
        # Create collection with extracted vector configuration
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=base_params  # Uses unnamed vector space
        )
        
        # Prepare data for upload by splitting each concept into its phrase variants
        # This allows Qdrant to match individual phrases while maintaining the schema_key
        ids = []
        descriptions = []
        payloads = []
        next_id = 0
        
        # Process each concept and its phrase variants
        for schema_key, phrases in TARGET_CONCEPTS_PHRASES.items():
            for phrase in phrases:
                ids.append(next_id)
                descriptions.append(phrase)
                payloads.append({"schema_key": schema_key})
                next_id += 1
        
        # Upload documents with automatic FastEmbed inference
        # Each phrase gets its own vector, all mapped to their schema_key
        qdrant_client.upload_collection(
            collection_name=COLLECTION_NAME,
            vectors=[models.Document(text=doc, model=MODEL_NAME) for doc in descriptions],
            payload=payloads,
            ids=ids,
        )
    
    except Exception as e:
        print(f"Error during Qdrant setup: {type(e).__name__}: {e}")
        raise

# Initialize Qdrant collection at module load time
try:
    setup_qdrant()
except Exception as e:
    print(f"Fatal error: Failed to initialize Qdrant. Application may not function correctly: {e}")

def query_qdrant(clean_text: str, threshold: float = 0.7) -> Optional[str]:
    """
    Queries the Qdrant collection for the best match to the provided text.
    Uses semantic similarity matching with phrase-based indexing where each concept
    can have multiple phrase variants that all map to the same schema_key.
    
    Args:
        clean_text (str): The text to query against the Qdrant collection.
        threshold (float): Minimum similarity score (0-1) required to return a match. 
                          Default 0.7 provides good precision with phrase-variant matching.
    
    Returns:
        Optional[str]: The schema key of the best match, or None if no match found or error occurs.
    """
    # Input validation
    if not clean_text or not isinstance(clean_text, str):
        print(f"Error: Invalid input. Expected non-empty string, got {type(clean_text).__name__}")
        return None
    
    try:
        # Query the collection with automatic vectorization
        response = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=models.Document(
                text=clean_text, 
                model=MODEL_NAME
            ),
            limit=1
        )
        # Extract and return the top match if available and meets threshold
        if response and response.points:
            best_match = response.points[0]  # ScoredPoint item
            score = best_match.score
            schema_key = best_match.payload.get('schema_key') if score > threshold else None
            if not schema_key: 
                # logging for debugging: save the score and payload for analysis
                logging.info(f"Query '{clean_text}' -> No match above threshold. Best score: {score:.4f}, Payload: {best_match.payload}")
            return schema_key
        else:
            print(f"Warning: No matches found for query '{clean_text}'")
            return None
    except Exception as e:
        print(f"Error querying Qdrant: {e}")
        return None

def classify_node_types(graph: Graph) -> Optional[dict]:
    """
    Classifies RDF nodes in the provided graph into CellML, SED-ML, and biological ontology terms.
    Also identifies process relationships (source/sink/mediator).
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
    
    Returns:
        Optional[dict]: Dictionary with keys:
            - 'cellml_terms': Set of CellML URIRef nodes
            - 'sedml_terms': Set of SED-ML URIRef nodes
            - 'bio_terms': Set of biological ontology URIRef nodes
            - 'unknown_terms': Set of unclassified URIRef nodes
            - 'unknown_predicates': Set of predicates that could not be classified
            - 'processes': Dict mapping process nodes to source/sink/mediator participants
                dict structure: { process_node: { "source": set(), "sink": set(), "mediator": set() } }
        None if an error occurs during classification.
    """
    # Input validation
    if not graph or not isinstance(graph, Graph):
        print(f"Error: Expected rdflib Graph object, got {type(graph).__name__}")
        return None
    
    # Initialize collections
    cellml_terms = set()
    sedml_terms = set()
    bio_terms = set()
    unknown_terms = set()
    literal_terms = set()
    processes = {}
    unknown_predicates = set()
    
    try:
        # Iterate through all triples in the graph
        for s, p, o in graph:
            # Classify subject node (s)
            if isinstance(s, URIRef):
                s_str = str(s)
                if cellml_term(s_str):
                    cellml_terms.add(s)
                elif sedml_term(s_str):
                    sedml_terms.add(s)
                elif ontology_term_bio(s_str):
                    bio_terms.add(s)
                else:
                    unknown_terms.add(s)
            
            # Classify object node (o)
            if isinstance(o, URIRef):
                o_str = str(o)
                if cellml_term(o_str):
                    cellml_terms.add(o)
                elif sedml_term(o_str):
                    sedml_terms.add(o)
                elif ontology_term_bio(o_str):
                    bio_terms.add(o)
                else:
                    unknown_terms.add(o)
            elif isinstance(o, Literal):
                literal_terms.add(o)
            # Analyze predicate to identify relationships
            p_str = str(p)
            qualifier = qualifier_term(p_str)
            if qualifier:
                role = query_qdrant(qualifier, threshold=0.6)
                if role:
                    # Identify process participants (source/sink/mediator)
                    if role in ["source", "sink", "mediator"]:
                        if s not in processes:
                            processes[s] = {"source": set(), "sink": set(), "mediator": set()}
                        processes[s][role].add(o)
            else:
                unknown_predicates.add(p_str)
        # Return classification results after processing all triples
        return {
            "cellml_terms": cellml_terms,
            "sedml_terms": sedml_terms,
            "bio_terms": bio_terms,
            "unknown_predicates": unknown_predicates,
            "unknown_terms": unknown_terms,
            "literal_terms": literal_terms,
            "processes": processes,
        }
    
    except Exception as e:
        print(f"Error classifying node types: {type(e).__name__}: {e}")
        return None

def find_neighbor_nodes(graph: Graph, node: URIRef) -> set:
    """
    Finds all neighboring nodes (both subjects and objects) connected to the given node.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
        node (URIRef): The node for which to find neighbors.
    
    Returns:
        set: A set of neighboring URIRef nodes.
    """
    neighbors = set()
    try:
        # Forward Traversal: current_node -> Object
        for _, _, obj_node in graph.triples((node, None, None)):
            neighbors.add(obj_node)
        
        # Backward Traversal: Subject -> current_node
        for subj_node, _, _ in graph.triples((None, None, node)):
            neighbors.add(subj_node)
        
        return neighbors
    except Exception as e:
        print(f"Error finding neighbor nodes for {node}: {type(e).__name__}: {e}")
        return set()

def get_nearest_nodes(graph: Graph, start_node: URIRef, set_A: set) -> set:
    """
    Finds the set of nodes B (subset of A) closest to start_node, 
    such that no other nodes from A exist on the path between them.
    Uses breadth-first search to find nodes at the nearest distance.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
        start_node (URIRef): The starting node for the search.
        set_A (set): The set of candidate nodes to search for.
    
    Returns:
        set: Subset of set_A containing nodes closest to start_node.
    """
    # Input validation
    if not graph or not isinstance(graph, Graph):
        print(f"Error: Expected rdflib Graph object, got {type(graph).__name__}")
        return set()
    
    if not start_node or not isinstance(start_node, URIRef):
        print(f"Error: Expected URIRef for start_node, got {type(start_node).__name__}")
        return set()
    
    if not set_A or not isinstance(set_A, set):
        print(f"Error: Expected set for set_A, got {type(set_A).__name__}")
        return set()
    set_B = set()
    visited = set()
    
    try:
        # Initialize BFS queue with the start node
        queue = deque([start_node])
        visited.add(start_node)
        
        # Perform breadth-first search to find nearest nodes
        while queue:
            current_node = queue.popleft()
            
                # We will use a set to gather neighbors to avoid checking 
            # the same node twice if it is connected by multiple edges
            neighbors = set()

            # 1. Forward Traversal: current_node -> Object
            for _, _, obj_node in graph.triples((current_node, None, None)):
                neighbors.add(obj_node)

            # 2. Backward Traversal: Subject -> current_node
            for subj_node, _, _ in graph.triples((None, None, current_node)):
                neighbors.add(subj_node)
            
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    
                    if neighbor in set_A:
                        # Found a node from set_A; add it but don't continue searching past it
                        set_B.add(neighbor)
                    else:
                        # Not in set_A; continue searching deeper
                        queue.append(neighbor)
        
        return set_B
    
    except Exception as e:
        print(f"Error finding nearest A nodes: {type(e).__name__}: {e}")
        return set()

def get_predicate_sequence(graph: Graph, node_a: URIRef, node_b: URIRef | Literal) -> list:
    """
    Finds the shortest sequence of predicates (edges) connecting node_a to node_b.
    Uses breadth-first search to ensure the shortest path is found first.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
        node_a (URIRef): The starting node.
        node_b (URIRef | Literal): The target node.
    
    Returns:
        list: A list of qualifier terms representing the predicate path, 
              or an empty list if no path exists.
    """
    # Input validation
    if not graph or not isinstance(graph, Graph):
        print(f"Error: Expected rdflib Graph object, got {type(graph).__name__}")
        return []
    
    if not isinstance(node_a, URIRef) or not isinstance(node_b, (URIRef, Literal)):
        print(f"Error: Both nodes must be URIRef or Literal objects")
        return []
    
    # Edge case: source and target are the same
    if node_a == node_b:
        return []
    
    try:
        # Initialize BFS with starting node and empty predicate path
        queue = deque([(node_a, [])])
        visited = set([node_a])
        
        # Perform breadth-first search for shortest predicate path
        while queue:
            current_node, current_path = queue.popleft()

            # ---------------------------------------------------------
            # 1. Forward Traversal (current_node is the Subject)
            # ---------------------------------------------------------
            for _, predicate, next_node in graph.triples((current_node, None, None)):
                if next_node == node_b:
                    if qualifier_term(str(predicate)):
                        return current_path + [qualifier_term(str(predicate))]
                    else:
                        return current_path + [str(predicate)]

                if next_node not in visited:
                    visited.add(next_node)
                    if qualifier_term(str(predicate)):
                        queue.append((next_node, current_path + [qualifier_term(str(predicate))]))
                    else:
                        queue.append((next_node, current_path + [str(predicate)]))

        # No path found between nodes
        return []
    
    except Exception as e:
        print(f"Error finding predicate sequence: {type(e).__name__}: {e}")
        return []

def resolve_ontology_term(graph: Graph, start_node: URIRef, set_A: set) -> Optional[dict]:
    """
    Resolves the ontology term for a given start_node by finding the nearest nodes in set_A
    and categorizing them based on their predicate sequences.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
        start_node (URIRef): The node for which we want to resolve the ontology term.
        set_A (set): A set of nodes considered as potential ontology terms.
    
    Returns:
        Optional[dict]: Dictionary with categories:
            - 'term': Ontology term nodes (matched to 'is' relationship)
            - 'properties': Property nodes (matched to 'hasProperty' or contain 'opb')
            - 'compartment': Anatomical nodes (matched to 'part' relationship)
        None if an error occurs during resolution.    
    """
    # Input validation
    if not graph or not isinstance(graph, Graph):
        print(f"Error: Expected rdflib Graph object, got {type(graph).__name__}")
        return None
    
    if not isinstance(start_node, URIRef):
        print(f"Error: Expected URIRef for start_node, got {type(start_node).__name__}")
        return None
    
    if not set_A or not isinstance(set_A, set):
        print(f"Error: Expected non-empty set for set_A, got {type(set_A).__name__}")
        return None
    
    try:
        # Find nodes in set_A nearest to start_node
        nearest_nodes = get_nearest_nodes(graph, start_node, set_A)
        # Separate nearest nodes into different term types for analysis
        bio_nodes = [node for node in nearest_nodes if ontology_term_bio(str(node))]
        cellml_nodes = [node for node in nearest_nodes if cellml_term(str(node))]
        literal_nodes = [node for node in nearest_nodes if isinstance(node, Literal)]
        # Initialize result dictionary
        resolved_terms = {"ontology ID": [], "properties": [], "compartment": [], "unknown_predicates": [], "coefficients": []}
        # Categorize each bio node based on its predicate sequence and URI
        for node in bio_nodes+literal_nodes:
            node_str = str(node).lower()            
            # Quick heuristic: OPB terms are properties
            if "opb" in node_str:
                resolved_terms["properties"].append(str(node))
                for cellml_node in cellml_nodes:                    
                     predicate_sequence_forward = get_predicate_sequence(graph, node, cellml_node)
                     predicate_sequence_backward = get_predicate_sequence(graph, cellml_node, node)
                     query_list = [query_qdrant(qualifier) for qualifier in predicate_sequence_forward]
                     query_list.extend([query_qdrant(qualifier) for qualifier in predicate_sequence_backward])
                     if "is" in query_list :
                        resolved_terms["properties"].append(str(cellml_node))
                continue
            
            # Get predicate sequence and match it to schema categories
            predicate_sequence = get_predicate_sequence(graph, start_node, node)
            if not predicate_sequence:
                continue           
            # Join predicates into a query string
            query_list = [query_qdrant(qualifier) for qualifier in predicate_sequence]   
     
            # Classify based on predicate sequence match
            part_match = "part"
            is_match = "is"
            multiplier_match = "multiplier"
            
            # Check if part_match is not None and is in query_list
            if part_match in query_list:
                # Predicate sequence matches 'part' relationship (anatomical)
                resolved_terms["compartment"].append(str(node))
            # Check if is_match is not None and is in query_list
            elif multiplier_match in query_list:
                # Predicate sequence matches 'multiplier' relationship (property)
                resolved_terms["coefficients"].append(str(node))
            elif is_match in query_list :
                # Predicate sequence matches 'is' relationship (ontology term)
                resolved_terms["ontology ID"].append(str(node))
            else:
                # Predicate sequence doesn't match known schemas; add to unknown predicates
                resolved_terms["unknown_predicates"].append(predicate_sequence)
        return resolved_terms
    
    except Exception as e:
        print(f"Error resolving ontology term: {type(e).__name__}: {e}")
        return None

def get_boundary_nodes(graph: Graph, nodes_info: dict) -> bool:
    """
    Finds the boundary nodes for each process and its participants (source, sink, mediator) in the RDF graph.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
        nodes_info (dict): A dictionary containing information about nodes.
    
    Returns:
        bool: True if boundary nodes are found successfully, False otherwise.

    Side effects:
        Updates the nodes_info dictionary in place, adding a "boundary_nodes" key for each process and its participants.
    """
    # Input validation
    processes = nodes_info.get("processes", {})
    if not processes:
        print("Warning: No processes found in node_info")
        return False
    
    # get the set of all source, sink, and mediator nodes for ontology resolution
    all_participants = set()
    for process_node, participants in processes.items():
        all_participants.update(participants.get("source", set()))
        all_participants.update(participants.get("sink", set()))
        all_participants.update(participants.get("mediator", set()))
    all_participants_neighbors = set()
    for participant in all_participants:
        all_participants_neighbors.update(find_neighbor_nodes(graph, participant))
    
    for process_node, participants in processes.items():
        set_P = nodes_info["bio_terms"].union(set(processes.keys())-{process_node}).union(all_participants).union(nodes_info["cellml_terms"]).union(nodes_info['literal_terms'])
        processes[process_node]["boundary_nodes"] = set_P
        for source_node in participants.get("source", set()):
            set_A = nodes_info["bio_terms"].union(set(processes.keys())).union(all_participants-{source_node}).union(nodes_info["cellml_terms"]).union(all_participants_neighbors-find_neighbor_nodes(graph, source_node)).union(nodes_info['literal_terms'])
            if source_node not in processes[process_node]:
                processes[process_node][source_node] = {}
            processes[process_node][source_node]["boundary_nodes"] = set_A
        for sink_node in participants.get("sink", set()):
            set_A = nodes_info["bio_terms"].union(set(processes.keys())).union(all_participants-{sink_node}).union(nodes_info["cellml_terms"]).union(all_participants_neighbors-find_neighbor_nodes(graph, sink_node)).union(nodes_info['literal_terms'])
            if sink_node not in processes[process_node]:
                processes[process_node][sink_node] = {}
            processes[process_node][sink_node]["boundary_nodes"] = set_A
        for mediator_node in participants.get("mediator", set()):
            set_A = nodes_info["bio_terms"].union(set(processes.keys())).union(all_participants-{mediator_node}).union(nodes_info["cellml_terms"]).union(all_participants_neighbors-find_neighbor_nodes(graph, mediator_node)).union(nodes_info['literal_terms'])
            if mediator_node not in processes[process_node]:
                processes[process_node][mediator_node] = {}
            processes[process_node][mediator_node]["boundary_nodes"] = set_A
    return True

def get_bioProcess(graph: Graph, output_json: Optional[str] = None) -> Dict:
    """
    Extracts biological process information from the RDF graph, organizing processes
    by their source, sink, and mediator participants with their associated properties.
    
    Args:
        graph (Graph): The rdflib Graph object containing RDF data.
    
    Returns:
        Dict: Dictionary mapping process nodes to their participant information:
            {
                process_node: {
                    "source": [{"ontology ID": bio_term, "properties": [...], "compartment": [...], "stoichiometry": float}, ...],
                    "sink": [...],
                    "mediator": [...]
                },
                ...
            }
    """
    # Input validation
    if not graph or not isinstance(graph, Graph):
        print(f"Error: Expected rdflib Graph object, got {type(graph).__name__}")
        return {}
    
    try:
        # Classify all nodes and extract process information
        nodes_info = classify_node_types(graph)
        if not nodes_info:
            print("Warning: No nodes classified from graph")
            return {}        
        processes = nodes_info.get("processes", {})
        if get_boundary_nodes(graph, nodes_info) is False:
            print("Warning: Failed to find boundary nodes for processes")
            return {}
        # Process each identified biological process
        bio_process_dict = {}
        for process_node, participants in processes.items():
            if not participants:
                print(f"Warning: No participants found for process node: {process_node}")
                continue          
            process_data ={ "source": [], "sink": [], "mediator": []}
            set_P = processes[process_node].get("boundary_nodes", set())
            resolved = resolve_ontology_term(graph, process_node, set_P)
            if not resolved:
                print(f"Warning: Failed to resolve ontology terms for process node: {process_node}")
                continue
            process_data.update(resolved)
            bio_process_dict[process_node] = process_data
            # Process source participants
            for source_node in participants.get("source", set()):
                source_info = {
                    "local ID": local_id(str(source_node))
                }
                # Resolve ontology terms for this source node
                set_A = processes[process_node][source_node].get("boundary_nodes", set())
                resolved = resolve_ontology_term(graph, source_node, set_A)
                if not resolved:
                    print(f"Warning: Failed to resolve ontology terms for source node: {source_node}")
                    continue
                source_info.update(resolved)
                process_data["source"].append(source_info)
            
            # Process sink participants
            for sink_node in participants.get("sink", set()):
                sink_info = {
                    "local ID": local_id(str(sink_node))
                }
                # Resolve ontology terms for this sink node
                set_B = processes[process_node][sink_node].get("boundary_nodes", set())
                resolved = resolve_ontology_term(graph, sink_node, set_B)
                if not resolved:
                    print(f"Warning: Failed to resolve ontology terms for sink node: {sink_node}")
                    continue
                sink_info.update(resolved)
                process_data["sink"].append(sink_info)
            
            # Process mediator participants
            for mediator_node in participants.get("mediator", set()):
                mediator_info = {
                    "local ID": local_id(str(mediator_node))
                }
                # Resolve ontology terms for this mediator node
                set_C = processes[process_node][mediator_node].get("boundary_nodes", set())
                resolved = resolve_ontology_term(graph, mediator_node, set_C)
                if not resolved:
                    print(f"Warning: Failed to resolve ontology terms for mediator node: {mediator_node}")
                    continue
                mediator_info.update(resolved)
                process_data["mediator"].append(mediator_info)
            
            # Store the processed data if it has participants
            if any(process_data[role] for role in ["source", "sink", "mediator"]):
                bio_process_dict[local_id(str(process_node))] = process_data
        if output_json:
            with open(output_json, 'w') as f:
                json.dump(bio_process_dict, f, indent=4)
        print(f"Biological process data written to {output_json}") 
        return bio_process_dict
    
    except Exception as e:
        print(f"Error extracting biological processes: {type(e).__name__}: {e}")
        return {}      



def get_participant_signature(participant: Dict[str, Any]) -> Tuple:
    """
    Creates a unique, order-independent signature for a participant based 
    on its ontology IDs and compartments.
    """
    ontologies = tuple(sorted(participant.get('ontology ID', [])))
    compartment = tuple(sorted(participant.get('compartment', [])))
    return (ontologies, compartment)

def get_process_signature(process: Dict[str, Any]) -> Tuple:
    """
    Creates a signature for a process to determine if it should be merged.
    Rule 1: If mediator exists, signature is based on the mediator(s).
    Rule 2: If no mediator, signature is based on source(s) and sink(s).
    """
    mediators = process.get('mediator', [])
    if mediators:
        med_sig = tuple(sorted(get_participant_signature(m) for m in mediators))
        return ('mediator', med_sig)
    else:
        src_sig = tuple(sorted(get_participant_signature(s) for s in process.get('source', [])))
        snk_sig = tuple(sorted(get_participant_signature(s) for s in process.get('sink', [])))
        return ('source_sink', src_sig, snk_sig)

def merge_participants(participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merges participants that share the exact same ontology IDs and compartments.
    Deduplicates properties, unknown_predicates, and coefficients.
    """
    merged_dict = {}
    for p in participants:
        sig = get_participant_signature(p)
        if sig not in merged_dict:
            # Deep copy to avoid mutating the original dictionary references
            merged_dict[sig] = copy.deepcopy(p)
        else:
            existing = merged_dict[sig]
            # Merge list attributes, keeping only unique elements
            for key in ['properties', 'unknown_predicates', 'coefficients']:
                if key in p:
                    if key not in existing:
                        existing[key] = []
                    for item in p[key]:
                        # A simple 'not in' prevents duplicate strings/lists 
                        if item not in existing[key]:
                            existing[key].append(item)
    return list(merged_dict.values())

def merge_processes(processes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Combines a group of processes into a single process.
    """
    if not processes:
        return {}
    
    # Base structure for the merged process
    merged = {
        'source': [],
        'sink': [],
        'mediator': [],
        'ontology ID': [],
        'properties': [],
        'compartments': [],
        'unknown_predicates': [],
        'coefficients': []
    }
    
    for p in processes:
        # Accumulate all participants
        merged['source'].extend(copy.deepcopy(p.get('source', [])))
        merged['sink'].extend(copy.deepcopy(p.get('sink', [])))
        merged['mediator'].extend(copy.deepcopy(p.get('mediator', [])))
        
        # Accumulate top-level process attributes without duplicates
        for key in ['ontology ID', 'properties', 'compartments', 'unknown_predicates', 'coefficients']:
            for item in p.get(key, []):
                if item not in merged[key]:
                    merged[key].append(item)
                    
    # Consolidate duplicate participants within the new lists
    merged['source'] = merge_participants(merged['source'])
    merged['sink'] = merge_participants(merged['sink'])
    merged['mediator'] = merge_participants(merged['mediator'])
    
    return merged

def simplify_bio_process(bio_process_dict: Dict[str, Any], output_json: Optional[str] = None) -> Dict[str, Any]:
    """
    Simplifies the biological process dictionary by removing repetitive entries 
    and merging processes/participants with the same ontology terms.
    """
    groups = {}
    
    # 1. Group processes by their signature
    for process_id, process_data in bio_process_dict.items():
        sig = get_process_signature(process_data)
        if sig not in groups:
            groups[sig] = []
        groups[sig].append(process_data)
        
    simplified_dict = {}
    
    # 2. Merge each group into a single process
    for i, (sig, processes) in enumerate(groups.items()):
        merged_process = merge_processes(processes)
        
        # You can format the new key however you prefer (e.g., 'merged_process_0')
        new_key = f"merged_process_{i}"
        simplified_dict[new_key] = merged_process
        
    if output_json:
        with open(output_json, 'w') as f:
            json.dump(simplified_dict, f, indent=4)

        print(f"Biological process data written to {output_json}")

    return simplified_dict

if __name__ == "__main__":
    # Test the Qdrant query functionality
    try:
        query_text = "has physical definition"
        query_text = "is property"
        result = query_qdrant(query_text)
        if result:
            print(f"Query succeeded: {result}")
        else:
            print(f"Query returned no result")
    except Exception as e:
        print(f"Error during query test: {type(e).__name__}: {e}")
        exit(1)

    # test classification and extraction of biological processes from a sample RDF file
 
    graph = read_rdf_file("Ostby_2009_NBC.ttl")  

    if graph:
        print("dict_nodes:")
        dict_nodes = classify_node_types(graph)
        # dump as JSON for easier inspection
        import json
        json_ready_dict = {key: [str(uri) for uri in value_set] for key, value_set in dict_nodes.items()}
        print(json.dumps(json_ready_dict, indent=4))
        
        print("bio_processes:")
        bio_processes = get_bioProcess(graph,"Ostby_2009_NBC.json")
        simplified_bio_processes = simplify_bio_process(bio_processes, output_json="Ostby_2009_NBC_simplified.json")

 