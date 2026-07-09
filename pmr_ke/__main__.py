import argparse
from pmr_ke import extract_rdf, get_bioProcess, simplify_bio_process, build_bioprocess_graph

def arg_parser():
    parser = argparse.ArgumentParser(description="Visualize biological processes from RDF data.")
    parser.add_argument("file_path", type=str,  help="The file path or web link to the RDF data file(s) to be processed.")
    args = parser.add_argument_group('options')
    args.add_argument('-ttl', '--ttl-output', dest='ttl_output', default=None, 
                      help='Output TTL file path. If omitted, no TTL file will be saved.')
    args.add_argument('-json', '--json-output', dest='json_output', default=None, 
                      help='Output JSON file path. If omitted, no JSON file will be saved.')
    args.add_argument('-png', '--png-output', dest='png_output', default=None, 
                      help='Output PNG file path. If omitted, no PNG file will be saved.')
    return parser

def main():
    parser = arg_parser()
    args = parser.parse_args()

    if args.ttl_output:
        rdf_data = extract_rdf(args.file_path, args.ttl_output)
    else:
        rdf_data = extract_rdf(args.file_path)
    if rdf_data is not None:
        bioprocess_Dict = get_bioProcess(rdf_data)
        if args.json_output:
            final_bioprocess_Dict = simplify_bio_process(bioprocess_Dict, args.json_output)
        else:
            final_bioprocess_Dict = bioprocess_Dict
        if args.png_output:
            build_bioprocess_graph(final_bioprocess_Dict, args.png_output)
        else:
            build_bioprocess_graph(final_bioprocess_Dict)

if __name__ == "__main__":
    main()