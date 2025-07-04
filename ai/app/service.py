from sentence_transformers import SentenceTransformer
from .config import settings
import re
import logging
import numpy as np
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from sklearn.metrics.pairwise import cosine_similarity
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Initialize embedding cache
embedding_cache = TTLCache(maxsize=settings.cache_size, ttl=settings.embedding_cache_ttl)

# Import necessary types and classes
from .schemas import CategorizationResponse, StandaloneEmailRequest
from .vector_store import VectorStore
from .thread_utils import ThreadUtils

class EmailCategorizationService:
    """Production-ready email categorization service"""
    
    def __init__(self, model_name: str = None):
        model_name = model_name or settings.sentence_transformer_model
        
        try:
            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Loaded model {model_name} with {self.embedding_dim} dimensions")
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise
    
    def clean_email_content(self, content: str) -> str:
        """Clean and preprocess email content"""
        if not content:
            return ""
        
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)
        
        # Remove signatures
        signature_patterns = [
            r'\n--\s*\n.*$',
            r'\nSent from my.*$',
            r'\n(Best regards?|Thanks?|Sincerely),.*$',
        ]
        
        for pattern in signature_patterns:
            content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove quoted replies
        lines = content.split('\n')
        clean_lines = [line for line in lines if not line.strip().startswith('>')]
        content = '\n'.join(clean_lines)
        
        # Normalize whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        return content
    
    def extract_meaningful_text(self, subject: str, body: str) -> str:
        """Extract meaningful text for categorization"""
        # Truncate to reasonable lengths
        subject = (subject or "")[:settings.max_subject_chars]
        cleaned_body = self.clean_email_content(body)[:settings.max_body_chars]
        
        if subject and cleaned_body:
            return f"{subject}. {cleaned_body}"
        return subject or cleaned_body or "General email"
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding with caching"""
        if not text or not text.strip():
            return [0.0] * self.embedding_dim
        
        # Check cache first
        cache_key = f"emb_{hash(text.strip())}"
        cached = embedding_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            embedding = self.model.encode(text, convert_to_tensor=False)
            embedding_list = embedding.tolist()
            
            # Cache the result
            embedding_cache[cache_key] = embedding_list
            return embedding_list
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return [0.0] * self.embedding_dim
    
    def generate_category_name(self, text: str) -> str:
        """Generate meaningful category name"""
        # Keyword-based category detection
        text_lower = text.lower()
        
        category_keywords = {
            "Work & Business": ["meeting", "project", "work", "business", "team", "client"],
            "Finance & Bills": ["payment", "invoice", "bill", "bank", "money", "expense"],
            "Travel & Bookings": ["flight", "hotel", "trip", "travel", "booking"],
            "Personal & Social": ["family", "friend", "personal", "vacation", "party"],
            "Shopping & Orders": ["order", "purchase", "shipping", "delivery", "cart"],
            "Health & Medical": ["doctor", "appointment", "health", "medical", "clinic"],
        }
        
        for category, keywords in category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        
        # Fallback to extracting meaningful words
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text)
        if words:
            return f"{words[0].title()} Related"
        
        return "General"
    
    def categorize_standalone_email(self, db: Session, request: StandaloneEmailRequest) -> CategorizationResponse:
        """Fixed categorize standalone email - properly creates new categories"""
        try:
            meaningful_text = self.extract_meaningful_text(request.subject, request.body)
            print(f"DEBUG: Meaningful text: '{meaningful_text}'")  # Debug logging
            
            email_embedding = self.generate_embedding(meaningful_text)
            print(f"DEBUG: Generated embedding with {len(email_embedding)} dimensions")
            
            # Find similar categories
            vector_store = VectorStore(db)
            similar_categories = vector_store.find_similar_categories(
                email_embedding, 
                threshold=settings.category_match_threshold,
                limit=1
            )
            
            print(f"DEBUG: Found {len(similar_categories)} similar categories")
            
            if similar_categories:
                category, similarity = similar_categories[0]
                print(f"DEBUG: Using existing category: {category.name} (similarity: {similarity:.3f})")
                
                # Update email count
                from .crud import update_category_email_count
                update_category_email_count(db, category.id, 1)
                
                return self._create_response(
                    request.email_id, request.user_id, category.name,
                    similarity, False, category.description
                )
            else:
                # THIS IS THE KEY FIX: Create new category when no matches found
                print("DEBUG: No similar categories found, creating new category")
                
                category_name = self.generate_category_name(meaningful_text)
                print(f"DEBUG: Generated category name: '{category_name}'")
                
                # IMPORTANT: Don't create "General" categories automatically
                if category_name == "General":
                    # Try to extract a better name from the content
                    category_name = self._extract_better_category_name(meaningful_text, request.subject)
                    print(f"DEBUG: Improved category name: '{category_name}'")
                
                return self._create_new_category_response(
                    db, request, category_name, meaningful_text, email_embedding
                )
            
        except Exception as e:
            logger.error(f"Error categorizing email {request.email_id}: {e}")
            # Only fall back to General if there's an actual error
            return self._fallback_response(db, request)

    def categorize_threaded_email(self, db: Session, request) -> CategorizationResponse:
        """Fixed categorize threaded email with proper debugging and fallback logic"""
        try:
            print(f"DEBUG THREADED: Starting categorization for email {request.email_id}")
            print(f"DEBUG THREADED: Previous category: {getattr(request, 'previous_category', 'None')}")
            print(f"DEBUG THREADED: Thread subject: {getattr(request, 'thread_subject', 'None')}")
            print(f"DEBUG THREADED: Current subject: {request.subject}")
            
            # Check thread consistency first
            if hasattr(request, 'previous_category') and request.previous_category:
                print(f"DEBUG THREADED: Checking previous category: {request.previous_category}")
                
                from .crud import get_category_by_name
                previous_category = get_category_by_name(db, request.previous_category)
                
                if previous_category:
                    print(f"DEBUG THREADED: Found previous category in DB: {previous_category.name}")
                    print(f"DEBUG THREADED: Has embedding: {previous_category.embedding_vector is not None}")
                    
                    if previous_category.embedding_vector:
                        # Check if subjects match (thread continuation)
                        thread_subject = getattr(request, 'thread_subject', None)
                        is_continuation = ThreadUtils.is_thread_continuation(request.subject, thread_subject)
                        print(f"DEBUG THREADED: Is thread continuation: {is_continuation}")
                        
                        if is_continuation:
                            meaningful_text = self.extract_meaningful_text(request.subject, request.body)
                            current_embedding = self.generate_embedding(meaningful_text)
                            
                            similarity = self._calculate_similarity(
                                current_embedding, previous_category.embedding_vector
                            )
                            
                            print(f"DEBUG THREADED: Similarity with previous category: {similarity:.3f}")
                            print(f"DEBUG THREADED: Thread consistency threshold: {settings.thread_consistency_threshold}")
                            
                            if similarity >= settings.thread_consistency_threshold:
                                print(f"DEBUG THREADED: Using previous category due to thread consistency")
                                
                                from .crud import update_category_email_count
                                update_category_email_count(db, previous_category.id, 1)
                                
                                # Boost confidence for thread consistency
                                boosted_confidence = min(0.95, similarity + getattr(settings, 'confidence_boost_for_threads', 0.1))
                                
                                return self._create_response(
                                    request.email_id, request.user_id, previous_category.name,
                                    boosted_confidence, False, previous_category.description
                                )
                            else:
                                print(f"DEBUG THREADED: Similarity too low, falling back to standalone categorization")
                        else:
                            print(f"DEBUG THREADED: Not a thread continuation, treating as standalone")
                    else:
                        print(f"DEBUG THREADED: Previous category has no embedding, treating as standalone")
                else:
                    print(f"DEBUG THREADED: Previous category not found in DB, treating as standalone")
            else:
                print(f"DEBUG THREADED: No previous category provided, treating as standalone")
            
            # Fall back to standalone categorization
            print(f"DEBUG THREADED: Falling back to standalone categorization")
            
            standalone_request = StandaloneEmailRequest(
                email_id=request.email_id,
                user_id=request.user_id,
                subject=request.subject,
                body=request.body,
                snippet=getattr(request, 'snippet', ''),
                sender_email=getattr(request, 'sender_email', ''),
                recipient_emails=getattr(request, 'recipient_emails', []),
                timestamp=getattr(request, 'timestamp', datetime.now()),
                labels=getattr(request, 'labels', [])
            )
            
            result = self.categorize_standalone_email(db, standalone_request)
            print(f"DEBUG THREADED: Standalone result: {result.assigned_category}")
            return result
            
        except Exception as e:
            logger.error(f"Error categorizing threaded email {request.email_id}: {e}")
            print(f"DEBUG THREADED: Exception occurred: {e}")
            return self._fallback_response(db, request)
    
   
    def _calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between embeddings"""
        try:
            vec1 = np.array(embedding1).reshape(1, -1)
            vec2 = np.array(embedding2).reshape(1, -1)
            return float(cosine_similarity(vec1, vec2)[0][0])
        except Exception as e:
            logger.error(f"Similarity calculation failed: {e}")
            return 0.0
    
    def _create_response(self, email_id: str, user_id: str, category: str, 
                        confidence: float, is_new: bool, description: str = None) -> CategorizationResponse:
        """Create standardized response"""
        return CategorizationResponse(
            email_id=email_id,
            user_id=user_id,
            assigned_category=category,
            confidence_score=confidence,
            is_new_category=is_new,
            processing_timestamp=datetime.now(),
            category_description=description
        )
    
    def _create_new_category_response(self, db: Session, request: StandaloneEmailRequest, category_name: str, 
                                    meaningful_text: str, embedding: List[float]) -> CategorizationResponse:
        """Create new category and response"""
        from .crud import get_category_by_name, create_category, update_category_email_count
        
        # Ensure unique name
        existing = get_category_by_name(db, category_name)
        if existing:
            category_name = f"{category_name} {datetime.now().strftime('%m%d')}"
        
        new_category = create_category(
            db=db,
            name=category_name,
            description=f"Auto-generated: {request.subject[:50]}...",
            embedding=embedding,
            sample_content=request.snippet
        )
        
        update_category_email_count(db, new_category.id, 1)
        
        return self._create_response(
            request.email_id, request.user_id, new_category.name,
            0.8, True, new_category.description
        )
    
    def _fallback_response(self, db: Session, request) -> CategorizationResponse:
        """Fallback to general category"""
        from .crud import get_category_by_name, create_category, update_category_email_count
        
        general_category = get_category_by_name(db, "General")
        if not general_category:
            general_category = create_category(db, "General", "General email category")
        
        update_category_email_count(db, general_category.id, 1)
        
        return self._create_response(
            request.email_id, request.user_id, "General",
            0.5, False, "General email category"
        )

# Global service instance
categorization_service = EmailCategorizationService()