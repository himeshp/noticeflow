# NoticeFlow — Architecture Diagram

Presentation-quality diagram for the writeup and demo video. A standalone
[`architecture.svg`](architecture.svg) is also provided for upload/video use.

```mermaid
flowchart LR
    IN["GST Notice<br/>(PDF / text)<br/>ASMT-10 · DRC-01 · ITC-mismatch"]

    subgraph ORCH["ADK SequentialAgent · Orchestrator (typed state passed agent → agent)"]
        direction LR
        CLS["<b>Classifier</b><br/>LlmAgent · Gemini 2.5 Flash<br/>output_schema (Pydantic)<br/>→ ClassifiedNotice"]
        RES["<b>Researcher</b><br/>LlmAgent · Gemini 2.5 Flash<br/>VertexAiSearchTool<br/>→ LegalContext"]
        DFT["<b>Drafter</b><br/>LlmAgent · Gemini 2.5 Pro<br/>MCPToolset<br/>→ ResponsePacket"]
        CLS --> RES --> DFT
    end

    VAS["<b>Vertex AI Search</b> (Discovery Engine, RAG)<br/>Real CBIC GST-law corpus:<br/>CGST Act · CGST Rules ·<br/>Circulars 31 / 135 / 183"]
    MCP["<b>MCP Server</b> (FastMCP) — external tool<br/>get_reconciliation_data(gstin, tax_period)<br/>mock ERP — GSTR-3B vs 2B"]

    GATE["<b>Human Gate</b><br/>review · approve · edit<br/>PENDING_REVIEW"]
    OUT["<b>Response Packet</b><br/>legal basis · citations ·<br/>annexure · deadline flag<br/>(filing-ready)"]

    IN --> CLS
    RES <--> VAS
    DFT <--> MCP
    DFT --> GATE --> OUT

    classDef flash fill:#e8f0fe,stroke:#4285f4,color:#202124;
    classDef green fill:#e6f4ea,stroke:#34a853,color:#202124;
    classDef amber fill:#fef7e0,stroke:#f9ab00,color:#202124;
    classDef gate fill:#fce8e6,stroke:#ea4335,color:#202124;
    classDef out fill:#e8f0fe,stroke:#1a73e8,color:#202124;
    class CLS flash;
    class RES,VAS green;
    class DFT,MCP amber;
    class GATE gate;
    class OUT out;
```

**Deployed on Vertex AI Agent Engine** · Gemini routed through Vertex AI (no AI Studio)
· compute region `us-central1` · search datastore `global`.

Engine resource: `projects/205182179995/locations/us-central1/reasoningEngines/6398074104947146752`
