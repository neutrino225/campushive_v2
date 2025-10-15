"""
CLO-PLO Mapping Engine

Advanced mapping using multiple strategies:
1. Bloom's Taxonomy alignment
2. Action verb matching
3. Semantic similarity
4. LLM-based reasoning
5. Composite scoring
"""

import re
from typing import List, Dict, Tuple
from collections import defaultdict
import numpy as np


# Bloom's Taxonomy Levels (Revised)
BLOOMS_TAXONOMY = {
    # Remembering (Lowest)
    "remembering": ["define", "list", "recall", "recognize", "identify", "name", "state", "describe", "retrieve"],
    
    # Understanding
    "understanding": ["explain", "interpret", "summarize", "classify", "compare", "discuss", "paraphrase", "illustrate", "translate"],
    
    # Applying
    "applying": ["apply", "implement", "use", "execute", "solve", "demonstrate", "operate", "employ", "practice"],
    
    # Analyzing
    "analyzing": ["analyze", "examine", "investigate", "categorize", "differentiate", "distinguish", "compare", "contrast", "test"],
    
    # Evaluating
    "evaluating": ["evaluate", "assess", "judge", "critique", "justify", "argue", "defend", "support", "validate"],
    
    # Creating (Highest)
    "creating": ["create", "design", "develop", "construct", "plan", "produce", "formulate", "generate", "compose"]
}

# Reverse mapping: verb -> level
VERB_TO_BLOOM = {}
for level, verbs in BLOOMS_TAXONOMY.items():
    for verb in verbs:
        VERB_TO_BLOOM[verb.lower()] = level

# Bloom's level hierarchy (for scoring)
BLOOM_HIERARCHY = {
    "remembering": 1,
    "understanding": 2,
    "applying": 3,
    "analyzing": 4,
    "evaluating": 5,
    "creating": 6
}


class CLOPLOMappingEngine:
    """Advanced CLO-PLO mapping engine with multiple strategies"""
    
    def __init__(self, embeddings=None):
        """
        Initialize the mapping engine.
        
        Args:
            embeddings: Optional embedding model for semantic similarity
        """
        self.embeddings = embeddings
    
    def extract_action_verbs(self, text: str) -> List[str]:
        """Extract action verbs from outcome text"""
        # Convert to lowercase
        text_lower = text.lower()
        
        # Find all verbs from Bloom's taxonomy
        found_verbs = []
        for verb in VERB_TO_BLOOM.keys():
            # Use word boundaries to match whole words
            pattern = r'\b' + re.escape(verb) + r'\b'
            if re.search(pattern, text_lower):
                found_verbs.append(verb)
        
        return found_verbs
    
    def get_bloom_level(self, text: str) -> Tuple[str, int]:
        """
        Determine the Bloom's taxonomy level of an outcome.
        
        Returns:
            Tuple of (level_name, level_score)
        """
        verbs = self.extract_action_verbs(text)
        
        if not verbs:
            return ("understanding", 2)  # Default to understanding
        
        # Get the highest Bloom's level from all verbs
        max_level = "remembering"
        max_score = 1
        
        for verb in verbs:
            level = VERB_TO_BLOOM.get(verb, "understanding")
            score = BLOOM_HIERARCHY.get(level, 2)
            if score > max_score:
                max_score = score
                max_level = level
        
        return (max_level, max_score)
    
    def bloom_alignment_score(self, clo: str, plo: str) -> float:
        """
        Calculate alignment score based on Bloom's taxonomy levels.
        
        CLOs should align with PLOs at similar or lower cognitive levels.
        
        Returns:
            Score between 0 and 1
        """
        clo_level, clo_score = self.get_bloom_level(clo)
        plo_level, plo_score = self.get_bloom_level(plo)
        
        # Perfect match
        if clo_score == plo_score:
            return 1.0
        
        # CLO at lower level than PLO (acceptable)
        if clo_score < plo_score:
            diff = plo_score - clo_score
            # Closer levels get higher scores
            return max(0.5, 1.0 - (diff * 0.15))
        
        # CLO at higher level than PLO (less ideal but possible)
        else:
            diff = clo_score - plo_score
            return max(0.3, 1.0 - (diff * 0.25))
    
    def verb_overlap_score(self, clo: str, plo: str) -> float:
        """
        Calculate score based on shared action verbs.
        
        Returns:
            Score between 0 and 1
        """
        clo_verbs = set(self.extract_action_verbs(clo))
        plo_verbs = set(self.extract_action_verbs(plo))
        
        if not clo_verbs or not plo_verbs:
            return 0.0
        
        # Jaccard similarity
        intersection = len(clo_verbs & plo_verbs)
        union = len(clo_verbs | plo_verbs)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def keyword_similarity_score(self, clo: str, plo: str) -> float:
        """
        Calculate score based on keyword overlap (excluding common words).
        
        Returns:
            Score between 0 and 1
        """
        # Common words to exclude
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "are", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "should",
            "could", "can", "may", "might", "must", "student", "students", "ability",
            "able", "course", "program", "learning", "outcome", "outcomes"
        }
        
        # Extract words
        clo_words = set(re.findall(r'\b\w+\b', clo.lower())) - stopwords
        plo_words = set(re.findall(r'\b\w+\b', plo.lower())) - stopwords
        
        # Remove verbs (already handled separately)
        clo_words -= set(VERB_TO_BLOOM.keys())
        plo_words -= set(VERB_TO_BLOOM.keys())
        
        if not clo_words or not plo_words:
            return 0.0
        
        # Jaccard similarity
        intersection = len(clo_words & plo_words)
        union = len(clo_words | plo_words)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def semantic_similarity_score(self, clo: str, plo: str) -> float:
        """
        Calculate semantic similarity using embeddings.
        
        Returns:
            Score between 0 and 1
        """
        if self.embeddings is None:
            return 0.0
        
        try:
            # Get embeddings
            clo_embedding = self.embeddings.embed_query(clo)
            plo_embedding = self.embeddings.embed_query(plo)
            
            # Cosine similarity
            clo_vec = np.array(clo_embedding)
            plo_vec = np.array(plo_embedding)
            
            dot_product = np.dot(clo_vec, plo_vec)
            norm_product = np.linalg.norm(clo_vec) * np.linalg.norm(plo_vec)
            
            if norm_product == 0:
                return 0.0
            
            similarity = dot_product / norm_product
            
            # Normalize to 0-1 range (cosine similarity is -1 to 1)
            return (similarity + 1) / 2
        
        except Exception as e:
            print(f"Semantic similarity error: {e}")
            return 0.0
    
    def calculate_composite_score(
        self,
        clo: str,
        plo: str,
        weights: Dict[str, float] = None
    ) -> Dict[str, float]:
        """
        Calculate composite mapping score using multiple strategies.
        
        Args:
            clo: Course Learning Outcome text
            plo: Program Learning Outcome text
            weights: Optional custom weights for each strategy
        
        Returns:
            Dictionary with individual scores and composite score
        """
        # Default weights (can be tuned)
        if weights is None:
            weights = {
                "bloom_alignment": 0.30,  # Most important
                "verb_overlap": 0.25,
                "keyword_similarity": 0.20,
                "semantic_similarity": 0.25
            }
        
        # Calculate individual scores
        bloom_score = self.bloom_alignment_score(clo, plo)
        verb_score = self.verb_overlap_score(clo, plo)
        keyword_score = self.keyword_similarity_score(clo, plo)
        semantic_score = self.semantic_similarity_score(clo, plo)
        
        # Calculate weighted composite score
        composite = (
            bloom_score * weights["bloom_alignment"] +
            verb_score * weights["verb_overlap"] +
            keyword_score * weights["keyword_similarity"] +
            semantic_score * weights["semantic_similarity"]
        )
        
        return {
            "bloom_alignment": bloom_score,
            "verb_overlap": verb_score,
            "keyword_similarity": keyword_score,
            "semantic_similarity": semantic_score,
            "composite": composite
        }
    
    def generate_mapping(
        self,
        clos: List[str],
        plos: List[str],
        threshold: float = 0.4
    ) -> Dict[int, List[Dict]]:
        """
        Generate CLO-PLO mapping with scores and justifications.
        
        Args:
            clos: List of CLO texts
            plos: List of PLO texts
            threshold: Minimum composite score for mapping (default 0.4)
        
        Returns:
            Dictionary mapping CLO index to list of mapped PLOs with scores
        """
        mapping = defaultdict(list)
        
        for clo_idx, clo in enumerate(clos):
            for plo_idx, plo in enumerate(plos):
                scores = self.calculate_composite_score(clo, plo)
                
                # Only include mappings above threshold
                if scores["composite"] >= threshold:
                    mapping[clo_idx].append({
                        "plo_index": plo_idx,
                        "scores": scores,
                        "clo_bloom": self.get_bloom_level(clo),
                        "plo_bloom": self.get_bloom_level(plo),
                        "clo_verbs": self.extract_action_verbs(clo),
                        "plo_verbs": self.extract_action_verbs(plo)
                    })
            
            # Sort by composite score (descending)
            mapping[clo_idx].sort(key=lambda x: x["scores"]["composite"], reverse=True)
        
        return dict(mapping)
    
    def generate_justification(
        self,
        clo: str,
        plo: str,
        mapping_info: Dict
    ) -> str:
        """
        Generate human-readable justification for a CLO-PLO mapping.
        
        Args:
            clo: CLO text
            plo: PLO text
            mapping_info: Mapping information from generate_mapping
        
        Returns:
            Justification text
        """
        scores = mapping_info["scores"]
        clo_bloom = mapping_info["clo_bloom"]
        plo_bloom = mapping_info["plo_bloom"]
        clo_verbs = mapping_info["clo_verbs"]
        plo_verbs = mapping_info["plo_verbs"]
        
        justification_parts = []
        
        # Bloom's taxonomy alignment
        if scores["bloom_alignment"] > 0.7:
            justification_parts.append(
                f"**Bloom's Alignment ({scores['bloom_alignment']:.2f})**: "
                f"CLO operates at '{clo_bloom[0]}' level (cognitive level {clo_bloom[1]}), "
                f"which aligns well with PLO's '{plo_bloom[0]}' level (level {plo_bloom[1]}). "
                f"This indicates appropriate cognitive complexity matching."
            )
        
        # Verb overlap
        shared_verbs = set(clo_verbs) & set(plo_verbs)
        if shared_verbs and scores["verb_overlap"] > 0.3:
            justification_parts.append(
                f"**Action Verb Match ({scores['verb_overlap']:.2f})**: "
                f"Both outcomes emphasize similar actions: {', '.join(shared_verbs)}. "
                f"This indicates aligned skill development."
            )
        
        # Semantic similarity
        if scores["semantic_similarity"] > 0.6:
            justification_parts.append(
                f"**Semantic Similarity ({scores['semantic_similarity']:.2f})**: "
                f"The outcomes share strong thematic and contextual overlap, "
                f"indicating alignment in subject matter and learning goals."
            )
        
        # Keyword similarity
        if scores["keyword_similarity"] > 0.3:
            justification_parts.append(
                f"**Domain Overlap ({scores['keyword_similarity']:.2f})**: "
                f"Significant overlap in domain-specific terminology suggests "
                f"the CLO contributes directly to achieving this PLO."
            )
        
        # Overall strength
        composite = scores["composite"]
        if composite >= 0.7:
            strength = "**Strong mapping**"
        elif composite >= 0.5:
            strength = "**Moderate mapping**"
        else:
            strength = "**Weak mapping**"
        
        justification_parts.append(
            f"**Overall Strength**: {strength} (composite score: {composite:.2f})"
        )
        
        return "\n".join(justification_parts)


# Convenience function
def create_mapping_engine(embeddings=None):
    """Create a CLO-PLO mapping engine instance"""
    return CLOPLOMappingEngine(embeddings=embeddings)
