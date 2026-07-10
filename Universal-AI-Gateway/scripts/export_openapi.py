"""
Utility script to export the FastAPI OpenAPI specification to a file.
Useful for SDK generation and documenting the API.
"""

import json
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.main import app

def export_openapi():
    output_path = "openapi.json"
    
    # Get the raw OpenAPI schema
    schema = app.openapi()
    
    # Write to file
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
    
    print(f"Successfully exported OpenAPI schema to {output_path}")

if __name__ == "__main__":
    export_openapi()
