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
    "remembering": [
        "define",
        "list",
        "recall",
        "recognize",
        "identify",
        "name",
        "state",
        "describe",
        "retrieve",
    ],
    # Understanding
    "understanding": [
        "explain",
        "interpret",
        "summarize",
        "classify",
        "compare",
        "discuss",
        "paraphrase",
        "illustrate",
        "translate",
    ],
    # Applying
    "applying": [
        "apply",
        "implement",
        "use",
        "execute",
        "solve",
        "demonstrate",
        "operate",
        "employ",
        "practice",
    ],
    # Analyzing
    "analyzing": [
        "analyze",
        "examine",
        "investigate",
        "categorize",
        "differentiate",
        "distinguish",
        "compare",
        "contrast",
        "test",
    ],
    # Evaluating
    "evaluating": [
        "evaluate",
        "assess",
        "judge",
        "critique",
        "justify",
        "argue",
        "defend",
        "support",
        "validate",
    ],
    # Creating (Highest)
    "creating": [
        "create",
        "design",
        "develop",
        "construct",
        "plan",
        "produce",
        "formulate",
        "generate",
        "compose",
    ],
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
    "creating": 6,
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
        # Lightweight domain and skill keyword sets for category-aware gating
        self.technical_keywords = {
            "image",
            "imaging",
            "vision",
            "computer vision",
            "geometry",
            "view",
            "epipolar",
            "stereo",
            "depth",
            "camera",
            "calibration",
            "filter",
            "filtering",
            "restoration",
            "reconstruction",
            "segmentation",
            "registration",
            "classification",
            "detection",
            "edge",
            "feature",
            "sift",
            "surf",
            "harris",
            "object",
            "recognition",
            "tracking",
            "motion",
            "estimation",
            "representation",
            "fourier",
            "frequency",
            "wavelet",
            "convolution",
            "kernel",
            "gradient",
            "morphology",
            "cnn",
            "deep",
            "neural",
        }
        self.soft_skill_keywords = {
            "team",
            "teamwork",
            "collaborate",
            "collaboration",
            "leader",
            "lead",
            "multidisciplinary",
            "communicate",
            "communication",
            "presentation",
            "report",
            "documentation",
            "societal",
            "society",
            "health",
            "safety",
            "legal",
            "cultural",
            "ethics",
            "ethical",
            "lifelong",
            "life-long",
            "independent learning",
            "self-directed",
            "professionalism",
        }
        # Recognizers for common PLO categories
        self.plo_category_keywords = {
            "knowledge": {
                "knowledge",
                "fundamentals",
                "abstraction",
                "conceptualization",
            },
            "analysis": {
                "analy",
                "identify",
                "formulate",
                "solve",
                "research",
                "conclusion",
            },
            "design": {"design", "develop", "evaluate", "solution", "system"},
            "tools": {"tool", "technique", "resource", "apply", "modern"},
            "team": {"team", "member", "leader", "multidisciplinary"},
            "communication": {"communicat", "presentation", "report", "documentation"},
            "society": {
                "societ",
                "health",
                "safety",
                "legal",
                "cultural",
                "professional",
            },
            "ethics": {"ethic", "responsib"},
            "lifelong": {"lifelong", "independent", "self-directed"},
        }

    def extract_action_verbs(self, text: str) -> List[str]:
        """Extract action verbs from outcome text"""
        # Convert to lowercase
        text_lower = text.lower()

        # Find all verbs from Bloom's taxonomy
        found_verbs = []
        for verb in VERB_TO_BLOOM.keys():
            # Use word boundaries to match whole words
            pattern = r"\b" + re.escape(verb) + r"\b"
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
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "are",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "should",
            "could",
            "can",
            "may",
            "might",
            "must",
            "student",
            "students",
            "ability",
            "able",
            "course",
            "program",
            "learning",
            "outcome",
            "outcomes",
        }

        # Extract words
        # Basic tokenization with crude lemmatization for plurals/ing
        def _tokens(s: str) -> List[str]:
            words = re.findall(r"\b\w+\b", s.lower())
            toks: List[str] = []
            for w in words:
                if w.endswith("ing") and len(w) > 5:
                    w = w[:-3]
                if w.endswith("es") and len(w) > 4:
                    w = w[:-2]
                elif w.endswith("s") and len(w) > 3:
                    w = w[:-1]
                toks.append(w)
            return toks

        clo_words = set(_tokens(clo)) - stopwords
        plo_words = set(_tokens(plo)) - stopwords

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

    # ---------------- Category awareness & gating ----------------
    def _is_technical_text(self, text: str) -> bool:
        text_l = text.lower()
        return any(k in text_l for k in self.technical_keywords)

    def _has_soft_skills(self, text: str) -> bool:
        text_l = text.lower()
        return any(k in text_l for k in self.soft_skill_keywords)

    def _infer_plo_categories(self, plo: str) -> List[str]:
        p = plo.lower()
        cats: List[str] = []
        for cat, keys in self.plo_category_keywords.items():
            if any(k in p for k in keys):
                cats.append(cat)
        # Fallback heuristic by title prefixes like "PLO 6: Individual and Team Work"
        if not cats:
            if re.search(r"\bteam\b|\bmember\b|\bleader\b", p):
                cats.append("team")
            if re.search(r"\bcommunicat", p):
                cats.append("communication")
            if re.search(r"\bethic", p):
                cats.append("ethics")
            if re.search(r"\blife[- ]?long|independent learning", p):
                cats.append("lifelong")
        return cats or ["knowledge"]

    def _category_alignment_factor(self, clo: str, plo: str) -> float:
        """Penalize mappings where technical CLOs map to soft-skill PLOs without soft cues, and vice versa.
        Returns a multiplicative factor in [0.3, 1.0]."""
        clo_is_tech = self._is_technical_text(clo)
        clo_has_soft = self._has_soft_skills(clo)
        plo_cats = set(self._infer_plo_categories(plo))
        plo_is_soft = any(
            c in {"team", "communication", "society", "ethics", "lifelong"}
            for c in plo_cats
        )

        # Technical CLO mapping to soft PLO without soft cues -> strong penalty
        if clo_is_tech and plo_is_soft and not clo_has_soft:
            return 0.45
        # Soft-skill CLO mapping to hardcore technical PLO (knowledge/analysis/design/tools) -> mild penalty
        if not clo_is_tech and (
            "knowledge" in plo_cats
            or "analysis" in plo_cats
            or "design" in plo_cats
            or "tools" in plo_cats
        ):
            return 0.7
        return 1.0

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
        self, clo: str, plo: str, weights: Dict[str, float] = None
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
                "semantic_similarity": 0.25,
            }

        # Calculate individual scores
        bloom_score = self.bloom_alignment_score(clo, plo)
        verb_score = self.verb_overlap_score(clo, plo)
        keyword_score = self.keyword_similarity_score(clo, plo)
        semantic_score = self.semantic_similarity_score(clo, plo)
        # Gate: at least one evidence channel besides Bloom should be present
        evidence_ok = (
            (verb_score >= 0.2) or (keyword_score >= 0.12) or (semantic_score >= 0.55)
        )
        # Category alignment multiplier
        category_factor = self._category_alignment_factor(clo, plo)

        # Calculate weighted composite score
        composite_raw = (
            bloom_score * weights["bloom_alignment"]
            + verb_score * weights["verb_overlap"]
            + keyword_score * weights["keyword_similarity"]
            + semantic_score * weights["semantic_similarity"]
        )
        composite = composite_raw * category_factor
        if not evidence_ok:
            # Severely downweight if no non-Bloom evidence supports the link
            composite *= 0.5

        return {
            "bloom_alignment": bloom_score,
            "verb_overlap": verb_score,
            "keyword_similarity": keyword_score,
            "semantic_similarity": semantic_score,
            "category_factor": category_factor,
            "composite": composite,
        }

    def generate_mapping(
        self, clos: List[str], plos: List[str], threshold: float = 0.5, top_k: int = 3
    ) -> Dict[int, List[Dict]]:
        """
        Generate CLO-PLO mapping with scores and justifications.

        Args:
            clos: List of CLO texts
            plos: List of PLO texts
            threshold: Minimum composite score for mapping (default 0.5)
            top_k: Keep only top K PLOs per CLO to avoid dilution

        Returns:
            Dictionary mapping CLO index to list of mapped PLOs with scores
        """
        mapping = defaultdict(list)

        for clo_idx, clo in enumerate(clos):
            for plo_idx, plo in enumerate(plos):
                scores = self.calculate_composite_score(clo, plo)

                # Only include mappings above threshold
                if scores["composite"] >= threshold:
                    mapping[clo_idx].append(
                        {
                            "plo_index": plo_idx,
                            "scores": scores,
                            "clo_bloom": self.get_bloom_level(clo),
                            "plo_bloom": self.get_bloom_level(plo),
                            "clo_verbs": self.extract_action_verbs(clo),
                            "plo_verbs": self.extract_action_verbs(plo),
                        }
                    )

            # Sort by composite score (descending)
            mapping[clo_idx].sort(key=lambda x: x["scores"]["composite"], reverse=True)
            # Keep only top_k
            if top_k is not None and top_k > 0:
                mapping[clo_idx] = mapping[clo_idx][:top_k]

        return dict(mapping)

    def generate_justification(self, clo: str, plo: str, mapping_info: Dict) -> str:
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
