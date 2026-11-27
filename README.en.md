# Ontology Platform

[简体中文](README.md)

An open-source ontology platform. Users provide documents and data; AI identifies business concepts and proposes evidence-backed changes. People review the changes before publishing a standards-based ontology for queries, questions, and external AI agents.

## What it does

- Upload documents so AI can identify terms, entity types, relationships, and properties and create change sets linked to source evidence.
- Review each change, merge accepted items into the working version, and publish an ontology version.
- Import and export RDF, OWL 2, SHACL, and SKOS content, including round trips through Protégé.
- Bind ontology elements to PostgreSQL tables and columns, query objects, and follow relationships; external data sources are read-only.
- Use access tokens with MCP to read the ontology, query objects, or submit change proposals for review.
- Export R2RML mappings from published bindings.
- Ask questions in natural language and inspect the ontology, data, and document evidence behind the answers.
- Define metrics and rules and inspect their calculations and checks in Explore.
- Turn ontology gaps found during Q&A into change proposals for review.
- Record competency questions the ontology should answer and check the answers after publishing.

The first industry case is [steelmaking](samples/steel). See the [roadmap](docs/roadmap.md) for future work.

## Quick start

You need Docker with Compose and PowerShell 7; AI extraction and Q&A require a model API key. Check the [quickstart guide](docs/quickstart.md) for local configuration, then run from the repository root:

```powershell
./dev.ps1 init-env
./dev.ps1 up
./dev.ps1 status
```

Open `http://<OP_DEV_HOST>:28080` (override the port with `OP_WEB_PORT`). See the [development guide](docs/development.md) for the development account.

## Documentation

- [Quickstart (Chinese)](docs/quickstart.md)
- [Contributing (Chinese)](CONTRIBUTING.md)
- [Architecture (Chinese)](docs/architecture.md)
- [UI guidelines (Chinese)](docs/ui-guidelines.md)
- [Roadmap (Chinese)](docs/roadmap.md)
- [Development guide (Chinese)](docs/development.md)
- [Collaboration rules (Chinese)](AGENTS.md)

## License

[Apache License 2.0](LICENSE)
