# TrustGraph

### Graph-Based Payment-Abuse Intelligence for Coordinated Abuse Rings

> **Detect → Investigate → Decide → Act → Audit**

TrustGraph is a defense-only payment risk intelligence system designed to identify **coordinated abuse rings** that may be difficult to detect when transactions are analyzed independently.

Instead of treating every transaction as an isolated event, TrustGraph connects customers, devices, networks, merchants, transaction behavior, timing patterns, returns, and shared infrastructure into an intelligence layer.

The system combines:

- deterministic graph and behavioral risk analysis
- machine-learning secondary validation
- Gemini-powered investigation
- deterministic policy enforcement
- bounded response actions
- Kafka-based event ingestion
- PostgreSQL persistence
- explainable evidence
- evaluation and adversarial validation

The goal is not simply to produce a risk score.

**The goal is to turn connected payment signals into an explainable risk decision.**

---

## Why TrustGraph?

Payment abuse is often coordinated.

A single transaction may appear normal:

- normal amount
- normal merchant
- valid customer
- successful payment

But several apparently legitimate transactions can become suspicious when their relationships are considered together.

Examples include:

- multiple customers sharing the same device
- multiple accounts using the same network infrastructure
- bursts of account creation
- unusually high return activity
- synchronized transaction behavior
- repeated infrastructure reuse
- coordinated activity across connected entities

Traditional transaction-level rules can miss these relationships.

TrustGraph therefore models payment activity as a **relationship graph** and evaluates both:

1. **individual behavioral signals**
2. **relationships between entities**

---

# System Overview

```text
                         PAYMENT EVENTS
                               │
                               ▼
                    ┌────────────────────┐
                    │   Kafka Ingestion  │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ PostgreSQL Storage │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Candidate Generator│
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │   Risk Engine      │
                    │ Graph + Behavioral │
                    └─────────┬──────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
       ┌──────────────────┐      ┌──────────────────┐
       │ ML Secondary     │      │ Explainable Risk │
       │ Validation       │      │ Contributors     │
       └────────┬─────────┘      └────────┬─────────┘
                │                         │
                └────────────┬────────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Gemini AI Investigator│
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Deterministic Policy │
                  │       Engine         │
                  └──────────┬───────────┘
                             │
                    ┌────────┴─────────┐
                    ▼                  ▼
               REVIEW / HOLD       ESCALATE
                    │                  │
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────┐
                    │ Audit Trail     │
                    └─────────────────┘

Core Intelligence Pipeline
1. Event Ingestion

TrustGraph supports payment-event ingestion through Kafka.

The Kafka layer is intentionally separated from the intelligence pipeline.

Its responsibility is to:

consume payment events
validate event structure
persist valid transactions
acknowledge messages only after successful handling

The consumer uses explicit offset control so that an event is committed only after the ingestion handler completes.

Kafka configuration:

Topic: trustgraph.events
Partitions: 3
Replication Factor: 1
Docker bootstrap server: kafka:9092
Host bootstrap server: localhost:9094

Kafka is an ingestion layer — it does not independently calculate risk, invoke Gemini, or make policy decisions.

2. Candidate Generation

TrustGraph first identifies groups of entities that may represent coordinated activity.

The system works with relationships involving:

Customer
   │
   ├── Device
   │
   ├── Network
   │
   ├── Merchant
   │
   └── Transaction

Candidate clusters are then evaluated using graph connectivity and behavioral evidence.

The production candidate-generation configuration was deliberately kept conservative rather than promoting a higher-coverage experiment that produced weaker headline precision.

3. Deterministic Risk Engine

The production risk score combines multiple interpretable contributors.

Examples include:

shared device relationships
shared network relationships
account creation bursts
transaction velocity
coordination signals
return anomalies
graph connectivity
financial exposure

Each risk decision can therefore be decomposed into evidence instead of producing an unexplained black-box score.

Example:

Risk Score: 76.05
Severity: CRITICAL

Contributors:
- Shared device/network: 15
- Account creation burst: 20
- Velocity: 6.36
- Coordination: 1.33
- Return anomaly: 13.36
- Graph connectivity: 20
4. Graph Intelligence

For a suspicious cluster, TrustGraph exposes the underlying graph structure.

Example cluster:

Customer ─────┐
              │
Customer ── Device
              │
Customer ─────┤
              │
           Network

The graph API provides:

nodes
relationships
entity types
cluster structure
connected infrastructure

This allows investigators to understand why entities were grouped together.

5. Machine-Learning Secondary Validation

ML is deliberately positioned as a secondary validation and candidate-prioritization layer, not as the sole production decision-maker.

The model used during validation was:

GradientBoostingClassifier

Evaluation configuration included:

5 random seeds
30 features
395 development rows
423 held-out rows
ML threshold: 0.37
Multi-seed held-out validation
Metric	Mean
Precision	94.36%
Recall	94.88%
F1	94.48%
False Positive Rate	1.84%
ROC-AUC	99.59%
PR-AUC	98.96%

The ML layer also provides a secondary signal for candidate prioritization and cross-checking against deterministic decisions.

6. Gemini AI Investigator

TrustGraph uses Gemini as an investigation layer, not as the final policy authority.

The investigator receives structured risk evidence and produces an investigation result containing information such as:

classification
severity
confidence
reasoning summary
recommendation

Example classification:

Classification:
POTENTIAL_COORDINATED_ABUSE

Severity:
CRITICAL

Confidence:
0.95

Recommendation:
ESCALATE

The AI investigation is deliberately bounded.

Gemini does not directly execute financial actions.

7. Deterministic Policy Engine

The policy engine converts risk evidence and investigation results into a controlled operational decision.

Example:

Risk:
CRITICAL

AI Recommendation:
HOLD_FOR_REVIEW

Policy Decision:
ESCALATE

The policy layer can consider:

risk severity
financial exposure
contradictory evidence
AI recommendation
deterministic safeguards

This prevents an LLM response from becoming an unrestricted operational command.

8. Bounded Response + Auditability

TrustGraph separates:

Detection
    ↓
Investigation
    ↓
Policy
    ↓
Action

Actions are bounded and auditable.

The system records:

investigation ID
decision ID
action ID
risk information
policy outcome
AI recommendation
evidence
timestamps

This creates an end-to-end audit trail from signal → investigation → decision → action.

Evaluation

TrustGraph includes a dedicated Evaluation interface for validating the production operating point and the secondary ML layer.

Production deterministic operating point

The selected production threshold is:

Risk Threshold = 52

At this operating point:

Metric	Cluster-Level
True Positives	6
False Positives	0
True Negatives	59
False Negatives	15
Precision	100%
Recall	28.57%
F1	44.44%
False Positive Rate	0%

Dataset:

Candidate clusters: 80
Detected abuse clusters: 6
Legitimate clusters flagged: 0
Flagged transaction value: ₹332,561.55
Customer-level cross-check
Metric	Customer-Level
True Positives	29
False Positives	0
True Negatives	850
False Negatives	121
Precision	100%
Recall	19.33%
F1	32.40%
False Positive Rate	0%

The production operating point intentionally favors precision and low false-positive impact.

Validation Research

TrustGraph also includes a dedicated research/evidence layer covering:

Threshold sensitivity

Multiple operating thresholds were evaluated to understand the precision/recall trade-off.

Multi-seed validation

The ML model was evaluated across five seeds rather than relying on a single random split.

Candidate-generation coverage

The initial candidate generator represented:

21 / 26 known abuse rings
= 80.8% coverage

A secondary behavioral candidate generator increased coverage to approximately:

92.31%

However, it diluted the headline production operating point, so it was not promoted.

This is an intentional example of choosing a more conservative production configuration instead of optimizing for a single metric.

Detector / ML disagreement analysis

Across the candidate set:

15 / 80

candidate decisions differed between deterministic detection and ML validation.

Role-based validation

The evaluation framework separates:

production deterministic detection
ML secondary validation / prioritization
detector–ML agreement analysis

This prevents different evaluation roles from being mixed together.

Adversarial Validation

TrustGraph was tested against several synthetic adversarial patterns, including:

infrastructure rotation
transaction amount randomization
temporal spreading
low-and-slow activity
high-fanout behavior

Observed findings included:

infrastructure rotation was the strongest identified blind spot
amount randomization remained comparatively robust
temporal spreading produced mixed results
low-and-slow behavior produced mixed results
high-fanout behavior caused modest degradation

These experiments are included as validation evidence rather than being presented as proof of universal robustness.

Sensitivity Analysis

The validation workflow included:

10 thresholds × 10 seeds
+
5 amount tolerances × 10 seeds

The production configuration remained:

Risk threshold: 52
Amount tolerance: 0.5%

No configuration change was promoted solely because it improved one isolated metric.

AI Ablation Study

A Gemini ablation experiment was also conducted to understand how often AI recommendations influenced downstream decisions.

Sample:

30 investigations requested
13 completed
17 rate-limited

Among the 13 completed investigations:

6 / 13
AI recommendations followed

7 / 13
AI recommendations overridden

1 / 13
Policy outcome changed

Mean completed-investigation latency:

28.36 seconds

Because of the limited completed sample and API rate limiting, these results are treated as exploratory evidence, not a generalized estimate of production AI behavior.

Dashboard

The React frontend provides an operational interface for exploring the intelligence pipeline.

Dashboard

Provides:

overall risk statistics
transaction statistics
high-risk cluster visibility
operational summaries
Clusters

Provides:

candidate cluster list
risk scores
severity
financial exposure
cluster details
graph relationships
Evaluation

Provides:

production validation
ML validation
threshold analysis
operating-point metrics
false-positive impact
production decision
Validation Research

Provides:

threshold sweep
multi-seed results
candidate-generation analysis
adversarial experiments
sensitivity analysis
ML disagreement analysis
AI ablation evidence
Technology Stack
Frontend
React 19
Vite
Tailwind CSS
React Flow
Recharts
Lucide React
Backend
Python
FastAPI
SQLAlchemy
Async PostgreSQL
Pydantic
AI / ML
Google Gemini
scikit-learn
Gradient Boosting
deterministic risk scoring
Streaming
Apache Kafka
aiokafka
Infrastructure
Docker
Docker Compose
PostgreSQL
API Surface

Important backend endpoints include:

GET  /health
GET  /health/db
GET  /stats

GET  /risk/clusters
GET  /risk/clusters/{cluster_id}
GET  /risk/evaluation

GET  /intelligence/clusters
GET  /intelligence/clusters/{cluster_id}/graph

POST /agent/investigate/{cluster_id}
POST /agent/respond/{cluster_id}

GET  /audit/{cluster_id}
GET  /policy/decisions/{decision_id}
GET  /actions/{action_id}
Repository Structure
TrustGraph/
│
├── artifacts/
│   └── detector_experiments/
│
├── backend/
│   ├── app/
│   │   ├── kafka/
│   │   ├── ...
│   │
│   └── data/
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/
│   │   └── ...
│   └── ...
│
├── docker-compose.yml
├── docker-compose.test.yml
└── README.md
Running Locally
Prerequisites
Docker Desktop
Node.js
npm
Git
Backend

Start the database and backend services:

docker compose up -d

The API is exposed locally according to the Docker Compose configuration.

Frontend

From the frontend directory:

npm install
npm run dev

The Vite development server runs on the configured local frontend port.

Kafka

The lab/integration Compose configuration provides Kafka for event ingestion.

Kafka uses:

Internal:
kafka:9092

Host:
localhost:9094
Configuration

Secrets and environment-specific configuration should be provided through environment variables.

Typical configuration includes:

DATABASE_URL
GEMINI_API_KEY
KAFKA_BOOTSTRAP_SERVERS
KAFKA_TOPIC

Do not commit real API keys or credentials.

Testing & Verification

The project includes targeted backend tests and validation experiments covering:

risk calculation
candidate generation
graph relationships
policy behavior
API behavior
Kafka ingestion
ML validation
adversarial scenarios
sensitivity analysis
AI investigation behavior

Kafka end-to-end verification was performed by publishing a test event through:

Producer
   ↓
Kafka
   ↓
Consumer
   ↓
FastAPI ingestion handler
   ↓
PostgreSQL

The published event was successfully consumed and persisted, with consumer lag returning to zero.

Design Principles
1. Deterministic systems make the final decisions

AI is used for investigation and reasoning, while deterministic policy controls operational outcomes.

2. Graph relationships are first-class evidence

TrustGraph does not rely only on transaction-level features.

3. Evaluation is part of the product

The system exposes validation evidence instead of hiding model weaknesses.

4. Precision matters

In financial-risk systems, false positives have operational and financial consequences.

5. AI is bounded

Gemini cannot directly perform unrestricted financial operations.

6. Defense-only

TrustGraph is designed exclusively for detecting, investigating, and responding to payment abuse.

Known Limitations

TrustGraph is a buildathon-scale system and is not presented as a production fraud platform.

Known limitations include:

candidate-generation recall remains a bottleneck
infrastructure rotation is a significant blind spot
the production operating point intentionally sacrifices recall for precision
Gemini investigations can be rate-limited
AI ablation results are based on a limited completed sample
Kafka deployment currently uses a single broker configuration
the event store and dataset are designed for controlled evaluation rather than production-scale traffic
additional real-world validation would be required before deployment

These limitations are intentionally documented rather than hidden.

Security & Safety

TrustGraph is strictly defense-oriented.

It is designed to:

detect suspicious payment behavior
identify coordinated abuse
investigate risk evidence
recommend controlled responses
maintain auditability

It does not provide capabilities for:

exploiting payment systems
bypassing fraud controls
stealing credentials
evading detection
attacking financial infrastructure
What Makes TrustGraph Different?

Most lightweight fraud demos stop at:

Transaction → Model → Risk Score

TrustGraph extends the workflow to:

Payment Events
      ↓
Relationship Graph
      ↓
Candidate Detection
      ↓
Deterministic Risk
      ↓
ML Validation
      ↓
AI Investigation
      ↓
Policy Decision
      ↓
Bounded Action
      ↓
Audit Trail

The system therefore treats payment risk as an operational intelligence problem, not merely a classification problem.

Buildathon Alignment

TrustGraph was built for the Razorpay AI Buildathon — AI Risk Manager track.

The project addresses the track's focus on:

payment risk
fraud / abuse detection
measurable precision and recall
false-positive awareness
working detection and response workflows
explainability
defense-only operation

The evaluation methodology intentionally separates:

Production Detection
        +
Secondary ML Validation
        +
AI Investigation
        +
Policy Enforcement

so that each layer has a clearly defined responsibility.

Status

Buildathon submission build

Core detection, intelligence, investigation, policy, ingestion, evaluation, and frontend workflows are implemented.

The repository represents the frozen submission state used for final demonstration and evaluation.

Author

Dharunika B

Built as an independent AI + cybersecurity project for the Razorpay AI Buildathon.

License

No license has been specified for this buildathon repository.
