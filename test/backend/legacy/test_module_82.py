"""
Tests for Module 82: Document Service
Tests for document management, version control, metadata handling, search capabilities, format conversion.
"""

import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

from backend.services.document import (
    DocumentService,
    Document,
    DocumentMetadata,
    DocumentVersion,
    SearchQuery,
    SearchResult,
    LocalFileStorage,
    DocumentConverter,
    DocumentSearchEngine,
    DocumentStatus,
    DocumentType,
    AccessLevel,
    VersionChangeType,
    get_document_service,
    create_document,
    search_documents,
    get_document_content
)


@pytest.fixture
def temp_storage_dir():
    """Create temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def document_service(temp_storage_dir):
    """Create document service with temporary storage."""
    storage = LocalFileStorage(temp_storage_dir)
    return DocumentService(storage)


@pytest.fixture
def sample_metadata():
    """Create sample document metadata."""
    return DocumentMetadata(
        title="Test Document",
        description="A test document for testing",
        author="Test Author",
        created_by="test_user",
        tags=["test", "sample"],
        keywords=["document", "test"],
        category="testing"
    )


@pytest.fixture
def sample_content():
    """Create sample document content."""
    return b"This is a test document content with some text for testing purposes."


class TestDocumentMetadata:
    """Test DocumentMetadata class."""
    
    def test_metadata_creation(self, sample_metadata):
        """Test metadata creation."""
        assert sample_metadata.title == "Test Document"
        assert sample_metadata.author == "Test Author"
        assert "test" in sample_metadata.tags
        assert "document" in sample_metadata.keywords
    
    def test_metadata_defaults(self):
        """Test metadata with default values."""
        metadata = DocumentMetadata(title="Minimal Document")
        assert metadata.title == "Minimal Document"
        assert metadata.description == ""
        assert metadata.tags == []
        assert metadata.keywords == []


class TestDocumentVersion:
    """Test DocumentVersion class."""
    
    def test_version_creation(self):
        """Test version creation."""
        version = DocumentVersion(
            version_id="v1",
            version_number="1.0.0",
            change_type=VersionChangeType.MAJOR,
            created_at=datetime.now(timezone.utc),
            created_by="test_user",
            changelog="Initial version"
        )
        
        assert version.version_id == "v1"
        assert version.version_number == "1.0.0"
        assert version.change_type == VersionChangeType.MAJOR
        assert version.changelog == "Initial version"


class TestLocalFileStorage:
    """Test LocalFileStorage class."""
    
    def test_storage_initialization(self, temp_storage_dir):
        """Test storage initialization."""
        storage = LocalFileStorage(temp_storage_dir)
        assert storage.base_path == Path(temp_storage_dir)
        assert storage.base_path.exists()
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_file(self, temp_storage_dir):
        """Test storing and retrieving files."""
        storage = LocalFileStorage(temp_storage_dir)
        
        test_content = b"Hello, World!"
        file_path = "test/file.txt"
        
        # Store file
        result = await storage.store_file(file_path, test_content)
        assert result is True
        
        # Retrieve file
        retrieved_content = await storage.retrieve_file(file_path)
        assert retrieved_content == test_content
    
    @pytest.mark.asyncio
    async def test_file_operations(self, temp_storage_dir):
        """Test file existence and size operations."""
        storage = LocalFileStorage(temp_storage_dir)
        
        test_content = b"Test content"
        file_path = "test.txt"
        
        # Initially file doesn't exist
        assert await storage.file_exists(file_path) is False
        assert await storage.get_file_size(file_path) == 0
        
        # Store file
        await storage.store_file(file_path, test_content)
        
        # Now file exists with correct size
        assert await storage.file_exists(file_path) is True
        assert await storage.get_file_size(file_path) == len(test_content)
        
        # Delete file
        result = await storage.delete_file(file_path)
        assert result is True
        assert await storage.file_exists(file_path) is False


class TestDocumentConverter:
    """Test DocumentConverter class."""
    
    def test_document_type_detection(self):
        """Test document type detection."""
        # Test by file extension
        assert DocumentConverter.detect_document_type("test.txt") == DocumentType.TEXT
        assert DocumentConverter.detect_document_type("image.jpg") == DocumentType.IMAGE
        assert DocumentConverter.detect_document_type("video.mp4") == DocumentType.VIDEO
        assert DocumentConverter.detect_document_type("audio.mp3") == DocumentType.AUDIO
        assert DocumentConverter.detect_document_type("document.pdf") == DocumentType.PDF
        assert DocumentConverter.detect_document_type("archive.zip") == DocumentType.ARCHIVE
        assert DocumentConverter.detect_document_type("spreadsheet.xlsx") == DocumentType.SPREADSHEET
        assert DocumentConverter.detect_document_type("presentation.pptx") == DocumentType.PRESENTATION
        assert DocumentConverter.detect_document_type("unknown.xyz") == DocumentType.OTHER
        
        # Test by MIME type
        assert DocumentConverter.detect_document_type("file", "text/plain") == DocumentType.TEXT
        assert DocumentConverter.detect_document_type("file", "image/jpeg") == DocumentType.IMAGE
        assert DocumentConverter.detect_document_type("file", "application/pdf") == DocumentType.PDF
    
    def test_checksum_calculation(self):
        """Test checksum calculation."""
        content1 = b"Hello, World!"
        content2 = b"Hello, World!"
        content3 = b"Different content"
        
        checksum1 = DocumentConverter.calculate_checksum(content1)
        checksum2 = DocumentConverter.calculate_checksum(content2)
        checksum3 = DocumentConverter.calculate_checksum(content3)
        
        assert checksum1 == checksum2  # Same content, same checksum
        assert checksum1 != checksum3  # Different content, different checksum
    
    @pytest.mark.asyncio
    async def test_text_conversion(self):
        """Test text conversion."""
        # Text content
        text_content = b"This is some text content."
        result = await DocumentConverter.convert_to_text("test.txt", text_content)
        assert "This is some text content." in result
        
        # Binary content (returns metadata)
        binary_content = b"\x00\x01\x02\x03"
        result = await DocumentConverter.convert_to_text("test.bin", binary_content)
        assert "Document: test.bin" in result
        assert "Type: other" in result


class TestDocumentSearchEngine:
    """Test DocumentSearchEngine class."""
    
    def test_search_engine_initialization(self):
        """Test search engine initialization."""
        engine = DocumentSearchEngine()
        assert engine.index == {}
        assert engine.text_index == {}
        assert engine.tag_index == {}
    
    @pytest.mark.asyncio
    async def test_document_indexing(self, sample_metadata):
        """Test document indexing."""
        engine = DocumentSearchEngine()
        
        document = Document(
            id="doc1",
            metadata=sample_metadata,
            document_type=DocumentType.TEXT,
            status=DocumentStatus.PUBLISHED,
            access_level=AccessLevel.PUBLIC,
            current_version=DocumentVersion(
                version_id="v1",
                version_number="1.0.0",
                change_type=VersionChangeType.MAJOR,
                created_at=datetime.now(timezone.utc),
                created_by="test_user"
            )
        )
        
        content = "This is test content with keywords"
        await engine.index_document(document, content)
        
        assert "doc1" in engine.index
        assert "test" in engine.text_index
        assert "doc1" in engine.text_index["test"]
        assert "test" in engine.tag_index
        assert "doc1" in engine.tag_index["test"]
    
    @pytest.mark.asyncio
    async def test_document_search(self, sample_metadata):
        """Test document searching."""
        engine = DocumentSearchEngine()
        
        # Create and index test documents
        doc1 = Document(
            id="doc1",
            metadata=DocumentMetadata(
                title="First Document",
                tags=["important", "test"],
                author="Author One"
            ),
            document_type=DocumentType.TEXT,
            status=DocumentStatus.PUBLISHED,
            access_level=AccessLevel.PUBLIC,
            current_version=DocumentVersion(
                version_id="v1",
                version_number="1.0.0",
                change_type=VersionChangeType.MAJOR,
                created_at=datetime.now(timezone.utc),
                created_by="test_user"
            )
        )
        
        doc2 = Document(
            id="doc2",
            metadata=DocumentMetadata(
                title="Second Document",
                tags=["normal", "test"],
                author="Author Two"
            ),
            document_type=DocumentType.PDF,
            status=DocumentStatus.DRAFT,
            access_level=AccessLevel.PRIVATE,
            current_version=DocumentVersion(
                version_id="v2",
                version_number="1.0.0",
                change_type=VersionChangeType.MAJOR,
                created_at=datetime.now(timezone.utc),
                created_by="test_user"
            )
        )
        
        await engine.index_document(doc1, "content with important information")
        await engine.index_document(doc2, "different content here")
        
        # Test text search
        query = SearchQuery(text="important")
        result = await engine.search(query)
        assert result.total_count == 1
        assert result.documents[0].id == "doc1"
        
        # Test tag search
        query = SearchQuery(tags=["test"])
        result = await engine.search(query)
        assert result.total_count == 2
        
        # Test filters
        query = SearchQuery(document_types=[DocumentType.PDF])
        result = await engine.search(query)
        assert result.total_count == 1
        assert result.documents[0].id == "doc2"


class TestDocumentService:
    """Test DocumentService class."""
    
    def test_service_initialization(self, document_service):
        """Test service initialization."""
        assert document_service.storage is not None
        assert document_service.documents == {}
        assert document_service.search_engine is not None
    
    @pytest.mark.asyncio
    async def test_create_document(self, document_service, sample_metadata, sample_content):
        """Test document creation."""
        document_id = await document_service.create_document(
            file_content=sample_content,
            metadata=sample_metadata,
            file_name="test.txt",
            created_by="test_user"
        )
        
        assert document_id is not None
        assert document_id in document_service.documents
        
        document = document_service.documents[document_id]
        assert document.metadata.title == "Test Document"
        assert document.document_type == DocumentType.TEXT
        assert document.status == DocumentStatus.DRAFT
        assert len(document.versions) == 1
        assert document.current_version.version_number == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_get_document(self, document_service, sample_metadata, sample_content):
        """Test getting a document."""
        # Create document first
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Get document
        document = await document_service.get_document(document_id)
        assert document is not None
        assert document.id == document_id
        
        # Non-existent document
        non_existent = await document_service.get_document("non-existent")
        assert non_existent is None
    
    @pytest.mark.asyncio
    async def test_update_document(self, document_service, sample_metadata, sample_content):
        """Test document updates."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Update with new content
        new_content = b"Updated content with new information"
        result = await document_service.update_document(
            document_id=document_id,
            file_content=new_content,
            updated_by="test_user",
            change_type=VersionChangeType.MINOR,
            changelog="Updated content"
        )
        
        assert result is True
        
        document = document_service.documents[document_id]
        assert len(document.versions) == 2
        assert document.current_version.version_number == "1.1.0"
        assert document.current_version.changelog == "Updated content"
        assert document.file_size == len(new_content)
    
    @pytest.mark.asyncio
    async def test_delete_document(self, document_service, sample_metadata, sample_content):
        """Test document deletion."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Soft delete
        result = await document_service.delete_document(document_id, permanent=False)
        assert result is True
        
        document = document_service.documents[document_id]
        assert document.status == DocumentStatus.DELETED
        
        # Permanent delete
        result = await document_service.delete_document(document_id, permanent=True)
        assert result is True
        assert document_id not in document_service.documents
    
    @pytest.mark.asyncio
    async def test_get_document_content(self, document_service, sample_metadata, sample_content):
        """Test getting document content."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Get content
        content = await document_service.get_document_content(document_id)
        assert content == sample_content
        
        # Non-existent document
        content = await document_service.get_document_content("non-existent")
        assert content is None
    
    @pytest.mark.asyncio
    async def test_document_locking(self, document_service, sample_metadata, sample_content):
        """Test document locking and unlocking."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Lock document
        result = await document_service.lock_document(document_id, "test_user")
        assert result is True
        
        document = document_service.documents[document_id]
        assert document.status == DocumentStatus.LOCKED
        assert document.locked_by == "test_user"
        
        # Try to update locked document (should fail)
        update_result = await document_service.update_document(
            document_id, b"new content", updated_by="other_user"
        )
        assert update_result is False
        
        # Unlock document
        result = await document_service.unlock_document(document_id, "test_user")
        assert result is True
        
        document = document_service.documents[document_id]
        assert document.status == DocumentStatus.DRAFT
        assert document.locked_by is None
    
    @pytest.mark.asyncio
    async def test_version_management(self, document_service, sample_metadata, sample_content):
        """Test version management."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "test_user"
        )
        
        # Test single update first
        result = await document_service.update_document(
            document_id, b"Version 2", updated_by="user", 
            change_type=VersionChangeType.MINOR
        )
        assert result is True
        
        # Get versions after first update
        versions = await document_service.get_document_versions(document_id)
        assert len(versions) == 2
        assert versions[0].version_number == "1.0.0"
        assert versions[1].version_number == "1.1.0"
        
        # Test second update
        result = await document_service.update_document(
            document_id, b"Version 3", updated_by="user", 
            change_type=VersionChangeType.PATCH
        )
        assert result is True
        
        # Get versions after second update
        versions = await document_service.get_document_versions(document_id)
        assert len(versions) == 3
        assert versions[2].version_number == "1.1.1"
        
        # Restore to previous version
        result = await document_service.restore_version(
            document_id, versions[0].version_id, "user"
        )
        assert result is True
        
        # Should have 4 versions now (original + 2 updates + restore)
        versions = await document_service.get_document_versions(document_id)
        assert len(versions) == 4
        assert versions[-1].changelog.startswith("Restored from version")
    
    @pytest.mark.asyncio
    async def test_search_documents(self, document_service, sample_content):
        """Test document searching."""
        # Create multiple documents
        meta1 = DocumentMetadata(
            title="Important Document",
            tags=["important", "business"],
            author="Author One"
        )
        meta2 = DocumentMetadata(
            title="Regular Document",
            tags=["regular", "business"],
            author="Author Two"
        )
        
        doc1_id = await document_service.create_document(
            sample_content, meta1, "doc1.txt", "user1"
        )
        doc2_id = await document_service.create_document(
            b"Different content", meta2, "doc2.txt", "user2"
        )
        
        # Search by text
        query = SearchQuery(text="test document")
        result = await document_service.search_documents(query)
        assert result.total_count >= 1
        
        # Search by tags
        query = SearchQuery(tags=["important"])
        result = await document_service.search_documents(query)
        assert result.total_count == 1
        assert result.documents[0].id == doc1_id
        
        # Search with filters
        query = SearchQuery(
            document_types=[DocumentType.TEXT],
            status_filter=[DocumentStatus.DRAFT]
        )
        result = await document_service.search_documents(query)
        assert result.total_count == 2
    
    @pytest.mark.asyncio
    async def test_statistics(self, document_service, sample_metadata, sample_content):
        """Test getting statistics."""
        # Create some documents
        await document_service.create_document(
            sample_content, sample_metadata, "doc1.txt", "user1"
        )
        await document_service.create_document(
            b"PDF content", sample_metadata, "doc2.pdf", "user2"
        )
        
        # Get statistics
        stats = await document_service.get_statistics()
        
        assert stats["total_documents"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["status_distribution"]["draft"] == 2
        assert stats["type_distribution"]["text"] == 1
        assert stats["type_distribution"]["pdf"] == 1


class TestDocumentUtilities:
    """Test document utility functions."""
    
    def test_get_document_service_singleton(self):
        """Test getting global document service."""
        service1 = get_document_service()
        service2 = get_document_service()
        
        assert service1 is service2  # Should be same instance
    
    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        with patch('backend.services.document.get_document_service') as mock_service:
            mock_instance = Mock()
            mock_instance.create_document = AsyncMock(return_value="doc-123")
            mock_instance.search_documents = AsyncMock(return_value=SearchResult(
                documents=[], total_count=0, page_count=0, current_page=1, search_time_ms=10
            ))
            mock_instance.get_document_content = AsyncMock(return_value=b"content")
            mock_service.return_value = mock_instance
            
            # Test create_document
            metadata = DocumentMetadata(title="Test")
            doc_id = await create_document(b"content", metadata, "test.txt", "user")
            assert doc_id == "doc-123"
            
            # Test search_documents
            query = SearchQuery(text="test")
            result = await search_documents(query)
            assert result.total_count == 0
            
            # Test get_document_content
            content = await get_document_content("doc-123")
            assert content == b"content"


class TestDocumentEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_invalid_operations(self, document_service):
        """Test operations on non-existent documents."""
        # Update non-existent document
        result = await document_service.update_document("non-existent", b"content")
        assert result is False
        
        # Delete non-existent document
        result = await document_service.delete_document("non-existent")
        assert result is False
        
        # Lock non-existent document
        result = await document_service.lock_document("non-existent", "user")
        assert result is False
        
        # Get versions of non-existent document
        versions = await document_service.get_document_versions("non-existent")
        assert versions == []
    
    @pytest.mark.asyncio
    async def test_locked_document_operations(self, document_service, sample_metadata, sample_content):
        """Test operations on locked documents."""
        # Create and lock document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "user1"
        )
        await document_service.lock_document(document_id, "user1")
        
        # Try to update locked document
        result = await document_service.update_document(
            document_id, b"new content", updated_by="user2"
        )
        assert result is False
        
        # Try to unlock with different user
        result = await document_service.unlock_document(document_id, "user2")
        assert result is False
        
        # Unlock with same user
        result = await document_service.unlock_document(document_id, "user1")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_version_operations(self, document_service, sample_metadata, sample_content):
        """Test version-related edge cases."""
        # Create document
        document_id = await document_service.create_document(
            sample_content, sample_metadata, "test.txt", "user"
        )
        
        # Try to restore non-existent version
        result = await document_service.restore_version(
            document_id, "non-existent-version", "user"
        )
        assert result is False
        
        # Try to restore version of non-existent document
        result = await document_service.restore_version(
            "non-existent", "version-id", "user"
        )
        assert result is False
    
    @pytest.mark.asyncio
    async def test_search_edge_cases(self, document_service):
        """Test search edge cases."""
        # Search with empty query
        query = SearchQuery()
        result = await document_service.search_documents(query)
        assert result.total_count == 0
        
        # Search with complex filters but no documents
        query = SearchQuery(
            text="nonexistent",
            tags=["nonexistent"],
            document_types=[DocumentType.VIDEO],
            status_filter=[DocumentStatus.ARCHIVED]
        )
        result = await document_service.search_documents(query)
        assert result.total_count == 0


class TestModule82BackendModule82:
    """Test module 82 integration and availability."""
    
    def test_module_availability(self):
        """Test that all required classes and functions are available."""
        # Test main classes
        assert DocumentService is not None
        assert Document is not None
        assert DocumentMetadata is not None
        assert DocumentVersion is not None
        assert LocalFileStorage is not None
        assert DocumentConverter is not None
        assert DocumentSearchEngine is not None
        
        # Test enums
        assert DocumentStatus is not None
        assert DocumentType is not None
        assert AccessLevel is not None
        assert VersionChangeType is not None
        
        # Test utility functions
        assert get_document_service is not None
        assert create_document is not None
        assert search_documents is not None
        assert get_document_content is not None
    
    def test_module_functionality(self):
        """Test basic module functionality."""
        service = DocumentService()
        assert service is not None
        
        # Test basic operations
        assert hasattr(service, 'create_document')
        assert hasattr(service, 'update_document')
        assert hasattr(service, 'delete_document')
        assert hasattr(service, 'search_documents')
        assert hasattr(service, 'get_document_content')
    
    def test_module_integration(self):
        """Test module integration with other components."""
        # Test that service can be instantiated and used
        service = get_document_service()
        stats = asyncio.run(service.get_statistics())
        
        assert isinstance(stats, dict)
        assert "total_documents" in stats
    
    @pytest.mark.asyncio
    async def test_full_document_workflow(self):
        """Test complete document management workflow."""
        service = DocumentService()
        
        # Create document
        metadata = DocumentMetadata(
            title="Workflow Test",
            description="Testing full workflow",
            author="Test User",
            tags=["workflow", "test"]
        )
        
        content = b"This is a test document for the workflow."
        
        doc_id = await service.create_document(
            file_content=content,
            metadata=metadata,
            file_name="workflow.txt",
            created_by="test_user"
        )
        
        assert doc_id is not None
        
        # Update document
        new_content = b"Updated content for workflow test."
        result = await service.update_document(
            document_id=doc_id,
            file_content=new_content,
            updated_by="test_user",
            changelog="Updated for workflow test"
        )
        assert result is True
        
        # Search for document
        query = SearchQuery(text="workflow")
        search_result = await service.search_documents(query)
        assert search_result.total_count == 1
        assert search_result.documents[0].id == doc_id
        
        # Get content
        retrieved_content = await service.get_document_content(doc_id)
        assert retrieved_content == new_content
        
        # Get statistics
        stats = await service.get_statistics()
        assert stats["total_documents"] == 1
