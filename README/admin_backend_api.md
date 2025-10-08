# Admin Backend API Documentation

## Overview

The Admin Backend API is a FastAPI-based RESTful service for managing vector stores across all agents in the university information system. It provides comprehensive endpoints for vector store creation, data refresh, health monitoring, and batch operations.

## 🚀 Quick Start

### Installation & Setup

```bash
# Install dependencies
pip install fastapi uvicorn

# Start the server
uvicorn admin_backend_api:app --reload --host 0.0.0.0 --port 8000
```

### Access Points

- **API Base URL**: `http://localhost:8000`
- **Interactive Docs**: `http://localhost:8000/docs`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

## 📋 API Endpoints

### Health & System Information

#### 1. Basic Health Check

```http
GET /health
```

**Response:**

```json
{
	"status": "healthy",
	"timestamp": "2025-09-15T14:30:00",
	"service": "University Admin API"
}
```

#### 2. Vector Stores Health Check

```http
GET /health/vector-stores
```

**Response:**

```json
{
	"status": "healthy",
	"total_stores": 3,
	"healthy_stores": 3,
	"stores": {
		"degree_programs": {
			"persist_dir": "data/vector_stores/degree_programs",
			"data_source": "data/degree_programs/degree_programs.json",
			"exists": true,
			"data_source_exists": true,
			"document_count": 248
		}
	},
	"timestamp": "2025-09-15T14:30:00"
}
```

#### 3. System Information

```http
GET /api/v1/system/info
```

**Response:**

```json
{
	"system": {
		"api_version": "1.0.0",
		"timestamp": "2025-09-15T14:30:00",
		"available_store_types": ["degree_programs", "faculty", "general"]
	},
	"statistics": {
		"total_stores": 3,
		"active_stores": 3,
		"total_documents": 8000
	},
	"stores": {
		/* detailed store info */
	}
}
```

### Vector Store Information

#### 4. Get All Vector Stores

```http
GET /api/v1/vector-stores
```

**Response:**

```json
{
	"degree_programs": {
		"type": "degree_programs",
		"persist_dir": "data/vector_stores/degree_programs",
		"data_source": "data/degree_programs/degree_programs.json",
		"exists": true,
		"data_source_exists": true,
		"document_count": 248
	},
	"faculty": {
		"type": "faculty",
		"persist_dir": "data/vector_stores/faculty",
		"data_source": "data/faculty",
		"exists": true,
		"data_source_exists": true,
		"document_count": 2020
	},
	"general": {
		"type": "general",
		"persist_dir": "data/vector_stores/general",
		"data_source": "data/general/raw",
		"exists": true,
		"data_source_exists": true,
		"document_count": 5715
	}
}
```

#### 5. Get Specific Vector Store Info

```http
GET /api/v1/vector-stores/{store_type}
```

**Parameters:**

- `store_type`: One of `degree_programs`, `faculty`, `general`

**Example:**

```http
GET /api/v1/vector-stores/degree_programs
```

**Response:**

```json
{
	"type": "degree_programs",
	"persist_dir": "data/vector_stores/degree_programs",
	"data_source": "data/degree_programs/degree_programs.json",
	"exists": true,
	"data_source_exists": true,
	"document_count": 248
}
```

### Vector Store Creation

#### 6. Create Specific Vector Store

```http
POST /api/v1/vector-stores/{store_type}/create
```

**Request Body:**

```json
{
	"force": true
}
```

**Parameters:**

- `store_type`: One of `degree_programs`, `faculty`, `general`
- `force`: Boolean - Force recreate existing store (default: false)

**Example:**

```http
POST /api/v1/vector-stores/degree_programs/create
Content-Type: application/json

{
  "force": true
}
```

**Response:**

```json
{
	"success": true,
	"message": "Vector store 'degree_programs' created successfully",
	"data": {
		"store_type": "degree_programs",
		"force": true
	},
	"timestamp": "2025-09-15T14:30:00"
}
```

### Data Refresh (Scrapers + Vector Store Rebuild)

#### 7. Refresh Vector Stores

```http
POST /api/v1/vector-stores/refresh
```

**Request Body:**

```json
{
	"store_types": ["degree_programs", "faculty"]
}
```

**Parameters:**

- `store_types`: Array of store types to refresh. If null/empty, refreshes all stores.

**Examples:**

**Refresh All Stores:**

```http
POST /api/v1/vector-stores/refresh
Content-Type: application/json

{
  "store_types": null
}
```

**Refresh Specific Stores:**

```http
POST /api/v1/vector-stores/refresh
Content-Type: application/json

{
  "store_types": ["degree_programs", "faculty"]
}
```

**Response:**

```json
{
	"success": true,
	"message": "Data refresh completed. 2/2 stores refreshed successfully.",
	"data": {
		"results": {
			"degree_programs": true,
			"faculty": true
		},
		"summary": {
			"total": 2,
			"successful": 2,
			"failed": 0
		}
	},
	"timestamp": "2025-09-15T14:30:00"
}
```

### Batch Operations

#### 8. Batch Operations on Multiple Stores

```http
POST /api/v1/vector-stores/batch
```

**Request Body:**

```json
{
	"action": "create",
	"store_types": ["degree_programs", "faculty"],
	"force": true
}
```

**Parameters:**

- `action`: Either `"create"` or `"info"`
- `store_types`: Array of store types to operate on
- `force`: Boolean - For create action, force recreate (default: false)

**Examples:**

**Batch Create:**

```http
POST /api/v1/vector-stores/batch
Content-Type: application/json

{
  "action": "create",
  "store_types": ["degree_programs", "faculty"],
  "force": true
}
```

**Batch Info:**

```http
POST /api/v1/vector-stores/batch
Content-Type: application/json

{
  "action": "info",
  "store_types": ["degree_programs", "faculty", "general"]
}
```

**Response:**

```json
{
	"overall_success": true,
	"results": {
		"degree_programs": {
			"success": true,
			"message": "Vector store 'degree_programs' created successfully"
		},
		"faculty": {
			"success": true,
			"message": "Vector store 'faculty' created successfully"
		}
	},
	"summary": "Batch create completed. 2/2 operations successful.",
	"timestamp": "2025-09-15T14:30:00"
}
```

## 🔧 Usage Examples

### Python Client Examples

#### Basic Operations

```python
import requests

BASE_URL = "http://localhost:8000"

# Check system health
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Get all vector stores info
response = requests.get(f"{BASE_URL}/api/v1/vector-stores")
stores = response.json()
print(f"Found {len(stores)} vector stores")

# Create a specific vector store
response = requests.post(
    f"{BASE_URL}/api/v1/vector-stores/degree_programs/create",
    json={"force": True}
)
print(response.json())
```

#### Data Refresh

```python
# Refresh all data (runs all scrapers)
response = requests.post(
    f"{BASE_URL}/api/v1/vector-stores/refresh",
    json={"store_types": None}
)
result = response.json()
print(f"Refresh completed: {result['success']}")
print(f"Message: {result['message']}")

# Refresh specific stores
response = requests.post(
    f"{BASE_URL}/api/v1/vector-stores/refresh",
    json={"store_types": ["degree_programs"]}
)
```

#### Batch Operations

```python
# Batch create multiple stores
response = requests.post(
    f"{BASE_URL}/api/v1/vector-stores/batch",
    json={
        "action": "create",
        "store_types": ["degree_programs", "faculty"],
        "force": True
    }
)
result = response.json()
print(f"Batch operation success: {result['overall_success']}")
```

### JavaScript/Frontend Examples

#### Using Fetch API

```javascript
const BASE_URL = "http://localhost:8000";

// Get vector stores info
async function getVectorStores() {
	try {
		const response = await fetch(`${BASE_URL}/api/v1/vector-stores`);
		const stores = await response.json();
		console.log("Vector stores:", stores);
		return stores;
	} catch (error) {
		console.error("Error fetching vector stores:", error);
	}
}

// Create vector store
async function createVectorStore(storeType, force = false) {
	try {
		const response = await fetch(
			`${BASE_URL}/api/v1/vector-stores/${storeType}/create`,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ force }),
			}
		);
		const result = await response.json();
		console.log("Create result:", result);
		return result;
	} catch (error) {
		console.error("Error creating vector store:", error);
	}
}

// Refresh data
async function refreshData(storeTypes = null) {
	try {
		const response = await fetch(`${BASE_URL}/api/v1/vector-stores/refresh`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({ store_types: storeTypes }),
		});
		const result = await response.json();
		console.log("Refresh result:", result);
		return result;
	} catch (error) {
		console.error("Error refreshing data:", error);
	}
}
```

### CURL Examples

#### Health Check

```bash
curl -X GET "http://localhost:8000/health"
```

#### Get Vector Stores

```bash
curl -X GET "http://localhost:8000/api/v1/vector-stores"
```

#### Create Vector Store

```bash
curl -X POST "http://localhost:8000/api/v1/vector-stores/degree_programs/create" \
     -H "Content-Type: application/json" \
     -d '{"force": true}'
```

#### Refresh All Data

```bash
curl -X POST "http://localhost:8000/api/v1/vector-stores/refresh" \
     -H "Content-Type: application/json" \
     -d '{"store_types": null}'
```

#### Batch Operations

```bash
curl -X POST "http://localhost:8000/api/v1/vector-stores/batch" \
     -H "Content-Type: application/json" \
     -d '{
       "action": "create",
       "store_types": ["degree_programs", "faculty"],
       "force": true
     }'
```

## 📝 Data Models

### VectorStoreInfo

```json
{
	"type": "string",
	"persist_dir": "string",
	"data_source": "string",
	"exists": "boolean",
	"data_source_exists": "boolean",
	"document_count": "integer|string|null"
}
```

### OperationResponse

```json
{
	"success": "boolean",
	"message": "string",
	"data": "object|null",
	"timestamp": "datetime"
}
```

### BatchOperationResponse

```json
{
	"overall_success": "boolean",
	"results": "object",
	"summary": "string",
	"timestamp": "datetime"
}
```

## 🎯 Store Types

The API supports three vector store types:

1. **`degree_programs`**

   - Source: University degree program data (JSON)
   - Contains: Program details, curriculum, requirements
   - Used by: Degree Advisor Agent

2. **`faculty`**

   - Source: Faculty information (JSON files)
   - Contains: Faculty profiles, publications, expertise
   - Used by: Faculty Agent

3. **`general`**
   - Source: General university information (Markdown files)
   - Contains: Policies, procedures, general information
   - Used by: General RAG System

## 🔄 Data Refresh Process

When you call the refresh endpoint, the API automatically:

1. **Runs Scrapers**: Executes appropriate scrapers to fetch fresh data

   - `scrapers/degree_scraper.py` → Updates degree program data
   - `scrapers/faculty_scraper.py` → Updates faculty information
   - `scrapers/general_scraper.py` → Updates general university data

2. **Processes Data**: Converts raw data into structured documents

3. **Rebuilds Vector Stores**: Creates fresh vector stores with updated data

4. **Validates**: Ensures new stores are working correctly

5. **Reports Results**: Returns success/failure status for each store

## ⚠️ Error Handling

### HTTP Status Codes

- `200`: Success
- `400`: Bad Request (invalid parameters)
- `500`: Internal Server Error
- `503`: Service Unavailable (manager not initialized)

### Error Response Format

```json
{
	"detail": "Error message",
	"timestamp": "2025-09-15T14:30:00"
}
```

### Common Errors

1. **Invalid Store Type**

   ```json
   {
   	"detail": "Invalid store type: invalid_type. Valid types: ['degree_programs', 'faculty', 'general']"
   }
   ```

2. **Vector Store Creation Failed**

   ```json
   {
   	"detail": "Error creating vector store: Data source not found"
   }
   ```

3. **Scraper Execution Failed**
   ```json
   {
   	"success": false,
   	"message": "Data refresh completed. 1/2 stores refreshed successfully.",
   	"data": {
   		"results": {
   			"degree_programs": true,
   			"faculty": false
   		}
   	}
   }
   ```

## 🚀 Deployment

### Development

```bash
uvicorn admin_backend_api:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
uvicorn admin_backend_api:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Deployment

```dockerfile
FROM python:3.10

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "admin_backend_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🔒 Security Considerations

1. **Authentication**: Add API key or JWT authentication for production
2. **CORS**: Configure CORS appropriately for your domain
3. **Rate Limiting**: Implement rate limiting for API endpoints
4. **Input Validation**: All inputs are validated using Pydantic models
5. **Error Handling**: Sensitive information is not exposed in error messages

## 📊 Monitoring & Logging

The API includes comprehensive logging:

- **Application Logs**: Structured logging with timestamps
- **Health Endpoints**: Monitor system and vector store health
- **Operation Tracking**: All operations are logged with results
- **Error Tracking**: Detailed error logging for debugging

## 🔧 Configuration

Key configuration options:

- **Host/Port**: Set via uvicorn command line
- **Log Level**: Configurable via uvicorn `--log-level`
- **CORS**: Modify CORS middleware settings
- **Thread Pool**: Adjust `max_workers` for concurrent operations

## 📈 Performance Notes

- **Async Operations**: Vector store operations run in thread pool
- **Background Tasks**: Large operations can be run in background
- **Concurrent Requests**: FastAPI handles multiple requests concurrently
- **Memory Usage**: Monitor memory usage during large vector store operations

This API provides a complete administrative interface for managing your multi-agent vector store system with comprehensive error handling, monitoring, and documentation.
