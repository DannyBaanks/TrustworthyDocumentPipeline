# Trustworthy Document Pipeline

An auditable document-processing application for the DevNetwork Nutrient DWS
Challenge.

The pipeline is intentionally small:

```text
document -> DWS operation -> normalized extraction -> confidence gate
         -> human review when needed -> replayable evidence
```

The public core does not contain private infrastructure names, machine paths,
credentials, or undocumented service endpoints. The DWS connection is an
explicit adapter configured by the caller.

## Current Status

The repository contains the deterministic pipeline contract, confidence gate,
evidence chain, and a local demo adapter. The real Nutrient DWS adapter is the
next integration step and will only be enabled after its official endpoint and
credentials are configured.

## Quick Start

```powershell
python -m venv .venv
python -m pip install -e .
python -m trustdocs.cli --demo
```

## Design Requirements

- DWS must perform a meaningful core document operation.
- Low-confidence extraction must stop for human review.
- Every decision must be replayable from recorded input and output hashes.
- Secrets must arrive through environment or deployment configuration.
- No absolute machine path is part of the application contract.

## License

MIT. See `LICENSE`.
