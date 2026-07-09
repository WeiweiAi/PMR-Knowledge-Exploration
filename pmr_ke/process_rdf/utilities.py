import io
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import Optional

BIOLOGICAL_ONTOLOGY_DOMAINS = {"identifiers.org", 
        "purl.obolibrary.org", 
        "www.obofoundry.org",
        "fma.biostr.washington.edu", # Added just in case FMA is referenced directly       
}

QUALIFIER_DOMAINS = {
    "www.bhi.washington.edu", # semsim qualifiers
    "www.bime.uw.edu", # semsim qualifiers
    "www.biomodels.net", # qualifiers
    "biomodels.net", # qualifiers
    "bime.uw.edu", # qualifiers
    "bhi.washington.edu", # qualifiers
    "www.obofoundry.org"
}

def is_web_url(file_path: str) -> Optional[urlparse]:
    """
    Safely checks if a provided string is a valid HTTP/HTTPS web URL.
    
    Args:
        file_path (str): The file path or URL to check.
        
    Returns:
        Optional[urlparse]: The parsed URL object if it's a valid web URL, None otherwise.
        The object includes: scheme, netloc, path, params, query, fragment
    """
    clean_path = file_path.strip()    
    try:
        # Parse the URL into its core components (scheme, network location, etc.)
        result = urlparse(clean_path)
        # Ensure it has both an acceptable web protocol and a domain name
        if result.scheme in ['http', 'https'] and bool(result.netloc):
            return result
    except ValueError:
        # Catch cases where the string is completely malformed
        return None

def qualifier_term(uri: str) -> Optional[str]:
    """
    Checks if a given term is likely an ontology term based on its structure.
    
    Args:
        term (str): The term to check.
        
    Returns:
        Optional[str]: The qualifier in free text if it's an qualifier term, None otherwise.
    """
    try:
        parsed_url = is_web_url(uri)
        if parsed_url and parsed_url.netloc in QUALIFIER_DOMAINS:
            if parsed_url.fragment:
                qualifier = parsed_url.fragment
            else:
                qualifier = parsed_url.path.split("/")[-1]  # Return the last segment of the path  
            # 1. Insert spaces between lower->Upper transitions
            spaced = re.sub(r"([a-z])([A-Z])", r"\g<1> \g<2>", qualifier)    
             # 2. Replace all annoying separators (_, -, :) with a space
            cleaned = re.sub(r"[_:\-]", " ", spaced)    
            # 3. Lowercase and strip extra edge spaces 
            return cleaned.lower().strip()
        else:
            return None
    except Exception as e:
        print(f"Error checking qualifier term '{uri}': {e}")
        return None

def ontology_term_bio(uri: str) -> Optional[str]:
    """
    Checks if a given term is likely an ontology term based on its structure.
    
    Args:
        term (str): The term to check.
        
    Returns:
        Optional[str]: The fragment identifier if it's an ontology term, None otherwise.
    """
    try:
        parsed_url = is_web_url(uri)
        if parsed_url and parsed_url.netloc in BIOLOGICAL_ONTOLOGY_DOMAINS:
            if parsed_url.fragment:
                return parsed_url.fragment
            else:
                return parsed_url.path.split("/")[-1]  # Return the last segment of the path
        else:
            return None
    except Exception as e:
        print(f"Error checking ontology term '{uri}': {e}")
        return None

def local_id(uri: str) -> Optional[str]:
    """
    Extracts the local ID from a given URI.
    
    Args:
        uri (str): The URI to extract the local ID from.
        
    Returns:
        Optional[str]: The local ID if it can be extracted, None otherwise.
    """
    clean_uri = uri.strip()
    # check # in the URI
    if '#' in clean_uri:
        source, fragment = clean_uri.split('#', 1)
        if not source.lower().endswith(('.cellml', '.sedml')): # TODO: Consider more robust checks for CellML and SED-ML terms
            return fragment
    return None

def cellml_term(uri: str) -> Optional[str]:
    """
    Checks if a given term is likely a CellML term based on its structure.
    
    Args:
        uri (str): The URI to check.
        
    Returns:
        Optional[str]: The fragment identifier if it's a CellML term, None otherwise.
    """
    clean_uri = uri.strip()
    # check # in the URI
    if '#' in clean_uri:
        source, fragment = clean_uri.split('#', 1)
        if source.lower().endswith(".cellml"): # TODO: Consider more robust checks for CellML terms
           return fragment
    return None

def sedml_term(uri: str) -> Optional[str]:
    """
    Checks if a given term is likely a SED-ML term based on its structure.
    
    Args:
        uri (str): The URI to check.
        
    Returns:
        Optional[str]: The fragment identifier if it's a SED-ML term, None otherwise.
    """
    clean_uri = uri.strip()
    # check # in the URI
    if '#' in clean_uri:
        source, fragment = clean_uri.split('#', 1)
        if source.lower().endswith(".sedml"): # TODO: Consider more robust checks for SED-ML terms
            return fragment
    return None

def get_file_buffer(input_path: str, timeout_seconds: int = 15) -> Optional[io.BytesIO]:
    """
    Takes a URL or a local file path and loads its contents into a reusable 
    in-memory byte buffer. 
    
    Args:
        input_path (str): The local file path or remote URL.
        timeout_seconds (int): Maximum time to wait for a web response.
        
    Returns:
        io.BytesIO: A byte buffer of the file contents, or None if an error occurs.
    """
    clean_path = input_path.strip()
    
    if is_web_url(clean_path):
        print(f"Downloading {clean_path}...")
        try:
            # Added a timeout to prevent the script from hanging on unresponsive servers
            with urllib.request.urlopen(clean_path, timeout=timeout_seconds) as response:
                return io.BytesIO(response.read())
        except urllib.error.URLError as e:
            print(f"Network error while downloading {clean_path}: {e}")
        except Exception as e:
            print(f"Unexpected error occurred while downloading {clean_path}: {e}")
        return None    
    else:
        # If it is not a web URL, treat it as a local file path
        try:
            with open(clean_path, 'rb') as f:
                return io.BytesIO(f.read())
        except FileNotFoundError:
            print(f"Error: Local file not found - {clean_path}")
        except PermissionError:
            print(f"Error: Permission denied when trying to read - {clean_path}")
        except Exception as e:
            print(f"Unexpected error occurred while reading {clean_path}: {e}")
        return None


