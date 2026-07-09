"""
=============================================================================
CellML RDF Extractor
=============================================================================
This script extracts embedded <rdf:RDF> metadata from CellML/XML files.

Key Features:
1. Robust Extraction: Handles local file paths and remote URLs seamlessly.
2. Namespace Detection: Automatically detects and binds XML namespaces to RDF.
3. Fault Tolerant: Includes network timeouts and safe file-system handling.
=============================================================================
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import contextlib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import XSD
from utilities import get_file_buffer


def read_rdf_file(rdf_file_path: str) -> Optional[Graph]:
    """
    Reads an RDF file and returns the corresponding rdflib Graph object.
    
    Args:
        rdf_file_path (str): The local file path or remote URL.
    
    Returns:
        Optional[Graph]: The rdflib Graph object representing the RDF data, or None if an error occurs.
    """
    # Input validation
    if not rdf_file_path or not isinstance(rdf_file_path, str):
        print(f"Error: Invalid file path. Expected non-empty string, got {type(rdf_file_path).__name__}")
        return None
    
    try:
        # Attempt to read the file buffer from local or remote source
        rdf_file_buffer = get_file_buffer(rdf_file_path)
        if rdf_file_buffer is None:
            return None        
        # Use context manager to ensure proper resource cleanup
        with contextlib.closing(rdf_file_buffer) as rdf_buffer:
            graph = Graph()
            graph.parse(rdf_buffer)
            print(f"Successfully parsed RDF graph with {len(graph)} triples.")
            return graph
    except Exception as e:
        print(f"Error parsing RDF file {rdf_file_path}: {type(e).__name__}: {e}")
        return None

def get_cellmlsource(g:Graph, cmeta_ids:set, cellmlFile:str) -> Graph:
    """
    Identifies and binds local identifiers to cellml source.
    note: This function for processing rdf embedded in cellml/xml files.
    These rdf triples treat cmeta:id as local identifiers, and replace them with a new URI based on the cellmlFile.
    
    Args:
        g (Graph): The rdflib Graph object containing RDF data.
        cmeta_ids (set): A set of cmeta:id attributes found in the XML.
        cellmlFile (str): The base CellML file path or URL.
    
    Returns:
        Graph: The modified rdflib Graph object with explicit cellml source identifiers.
    """
    
    MODEL_BASE = Namespace(f"{cellmlFile}#")
    g.bind("model_base", MODEL_BASE)
    for s, p, o in list(g):
        new_s, new_o = s, o
        def process_uri(uri_ref):
            uri_str = str(uri_ref)
            if "#" in uri_str and (uri_str.startswith("file://") or not uri_str.startswith("http")):
                local_id = uri_str.split("#")[-1]
                if local_id in cmeta_ids:
                    return MODEL_BASE[local_id]
            return uri_ref
        if isinstance(s, URIRef):
            new_s = process_uri(s)
        if isinstance(o, URIRef):
            new_o = process_uri(o)
        if isinstance(o, Literal) and str(o).replace('.', '', 1).isdigit():
            new_o = Literal(str(o), datatype=XSD.float)

        if new_s != s or new_o != o:
            g.remove((s, p, o))
            g.add((new_s, p, new_o))
            print(f"Replaced: {s} -> {new_s}, {o} -> {new_o}")

    return g
  

def extract_rdf(input_path: str, output_file: Optional[str] = None) -> Optional[Graph]:
    """
    Main function to extract, parse, and optionally save RDF data 
    from a CellML/XML source.
    
    Args:
        input_path (str): The location of the XML file (URL or local path).
        output_file (str, optional): The path where the serialized RDF should be saved.
        
    Returns:
        Graph: The parsed rdflib Graph object, or None if extraction fails.
    """
    file_buffer = get_file_buffer(input_path)
    if not file_buffer:
        print("Error: Failed to retrieve file buffer. Aborting extraction.")
        return None

    with contextlib.closing(file_buffer) as xml_buffer:    
        try:
            # 1. Extract XML namespaces safely
            # We use 'start-ns' events to catch every namespace declaration in the document
            xml_namespaces = {}
            for event, (prefix, uri) in ET.iterparse(xml_buffer, events=['start-ns']):
                # ElementTree allows None for default namespaces, so we check if prefix exists
                xml_namespaces[prefix] = uri

            # 2. Rewind the buffer pointer back to the beginning before full parsing
            xml_buffer.seek(0)

            # 3. Parse the XML tree
            tree = ET.parse(xml_buffer)
            root = tree.getroot()
            
            # get the cmeta id attribute if it exists
            cmeta_ns = "http://www.cellml.org/metadata/1.0#"
            cmeta_key = f"{{{cmeta_ns}}}id"

            cmeta_ids = set()
            for elem in root.iter():
                if cmeta_key in elem.attrib:
                    cmeta_ids.add(elem.attrib[cmeta_key])
            print(f"Found {len(cmeta_ids)} cmeta:id attributes in the XML.")
            # Search for the <rdf:RDF> tag. Using endswith avoids strict namespace 
            # URI hardcoding, making it resilient to slight XML namespace variations.
            rdf_element = next((elem for elem in root.iter() if elem.tag.endswith('}RDF')), None)

            if rdf_element is not None:
                # Convert the isolated RDF XML element back to a string format for rdflib
                rdf_string = ET.tostring(rdf_element, encoding='unicode')
                g = Graph()            

                # Re-bind the namespaces we discovered so the output looks clean 
                # (e.g., using 'semsim:' instead of a full, messy URL)
                for prefix, uri in xml_namespaces.items():
                    if prefix: 
                        g.bind(prefix, Namespace(uri))

                # Parse the RDF string into the rdflib Graph
                g.parse(data=rdf_string, format='xml')                 
                g=get_cellmlsource(g, cmeta_ids, input_path)
                # 4. Handle optional file saving
                if output_file: 
                    # Create the output directory if it doesn't exist
                    output_path = Path(output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    # Determine format based on file extension
                    if output_path.suffix.lower() == '.ttl':
                        g.serialize(destination=output_file, format='turtle')
                    else:
                        g.serialize(destination=output_file, format='xml')

                    print(f"Success: Clean RDF data extracted and saved to '{output_file}'.")

                return g

            else:
                print("Error: No <rdf:RDF> element found in the provided XML buffer.")
                return None

        except ET.ParseError as e:
            print(f"XML Parsing Error: The file is likely malformed. Details: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during RDF extraction: {e}")
            return None
# =============================================================================
# Testing Block
# =============================================================================
if __name__ == "__main__":
    # Test with a remote Physiome Project file
    input_cellml_file = "https://models.physiomeproject.org/workspace/267/rawfile/HEAD/Ostby_2009_NBC.cellml"
    base_name = "Ostby_2009_NBC"

    input_cellml_file = "https://models.physiomeproject.org/workspace/267/rawfile/HEAD/Weinstein_2000.cellml"
    base_name = "Weinstein_2000"
    
    # Define output file. The script will now safely create any missing folders
    output_turtle_file = f"./{base_name}.ttl"    
    
    # Run the extractor
    extracted_graph = extract_rdf(input_cellml_file, output_turtle_file)
    
    if extracted_graph:
        print(f"Successfully loaded {len(extracted_graph)} triples into the graph.")