# PMR Knowledge Exploration

PMR Knowledge Exploration is a Python package for extracting RDF metadata from CellML files, identifying biological process participants, and generating process visualizations.

The current codebase focuses on three main steps:

1. Read RDF data from a local file path or remote URL.
2. Analyse RDF triples to identify biological process roles (source, sink, mediator) and related ontology terms.
3. Visualize simplified process relationships as a Graphviz network.

## What this project contains

- RDF extraction from embedded XML RDF blocks.
- Biological term and qualifier detection utilities.
- Process analysis with semantic predicate matching (Qdrant + FastEmbed).
- Graph rendering for biological process diagrams.

## Project structure

- `pmr_ke/process_rdf/extract_rdf.py`: Extract and parse RDF from CellML/XML input.
- `pmr_ke/process_rdf/analyse_rdf.py`: Classify nodes, resolve participant metadata, simplify process data.
- `pmr_ke/process_rdf/utilities.py`: URL/file helpers and URI term classification helpers.
- `pmr_ke/visulisation/vis_bioProcess.py`: Build a Graphviz diagram from process JSON/dict input.
- `pmr_ke/__main__.py`: Intended CLI entrypoint for an end-to-end flow.

## Requirements

- Python 3.12+
- Graphviz installed on your system (required by `graphviz` Python package for rendering images)

Python dependencies are defined in `pyproject.toml`:

- rdflib
- qdrant-client
- fastembed
- graphviz
- pyvis

## Installation

Using uv (recommended):

```bash
uv add git+https://github.com/WeiweiAi/PMR-Knowledge-Exploration.git
```

Using pip:

```bash
pip install git+https://github.com/WeiweiAi/PMR-Knowledge-Exploration.git .
```

## Typical workflow

The intended workflow in code is:

1. Extract RDF:
	- `extract_rdf(input_path, output_ttl_optional)`
2. Analyse processes:
	- `get_bioProcess(graph, output_json_optional)`
3. Simplify output:
	- `simplify_bio_process(process_dict, output_json_optional)`
4. Visualize:
	- `build_bioprocess_graph(simplified_json_or_dict, output_png_optional)`

## CLI Usage

The package provides a CLI command:

```bash
uv run pmr_ke <file_path> [options]
```

Options:

- `-ttl`, `--ttl-output`: Save extracted RDF as a Turtle file.
- `-json`, `--json-output`: Save simplified process output as JSON.
- `-png`, `--png-output`: Save process visualization output as PNG.

Example:

```bash
uv run pmr_ke "https://models.physiomeproject.org/workspace/267/rawfile/HEAD/Weinstein_2000.cellml" `
  --ttl-output output/weinstein.ttl `
  --json-output output/weinstein_simplified.json `
  --png-output output/weinstein_graph
```

## Running the Visualisation Script

From the `pmr_ke/visulisation` folder:

```bash
uv run .\vis_bioProcess.py
```

This runs the local example block in the script and renders a Graphviz PNG output when input data is available.

## License

Apache-2.0
