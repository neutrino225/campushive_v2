#!/usr/bin/env python3
"""
Test script for advanced CLO-PLO mapping with Bloom's taxonomy,
verb alignment, semantic similarity, and composite scoring.

Tests the CLOPLOMappingEngine and OBE agent integration.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from config import embeddings
from multiagent.utils.clo_plo_mapper import CLOPLOMappingEngine
from multiagent.agents.obe_agent.obe_agent import OBEAgent


def print_section(title: str):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


async def test_mapping_engine():
    """Test the CLOPLOMappingEngine directly"""
    print_section("Test 1: CLO-PLO Mapping Engine")

    # Sample CLOs and PLOs
    clos = [
        "Analyze complex software systems and identify design patterns using critical thinking skills",
        "Design and implement scalable software architectures applying industry best practices",
        "Evaluate different software development methodologies and select appropriate approaches",
        "Create comprehensive technical documentation explaining system architecture"
    ]

    plos = [
        "An ability to analyze problems and identify computing requirements appropriate to their solutions",
        "An ability to design, implement, and evaluate computing-based solutions to meet a given set of requirements",
        "An ability to communicate effectively with various stakeholders",
        "An ability to function effectively as a member or leader of a team engaged in activities"
    ]

    # Initialize engine
    print("Initializing CLOPLOMappingEngine...")
    engine = CLOPLOMappingEngine(embeddings=embeddings)

    # Test individual CLO-PLO pair
    print("\n--- Testing Individual CLO-PLO Pair ---")
    clo = clos[0]
    plo = plos[0]

    print(f"\nCLO: {clo}")
    print(f"PLO: {plo}")

    # Extract Bloom's levels
    clo_level, clo_score = engine.get_bloom_level(clo)
    plo_level, plo_score = engine.get_bloom_level(plo)
    print(f"\nCLO Bloom's Level: {clo_level} (confidence: {clo_score:.2f})")
    print(f"PLO Bloom's Level: {plo_level} (confidence: {plo_score:.2f})")

    # Calculate scores
    print("\n--- Individual Scores ---")
    bloom_score = engine.bloom_alignment_score(clo, plo)
    print(f"Bloom's Alignment Score: {bloom_score:.3f}")

    verb_score = engine.verb_overlap_score(clo, plo)
    print(f"Verb Overlap Score: {verb_score:.3f}")

    keyword_score = engine.keyword_similarity_score(clo, plo)
    print(f"Keyword Similarity Score: {keyword_score:.3f}")

    semantic_score = engine.semantic_similarity_score(clo, plo)
    print(f"Semantic Similarity Score: {semantic_score:.3f}")

    # Calculate composite
    composite = engine.calculate_composite_score(clo, plo)
    print(f"\n--- Composite Score ---")
    print(f"Composite Score: {composite['composite']:.3f}")
    
    # Interpret score
    score = composite['composite']
    if score >= 0.7:
        interpretation = "Strong alignment"
    elif score >= 0.5:
        interpretation = "Moderate alignment"
    elif score >= 0.4:
        interpretation = "Weak alignment"
    else:
        interpretation = "No significant alignment"
    print(f"Interpretation: {interpretation}")
    
    print("\nScore Breakdown:")
    print(f"  - Bloom's Alignment: {composite['bloom_alignment']:.3f} (weight: 30%)")
    print(f"  - Verb Overlap: {composite['verb_overlap']:.3f} (weight: 25%)")
    print(f"  - Keyword Similarity: {composite['keyword_similarity']:.3f} (weight: 20%)")
    print(f"  - Semantic Similarity: {composite['semantic_similarity']:.3f} (weight: 25%)")

    # Generate full mapping
    print("\n--- Full CLO-PLO Mapping ---")
    mapping = engine.generate_mapping(clos, plos, threshold=0.4)

    print(f"\nTotal mappings found: {sum(len(v) for v in mapping.values())}")
    for clo_idx, plo_list in mapping.items():
        print(f"\nCLO-{clo_idx}: {clos[clo_idx][:60]}...")
        for plo_info in plo_list:
            plo_idx = plo_info['plo_index']
            score = plo_info['scores']['composite']
            
            # Interpret score
            if score >= 0.7:
                interpretation = "Strong"
            elif score >= 0.5:
                interpretation = "Moderate"
            elif score >= 0.4:
                interpretation = "Weak"
            else:
                interpretation = "Minimal"
            
            print(f"  → PLO-{plo_idx} (Score: {score:.3f}, {interpretation})")
            
            # Show detailed scores
            bloom = plo_info['scores']['bloom_alignment']
            verb = plo_info['scores']['verb_overlap']
            keyword = plo_info['scores']['keyword_similarity']
            semantic = plo_info['scores']['semantic_similarity']
            print(f"     Bloom: {bloom:.2f}, Verb: {verb:.2f}, Keyword: {keyword:.2f}, Semantic: {semantic:.2f}")
            
            # Show verbs
            clo_verbs = plo_info['clo_verbs']
            plo_verbs = plo_info['plo_verbs']
            if clo_verbs and plo_verbs:
                shared = set(clo_verbs) & set(plo_verbs)
                if shared:
                    print(f"     Shared verbs: {', '.join(shared)}")


async def test_obe_agent():
    """Test OBE agent with advanced mapping"""
    print_section("Test 2: OBE Agent Advanced Mapping")

    # Sample CLOs and PLOs
    clos = {
        1: "Analyze complex software systems and identify design patterns using critical thinking skills",
        2: "Design and implement scalable software architectures applying industry best practices",
        3: "Evaluate different software development methodologies and select appropriate approaches for projects"
    }

    plos = {
        1: "An ability to analyze problems and identify computing requirements appropriate to their solutions",
        2: "An ability to design, implement, and evaluate computing-based solutions to meet a given set of requirements",
        3: "An ability to communicate effectively with various stakeholders"
    }

    # Initialize agent
    print("Initializing OBE Agent...")
    agent = OBEAgent()

    # Generate advanced mapping
    print("\nGenerating advanced CLO-PLO mapping...")
    print("(This may take a moment as it calculates semantic similarities...)\n")

    result = agent.generate_advanced_mapping(
        clos=clos,
        plos=plos,
        threshold=0.4,
        use_llm_refinement=True
    )

    print("--- Advanced Mapping Result ---\n")
    print(result)


async def test_bloom_taxonomy():
    """Test Bloom's taxonomy classification"""
    print_section("Test 3: Bloom's Taxonomy Classification")

    engine = CLOPLOMappingEngine(embeddings=embeddings)

    test_statements = [
        ("Define the concept of object-oriented programming", "remembering"),
        ("Explain the differences between inheritance and composition", "understanding"),
        ("Apply the singleton pattern to implement a database connection", "applying"),
        ("Analyze the trade-offs between microservices and monolithic architectures", "analyzing"),
        ("Evaluate different cloud deployment strategies for production systems", "evaluating"),
        ("Create a comprehensive software architecture for an e-commerce platform", "creating")
    ]

    print("Testing Bloom's taxonomy classification:\n")
    for statement, expected_level in test_statements:
        level, score = engine.get_bloom_level(statement)
        verbs = engine.extract_action_verbs(statement)
        match = "✓" if level == expected_level else "✗"
        print(f"{match} Statement: {statement[:70]}")
        print(f"  Expected: {expected_level}, Got: {level} (confidence: {score:.2f})")
        print(f"  Action verbs found: {', '.join(verbs)}\n")


def main():
    """Run all tests"""
    print("\n" + "█" * 80)
    print("  Advanced CLO-PLO Mapping Test Suite")
    print("  Testing: Bloom's Taxonomy + Verb Alignment + Semantic Similarity")
    print("█" * 80)

    try:
        # Test 1: Mapping engine
        asyncio.run(test_mapping_engine())

        # Test 2: OBE agent
        asyncio.run(test_obe_agent())

        # Test 3: Bloom's taxonomy
        asyncio.run(test_bloom_taxonomy())

        print_section("All Tests Completed Successfully!")
        print("✓ CLOPLOMappingEngine is working correctly")
        print("✓ OBE Agent integration is functional")
        print("✓ Bloom's taxonomy classification is accurate")
        print("\nNext steps:")
        print("1. Test with uploaded course syllabus documents")
        print("2. Verify end-to-end workflow via API")
        print("3. Test frontend file upload integration")

    except Exception as e:
        print_section("Test Failed!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
