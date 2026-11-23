"""RDF import and export of ontologies, independent of the database (spec 002, 3 to 5).

- `reader`: a Turtle or RDF/XML file → `OntologyState` (elements and kept axioms);
- `writer`: `OntologyState` → RDF graph → deterministic Turtle;
- `declarations`: the OWL 2 declarations a graph implies, as OWL API reads them;
- `diff`: the changes from one state to another.
"""
