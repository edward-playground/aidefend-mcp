"""
Threat Keywords Dictionary for AIDEFEND MCP Service (v3)

Static mapping of common threat terms to standard framework IDs (OWASP LLM/ML Top 10,
MITRE ATLAS, MAESTRO agentic-layer model).
Used by classify_threat_from_text tool for simple keyword-based threat identification.

NOTE:
- This is a production-grade static dictionary. No NLP/embedding is used.
- The LLM handles text understanding; this module only provides standardized mappings.
- Schema is intentionally simple and stable for long-term compatibility.

Schema
------
THREAT_KEYWORDS: Dict[str, Dict[str, Any]] where each entry is:

    {
        "frameworks": {
            "owasp": [<OWASP IDs: LLM01, ML02:2023, ...>],
            "atlas":  [<MITRE ATLAS technique IDs: AML.T00xx...>],
            "maestro":[<Maestro layer/risk identifiers>],
        },
        "confidence": <float 0-1>,
        "aliases": [<other phrases that should map to the same thing>]
    }

The same threat keyword can map to multiple frameworks.
"""

from typing import Dict, List, Any

# Threat keyword mapping dictionary
# Format: keyword -> {frameworks, confidence, aliases}
THREAT_KEYWORDS: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # OWASP TOP 10 FOR LLM APPLICATIONS 2025 (OWASP LLM Top 10)
    # =========================================================================
    # Reference codes simplified: LLM01..LLM10 (no year suffix)

    # LLM01: Prompt Injection
    "prompt injection": {
        "frameworks": {
            "owasp": ["LLM01"],
            "atlas": ["AML.T0051"],
            "maestro": ["L1-Adversarial-Examples", "Cross-Goal-Misalignment-Cascades"],
        },
        "confidence": 0.98,
        "aliases": [
            "prompt hijacking",
            "indirect prompt injection",
            "direct prompt injection",
            "jailbreak",
            "jailbreaking",
            "system prompt override",
            "prompt manipulation",
            "prompt hacking",
            "cross-plugin prompt injection",
            # reviewer suggested
            "context manipulation",
            "instruction override",
            # 2025 emerging
            "system message override",
            "role confusion",
        ],
    },

    # LLM02: Sensitive Information Disclosure
    "sensitive information disclosure": {
        "frameworks": {
            "owasp": ["LLM02"],
            "atlas": ["AML.T0057"],  # LLM data leakage
            "maestro": ["Cross-Data-Leakage", "L5-Data-Leakage-Through-Observability"],
        },
        "confidence": 0.92,
        "aliases": [
            "sensitive data disclosure",
            "data leakage",
            "pii leakage",
            "training data disclosure",
            "prompt data leakage",
            "information disclosure",
            "data exfiltration via llm response",
        ],
    },

    # Extra generic data leakage keyword that still maps to LLM02
    "data leakage": {
        "frameworks": {
            "owasp": ["LLM02"],
            "maestro": ["Cross-Data-Leakage", "L5-Data-Leakage-Through-Observability"],
        },
        "confidence": 0.85,
        "aliases": [
            "data leak",
            "information leakage",
            "pii leak",
        ],
    },

    # LLM03: Supply Chain
    "supply chain compromise": {
        "frameworks": {
            "owasp": ["LLM03"],
            "atlas": ["AML.T0010"],
            "maestro": ["Cross-Supply-Chain-Attacks"],
        },
        "confidence": 0.9,
        "aliases": [
            "llm supply chain",
            "ml supply chain compromise",
            "dependency poisoning",
            "malicious huggingface model",
            "ai supply chain attack",
            "third-party model compromise",
        ],
    },

    # LLM04: Data and Model Poisoning
    "training data poisoning": {
        "frameworks": {
            "owasp": ["LLM04"],
            "atlas": ["AML.T0010", "AML.T0018", "AML.T0020"],
            "maestro": [
                "L2-Data-Poisoning",
                "L1-Data-Poisoning-Training-Phase",
                "Cross-Supply-Chain-Attacks",
            ],
        },
        "confidence": 0.96,
        "aliases": [
            "data poisoning",
            "dataset poisoning",
            "backdoor poisoning",
            "split-view data poisoning",
            "frontrunning poisoning",
            "poisoned fine-tuning dataset",
            "poisoned embedding corpus",
        ],
    },

    # LLM05: Improper Output Handling
    "insecure output handling": {
        "frameworks": {"owasp": ["LLM05"]},
        "confidence": 0.9,
        "aliases": [
            "insecure output",
            "unsafe output rendering",
            "xss in llm",
            "html injection in response",
            "template injection from llm",
            "output injection",
            "output not validated",
        ],
    },

    # LLM06: Excessive Agency
    "excessive agency": {
        "frameworks": {
            "owasp": ["LLM06"],
            "atlas": ["AML.T0053"],  # agent plugin/tool abuse
            "maestro": [
                "L7-Agent-Tool-Misuse",
                "L7-Agent-Goal-Manipulation",
                "L7-Agent-Identity-Attack",
            ],
        },
        "confidence": 0.9,
        "aliases": [
            "over-privileged agent",
            "excessive permissions",
            "over-permissioned llm agent",
            "agent overreach",
            "runaway agent",
        ],
    },

    "agent tool misuse": {
        "frameworks": {
            "owasp": ["LLM06"],
            "maestro": ["L7-Agent-Tool-Misuse"],
            "atlas": ["AML.T0053"],
        },
        "confidence": 0.95,
        "aliases": [
            "unsafe tool invocation",
            "abusive tool use",
            "harmful tool calls",
            "tool abuse by agent",
        ],
    },

    # Explicitly separate out tool-call injection
    "tool call injection": {
        "frameworks": {
            "owasp": ["LLM01", "LLM06"],
            "atlas": ["AML.T0053", "AML.T0051"],
            "maestro": ["L7-Agent-Tool-Misuse", "L7-Agent-Goal-Manipulation"],
        },
        "confidence": 0.92,
        "aliases": [
            "tool invocation injection",
            "function call injection",
            "tool misuse via prompt",
        ],
    },

    # LLM07: System Prompt Leakage
    "system prompt leakage": {
        "frameworks": {
            "owasp": ["LLM07"],
            "atlas": ["AML.T0056"],
        },
        "confidence": 0.9,
        "aliases": [
            "system prompt disclosure",
            "prompt template leakage",
            "jailbreak to read system prompt",
            "leak system instructions",
        ],
    },

    # LLM08: Vector and Embedding Weaknesses
    "vector and embedding weaknesses": {
        "frameworks": {
            "owasp": ["LLM08"],
            "atlas": ["AML.T0070", "AML.T0071", "AML.T0085.000"],
            "maestro": ["L2-Compromised-RAG-Pipelines"],
        },
        "confidence": 0.9,
        "aliases": [
            "embedding weakness",
            "vector db weakness",
            "vector store weakness",
            "embedding poisoning",
            "vector search manipulation",
        ],
    },

    # LLM09: Misinformation
    "misinformation": {
        "frameworks": {
            "owasp": ["LLM09"],
            "maestro": ["L5-Evaluation-Hallucination-Issue"],
        },
        "confidence": 0.85,
        "aliases": [
            "false information",
            "fake content",
            "disinformation",
            "llm misinformation",
        ],
    },

    # LLM10: Unbounded Consumption
    "unbounded consumption": {
        "frameworks": {
            "owasp": ["LLM10"],
            "atlas": ["AML.T0029", "AML.T0034", "AML.T0040"],
            "maestro": [
                "L1-DoS-On-Foundation-Model",
                "L4-DoS-On-AI-Infrastructure",
            ],
        },
        "confidence": 0.9,
        "aliases": [
            "resource exhaustion",
            "cost harvesting",
            "llm cost abuse",
            "compute exhaustion",
            "billing abuse",
        ],
    },

    "llm denial of service": {
        "frameworks": {
            "owasp": ["LLM10"],
            "maestro": ["L1-DoS-On-Foundation-Model"],
            "atlas": ["AML.T0029", "AML.T0034", "AML.T0040"],
        },
        "confidence": 0.9,
        "aliases": [
            "model denial of service",
            "llm dos",
            "llm resource exhaustion",
            "prompt flooding",
            "sponge attacks",
        ],
    },

    # Plugins / connectors
    "insecure plugin": {
        "frameworks": {
            "owasp": ["LLM03", "LLM06"],
            "maestro": ["L7-Agent-Tool-Misuse"],
            "atlas": ["AML.T0053"],
        },
        "confidence": 0.88,
        "aliases": [
            "plugin vulnerability",
            "unsafe plugin",
            "malicious plugin",
            "compromised connector",
            "insecure tool",
            "unsafe third-party tool",
        ],
    },

    # Automation bias / overreliance
    "overreliance": {
        "frameworks": {
            "owasp": ["LLM09"],
            "maestro": ["L7-Overreliance-And-Automation-Bias"],
        },
        "confidence": 0.8,
        "aliases": [
            "automation bias",
            "llm overreliance",
            "blind trust in llm",
            "uncritical acceptance",
        ],
    },

    # =========================================================================
    # OWASP MACHINE LEARNING SECURITY TOP 10 (ML01–ML10:2023)
    # =========================================================================
    # Reference: ML01:2023..ML10:2023

    # ML01:2023 Input Manipulation Attack
    "input manipulation attack": {
        "frameworks": {
            "owasp": ["ML01:2023"],
            "atlas": ["AML.T0043"],
            "maestro": ["L1-Adversarial-Examples"],
        },
        "confidence": 0.95,
        "aliases": [
            "adversarial example",
            "adversarial attack",
            "evasion attack",
            "adversarial perturbation",
            "crafted input",
        ],
    },

    # ML02:2023 Data Poisoning Attack
    "ml data poisoning attack": {
        "frameworks": {
            "owasp": ["ML02:2023"],
            "atlas": ["AML.T0010", "AML.T0018", "AML.T0020"],
            "maestro": ["L2-Data-Poisoning", "L1-Data-Poisoning-Training-Phase"],
        },
        "confidence": 0.96,
        "aliases": [
            "ml data poisoning",
            "poison training data",
            "poisoned dataset",
            "dataset contamination",
        ],
    },

    # ML03:2023 Model Inversion Attack
    "model inversion attack": {
        "frameworks": {
            "owasp": ["ML03:2023"],
            "atlas": ["AML.T0029"],
            "maestro": ["L1-Model-Inversion"],
        },
        "confidence": 0.9,
        "aliases": [
            "model inversion",
            "reconstruction attack",
            "training data reconstruction",
        ],
    },

    # ML04:2023 Membership Inference Attack
    "membership inference attack": {
        "frameworks": {
            "owasp": ["ML04:2023"],
            "atlas": ["AML.T0028"],
            "maestro": ["L1-Membership-Inference"],
        },
        "confidence": 0.9,
        "aliases": [
            "membership inference",
            "training data membership test",
            "privacy attack on training membership",
        ],
    },

    # ML05:2023 Model Theft
    "ml model theft": {
        "frameworks": {
            "owasp": ["ML05:2023"],
            "atlas": ["AML.T0002"],
            "maestro": ["L1-Model-Stealing"],
        },
        "confidence": 0.95,
        "aliases": [
            "steal ml model",
            "ml model extraction",
            "clone model parameters",
        ],
    },

    # ML06:2023 ML Supply Chain Attacks
    "ai supply chain attacks": {
        "frameworks": {
            "owasp": ["ML06:2023"],
            "atlas": ["AML.T0010"],
            "maestro": ["Cross-Supply-Chain-Attacks"],
        },
        "confidence": 0.9,
        "aliases": [
            "ai supply chain attack",
            "ml supply chain attacks",
            "model repository compromise",
            "dependency compromise",
        ],
    },

    # ML07:2023 Transfer Learning Attack
    "transfer learning attack": {
        "frameworks": {
            "owasp": ["ML07:2023"],
            "atlas": ["AML.T0018"],
            "maestro": ["L1-Transfer-Learning-Abuse"],
        },
        "confidence": 0.88,
        "aliases": [
            "poison pre-trained model",
            "transfer learning abuse",
            "fine-tuning backdoor",
        ],
    },

    # ML08:2023 Model Skewing
    "model skewing": {
        "frameworks": {
            "owasp": ["ML08:2023"],
            "maestro": ["L2-Model-Skewing"],
        },
        "confidence": 0.88,
        "aliases": [
            "data drift exploitation",
            "concept drift exploitation",
            "skewed model behavior",
        ],
    },

    # ML09:2023 Output Integrity Attack
    "output integrity attack": {
        "frameworks": {
            "owasp": ["ML09:2023"],
            "maestro": ["L5-Output-Integrity-Issues"],
            "atlas": ["AML.T0049"],
        },
        "confidence": 0.88,
        "aliases": [
            "tampered model output",
            "corrupted inference output",
            "output manipulation",
        ],
    },

    # ML10:2023 Model Poisoning
    "model poisoning": {
        "frameworks": {
            "owasp": ["ML10:2023"],
            "atlas": ["AML.T0031"],
            "maestro": ["L1-Backdoor-Attacks", "L2-Data-Poisoning"],
        },
        "confidence": 0.9,
        "aliases": [
            "poison model weights",
            "backdoor the model",
            "trojan model",
        ],
    },

    # =========================================================================
    # MAESTRO / AGENTIC LAYERS – LAYER-SPECIFIC RISKS
    # =========================================================================
    # Maestro identifiers follow the pattern:
    #   L<layer_number>-<Short-Name>
    #   Cross-<Short-Name> for cross-layer issues.

    # ----- Layer 7: Agent Ecosystem -----

    "compromised agent": {
        "frameworks": {
            "maestro": ["L7-Compromised-Agents"],
            "atlas": ["AML.T0053", "AML.T0048"],
        },
        "confidence": 0.9,
        "aliases": [
            "malicious agent",
            "rogue agent",
            "backdoored agent",
            "compromised llm agent",
        ],
    },

    "agent impersonation": {
        "frameworks": {
            "maestro": ["L7-Agent-Impersonation"],
            "atlas": ["AML.T0052", "AML.T0048.001"],
        },
        "confidence": 0.9,
        "aliases": [
            "agent spoofing",
            "llm agent impersonation",
            "fake agent identity",
        ],
    },

    "agent identity attack": {
        "frameworks": {
            "maestro": ["L7-Agent-Identity-Attack"],
            "atlas": ["AML.T0052.000"],
        },
        "confidence": 0.88,
        "aliases": [
            "agent identity compromise",
            "agent credential theft",
            "agent key theft",
        ],
    },

    "agent goal manipulation": {
        "frameworks": {
            "maestro": ["L7-Agent-Goal-Manipulation", "Cross-Goal-Misalignment-Cascades"],
            "atlas": ["AML.T0048.002"],
        },
        "confidence": 0.9,
        "aliases": [
            "goal hijacking",
            "objective hijacking",
            "reward hacking",
            "agent misalignment",
        ],
    },

    "marketplace manipulation": {
        "frameworks": {"maestro": ["L7-Marketplace-Manipulation"]},
        "confidence": 0.85,
        "aliases": [
            "fake agent ratings",
            "agent review fraud",
            "marketplace poisoning",
        ],
    },

    "integration risk": {
        "frameworks": {"maestro": ["L7-Integration-Risks"], "owasp": ["LLM03"]},
        "confidence": 0.8,
        "aliases": [
            "insecure api integration",
            "sdk integration risk",
            "weak integration controls",
        ],
    },

    "horizontal vertical solution vulnerability": {
        "frameworks": {"maestro": ["L7-Horizontal-Vertical-Solution-Vulnerabilities"]},
        "confidence": 0.75,
        "aliases": [
            "vertical solution weakness",
            "industry-specific agent vulnerability",
        ],
    },

    "agent repudiation": {
        "frameworks": {"maestro": ["L7-Repudiation"]},
        "confidence": 0.8,
        "aliases": [
            "agent action repudiation",
            "non-repudiation failure",
            "unattributed agent actions",
        ],
    },

    "compromised agent registry": {
        "frameworks": {"maestro": ["L7-Compromised-Agent-Registry"]},
        "confidence": 0.85,
        "aliases": [
            "registry poisoning",
            "agent catalog compromise",
            "agent listing tampering",
        ],
    },

    "malicious agent discovery": {
        "frameworks": {"maestro": ["L7-Malicious-Agent-Discovery"]},
        "confidence": 0.85,
        "aliases": [
            "manipulated agent discovery",
            "search results manipulation",
            "agent ranking fraud",
        ],
    },

    "agent pricing model manipulation": {
        "frameworks": {"maestro": ["L7-Agent-Pricing-Model-Manipulation"]},
        "confidence": 0.8,
        "aliases": [
            "agent billing fraud",
            "pricing abuse",
            "economic manipulation of agents",
        ],
    },

    "inaccurate agent capability description": {
        "frameworks": {"maestro": ["L7-Inaccurate-Agent-Capability-Description"]},
        "confidence": 0.8,
        "aliases": [
            "misleading agent description",
            "false agent capabilities",
            "agent overclaiming",
        ],
    },

    # ----- Layer 6: Security and Compliance (Vertical) -----

    "security agent data poisoning": {
        "frameworks": {
            "maestro": ["L6-Security-Agent-Data-Poisoning"],
            "atlas": ["AML.T0010", "AML.T0018"],
        },
        "confidence": 0.9,
        "aliases": [
            "poisoning security ai agent",
            "security ml data poisoning",
            "siem ai poisoning",
        ],
    },

    "evasion of security ai agents": {
        "frameworks": {
            "maestro": ["L6-Evasion-Of-Security-AI-Agents"],
            "atlas": ["AML.T0043", "AML.T0034"],
        },
        "confidence": 0.88,
        "aliases": [
            "evade security ai",
            "evade detection by ai agent",
            "adversarial evasion of detector",
        ],
    },

    "compromised security ai agent": {
        "frameworks": {"maestro": ["L6-Compromised-Security-AI-Agents"]},
        "confidence": 0.9,
        "aliases": [
            "security agent takeover",
            "backdoored security agent",
            "security ai compromise",
        ],
    },

    "regulatory non-compliance by ai security agents": {
        "frameworks": {"maestro": ["L6-Regulatory-Non-Compliance-By-AI-Security-Agents"]},
        "confidence": 0.8,
        "aliases": [
            "non-compliant security ai",
            "privacy-violating security agent",
            "gdpr violating ai monitor",
        ],
    },

    "bias in security ai agents": {
        "frameworks": {"maestro": ["L6-Bias-In-Security-AI-Agents"]},
        "confidence": 0.8,
        "aliases": [
            "biased security ai",
            "uneven enforcement by ai",
            "discriminatory security agent",
        ],
    },

    "lack of explainability in security ai agents": {
        "frameworks": {"maestro": ["L6-Lack-Of-Explainability-In-Security-AI-Agents"]},
        "confidence": 0.8,
        "aliases": [
            "black box security ai",
            "non-transparent security agent",
            "unexplainable detection decision",
        ],
    },

    "model extraction of ai security agents": {
        "frameworks": {
            "maestro": ["L6-Model-Extraction-Of-AI-Security-Agents"],
            "atlas": ["AML.T0002"],
        },
        "confidence": 0.88,
        "aliases": [
            "steal security model",
            "extract security ai model",
            "security model theft",
        ],
    },

    # ----- Layer 5: Evaluation and Observability -----

    "manipulation of evaluation metrics": {
        "frameworks": {"maestro": ["L5-Manipulation-Of-Evaluation-Metrics"]},
        "confidence": 0.85,
        "aliases": [
            "eval metric gaming",
            "goodhart law on ai metrics",
            "benchmark manipulation",
        ],
    },

    "compromised observability tools": {
        "frameworks": {
            "maestro": ["L5-Compromised-Observability-Tools"],
            "owasp": ["LLM03", "LLM05"],  # Supply Chain + Output Handling
        },
        "confidence": 0.88,
        "aliases": [
            "tampered monitoring pipeline",
            "compromised logging",
            "backdoored observability",
        ],
    },

    "denial of service on evaluation infrastructure": {
        "frameworks": {"maestro": ["L5-DoS-On-Evaluation-Infrastructure"]},
        "confidence": 0.85,
        "aliases": [
            "dos on eval infra",
            "benchmarking infrastructure dos",
            "load testing abuse",
        ],
    },

    "evasion of detection": {
        "frameworks": {
            "maestro": ["L5-Evasion-Of-Detection"],
            "atlas": ["AML.T0043", "AML.T0034"],
        },
        "confidence": 0.9,
        "aliases": [
            "detector evasion",
            "security detection evasion",
            "evasion of monitoring",
        ],
    },

    "data leakage through observability": {
        "frameworks": {
            "maestro": ["L5-Data-Leakage-Through-Observability"],
            "owasp": ["LLM02"],
        },
        "confidence": 0.9,
        "aliases": [
            "log data leakage",
            "logging sensitive data",
            "metric dashboard data leak",
        ],
    },

    "poisoning observability data": {
        "frameworks": {"maestro": ["L5-Poisoning-Observability-Data"]},
        "confidence": 0.86,
        "aliases": [
            "poison monitoring data",
            "tamper telemetry",
            "fake observability events",
        ],
    },

    # ----- Layer 4: Deployment and Infrastructure -----

    "compromised container images": {
        "frameworks": {
            "maestro": ["L4-Compromised-Container-Images"],
            "owasp": ["ML06:2023", "LLM03"],
        },
        "confidence": 0.9,
        "aliases": [
            "backdoored container image",
            "malicious docker image",
            "compromised ml container",
        ],
    },

    "orchestration attacks": {
        "frameworks": {"maestro": ["L4-Orchestration-Attacks"]},
        "confidence": 0.88,
        "aliases": [
            "kubernetes attack",
            "k8s misconfiguration exploitation",
            "orchestrator compromise",
        ],
    },

    "infrastructure as code manipulation": {
        "frameworks": {"maestro": ["L4-IaC-Manipulation"]},
        "confidence": 0.86,
        "aliases": [
            "iac manipulation",
            "terraform tampering",
            "cloudformation tampering",
            "pipeline config tampering",
        ],
    },

    "dos on ai infrastructure": {
        "frameworks": {
            "maestro": ["L4-DoS-On-AI-Infrastructure"],
            "owasp": ["LLM10"],
            "atlas": ["AML.T0034", "AML.T0040"],
        },
        "confidence": 0.9,
        "aliases": [
            "infrastructure dos",
            "resource exhaustion on cluster",
            "ddos on inference endpoints",
        ],
    },

    "resource hijacking": {
        "frameworks": {"maestro": ["L4-Resource-Hijacking"]},
        "confidence": 0.86,
        "aliases": [
            "cryptomining on gpu",
            "gpu hijacking",
            "unauthorized workload on cluster",
        ],
    },

    "lateral movement in ai infra": {
        "frameworks": {
            "maestro": ["L4-Lateral-Movement"],
            "atlas": ["AML.T0049"],
            "owasp": ["LLM03"],
        },
        "confidence": 0.86,
        "aliases": [
            "lateral movement",
            "pivoting inside ai cluster",
            "east west movement in ai network",
        ],
    },

    # ----- Layer 3: Agent Frameworks -----

    "compromised framework components": {
        "frameworks": {
            "maestro": ["L3-Compromised-Framework-Components"],
            "owasp": ["ML06:2023"],
        },
        "confidence": 0.88,
        "aliases": [
            "malicious framework library",
            "vulnerable ai framework",
            "compromised agent sdk",
        ],
    },

    "framework backdoor attacks": {
        "frameworks": {
            "maestro": ["L3-Backdoor-Attacks"],
            "atlas": ["AML.T0018"],
        },
        "confidence": 0.9,
        "aliases": [
            "framework-level trojan",
            "backdoor in ai framework",
        ],
    },

    "input validation attacks on framework": {
        "frameworks": {"maestro": ["L3-Input-Validation-Attacks"]},
        "confidence": 0.86,
        "aliases": [
            "framework input validation failure",
            "unvalidated input to tools",
            "unsafe parsing in agent framework",
        ],
    },

    "framework supply chain attacks": {
        "frameworks": {
            "maestro": ["L3-Supply-Chain-Attacks"],
            "owasp": ["ML06:2023", "LLM03"],
        },
        "confidence": 0.88,
        "aliases": [
            "framework dependency compromise",
            "framework supply chain compromise",
        ],
    },

    "dos on framework apis": {
        "frameworks": {"maestro": ["L3-DoS-On-Framework-APIs"]},
        "confidence": 0.85,
        "aliases": [
            "framework api dos",
            "agent framework rate limiting bypass",
        ],
    },

    "framework evasion": {
        "frameworks": {"maestro": ["L3-Framework-Evasion"]},
        "confidence": 0.82,
        "aliases": [
            "evade framework policies",
            "bypass agent policies",
            "framework security bypass",
        ],
    },

    # ----- Layer 2: Data Operations -----

    "data poisoning in data ops": {
        "frameworks": {
            "maestro": ["L2-Data-Poisoning"],
            "owasp": ["ML02:2023", "LLM04"],
            "atlas": ["AML.T0010", "AML.T0020"],
        },
        "confidence": 0.95,
        "aliases": [
            "poison data pipeline",
            "data pipeline poisoning",
            "rag corpus poisoning",
        ],
    },

    "data exfiltration from data ops": {
        "frameworks": {
            "maestro": ["L2-Data-Exfiltration"],
            "atlas": ["AML.T0024"],
            "owasp": ["LLM02"],
        },
        "confidence": 0.92,
        "aliases": [
            "exfiltrate vector store",
            "steal embedding store",
            "data store exfiltration",
        ],
    },

    "dos on data infrastructure": {
        "frameworks": {"maestro": ["L2-DoS-On-Data-Infrastructure"]},
        "confidence": 0.86,
        "aliases": [
            "dos on database for ai",
            "vector db dos",
            "data pipeline outage",
        ],
    },

    "data tampering in data ops": {
        "frameworks": {
            "maestro": ["L2-Data-Tampering"],
            "atlas": ["AML.T0049"],
        },
        "confidence": 0.86,
        "aliases": [
            "tamper stored data",
            "modify ai dataset",
            "data corruption attack",
        ],
    },

    "compromised rag pipelines": {
        "frameworks": {
            "maestro": ["L2-Compromised-RAG-Pipelines"],
            "atlas": ["AML.T0070", "AML.T0071", "AML.T0085.000"],
        },
        "confidence": 0.9,
        "aliases": [
            "rag poisoning",
            "retrieval poisoning",
            "knowledge base poisoning",
            "context poisoning",
            # reviewer suggested
            "document injection",
        ],
    },

    # ----- Layer 1: Foundation Models -----

    "foundation model adversarial examples": {
        "frameworks": {
            "maestro": ["L1-Adversarial-Examples"],
            "atlas": ["AML.T0043"],
        },
        "confidence": 0.95,
        "aliases": [
            "adversarial example on foundation model",
            "foundation model evasion",
            "base model adversarial attack",
        ],
    },

    "foundation model stealing": {
        "frameworks": {
            "maestro": ["L1-Model-Stealing"],
            "atlas": ["AML.T0002"],
        },
        "confidence": 0.95,
        "aliases": [
            "steal foundation model",
            "large model extraction",
            "api model stealing",
        ],
    },

    "foundation model backdoor": {
        "frameworks": {
            "maestro": ["L1-Backdoor-Attacks"],
            "atlas": ["AML.T0018"],
        },
        "confidence": 0.9,
        "aliases": [
            "backdoor foundation model",
            "trojaned base model",
            "sleeper agent backdoor",
        ],
    },

    "foundation model membership inference": {
        "frameworks": {
            "maestro": ["L1-Membership-Inference"],
            "atlas": ["AML.T0028"],
        },
        "confidence": 0.9,
        "aliases": [
            "membership inference on foundation model",
            "foundation model membership leak",
        ],
    },

    "foundation model data poisoning": {
        "frameworks": {
            "maestro": ["L1-Data-Poisoning-Training-Phase"],
            "atlas": ["AML.T0010", "AML.T0020"],
        },
        "confidence": 0.92,
        "aliases": [
            "pretraining data poisoning",
            "foundation model pretraining poisoning",
        ],
    },

    "reprogramming attacks": {
        "frameworks": {
            "maestro": ["L1-Reprogramming-Attacks"],
            "atlas": ["AML.T0049"],
        },
        "confidence": 0.85,
        "aliases": [
            "model reprogramming",
            "task reprogramming",
            "llm jailbreak via reprogramming",
        ],
    },

    "dos on foundation models": {
        "frameworks": {
            "maestro": ["L1-DoS-On-Foundation-Model"],
            "atlas": ["AML.T0029", "AML.T0034"],
        },
        "confidence": 0.9,
        "aliases": [
            "foundation model dos",
            "base model resource exhaustion",
        ],
    },

    # =========================================================================
    # CROSS-LAYER THREATS (MAESTRO CROSS-CUTTING)
    # =========================================================================

    "cross-layer supply chain attack": {
        "frameworks": {
            "maestro": ["Cross-Supply-Chain-Attacks"],
            "owasp": ["ML06:2023", "LLM03"],
            "atlas": ["AML.T0010"],
        },
        "confidence": 0.92,
        "aliases": [
            "supply chain attack",
            "ml supply chain compromise",
            "llm supply chain compromise",
        ],
    },

    "cross-layer lateral movement": {
        "frameworks": {
            "maestro": ["Cross-Lateral-Movement"],
            "atlas": ["AML.T0049"],
        },
        "confidence": 0.86,
        "aliases": [
            "lateral movement between layers",
            "pivot across ai layers",
        ],
    },

    "privilege escalation across layers": {
        "frameworks": {
            "maestro": ["Cross-Privilege-Escalation"],
            "atlas": ["AML.T0053"],
        },
        "confidence": 0.84,
        "aliases": [
            "agent privilege escalation",
            "cross-layer privilege escalation",
        ],
    },

    "data leakage across layers": {
        "frameworks": {
            "maestro": ["Cross-Data-Leakage"],
            "owasp": ["LLM02"],
        },
        "confidence": 0.9,
        "aliases": [
            "data leakage between layers",
            "cross-layer data leak",
        ],
    },

    "goal misalignment cascades": {
        "frameworks": {"maestro": ["Cross-Goal-Misalignment-Cascades"]},
        "confidence": 0.88,
        "aliases": [
            "cascading goal misalignment",
            "multi-agent misalignment cascade",
        ],
    },

    # =========================================================================
    # EMERGING / COMMON AI & LLM THREATS (FROM REVIEWER SUGGESTIONS)
    # =========================================================================

    # RAG bypass / circumvention attacks
    "rag bypass": {
        "frameworks": {
            "owasp": ["LLM08"],
            "atlas": ["AML.T0070"],
            "maestro": ["L2-Compromised-RAG-Pipelines"],
        },
        "confidence": 0.85,
        "aliases": [
            "retrieval bypass",
            "rag circumvention",
            "context injection bypass",
        ],
    },

    # Model collapse / synthetic feedback loops
    "model collapse": {
        "frameworks": {
            "owasp": ["ML08:2023"],
            "maestro": ["L2-Model-Skewing"],
        },
        "confidence": 0.8,
        "aliases": [
            "model degradation",
            "quality collapse",
            "synthetic data feedback loop",
        ],
    },

    # Chain of thought / reasoning manipulation
    "chain of thought manipulation": {
        "frameworks": {
            "owasp": ["LLM01"],
            "atlas": ["AML.T0051"],
            "maestro": ["L1-Adversarial-Examples"],
        },
        "confidence": 0.82,
        "aliases": [
            "cot attack",
            "reasoning manipulation",
            "thought process hijacking",
        ],
    },

    # Context window / eviction attacks
    "context window attack": {
        "frameworks": {
            "owasp": ["LLM01", "LLM10"],
            "atlas": ["AML.T0051", "AML.T0040"],
            "maestro": ["L1-Adversarial-Examples", "L1-DoS-On-Foundation-Model"],
        },
        "confidence": 0.88,
        "aliases": [
            "context flooding",
            "instruction burial",
            "context eviction attack",
        ],
    },

    # Constitutional AI / safety bypass
    "constitutional ai bypass": {
        "frameworks": {
            "owasp": ["LLM01", "LLM06"],
            "maestro": ["L7-Agent-Goal-Manipulation"],
        },
        "confidence": 0.78,
        "aliases": [
            "constitutional bypass",
            "safety constraint bypass",
            "alignment bypass",
        ],
    },

    # Multi-modal jailbreaks / attacks
    "multi-modal attacks": {
        "frameworks": {
            "owasp": ["ML01:2023", "LLM01"],
            "atlas": ["AML.T0043", "AML.T0051", "AML.T0040"],
            "maestro": ["L1-Adversarial-Examples"],
        },
        "confidence": 0.85,
        "aliases": [
            "vision language model attack",
            "vlm jailbreak",
            "image prompt injection",
        ],
    },

    # API rate limit / quota abuse
    "api rate limit bypass": {
        "frameworks": {
            "owasp": ["LLM10"],
            "atlas": ["AML.T0040", "AML.T0034"],
            "maestro": ["L4-DoS-On-AI-Infrastructure", "L1-DoS-On-Foundation-Model"],
        },
        "confidence": 0.9,
        "aliases": [
            "rate limiting bypass",
            "quota exhaustion",
            "billing abuse via api",
        ],
    },

    # Session hijacking around AI agents / UIs
    "session hijacking": {
        "frameworks": {
            "owasp": ["LLM02", "LLM10"],
            "atlas": ["AML.T0055"],
            "maestro": ["Cross-Privilege-Escalation", "L7-Agent-Identity-Attack"],
        },
        "confidence": 0.88,
        "aliases": [
            "session takeover",
            "token theft",
            "cookie hijacking",
        ],
    },

    # Shadow AI (unsanctioned use of external LLMs / SaaS)
    "shadow ai": {
        "frameworks": {
            "owasp": ["LLM02", "LLM03"],
            "maestro": [
                "L7-Integration-Risks",
                "L6-Regulatory-Non-Compliance-By-AI-Security-Agents",
            ],
        },
        "confidence": 0.82,
        "aliases": [
            "unsanctioned llm usage",
            "rogue ai usage",
            "unapproved ai service",
        ],
    },

    # Unsecured credentials (ATLAS AML.T0055)
    "unsecured credentials": {
        "frameworks": {
            "atlas": ["AML.T0055"],
            "maestro": ["Cross-Privilege-Escalation"],
            "owasp": ["LLM02"],
        },
        "confidence": 0.9,
        "aliases": [
            "exposed secrets",
            "hardcoded credentials",
            "leaked api key",
            "plaintext passwords",
        ],
    },

    # Inference API access / abuse (ATLAS AML.T0040)
    "ml model inference api access": {
        "frameworks": {
            "atlas": ["AML.T0040"],
            "owasp": ["LLM10"],
            "maestro": ["L4-DoS-On-AI-Infrastructure"],
        },
        "confidence": 0.88,
        "aliases": [
            "inference api abuse",
            "unprotected inference endpoint",
            "public ml api abuse",
        ],
    },

    # =========================================================================
    # OTHER COMMON AI / LLM THREAT TERMS (BACKWARD-COMPAT)
    # =========================================================================

    "rag poisoning": {
        "frameworks": {
            "owasp": ["LLM04", "LLM08"],
            "atlas": ["AML.T0070", "AML.T0071", "AML.T0085.000"],
            "maestro": ["L2-Compromised-RAG-Pipelines"],
        },
        "confidence": 0.9,
        "aliases": [
            "retrieval poisoning",
            "context poisoning",
            "knowledge base poisoning",
            "vector store poisoning",
            "document injection",
            # 2025 emerging
            "semantic injection",
            "embedding space poisoning",
        ],
    },

    "hallucination": {
        "frameworks": {
            "owasp": ["LLM09"],
            "maestro": ["L5-Evaluation-Hallucination-Issue"],
        },
        "confidence": 0.75,
        "aliases": [
            "confabulation",
            "fabrication",
            "false information",
            "made-up answer",
        ],
    },

    "bias": {
        "frameworks": {
            "owasp": ["LLM09"],
            "maestro": ["L6-Bias-In-Security-AI-Agents"],
        },
        "confidence": 0.7,
        "aliases": [
            "algorithmic bias",
            "model bias",
            "fairness issue",
            "unfair outputs",
        ],
    },

    "adversarial training": {
        "frameworks": {
            "atlas": ["AML.T0043"],
            "owasp": ["ML01:2023"],
        },
        "confidence": 0.8,
        "aliases": [
            "robustness training",
            "adversarial defense",
        ],
    },

    "federated learning": {
        "frameworks": {
            "atlas": ["AML.T0020"],
            "owasp": ["ML02:2023"],
        },
        "confidence": 0.75,
        "aliases": [
            "distributed learning",
            "federated poisoning",
        ],
    },

    "sybil attack": {
        "frameworks": {
            "atlas": ["AML.T0020"],
            "owasp": ["ML02:2023"],
        },
        "confidence": 0.78,
        "aliases": [
            "multiple identity attack",
            "fake participant",
        ],
    },

    "gradient leakage": {
        "frameworks": {
            "atlas": ["AML.T0028"],
            "owasp": ["ML04:2023"],
        },
        "confidence": 0.82,
        "aliases": [
            "gradient inference",
            "gradient attack",
        ],
    },

    "transfer learning attack (generic)": {
        "frameworks": {
            "atlas": ["AML.T0018"],
            "owasp": ["ML07:2023"],
        },
        "confidence": 0.8,
        "aliases": [
            "pre-trained model attack",
            "poison transfer learning",
        ],
    },

    # ----- Infrastructure & Deployment (backward-compat original entries) -----

    "model serving": {
        "frameworks": {
            "owasp": ["LLM10"],
            "maestro": ["L4-DoS-On-AI-Infrastructure"],
            "atlas": ["AML.T0040", "AML.T0034"],
        },
        "confidence": 0.7,
        "aliases": [
            "inference endpoint",
            "api abuse",
        ],
    },

    "container escape": {
        "frameworks": {
            "owasp": ["LLM05", "LLM03"],
            "maestro": ["L4-Compromised-Container-Images"],
        },
        "confidence": 0.75,
        "aliases": [
            "sandbox escape",
            "isolation breach",
        ],
    },

    # ----- Model theft via LLM (generic mapping) -----

    "model theft via llm": {
        "frameworks": {
            "atlas": ["AML.T0002"],
            "maestro": ["L1-Model-Stealing"],
        },
        "confidence": 0.9,
        "aliases": [
            "model theft",
            "model stealing",
            "model extraction",
            "llm ip theft",
        ],
    },

    "model theft": {
        "frameworks": {
            "atlas": ["AML.T0002"],
            "maestro": ["L1-Model-Stealing"],
            "owasp": ["ML05:2023"],
        },
        "confidence": 0.9,
        "aliases": [
            "model stealing",
            "model extraction",
            "ip theft",
            "weight extraction",
            "api scraping",
        ],
    },
}


def get_all_threat_keywords() -> List[str]:
    """Get all primary threat keywords.

    Returns:
        List of primary keywords
    """
    return list(THREAT_KEYWORDS.keys())


def get_threat_frameworks() -> Dict[str, List[str]]:
    """Get all unique threat IDs by framework.

    Returns:
        Dict with framework -> [threat_ids]
    """
    frameworks = {"owasp": set(), "atlas": set(), "maestro": set()}

    for keyword_data in THREAT_KEYWORDS.values():
        for framework, threat_ids in keyword_data["frameworks"].items():
            # Ensure we only collect expected framework keys
            if framework not in frameworks:
                continue
            frameworks[framework].update(threat_ids)

    return {k: sorted(list(v)) for k, v in frameworks.items()}


def normalize_threat_keyword(keyword: str) -> str:
    """Normalize a threat keyword (lowercase, strip).

    Args:
        keyword: Raw keyword

    Returns:
        Normalized keyword
    """
    return keyword.lower().strip()
