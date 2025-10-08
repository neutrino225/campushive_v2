# Multi-Agent Vector Store Management System

## Overview

This system provides centralized vector store management for multiple AI agents in your university information system. All vector stores are now managed through a single, unified interface that abstracts the complexity of vector store creation, loading, and maintenance.

## Architecture

### Core Components

1. **VectorStoreManager**: Central class that manages all vector stores
2. **VectorStoreType**: Enum defining supported store types
3. **DataProcessor**: Base class for processing different data formats
4. **Admin Interface**: Scripts for managing the system

### Directory Structure

```
data/
├── vector_stores/          # All vector stores (new centralized location)
│   ├── degree_programs/    # Degree advisor vector store
│   ├── faculty/           # Faculty information vector store
│   └── general/           # General university information vector store
├── degree_programs/       # Degree program source data
│   └── degree_programs.json
├── faculty/              # Faculty source data
│   ├── CS.json
│   ├── EE.json
│   └── ...
└── general/             # General university information
    └── raw/             # Markdown files
        └── *.md
```

## Features

### Centralized Management

- Single point of control for all vector stores
- Consistent configuration across agents
- Unified data processing pipeline

### Data Source Processing

- **Degree Programs**: JSON processing with structured program information
- **Faculty**: JSON processing with faculty profiles and publications
- **General**: Markdown file processing for university information

### Retrieval Configuration

- Hybrid retrieval with BM25 + Vector Similarity + MMR
- Configurable parameters per store type
- Ensemble weights optimization

### Admin Functions

- Create/recreate vector stores
- Run scrapers and refresh data
- Monitor store status and health
- Test agent functionality

## Usage

### Administrative Commands

```bash
# Check status of all vector stores
python admin_vector_store.py --action info

# Check specific store
python admin_vector_store.py --action info --store-type degree_programs

# Create all vector stores
python admin_vector_store.py --action create --all

# Create specific store (with force recreate)
python admin_vector_store.py --action create --store-type faculty --force

# Refresh data (runs scrapers and rebuilds stores)
python admin_vector_store.py --action refresh --all

# Refresh specific store
python admin_vector_store.py --action refresh --store-type general

# Test all agents
python admin_vector_store.py --action test
```

### Programmatic Usage

#### Using VectorStoreManager

```python
from vector_store_manager import VectorStoreManager, VectorStoreType
from config import embeddings

# Initialize manager
manager = VectorStoreManager(embeddings=embeddings)

# Get retriever for any agent
retriever = manager.get_retriever(VectorStoreType.DEGREE_PROGRAMS, use_ensemble=True)

# Create or refresh vector store
vector_store = manager.create_vector_store(VectorStoreType.FACULTY, force_recreate=True)

# Get store information
info = manager.get_store_info(VectorStoreType.GENERAL)
```

#### Agent Integration

Each agent now uses the centralized system:

```python
# Degree Advisor Agent
from degree_advisor_agent import get_degree_advisor_agent
agent = get_degree_advisor_agent()
response = agent.invoke("What computer science programs do you offer?")

# Faculty Agent
from faculty_agent import FacultyAgent
agent = FacultyAgent()
response = agent.answer("Who teaches machine learning?")

# General RAG
from rag import AdvancedUniversityRAGCLI
cli = AdvancedUniversityRAGCLI()
```

## Configuration

### Vector Store Types

1. **DEGREE_PROGRAMS**

   - Source: `data/degree_programs/degree_programs.json`
   - Processor: `DegreeDataProcessor`
   - Features: Program details, curriculum, requirements

2. **FACULTY**

   - Source: `data/faculty/*.json`
   - Processor: `FacultyDataProcessor`
   - Features: Faculty profiles, publications, expertise

3. **GENERAL**
   - Source: `data/general/raw/*.md`
   - Processor: `GeneralDataProcessor`
   - Features: University policies, general information

### Retrieval Configuration

Each store type has optimized configurations:

```python
# Degree Programs
chunk_size=1000, chunk_overlap=200
bm25_k=15, embed_k=15, mmr_k=15
ensemble_weights=(0.5, 0.3, 0.2)

# Faculty
chunk_size=800, chunk_overlap=150
bm25_k=12, embed_k=12, mmr_k=12
ensemble_weights=(0.5, 0.3, 0.2)

# General
chunk_size=800, chunk_overlap=100
bm25_k=15, embed_k=15, mmr_k=15
ensemble_weights=(0.5, 0.3, 0.2)
```

## Data Refresh Workflow

The system provides an automated data refresh workflow:

1. **Run Scrapers**: Execute appropriate scraper for each data type
2. **Backup**: Safely backup existing vector stores
3. **Process Data**: Convert raw data to documents
4. **Create Stores**: Build new vector stores with updated data
5. **Validate**: Test that new stores work correctly
6. **Clean Up**: Remove old backups

### Scraper Integration

The system automatically runs these scrapers:

- `scrapers/degree_scraper.py` → Updates degree program data
- `scrapers/faculty_scraper.py` → Updates faculty information
- `scrapers/general_scraper.py` → Updates general university data

## Error Handling

The system includes comprehensive error handling:

- **Graceful Degradation**: Agents fall back to existing stores if refresh fails
- **Data Validation**: Checks data source existence before processing
- **Atomic Updates**: Ensures stores are only replaced if creation succeeds
- **Logging**: Detailed logging for debugging and monitoring

## Migration from Old System

The old individual vector store files have been migrated:

- `degree_chroma_db/` → `data/vector_stores/degree_programs/`
- `faculty_chroma_db/` → `data/vector_stores/faculty/`
- `chroma_db/` → `data/vector_stores/general/`

Old agent code has been refactored to use the centralized system while maintaining the same external API.

## Best Practices

1. **Regular Refresh**: Run data refresh weekly or when source data changes
2. **Monitor Status**: Check vector store health regularly
3. **Test Agents**: Validate agent functionality after any changes
4. **Backup Data**: Keep backups of source data before running scrapers
5. **Version Control**: Track changes to vector store configurations

## Troubleshooting

### Common Issues

**Vector Store Not Found**

```bash
python admin_vector_store.py --action create --store-type <type>
```

**Data Source Missing**

- Check that source files exist in expected locations
- Run appropriate scraper to regenerate data

**Agent Errors**

```bash
python admin_vector_store.py --action test
```

**Performance Issues**

- Check document counts with `--action info`
- Consider adjusting chunk sizes or retrieval parameters

### Logs and Debugging

- Enable verbose logging: `--verbose`
- Check individual agent logs for detailed error information
- Monitor vector store creation logs for data processing issues

## Future Enhancements

1. **Multi-Environment Support**: Different configurations for dev/prod
2. **Incremental Updates**: Update only changed documents
3. **Performance Monitoring**: Track query latency and accuracy
4. **Auto-Scaling**: Dynamic parameter adjustment based on data size
5. **Web Interface**: GUI for vector store management

## API Reference

See `vector_store_manager.py` for detailed API documentation of all classes and methods.
