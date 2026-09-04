# TrustGraph

## Graph-Based Payment-Abuse Intelligence

> **Detect → Investigate → Decide → Act → Audit**

TrustGraph is a defense-only payment risk intelligence system designed to identify **coordinated payment-abuse rings** that may be difficult to detect when transactions are analyzed independently.

Instead of treating every transaction as an isolated event, TrustGraph connects customers, devices, networks, merchants, transaction behavior, timing patterns, returns, and shared infrastructure into an intelligence layer.

The system combines:

- Deterministic graph and behavioral risk analysis
- Machine-learning secondary validation
- Gemini-powered investigation
- Deterministic policy enforcement
- Bounded response actions
- Kafka-based event ingestion
- PostgreSQL persistence
- Explainable risk evidence
- Evaluation and adversarial validation
- End-to-end auditability

---

## Why TrustGraph?

Payment abuse is often coordinated.

A single transaction may appear normal:

- Normal amount
- Normal merchant
- Valid customer
- Successful payment

However, multiple apparently legitimate transactions can become suspicious when their relationships are considered together.

TrustGraph looks for signals such as:

- Multiple customers sharing the same device
- Multiple accounts using the same network infrastructure
- Bursts of account creation
- Unusually high return activity
- Synchronized transaction behavior
- Repeated infrastructure reuse
- Coordinated activity across connected entities

Traditional transaction-level rules can miss these relationships.

TrustGraph therefore evaluates both:

1. **Individual behavioral signals**
2. **Relationships between entities**

---

## System Architecture

```text
                    PAYMENT EVENTS
                          |
                          v
                 +------------------+
                 | Kafka Ingestion  |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 |   PostgreSQL     |
                 |     Storage      |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | Candidate        |
                 | Generation       |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | Deterministic    |
                 | Risk Engine      |
                 +--------+---------+
                          |
              +-----------+-----------+
              |                       |
              v                       v
      +---------------+       +---------------+
      | ML Secondary  |       | Explainable   |
      | Validation    |       | Risk Evidence |
      +-------+-------+       +-------+-------+
              |                       |
              +-----------+-----------+
                          |
                          v
                 +------------------+
                 | Gemini AI        |
                 | Investigator     |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | Deterministic    |
                 | Policy Engine    |
                 +--------+---------+
                          |
                 +--------+--------+
                 |                 |
                 v                 v
             REVIEW            ESCALATE
                 |                 |
                 +--------+--------+
                          |
                          v
                 +------------------+
                 | Audit Trail      |
                 +------------------+
Intelligence Pipeline
1. Event Ingestion

TrustGraph supports payment-event ingestion through Kafka.

The Kafka layer is intentionally separated from the intelligence pipeline.

Its responsibilities are:

Consume payment events
Validate event structure
Persist valid transactions
Acknowledge messages only after successful handling

The consumer uses explicit offset control so that events are committed only after successful processing.

Kafka configuration

Configuration	Value
Topic	trustgraph.events
Partitions	3
Replication Factor	1
Docker Bootstrap	kafka:9092
Host Bootstrap	localhost:9094

Kafka is an ingestion layer. It does not independently calculate risk, invoke Gemini, or make policy decisions.

2. Candidate Generation

TrustGraph identifies groups of entities that may represent coordinated activity.

The relationship model includes:

Customer
   |
   +--- Device
   |
   +--- Network
   |
   +--- Merchant
   |
   +--- Transaction

Candidate clusters are evaluated using graph connectivity and behavioral evidence.

The production candidate generator was deliberately kept conservative rather than promoting a higher-coverage experiment that produced a weaker production operating point.

3. Deterministic Risk Engine

The production risk score combines multiple interpretable contributors.

Examples include:

Shared device relationships
Shared network relationships
Account creation bursts
Transaction velocity
Coordination signals
Return anomalies
Graph connectivity
Financial exposure

Each risk decision can therefore be decomposed into evidence instead of producing an unexplained black-box score.

Example

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

Example:

Customer ----+
             |
Customer ----+---- Device
             |
Customer ----+
             |
           Network

The graph layer provides:

Nodes
Relationships
Entity types
Cluster structure
Connected infrastructure

This allows investigators to understand why entities were grouped together.

5. Machine-Learning Secondary Validation

ML is deliberately positioned as a secondary validation and candidate-prioritization layer, not as the sole production decision-maker.

The validation model used was:

GradientBoostingClassifier

Evaluation configuration:

5 random seeds
30 features
395 development rows
423 held-out rows
ML threshold: 0.37
Multi-Seed Held-Out Validation
Metric	Mean
Precision	94.36%
Recall	94.88%
F1	94.48%
False Positive Rate	1.84%
ROC-AUC	99.59%
PR-AUC	98.96%

The ML layer provides a secondary signal for candidate prioritization and cross-checking against deterministic decisions.

6. Gemini AI Investigator

TrustGraph uses Gemini as an investigation layer, not as the final policy authority.

The investigator receives structured risk evidence and produces:

Classification
Severity
Confidence
Investigation summary
Recommendation

Example:

Classification:
POTENTIAL_COORDINATED_ABUSE

Severity:
CRITICAL

Confidence:
0.95

Recommendation:
ESCALATE

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

Risk severity
Financial exposure
Contradictory evidence
AI recommendation
Deterministic safeguards

This prevents an LLM response from becoming an unrestricted operational command.

8. Bounded Response and Auditability

TrustGraph separates:

Detection
    |
    v
Investigation
    |
    v
Policy
    |
    v
Action

Actions are bounded and auditable.

The system records:

Investigation ID
Decision ID
Action ID
Risk information
Policy outcome
AI recommendation
Evidence
Timestamps

This creates an end-to-end audit trail from signal → investigation → decision → action.

Evaluation

TrustGraph includes a dedicated Evaluation interface for validating the production operating point and the secondary ML layer.

Production Deterministic Operating Point

The selected production threshold is:

Risk Threshold = 52

Cluster-Level Validation
Metric	Result
True Positives	6
False Positives	0
True Negatives	59
False Negatives	15
Precision	100%
Recall	28.57%
F1	44.44%
False Positive Rate	0%
Evaluation Dataset
Measure	Result
Candidate Clusters	80
Detected Abuse Clusters	6
Legitimate Clusters Flagged	0
Flagged Transaction Value	₹332,561.55
Customer-Level Cross-Check
Metric	Result
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

TrustGraph includes a dedicated research and evidence layer.

Threshold Sensitivity

Multiple operating thresholds were evaluated to understand the precision/recall trade-off.

Multi-Seed Validation

The ML model was evaluated across five seeds rather than relying on a single random split.

Candidate-Generation Coverage

The initial candidate generator represented:

21 / 26 known abuse rings = 80.8% coverage

A secondary behavioral candidate generator increased coverage to approximately:

92.31%

However, it diluted the production operating point and was therefore not promoted.

This demonstrates that TrustGraph does not optimize for a single metric in isolation.

Detector / ML Disagreement

Across the candidate set:

15 / 80 candidate decisions differed

between deterministic detection and ML validation.

Adversarial Validation

TrustGraph was evaluated against several synthetic adversarial patterns:

Infrastructure rotation
Transaction amount randomization
Temporal spreading
Low-and-slow activity
High-fanout behavior

Key observations:

Infrastructure rotation was the strongest identified blind spot.
Amount randomization remained comparatively robust.
Temporal spreading produced mixed results.
Low-and-slow behavior produced mixed results.
High-fanout behavior caused modest degradation.

These experiments are presented as validation evidence, not as proof of universal robustness.

Sensitivity Analysis

The validation workflow included:

10 thresholds × 10 seeds
+
5 amount tolerances × 10 seeds

Production configuration:

Risk threshold: 52
Amount tolerance: 0.5%

No configuration change was promoted solely because it improved one isolated metric.

AI Ablation Study

An AI ablation experiment was conducted to understand how often Gemini recommendations influenced downstream decisions.

Sample
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

Overall risk statistics
Transaction statistics
High-risk cluster visibility
Operational summaries
Clusters

Provides:

Candidate cluster list
Risk scores
Severity
Financial exposure
Cluster details
Graph relationships
Evaluation

Provides:

Production validation
ML validation
Threshold analysis
Operating-point metrics
False-positive impact
Production decision
Validation Research

Provides:

Threshold sweeps
Multi-seed results
Candidate-generation analysis
Adversarial experiments
Sensitivity analysis
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
Deterministic risk scoring
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
|
+-- artifacts/
|   +-- detector_experiments/
|
+-- backend/
|   +-- app/
|   |   +-- kafka/
|   |   +-- ...
|   |
|   +-- data/
|
+-- frontend/
|   +-- src/
|       +-- pages/
|       +-- components/
|       +-- api/
|       +-- ...
|
+-- docker-compose.yml
+-- docker-compose.test.yml
+-- README.md
Running Locally
Prerequisites
Docker Desktop
Node.js
npm
Git
Backend

Start the database and backend services:

docker compose up -d
Frontend

From the frontend directory:

npm install
npm run dev
Kafka

The integration Compose configuration provides Kafka for event ingestion.

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

Never commit real API keys or credentials.

Testing and Verification

The project includes targeted backend tests and validation experiments covering:

Risk calculation
Candidate generation
Graph relationships
Policy behavior
API behavior
Kafka ingestion
ML validation
Adversarial scenarios
Sensitivity analysis
AI investigation behavior

Kafka end-to-end verification:

Producer
   |
   v
Kafka
   |
   v
Consumer
   |
   v
FastAPI Ingestion Handler
   |
   v
PostgreSQL

A test event was successfully consumed and persisted, with consumer lag returning to zero.

Design Principles
1. Deterministic systems make final decisions

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

Candidate-generation recall remains a bottleneck.
Infrastructure rotation is a significant blind spot.
The production operating point intentionally sacrifices recall for precision.
Gemini investigations can be rate-limited.
AI ablation results are based on a limited completed sample.
Kafka deployment currently uses a single-broker configuration.
The dataset is designed for controlled evaluation rather than production-scale traffic.
Additional real-world validation would be required before deployment.

These limitations are intentionally documented rather than hidden.

Security and Safety

TrustGraph is strictly defense-oriented.

It is designed to:

Detect suspicious payment behavior
Identify coordinated abuse
Investigate risk evidence
Recommend controlled responses
Maintain auditability

It does not provide capabilities for:

Exploiting payment systems
Bypassing fraud controls
Stealing credentials
Evading detection
Attacking financial infrastructure
What Makes TrustGraph Different?

A basic fraud demo often looks like:

Transaction
     |
     v
   Model
     |
     v
Risk Score

TrustGraph extends the workflow:

Payment Events
      |
      v
Relationship Graph
      |
      v
Candidate Detection
      |
      v
Deterministic Risk
      |
      v
ML Validation
      |
      v
AI Investigation
      |
      v
Policy Decision
      |
      v
Bounded Action
      |
      v
Audit Trail

TrustGraph therefore treats payment risk as an operational intelligence problem, not merely a classification problem.

Buildathon Alignment

TrustGraph was built for the Razorpay AI Buildathon — AI Risk Manager track.

The project addresses:

Payment risk
Fraud and abuse detection
Measurable precision and recall
False-positive awareness
Working detection and response workflows
Explainability
Defense-only operation

The evaluation methodology separates:

Production Detection
        +
Secondary ML Validation
        +
AI Investigation
        +
Policy Enforcement

Each layer has a clearly defined responsibility.

Project Status

Buildathon Submission Build

Core detection, intelligence, investigation, policy, ingestion, evaluation, and frontend workflows are implemented.

This repository represents the frozen submission state prepared for final demonstration and evaluation.

Author

Dharunika B

Built as an independent AI + cybersecurity project for the Razorpay AI Buildathon.
