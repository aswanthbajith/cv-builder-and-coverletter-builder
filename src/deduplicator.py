"""Duplicate job detection using multiple methods."""

import logging
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from typing import List, Tuple
try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


class Deduplicator:
    """Detect and mark duplicate job postings."""
    
    def __init__(self):
        self.similarity_threshold = config.get('duplicate_similarity_threshold', 0.95)
        self.model = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load sentence transformer model for embeddings if available."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded sentence transformer model")
        except Exception as e:
            logger.warning(f"Could not load sentence transformer: {e}")
            self.model = None
    
    def deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mark duplicate jobs in the DataFrame."""
        df = df.copy()
        df['duplicate'] = False
        df['duplicate_of'] = None
        df['deduplication_reason'] = None
        
        duplicates = self._find_duplicates(df)
        
        for idx, duplicate_of, reason in duplicates:
            df.at[idx, 'duplicate'] = True
            df.at[idx, 'duplicate_of'] = duplicate_of
            df.at[idx, 'deduplication_reason'] = reason
        
        logger.info(f"Found {len(duplicates)} duplicates out of {len(df)} jobs")
        return df
    
    def _find_duplicates(self, df: pd.DataFrame) -> List[Tuple[int, int, str]]:
        """Find duplicate job pairs."""
        duplicates = []
        n = len(df)
        
        for i in range(n):
            if i in [d[0] for d in duplicates]:
                continue
            
            for j in range(i + 1, n):
                if j in [d[0] for d in duplicates]:
                    continue
                
                similarity, reason = self._compute_similarity(df, i, j)
                
                if similarity >= self.similarity_threshold:
                    duplicates.append((j, i, reason))
                    logger.debug(f"Duplicate found: {j} is duplicate of {i} (score: {similarity:.3f})")
        
        return duplicates
    
    def _compute_similarity(self, df: pd.DataFrame, i: int, j: int) -> Tuple[float, str]:
        """Compute composite similarity between two jobs."""
        scores = []
        reasons = []
        
        # 1. Exact URL match
        if 'application_url' in df.columns:
            url_i = str(df.at[i, 'application_url']).strip().lower()
            url_j = str(df.at[j, 'application_url']).strip().lower()
            if url_i and url_j and url_i == url_j and url_i != 'nan':
                return 1.0, "Exact URL match"
        
        # 2. Company + Title fuzzy match
        company_i = str(df.at[i, 'company']).lower()
        company_j = str(df.at[j, 'company']).lower()
        title_i = str(df.at[i, 'job_title']).lower()
        title_j = str(df.at[j, 'job_title']).lower()
        
        company_score = fuzz.ratio(company_i, company_j) / 100.0
        title_score = fuzz.ratio(title_i, title_j) / 100.0
        
        if company_score > 0.9 and title_score > 0.9:
            scores.append((company_score + title_score) / 2)
            reasons.append("Company+Title match")
        
        # 3. Location match
        loc_i = str(df.at[i, 'location']).lower()
        loc_j = str(df.at[j, 'location']).lower()
        loc_score = fuzz.ratio(loc_i, loc_j) / 100.0
        scores.append(loc_score * 0.1)  # Small weight
        
        # 4. Description semantic similarity
        if self.model is not None and 'job_description' in df.columns:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                desc_i = str(df.at[i, 'job_description'])
                desc_j = str(df.at[j, 'job_description'])
                
                if len(desc_i) > 50 and len(desc_j) > 50:
                    embeddings = self.model.encode([desc_i, desc_j])
                    semantic_score = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
                    scores.append(semantic_score * 0.5)  # High weight
                    reasons.append(f"Semantic similarity: {semantic_score:.3f}")
            except Exception:
                pass
        
        # 5. Required skills overlap
        if 'required_skills' in df.columns:
            skills_i = set(str(df.at[i, 'required_skills']).lower().split(';'))
            skills_j = set(str(df.at[j, 'required_skills']).lower().split(';'))
            if skills_i and skills_j:
                overlap = len(skills_i & skills_j) / max(len(skills_i), len(skills_j))
                scores.append(overlap * 0.2)
        
        final_score = min(sum(scores), 1.0) if scores else 0.0
        reason_str = "; ".join(reasons) if reasons else "Composite match"
        
        return final_score, reason_str
