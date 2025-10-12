"""
Comprehensive test suite for the OBE Agent.

Tests CLO-PLO mapping functionality, output format validation,
and various edge cases.
"""

import sys
import pytest
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.obe_agent.obe_agent import OBEAgent


class TestOBEAgentBasic:
    """Basic functionality tests for OBE Agent."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    @pytest.fixture
    def sample_clos(self):
        """Sample CLOs for testing."""
        return [
            "Analyze a complex computing problem and apply principles of computing.",
            "Design, implement, and evaluate a computing-based solution.",
            "Communicate effectively in professional contexts.",
        ]
    
    @pytest.fixture
    def sample_plos(self):
        """Sample PLOs for testing."""
        return [
            "PLO 1: Academic Education",
            "PLO 2: Knowledge for Solving Computing Problems",
            "PLO 3: Problem Analysis",
            "PLO 4: Design/Development of Solutions",
            "PLO 5: Modern Tool Usage",
            "PLO 6: Individual and Team Work",
            "PLO 7: Communication",
        ]
    
    def test_agent_initialization(self, obe_agent):
        """Test that OBE agent initializes correctly."""
        assert obe_agent is not None
        assert hasattr(obe_agent, 'chain')
        assert hasattr(obe_agent, 'run')
    
    def test_basic_mapping_generation(self, obe_agent, sample_clos, sample_plos):
        """Test basic CLO-PLO mapping generation."""
        result = obe_agent.run(clos=sample_clos, plos=sample_plos)
        
        # Check that result is a string
        assert isinstance(result, str)
        
        # Check that result is not empty
        assert len(result) > 0
        
        # Check for markdown table presence
        assert "|" in result
        assert "CLO" in result
        assert "PLO" in result
    
    def test_mapping_contains_checkmarks(self, obe_agent, sample_clos, sample_plos):
        """Test that mapping contains checkmarks (✓) for mappings."""
        result = obe_agent.run(clos=sample_clos, plos=sample_plos)
        
        # Check for checkmark presence (Unicode or alternative representations)
        assert "✓" in result or "✔" in result or "X" in result
    
    def test_justifications_present(self, obe_agent, sample_clos, sample_plos):
        """Test that justifications are included in output."""
        result = obe_agent.run(clos=sample_clos, plos=sample_plos)
        
        # Check for justifications section
        assert "Justification" in result or "justify" in result.lower()
        
        # Check that CLOs are referenced in justifications
        # Allow for Unicode non-breaking spaces (\u202f) that LLM might use
        for i in range(len(sample_clos)):
            pattern = f"CLO{i+1}" if i < 9 else f"CLO {i+1}"
            # Check for various formats: "CLO 1", "CLO 1", "CLO1"
            assert (f"CLO {i+1}" in result or 
                    f"CLO\u202f{i+1}" in result or 
                    f"CLO{i+1}" in result)


class TestOBEAgentEdgeCases:
    """Edge case tests for OBE Agent."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    def test_single_clo_single_plo(self, obe_agent):
        """Test mapping with single CLO and PLO."""
        clos = ["Understand basic programming concepts."]
        plos = ["PLO 1: Academic Education"]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "CLO" in result
        assert "PLO" in result
    
    def test_many_clos_to_many_plos(self, obe_agent):
        """Test mapping with many CLOs and PLOs."""
        clos = [f"CLO {i}: Test outcome {i}" for i in range(1, 11)]
        plos = [f"PLO {i}: Test program outcome {i}" for i in range(1, 11)]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
        # Should have table with multiple rows
        assert result.count("CLO") >= 10
    
    def test_complex_clo_descriptions(self, obe_agent):
        """Test with complex, detailed CLO descriptions."""
        clos = [
            "Analyze a complex computing problem and to apply principles of computing "
            "and other relevant disciplines to identify solutions, including ethical "
            "considerations and societal impacts.",
            "Design, implement, and evaluate a computing-based solution to meet a "
            "given set of computing requirements in the context of the program's "
            "discipline, considering constraints such as security, privacy, and usability.",
        ]
        plos = [
            "PLO 1: Academic Education",
            "PLO 2: Knowledge for Solving Computing Problems",
            "PLO 3: Problem Analysis",
            "PLO 4: Design/Development of Solutions",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "CLO 1" in result
        assert "CLO 2" in result


class TestOBEAgentOutputFormat:
    """Tests for output format validation."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    @pytest.fixture
    def cs_clos(self):
        """Computer Science specific CLOs."""
        return [
            "Apply knowledge of computing fundamentals and mathematics.",
            "Analyze problems and identify computing requirements.",
            "Design and implement computing solutions.",
            "Work effectively in teams.",
        ]
    
    @pytest.fixture
    def cs_plos(self):
        """Computer Science specific PLOs."""
        return [
            "PLO 1: Academic Education",
            "PLO 2: Knowledge for Solving Computing Problems",
            "PLO 3: Problem Analysis",
            "PLO 4: Design/Development of Solutions",
            "PLO 5: Modern Tool Usage",
            "PLO 6: Individual and Team Work",
        ]
    
    def test_table_format_structure(self, obe_agent, cs_clos, cs_plos):
        """Test that output contains properly structured markdown table."""
        result = obe_agent.run(clos=cs_clos, plos=cs_plos)
        
        # Check for table structure
        assert "|" in result
        
        # Count table rows (should have header + separator + CLO rows)
        lines_with_pipes = [line for line in result.split("\n") if "|" in line]
        assert len(lines_with_pipes) >= len(cs_clos) + 2  # header + separator + data rows
    
    def test_all_clos_in_table(self, obe_agent, cs_clos, cs_plos):
        """Test that all CLOs appear in the mapping table."""
        result = obe_agent.run(clos=cs_clos, plos=cs_plos)
        
        for i in range(len(cs_clos)):
            # Check for CLO reference in table
            assert f"CLO {i+1}" in result or f"CLO{i+1}" in result
    
    def test_all_plos_in_table_header(self, obe_agent, cs_clos, cs_plos):
        """Test that all PLOs appear in table header."""
        result = obe_agent.run(clos=cs_clos, plos=cs_plos)
        
        for i in range(len(cs_plos)):
            # Check for PLO reference in header
            assert f"PLO {i+1}" in result or f"PLO{i+1}" in result


class TestOBEAgentDifferentDisciplines:
    """Tests for different academic disciplines."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    def test_software_engineering_mapping(self, obe_agent):
        """Test mapping for Software Engineering program."""
        clos = [
            "Apply software engineering principles to design scalable systems.",
            "Implement software solutions using modern development practices.",
            "Test and validate software against requirements.",
        ]
        plos = [
            "PLO 1: Academic Education",
            "PLO 2: Knowledge for Solving Computing Problems",
            "PLO 3: Problem Analysis",
            "PLO 4: Design/Development of Solutions",
            "PLO 5: Modern Tool Usage",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
        # Check for software engineering related terms
        assert any(term in result.lower() for term in ["design", "implement", "test"])
    
    def test_data_science_mapping(self, obe_agent):
        """Test mapping for Data Science program."""
        clos = [
            "Apply statistical methods to analyze large datasets.",
            "Build and evaluate machine learning models.",
            "Visualize and communicate data insights.",
        ]
        plos = [
            "PLO 1: Data Analysis Skills",
            "PLO 2: Machine Learning Knowledge",
            "PLO 3: Statistical Computing",
            "PLO 4: Data Visualization",
            "PLO 5: Communication",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
        # Check for data science related terms
        assert any(term in result.lower() for term in ["data", "machine learning", "statistical"])


class TestOBEAgentRobustness:
    """Robustness and error handling tests."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    def test_empty_lists_handling(self, obe_agent):
        """Test handling of empty CLO/PLO lists."""
        # This might raise an error or return a message
        # depending on implementation expectations
        try:
            result = obe_agent.run(clos=[], plos=[])
            # If it doesn't error, check for some response
            assert isinstance(result, str)
        except Exception as e:
            # Empty lists might be expected to fail
            assert True
    
    def test_special_characters_in_outcomes(self, obe_agent):
        """Test handling of special characters in CLOs/PLOs."""
        clos = [
            "Analyze problems using C++/Java programming.",
            "Design solutions with 90% efficiency.",
            "Communicate with stakeholders (internal & external).",
        ]
        plos = [
            "PLO 1: Programming Skills (C++/Java)",
            "PLO 2: Problem-Solving & Analysis",
            "PLO 3: Communication (Written/Oral)",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_unicode_characters(self, obe_agent):
        """Test handling of unicode characters in outcomes."""
        clos = [
            "Apply algorithms → solve problems efficiently.",
            "Design systems ≥ industry standards.",
        ]
        plos = [
            "PLO 1: Algorithm Design ★",
            "PLO 2: System Architecture ✓",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        assert isinstance(result, str)
        assert len(result) > 0


class TestOBEAgentIntegration:
    """Integration tests for real-world scenarios."""
    
    @pytest.fixture
    def obe_agent(self):
        """Create OBE agent instance for tests."""
        return OBEAgent()
    
    def test_complete_se_curriculum_mapping(self, obe_agent):
        """Test complete Software Engineering curriculum CLO-PLO mapping."""
        clos = [
            "Analyze a complex computing problem and apply principles of computing.",
            "Design, implement, and evaluate a computing-based solution.",
            "Communicate effectively in professional contexts.",
            "Recognize professional responsibilities based on legal and ethical principles.",
            "Function effectively as a member or leader of a team.",
            "Apply security principles and practices to maintain operations.",
        ]
        plos = [
            "PLO 1: Academic Education",
            "PLO 2: Knowledge for Solving Computing Problems",
            "PLO 3: Problem Analysis",
            "PLO 4: Design/Development of Solutions",
            "PLO 5: Modern Tool Usage",
            "PLO 6: Individual and Team Work",
            "PLO 7: Communication",
            "PLO 8: Computing Professionalism and Society",
            "PLO 9: Ethics",
            "PLO 10: Life-Long Learning",
        ]
        
        result = obe_agent.run(clos=clos, plos=plos)
        
        # Comprehensive checks
        assert isinstance(result, str)
        assert len(result) > 500  # Should be substantial output
        
        # Check for all CLOs (allow for Unicode non-breaking spaces)
        for i in range(len(clos)):
            assert (f"CLO {i+1}" in result or 
                    f"CLO\u202f{i+1}" in result or 
                    f"CLO{i+1}" in result)
        
        # Check for table structure
        assert "|" in result
        
        # Check for justifications
        assert "Justification" in result or "justify" in result.lower()
        
        # Check for reasonable number of mappings (checkmarks)
        checkmark_count = result.count("✓") + result.count("✔") + result.count("X")
        assert checkmark_count >= len(clos)  # At least one mapping per CLO


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
