import asyncio

from app.agent.pipeline import investigate_cluster
from app.db.session import AsyncSessionLocal


async def main():
    cluster_id = "cc-0055"

    async with AsyncSessionLocal() as session:
        result = await investigate_cluster(
            cluster_id=cluster_id,
            session=session,
        )

    print(f"\n=== {cluster_id} | ML → GEMINI DISAGREEMENT TEST ===")
    print(f"status: {result.status.value}")
    print(f"model: {result.metadata.model}")
    print(f"classification: {result.assessment.classification.value}")
    print(f"severity: {result.assessment.severity.value}")
    print(f"confidence: {result.assessment.confidence}")
    print(f"\nsummary:\n{result.summary}")

    print("\nKEY FINDINGS:")
    for finding in result.key_findings:
        print(f"- {finding.finding}")

    print("\nSUPPORTING EVIDENCE:")
    for item in result.supporting_evidence:
        print(f"- {item}")

    print("\nCONTRADICTING EVIDENCE:")
    for item in result.contradicting_evidence:
        print(f"- {item}")

    print("\nRECOMMENDATIONS:")
    for item in result.investigation_recommendations:
        print(f"- {item}")

    print(f"\nRECOMMENDED ACTION: {result.recommended_action.value}")


if __name__ == "__main__":
    asyncio.run(main())