# Ontology Platform

[简体中文](README.md)

An open-source, AI-native ontology platform. Give it your documents and data: AI identifies business concepts, relationships and constraints and proposes changes backed by evidence. People review the proposals, and approved changes are published as a standards-based ontology (RDF, OWL 2, SHACL, SKOS) that you can query, ask questions about, and share with external AI agents.

> Status: **rebuilding (M0 foundation)**. Capabilities ship milestone by milestone, see the [roadmap](docs/roadmap.md) (Chinese). The list below describes the target.

## What it does

- **AI reads your documents**: upload procedures, standards and reports; AI extracts terms, entity types and hierarchy, relationships and constraints in stages, each suggestion linked to the source text with a confidence level.
- **Humans approve, AI proposes**: every AI change is a change set that people accept, edit or reject item by item. Every published version can be compared and rolled back.
- **Standards-based**: import and export W3C ontologies and round-trip with tools such as Protégé.
- **Connect data**: bind entity types to PostgreSQL tables and browse real data through the ontology, read-only. Oracle, Doris, TDengine and Web API connectors will follow once there is an environment to test them against; see the [roadmap](docs/roadmap.md).
- **AI analysis**: ask questions in natural language and get answers with data and document citations, hypotheses and counter-evidence.
- **For agents**: expose the ontology to external AI agents via MCP.

The first industry case is quality analysis in steelmaking (steelmaking, refining, continuous casting, rolling), see [samples/steel](samples/steel). The platform itself is industry-neutral; contributions of other industry cases are welcome.

## Quick start (development)

Requires Docker with Compose and PowerShell 7.

```powershell
./dev.ps1 up
```

Open `http://<docker-host>:28080`. Development credentials are in [docs/development.md](docs/development.md).

## License

[Apache License 2.0](LICENSE)
