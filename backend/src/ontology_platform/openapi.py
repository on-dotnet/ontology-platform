"""Print the OpenAPI document to stdout: python -m ontology_platform.openapi"""

import json
import sys

from ontology_platform.main import create_app


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
