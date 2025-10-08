# Degree Advisor Agent

A sophisticated AI-powered degree advisor agent built with LangChain and LangGraph that helps students choose the right degree programs based on their interests, career goals, and academic background.

## Features

### 🎯 Core Capabilities

- **Smart Degree Search**: Find programs by field, level (BS/MS/PhD), and keywords
- **Personalized Recommendations**: Get degree suggestions based on interests and career goals
- **Program Comparison**: Side-by-side comparison of different degree programs
- **Detailed Information**: Access comprehensive program details including curriculum, requirements, and career outcomes
- **Multi-Agent Integration**: Seamlessly plugs into LangGraph multi-agent systems

### 🛠 Technical Features

- **Hybrid Retrieval**: Combines vector similarity and BM25 for optimal search results
- **Specialized Vector Store**: Optimized for degree program data with smart chunking
- **LangGraph Compatible**: Designed for multi-agent workflows
- **Groq LLM Integration**: Fast and efficient language model responses
- **Nomic Embeddings**: High-quality semantic search with nomic-embed-text
- **Chroma Vector Store**: Persistent and scalable vector storage

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Degree Advisor Agent                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   Search    │  │ Recommend   │  │  Compare    │       │
│  │   Tools     │  │   Tools     │  │   Tools     │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │            LangGraph State Management            │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   Vector    │  │  Hybrid     │  │   Groq      │       │
│  │   Store     │  │ Retrieval   │  │    LLM      │       │
│  │  (Chroma)   │  │  (BM25+VS)  │  │             │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Installation

1. **Install dependencies**:

```bash
pip install -r requirements_degree_advisor.txt
```

2. **Set up environment variables**:
   Create a `.env` file with:

```env
GROQ_API_KEY=your_groq_api_key_here
```

3. **Ensure Ollama is running** (for nomic-embed-text embeddings):

```bash
ollama pull nomic-embed-text
ollama serve
```

## Quick Start

### Basic Usage

```python
from degree_advisor_agent import get_degree_advisor_agent

# Initialize the agent
agent = get_degree_advisor_agent()

# Ask questions about degree programs
response = agent.invoke("I'm interested in artificial intelligence. What programs do you recommend?")
print(response)
```

### Using Individual Tools

```python
from degree_advisor_agent import (
    search_degrees_by_field,
    recommend_degrees_for_interest,
    compare_degree_programs
)

# Search by field
cs_programs = search_degrees_by_field.invoke({"field": "Computer Science"})

# Get recommendations
ai_recommendations = recommend_degrees_for_interest.invoke({
    "interest_area": "artificial intelligence",
    "level": "Bachelor"
})

# Compare programs
comparison = compare_degree_programs.invoke({
    "program1": "Computer Science",
    "program2": "Software Engineering"
})
```

### LangGraph Integration

```python
from langgraph.graph import StateGraph, MessagesState
from degree_advisor_agent import DegreeAdvisorAgent

class MultiAgentState(MessagesState):
    current_agent: str
    recommendations: dict

def degree_advisor_node(state):
    agent = DegreeAdvisorAgent()
    response = agent.advisor_node(state)
    return response

# Create multi-agent workflow
workflow = StateGraph(MultiAgentState)
workflow.add_node("degree_advisor", degree_advisor_node)
# Add other agents...

multi_agent_system = workflow.compile()
```

## Available Tools

### 🔍 Search Tools

- `search_degrees_by_field(field: str)`: Find programs in specific fields
- `search_degrees_by_level(level: str)`: Filter by degree level (Bachelor/Master/PhD)
- `get_degree_details(program_title: str)`: Get comprehensive program information

### 💡 Advisory Tools

- `recommend_degrees_for_interest(interest_area: str, level: str)`: Personalized recommendations
- `compare_degree_programs(program1: str, program2: str)`: Side-by-side comparison

### Example Queries

The agent can handle various types of questions:

**Field-based queries:**

- "What computer science programs do you offer?"
- "I want to study business. What are my options?"
- "Show me all engineering degrees."

**Interest-based recommendations:**

- "I love AI and machine learning. What should I study?"
- "I want to work in finance. Which degree is best?"
- "I'm interested in cybersecurity. What programs do you recommend?"

**Comparison requests:**

- "Compare Computer Science vs Software Engineering"
- "What's the difference between BBA and MBA?"
- "Should I choose Electrical Engineering or Computer Engineering?"

**Detailed information:**

- "Tell me about the Computer Science curriculum"
- "What are the admission requirements for the MBA program?"
- "How long does the Data Science degree take?"

## Demo Script

Run the interactive demonstration:

```bash
python demo_degree_advisor.py
```

This provides several demo modes:

1. Individual tool testing
2. Conversation scenarios
3. LangGraph integration demo
4. Interactive chat mode

## Data Structure

The agent processes degree program data with the following structure:

```python
{
    "title": "Bachelor of Science (Computer Science)",
    "level": "Bachelor",
    "field": "Computer Science",
    "eligibility": "HSSC or equivalent",
    "vision": "Program vision statement",
    "mission": "Program mission statement",
    "career_opportunities": "Career paths description",
    "peos": ["Educational objective 1", "..."],
    "plos": ["Learning outcome 1", "..."],
    "semesters": {
        "semester_1": [
            {
                "code": "CS101",
                "name": "Introduction to Programming",
                "credit_hours": "3+1"
            }
        ]
    },
    "total_credit_hours": 135,
    "duration_years": 4
}
```

## Configuration

The agent uses configuration from `config.py`:

```python
# LLM Configuration
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.1,
    streaming=True,
)

# Embeddings Configuration
embeddings = OllamaEmbeddings(model="nomic-embed-text")
```

## Multi-Agent Integration

The degree advisor is designed to work seamlessly in multi-agent systems:

### State Management

```python
class DegreeAdvisorState(MessagesState):
    current_query: str
    search_results: List[str]
    recommendations: List[str]
```

### Graph Integration

```python
def setup_graph(self):
    workflow = StateGraph(DegreeAdvisorState)
    workflow.add_node("advisor", self.advisor_node)
    workflow.add_node("tools", self.tool_node)
    workflow.add_edge("advisor", "tools")
    workflow.add_edge("tools", "advisor")
    self.graph = workflow.compile()
```

## Performance Optimization

### Vector Store Optimization

- **Chunking Strategy**: 1000 tokens with 200 overlap for optimal retrieval
- **Hybrid Retrieval**: 60% vector similarity + 40% MMR for diversity
- **Persistent Storage**: Chroma DB for fast startup times

### Query Optimization

- **Smart Routing**: Keyword-based routing to appropriate tools
- **Context Filtering**: Relevant document selection before LLM processing
- **Caching**: Vector store persistence eliminates re-indexing

## Troubleshooting

### Common Issues

1. **Vector store not found**:

   - Ensure `degree_programs.json` exists in `data/degree_programs/`
   - Check file permissions and path

2. **Groq API errors**:

   - Verify `GROQ_API_KEY` in environment
   - Check API quota and rate limits

3. **Ollama connection issues**:

   - Ensure Ollama service is running
   - Verify `nomic-embed-text` model is pulled

4. **Import errors**:
   - Install all requirements: `pip install -r requirements_degree_advisor.txt`
   - Check Python version compatibility (3.8+)

### Performance Tips

- **First run**: Initial vector store creation takes 1-2 minutes
- **Subsequent runs**: Use persistent storage for instant startup
- **Large datasets**: Adjust chunk size and retrieval parameters
- **Memory usage**: Monitor Chroma DB size for large document sets

## Contributing

To extend the agent:

1. **Add new tools**: Implement functions with `@tool` decorator
2. **Modify prompts**: Update `DEGREE_ADVISOR_PROMPT` for different behavior
3. **Enhance retrieval**: Adjust vector store parameters in `DegreeVectorStore`
4. **Extend state**: Add fields to `DegreeAdvisorState` for new capabilities

## License

This project is part of a university knowledge base system. Please check your institution's policies regarding AI tool usage and data handling.

---

**Built with LangChain 🦜🔗 and LangGraph 🕸️**
