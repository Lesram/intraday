"""
Module 82: Document Service
Document management, version control, metadata handling, search capabilities, format conversion.
"""

import asyncio
import json
import os
import shutil
import hashlib
import mimetypes
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Set, Callable, Type, BinaryIO, TextIO
from enum import Enum
from pathlib import Path
import logging
import uuid
import zipfile
import copy
import base64

# Configure logging
logger = logging.getLogger(__name__)


class DocumentStatus(Enum):
    """Document status values."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    DELETED = "deleted"
    LOCKED = "locked"


class DocumentType(Enum):
    """Document type classifications."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    PDF = "pdf"
    ARCHIVE = "archive"
    OTHER = "other"


class AccessLevel(Enum):
    """Access levels for documents."""
    PUBLIC = "public"
    PRIVATE = "private"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class VersionChangeType(Enum):
    """Types of version changes."""
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    HOTFIX = "hotfix"


@dataclass
class DocumentMetadata:
    """Document metadata information."""
    title: str
    description: str = ""
    author: str = ""
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    category: str = ""
    language: str = "en"
    custom_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentVersion:
    """Document version information."""
    version_id: str
    version_number: str
    change_type: VersionChangeType
    created_at: datetime
    created_by: str
    changelog: str = ""
    file_path: str = ""
    file_size: int = 0
    checksum: str = ""
    is_current: bool = False


@dataclass
class Document:
    """Document entity with full information."""
    id: str
    metadata: DocumentMetadata
    document_type: DocumentType
    status: DocumentStatus
    access_level: AccessLevel
    current_version: DocumentVersion
    versions: List[DocumentVersion] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: Optional[datetime] = None
    file_path: str = ""
    file_size: int = 0
    mime_type: str = ""
    encoding: str = "utf-8"
    checksum: str = ""
    parent_id: Optional[str] = None
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    
    def __post_init__(self):
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        if isinstance(self.updated_at, str):
            self.updated_at = datetime.fromisoformat(self.updated_at.replace('Z', '+00:00'))


@dataclass
class SearchQuery:
    """Document search query."""
    text: str = ""
    tags: List[str] = field(default_factory=list)
    document_types: List[DocumentType] = field(default_factory=list)
    status_filter: List[DocumentStatus] = field(default_factory=list)
    access_levels: List[AccessLevel] = field(default_factory=list)
    author: str = ""
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    file_size_min: Optional[int] = None
    file_size_max: Optional[int] = None
    custom_filters: Dict[str, Any] = field(default_factory=dict)
    sort_by: str = "updated_at"
    sort_order: str = "desc"
    limit: int = 50
    offset: int = 0


@dataclass
class SearchResult:
    """Document search result."""
    documents: List[Document]
    total_count: int
    page_count: int
    current_page: int
    search_time_ms: int
    facets: Dict[str, Dict[str, int]] = field(default_factory=dict)


class DocumentStorage(ABC):
    """Abstract base class for document storage."""
    
    @abstractmethod
    async def store_file(self, file_path: str, content: bytes) -> bool:
        """Store file content."""
        pass
    
    @abstractmethod
    async def retrieve_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content."""
        pass
    
    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete file."""
        pass
    
    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        pass
    
    @abstractmethod
    async def get_file_size(self, file_path: str) -> int:
        """Get file size."""
        pass


class LocalFileStorage(DocumentStorage):
    """Local file system storage implementation."""
    
    def __init__(self, base_path: str = "documents"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def store_file(self, file_path: str, content: bytes) -> bool:
        """Store file content to local filesystem."""
        try:
            full_path = self.base_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'wb') as f:
                f.write(content)
            
            return True
        except Exception as e:
            logger.error(f"Failed to store file {file_path}: {e}")
            return False
    
    async def retrieve_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content from local filesystem."""
        try:
            full_path = self.base_path / file_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    return f.read()
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve file {file_path}: {e}")
            return None
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from local filesystem."""
        try:
            full_path = self.base_path / file_path
            if full_path.exists():
                full_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False
    
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in local filesystem."""
        try:
            full_path = self.base_path / file_path
            return full_path.exists()
        except Exception as e:
            logger.error(f"Failed to check file existence {file_path}: {e}")
            return False
    
    async def get_file_size(self, file_path: str) -> int:
        """Get file size from local filesystem."""
        try:
            full_path = self.base_path / file_path
            if full_path.exists():
                return full_path.stat().st_size
            return 0
        except Exception as e:
            logger.error(f"Failed to get file size {file_path}: {e}")
            return 0


class DocumentConverter:
    """Handle document format conversions."""
    
    @staticmethod
    def detect_document_type(file_path: str, mime_type: str = None) -> DocumentType:
        """Detect document type from file extension and MIME type."""
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type:
            if mime_type.startswith('text/'):
                return DocumentType.TEXT
            elif mime_type.startswith('image/'):
                return DocumentType.IMAGE
            elif mime_type.startswith('video/'):
                return DocumentType.VIDEO
            elif mime_type.startswith('audio/'):
                return DocumentType.AUDIO
            elif mime_type == 'application/pdf':
                return DocumentType.PDF
            elif mime_type in ['application/zip', 'application/x-tar', 'application/x-gzip']:
                return DocumentType.ARCHIVE
            elif mime_type in [
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ]:
                return DocumentType.SPREADSHEET
            elif mime_type in [
                'application/vnd.ms-powerpoint',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            ]:
                return DocumentType.PRESENTATION
        
        # Fallback to file extension
        ext = Path(file_path).suffix.lower()
        if ext in ['.txt', '.md', '.html', '.xml', '.json', '.csv']:
            return DocumentType.TEXT
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']:
            return DocumentType.IMAGE
        elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv']:
            return DocumentType.VIDEO
        elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg']:
            return DocumentType.AUDIO
        elif ext == '.pdf':
            return DocumentType.PDF
        elif ext in ['.zip', '.tar', '.gz', '.rar']:
            return DocumentType.ARCHIVE
        elif ext in ['.xls', '.xlsx', '.ods']:
            return DocumentType.SPREADSHEET
        elif ext in ['.ppt', '.pptx', '.odp']:
            return DocumentType.PRESENTATION
        
        return DocumentType.OTHER
    
    @staticmethod
    def calculate_checksum(content: bytes) -> str:
        """Calculate MD5 checksum of content."""
        return hashlib.md5(content).hexdigest()
    
    @staticmethod
    async def convert_to_text(file_path: str, content: bytes) -> str:
        """Convert document content to plain text for indexing."""
        try:
            document_type = DocumentConverter.detect_document_type(file_path)
            
            if document_type == DocumentType.TEXT:
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return content.decode('latin-1')
                    except UnicodeDecodeError:
                        return content.decode('utf-8', errors='ignore')
            
            # For other types, return basic metadata
            return f"Document: {Path(file_path).name}\nType: {document_type.value}\nSize: {len(content)} bytes"
            
        except Exception as e:
            logger.error(f"Failed to convert {file_path} to text: {e}")
            return ""


class DocumentSearchEngine:
    """Document search and indexing engine."""
    
    def __init__(self):
        self.index: Dict[str, Document] = {}
        self.text_index: Dict[str, Set[str]] = {}  # word -> document_ids
        self.tag_index: Dict[str, Set[str]] = {}   # tag -> document_ids
    
    async def index_document(self, document: Document, content: str = ""):
        """Index a document for searching."""
        try:
            self.index[document.id] = document
            
            # Index text content
            if content:
                words = self._tokenize_text(content.lower())
                for word in words:
                    if word not in self.text_index:
                        self.text_index[word] = set()
                    self.text_index[word].add(document.id)
            
            # Index tags
            for tag in document.metadata.tags:
                tag_lower = tag.lower()
                if tag_lower not in self.tag_index:
                    self.tag_index[tag_lower] = set()
                self.tag_index[tag_lower].add(document.id)
            
            # Index keywords
            for keyword in document.metadata.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self.text_index:
                    self.text_index[keyword_lower] = set()
                self.text_index[keyword_lower].add(document.id)
                
        except Exception as e:
            logger.error(f"Failed to index document {document.id}: {e}")
    
    async def remove_from_index(self, document_id: str):
        """Remove document from search index."""
        try:
            if document_id in self.index:
                document = self.index[document_id]
                
                # Remove from text index
                for word_set in self.text_index.values():
                    word_set.discard(document_id)
                
                # Remove from tag index
                for tag_set in self.tag_index.values():
                    tag_set.discard(document_id)
                
                # Remove from main index
                del self.index[document_id]
                
        except Exception as e:
            logger.error(f"Failed to remove document {document_id} from index: {e}")
    
    async def search(self, query: SearchQuery) -> SearchResult:
        """Search documents based on query."""
        start_time = datetime.now()
        
        try:
            # Start with all documents
            candidate_ids = set(self.index.keys())
            
            # Text search
            if query.text:
                text_words = self._tokenize_text(query.text.lower())
                text_matches = set()
                
                for word in text_words:
                    if word in self.text_index:
                        if not text_matches:
                            text_matches = self.text_index[word].copy()
                        else:
                            text_matches &= self.text_index[word]
                
                candidate_ids &= text_matches
            
            # Tag filter
            if query.tags:
                tag_matches = set()
                for tag in query.tags:
                    tag_lower = tag.lower()
                    if tag_lower in self.tag_index:
                        if not tag_matches:
                            tag_matches = self.tag_index[tag_lower].copy()
                        else:
                            tag_matches |= self.tag_index[tag_lower]
                
                if tag_matches:
                    candidate_ids &= tag_matches
            
            # Apply filters
            filtered_documents = []
            for doc_id in candidate_ids:
                if doc_id in self.index:
                    doc = self.index[doc_id]
                    if self._matches_filters(doc, query):
                        filtered_documents.append(doc)
            
            # Sort results
            sorted_documents = self._sort_documents(filtered_documents, query)
            
            # Pagination
            total_count = len(sorted_documents)
            start_idx = query.offset
            end_idx = start_idx + query.limit
            page_documents = sorted_documents[start_idx:end_idx]
            
            # Calculate facets
            facets = self._calculate_facets(filtered_documents)
            
            search_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return SearchResult(
                documents=page_documents,
                total_count=total_count,
                page_count=(total_count + query.limit - 1) // query.limit,
                current_page=(query.offset // query.limit) + 1,
                search_time_ms=int(search_time),
                facets=facets
            )
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return SearchResult(
                documents=[],
                total_count=0,
                page_count=0,
                current_page=1,
                search_time_ms=0
            )
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Simple text tokenization."""
        # Remove punctuation and split on whitespace
        import re
        words = re.findall(r'\b\w+\b', text)
        return [word for word in words if len(word) > 2]  # Filter short words
    
    def _matches_filters(self, document: Document, query: SearchQuery) -> bool:
        """Check if document matches query filters."""
        # Document type filter
        if query.document_types and document.document_type not in query.document_types:
            return False
        
        # Status filter
        if query.status_filter and document.status not in query.status_filter:
            return False
        
        # Access level filter
        if query.access_levels and document.access_level not in query.access_levels:
            return False
        
        # Author filter
        if query.author and query.author.lower() not in document.metadata.author.lower():
            return False
        
        # Date filters
        if query.created_after and document.created_at < query.created_after:
            return False
        
        if query.created_before and document.created_at > query.created_before:
            return False
        
        # File size filters
        if query.file_size_min and document.file_size < query.file_size_min:
            return False
        
        if query.file_size_max and document.file_size > query.file_size_max:
            return False
        
        return True
    
    def _sort_documents(self, documents: List[Document], query: SearchQuery) -> List[Document]:
        """Sort documents by specified criteria."""
        reverse = query.sort_order.lower() == "desc"
        
        if query.sort_by == "title":
            return sorted(documents, key=lambda d: d.metadata.title, reverse=reverse)
        elif query.sort_by == "created_at":
            return sorted(documents, key=lambda d: d.created_at, reverse=reverse)
        elif query.sort_by == "file_size":
            return sorted(documents, key=lambda d: d.file_size, reverse=reverse)
        else:  # Default to updated_at
            return sorted(documents, key=lambda d: d.updated_at, reverse=reverse)
    
    def _calculate_facets(self, documents: List[Document]) -> Dict[str, Dict[str, int]]:
        """Calculate facet counts for search results."""
        facets = {
            "document_types": {},
            "status": {},
            "access_levels": {},
            "tags": {}
        }
        
        for doc in documents:
            # Document type facets
            doc_type = doc.document_type.value
            facets["document_types"][doc_type] = facets["document_types"].get(doc_type, 0) + 1
            
            # Status facets
            status = doc.status.value
            facets["status"][status] = facets["status"].get(status, 0) + 1
            
            # Access level facets
            access_level = doc.access_level.value
            facets["access_levels"][access_level] = facets["access_levels"].get(access_level, 0) + 1
            
            # Tag facets
            for tag in doc.metadata.tags:
                facets["tags"][tag] = facets["tags"].get(tag, 0) + 1
        
        return facets


class DocumentService:
    """Service for managing documents with version control and search."""
    
    def __init__(self, storage: Optional[DocumentStorage] = None):
        self.storage = storage or LocalFileStorage()
        self.documents: Dict[str, Document] = {}
        self.search_engine = DocumentSearchEngine()
        self._lock = asyncio.Lock()
    
    async def create_document(
        self,
        file_content: bytes,
        metadata: DocumentMetadata,
        file_name: str,
        created_by: str,
        document_type: Optional[DocumentType] = None,
        access_level: AccessLevel = AccessLevel.PRIVATE
    ) -> str:
        """Create a new document."""
        try:
            document_id = str(uuid.uuid4())
            
            # Detect document type if not provided
            if document_type is None:
                mime_type, _ = mimetypes.guess_type(file_name)
                document_type = DocumentConverter.detect_document_type(file_name, mime_type)
            
            # Calculate checksum
            checksum = DocumentConverter.calculate_checksum(file_content)
            
            # Generate file path
            file_path = f"{document_id}/{file_name}"
            
            # Store file
            await self.storage.store_file(file_path, file_content)
            
            # Create initial version
            version = DocumentVersion(
                version_id=str(uuid.uuid4()),
                version_number="1.0.0",
                change_type=VersionChangeType.MAJOR,
                created_at=datetime.now(timezone.utc),
                created_by=created_by,
                changelog="Initial version",
                file_path=file_path,
                file_size=len(file_content),
                checksum=checksum,
                is_current=True
            )
            
            # Create document
            document = Document(
                id=document_id,
                metadata=metadata,
                document_type=document_type,
                status=DocumentStatus.DRAFT,
                access_level=access_level,
                current_version=version,
                versions=[version],
                file_path=file_path,
                file_size=len(file_content),
                mime_type=mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                checksum=checksum
            )
            
            self.documents[document_id] = document
            
            # Index for search
            text_content = await DocumentConverter.convert_to_text(file_name, file_content)
            await self.search_engine.index_document(document, text_content)
            
            logger.info(f"Created document {document_id}: {metadata.title}")
            return document_id
                
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise
    
    async def get_document(self, document_id: str) -> Optional[Document]:
        """Get document by ID."""
        return self.documents.get(document_id)
    
    async def update_document(
        self,
        document_id: str,
        file_content: Optional[bytes] = None,
        metadata: Optional[DocumentMetadata] = None,
        updated_by: str = "",
        change_type: VersionChangeType = VersionChangeType.MINOR,
        changelog: str = ""
    ) -> bool:
        """Update an existing document."""
        try:
            if document_id not in self.documents:
                return False
            
            document = self.documents[document_id]
            
            # Check if document is locked
            if document.status == DocumentStatus.LOCKED:
                logger.warning(f"Cannot update locked document {document_id}")
                return False
            
            # Update metadata if provided
            if metadata:
                document.metadata = metadata
            
            # Update file content if provided
            if file_content:
                # Calculate new checksum
                new_checksum = DocumentConverter.calculate_checksum(file_content)
                
                # Generate new version number
                current_version = document.current_version.version_number
                new_version_number = self._increment_version(current_version, change_type)
                
                # Generate new file path
                file_name = Path(document.file_path).name
                new_file_path = f"{document_id}/{new_version_number}_{file_name}"
                
                # Store new version
                await self.storage.store_file(new_file_path, file_content)
                
                # Mark current version as not current
                document.current_version.is_current = False
                
                # Create new version
                new_version = DocumentVersion(
                    version_id=str(uuid.uuid4()),
                    version_number=new_version_number,
                    change_type=change_type,
                    created_at=datetime.now(timezone.utc),
                    created_by=updated_by,
                    changelog=changelog,
                    file_path=new_file_path,
                    file_size=len(file_content),
                    checksum=new_checksum,
                    is_current=True
                )
                
                document.versions.append(new_version)
                document.current_version = new_version
                document.file_path = new_file_path
                document.file_size = len(file_content)
                document.checksum = new_checksum
            
            document.updated_at = datetime.now(timezone.utc)
            
            # Re-index for search
            if file_content:
                text_content = await DocumentConverter.convert_to_text(
                    document.file_path, file_content
                )
                await self.search_engine.index_document(document, text_content)
            else:
                await self.search_engine.index_document(document)
            
            logger.info(f"Updated document {document_id}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to update document {document_id}: {e}")
            return False
    
    async def delete_document(self, document_id: str, permanent: bool = False) -> bool:
        """Delete a document (soft delete by default)."""
        try:
            async with self._lock:
                if document_id not in self.documents:
                    return False
                
                document = self.documents[document_id]
                
                if permanent:
                    # Delete all versions from storage
                    for version in document.versions:
                        await self.storage.delete_file(version.file_path)
                    
                    # Remove from search index
                    await self.search_engine.remove_from_index(document_id)
                    
                    # Remove from documents
                    del self.documents[document_id]
                    
                    logger.info(f"Permanently deleted document {document_id}")
                else:
                    # Soft delete
                    document.status = DocumentStatus.DELETED
                    document.updated_at = datetime.now(timezone.utc)
                    
                    logger.info(f"Soft deleted document {document_id}")
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    async def get_document_content(self, document_id: str, version_id: Optional[str] = None) -> Optional[bytes]:
        """Get document content for a specific version."""
        try:
            if document_id not in self.documents:
                return None
            
            document = self.documents[document_id]
            
            # Find the version
            if version_id:
                version = next((v for v in document.versions if v.version_id == version_id), None)
                if not version:
                    return None
            else:
                version = document.current_version
            
            # Update access time
            document.accessed_at = datetime.now(timezone.utc)
            
            return await self.storage.retrieve_file(version.file_path)
            
        except Exception as e:
            logger.error(f"Failed to get content for document {document_id}: {e}")
            return None
    
    async def search_documents(self, query: SearchQuery) -> SearchResult:
        """Search documents."""
        return await self.search_engine.search(query)
    
    async def lock_document(self, document_id: str, locked_by: str) -> bool:
        """Lock a document to prevent modifications."""
        try:
            if document_id not in self.documents:
                return False
            
            document = self.documents[document_id]
            
            if document.status == DocumentStatus.LOCKED:
                return False  # Already locked
            
            document.status = DocumentStatus.LOCKED
            document.locked_by = locked_by
            document.locked_at = datetime.now(timezone.utc)
            
            logger.info(f"Locked document {document_id} by {locked_by}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to lock document {document_id}: {e}")
            return False
    
    async def unlock_document(self, document_id: str, unlocked_by: str) -> bool:
        """Unlock a document."""
        try:
            if document_id not in self.documents:
                return False
            
            document = self.documents[document_id]
            
            # Check if user can unlock (same user who locked or admin)
            if document.locked_by and document.locked_by != unlocked_by:
                logger.warning(f"User {unlocked_by} cannot unlock document {document_id} locked by {document.locked_by}")
                return False
            
            document.status = DocumentStatus.DRAFT
            document.locked_by = None
            document.locked_at = None
            
            logger.info(f"Unlocked document {document_id} by {unlocked_by}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unlock document {document_id}: {e}")
            return False
    
    async def get_document_versions(self, document_id: str) -> List[DocumentVersion]:
        """Get all versions of a document."""
        if document_id in self.documents:
            return self.documents[document_id].versions.copy()
        return []
    
    async def restore_version(self, document_id: str, version_id: str, restored_by: str) -> bool:
        """Restore a specific version as the current version."""
        try:
            async with self._lock:
                if document_id not in self.documents:
                    return False
                
                document = self.documents[document_id]
                
                # Find the version to restore
                version_to_restore = next(
                    (v for v in document.versions if v.version_id == version_id), 
                    None
                )
                
                if not version_to_restore:
                    return False
                
                # Get the content of the version to restore
                content = await self.storage.retrieve_file(version_to_restore.file_path)
                if not content:
                    return False
                
                # Create new version based on restored content
                await self.update_document(
                    document_id=document_id,
                    file_content=content,
                    updated_by=restored_by,
                    change_type=VersionChangeType.MAJOR,
                    changelog=f"Restored from version {version_to_restore.version_number}"
                )
                
                logger.info(f"Restored document {document_id} to version {version_to_restore.version_number}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to restore document {document_id} to version {version_id}: {e}")
            return False
    
    def _increment_version(self, current_version: str, change_type: VersionChangeType) -> str:
        """Increment version number based on change type."""
        try:
            parts = current_version.split('.')
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            
            if change_type == VersionChangeType.MAJOR:
                major += 1
                minor = 0
                patch = 0
            elif change_type == VersionChangeType.MINOR:
                minor += 1
                patch = 0
            elif change_type in [VersionChangeType.PATCH, VersionChangeType.HOTFIX]:
                patch += 1
            
            return f"{major}.{minor}.{patch}"
            
        except Exception:
            # Fallback to simple increment
            return "1.0.0"
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get document statistics."""
        try:
            total_documents = len(self.documents)
            total_size = sum(doc.file_size for doc in self.documents.values())
            
            # Count by status
            status_counts = {}
            for status in DocumentStatus:
                status_counts[status.value] = sum(
                    1 for doc in self.documents.values() 
                    if doc.status == status
                )
            
            # Count by type
            type_counts = {}
            for doc_type in DocumentType:
                type_counts[doc_type.value] = sum(
                    1 for doc in self.documents.values() 
                    if doc.document_type == doc_type
                )
            
            # Recent activity
            recent_documents = [
                doc for doc in self.documents.values()
                if doc.updated_at > datetime.now(timezone.utc) - timedelta(days=7)
            ]
            
            return {
                "total_documents": total_documents,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "status_distribution": status_counts,
                "type_distribution": type_counts,
                "recent_activity": len(recent_documents),
                "total_versions": sum(len(doc.versions) for doc in self.documents.values())
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}


# Global instance
_document_service = None


def get_document_service() -> DocumentService:
    """Get global document service instance."""
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service


# Convenience functions
async def create_document(
    file_content: bytes,
    metadata: DocumentMetadata,
    file_name: str,
    created_by: str,
    **kwargs
) -> str:
    """Convenience function to create a document."""
    return await get_document_service().create_document(
        file_content, metadata, file_name, created_by, **kwargs
    )


async def search_documents(query: SearchQuery) -> SearchResult:
    """Convenience function to search documents."""
    return await get_document_service().search_documents(query)


async def get_document_content(document_id: str, version_id: Optional[str] = None) -> Optional[bytes]:
    """Convenience function to get document content."""
    return await get_document_service().get_document_content(document_id, version_id)