# Semantic Event

**Status:** `[DESIGN/PLANNING]`

## Definition
A Semantic Event represents the structured input that an agent receives from the virtualization boundary (Agent Hypervisor). The agent never receives raw input (e.g., raw text from emails, documents, or web pages). 

## Core Principles
When external signals enter the system, they are transformed into a Semantic Event that includes:
- **Source:** The origin of the signal (e.g., email, web, MCP tool).
- **Trust Level:** e.g., trusted, untrusted, or tainted.
- **Capabilities:** Defined actions permitted in the context of the input.
- **Provenance:** Origin tracking metadata.
- **Sanitized Payload:** The content from which hidden or executable instructions have been stripped.

## Code Reality
Currently, the codebase does not have an implemented structure for generating or handling Semantic Events. Input virtualization and sanitization logic exists only in the architectural whitepapers and technical specs.
