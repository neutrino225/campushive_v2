"""
Simplified ReAct-based exam generation agent with built-in memory.
Uses LangGraph's create_react_agent for natural conversation handling.
"""

from __future__ import annotations
from typing import Optional, AsyncGenerator, Dict
import sys
import re
from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from config import llm, embeddings
from vector_store_manager import VectorStoreManager, VectorStoreType


# ============================================================================
# Tools for the Exam Agent
# ============================================================================


@tool
def search_uploaded_lecture_content(query: str, user_id: int, session_id: str) -> str:
    """
    Search through uploaded lecture slides, notes, or course materials for relevant content.
    Use this to understand what topics were covered and get inspiration from actual lecture content.

    Args:
        query: What to search for (e.g., "networking protocols", "machine learning algorithms")
        user_id: The user's ID
        session_id: The session ID where documents were uploaded

    Returns:
        Relevant content from uploaded course materials
    """
    try:
        from multiagent.memory.retriever_manager import get_session_retriever

        retriever = get_session_retriever(user_id, session_id)

        if not retriever:
            return "❌ No course materials uploaded yet. Please upload lecture slides or notes first to generate contextual exam questions."

        # Retrieve relevant chunks
        docs = retriever.get_relevant_documents(query)

        if not docs:
            return f"No content found for '{query}' in uploaded materials."

        # Format results
        content_parts = []
        for i, doc in enumerate(docs[:10], 1):  # Top 5 most relevant chunks
            source = doc.metadata.get("source", "Unknown")
            content_parts.append(
                f"--- From {source} (Section {i}) ---\n{doc.page_content}"
            )

        return "\n\n".join(content_parts)
    except Exception as e:
        return f"Error retrieving uploaded content: {e}"


@tool
def search_exam_inspiration(
    course: str, topic: str = "", difficulty: str = "Hard"
) -> str:
    """
    Search for inspiration questions from past exams database.

    Args:
        course: The course name (e.g., "Computer Networks", "Artificial Intelligence")
        topic: Optional specific topic to focus on
        difficulty: Difficulty level (Easy, Medium, Hard)

    Returns:
        A collection of past exam questions for inspiration
    """
    try:
        manager = VectorStoreManager(embeddings=embeddings)
        retriever = manager.get_retriever(VectorStoreType.EXAMS)

        query = f"course: {course}"
        if topic:
            query += f", topic: {topic}"
        if difficulty:
            query += f", difficulty: {difficulty}"

        docs = retriever.invoke(query)
        if not docs:
            return f"No past exam questions found for {course}."

        # Format inspiration docs
        inspiration_parts = []
        for i, doc in enumerate(docs[:8], 1):
            inspiration_parts.append(
                f"--- Inspiration Question {i} ---\n{doc.page_content}"
            )

        return "\n\n".join(inspiration_parts)
    except Exception as e:
        return f"Error retrieving inspiration: {e}"


@tool
def calculate_exam_marks(exam_text: str) -> str:
    """
    Calculate total marks from an exam by parsing mark allocations.
    Helps verify marks add up correctly.

    Args:
        exam_text: The exam text containing mark allocations

    Returns:
        Breakdown of marks by section and total
    """
    # Extract all mark allocations [X marks] or (X marks)
    marks_pattern = r"\[(\d+)\s*marks?\]|\((\d+)\s*marks?\)"
    marks_found = re.findall(marks_pattern, exam_text, re.IGNORECASE)

    # Flatten tuples and convert to integers
    all_marks = [int(m[0] or m[1]) for m in marks_found]

    if not all_marks:
        return "⚠️ No mark allocations found in exam text"

    # Try to break down by sections
    section_a_marks = 0
    section_b_marks = 0
    section_c_marks = 0

    # Split by sections and calculate
    sections = re.split(r"Section\s+[ABC]", exam_text, flags=re.IGNORECASE)

    if len(sections) >= 2:  # Has Section A
        section_a_text = sections[1] if len(sections) > 1 else ""
        section_a_marks_found = re.findall(marks_pattern, section_a_text, re.IGNORECASE)
        section_a_marks = sum(int(m[0] or m[1]) for m in section_a_marks_found)

    if len(sections) >= 3:  # Has Section B
        section_b_text = sections[2] if len(sections) > 2 else ""
        section_b_marks_found = re.findall(marks_pattern, section_b_text, re.IGNORECASE)
        section_b_marks = sum(int(m[0] or m[1]) for m in section_b_marks_found)

    if len(sections) >= 4:  # Has Section C
        section_c_text = sections[3] if len(sections) > 3 else ""
        section_c_marks_found = re.findall(marks_pattern, section_c_text, re.IGNORECASE)
        section_c_marks = sum(int(m[0] or m[1]) for m in section_c_marks_found)

    total = sum(all_marks)

    result = f"MARKS BREAKDOWN:\n"
    if section_a_marks > 0:
        result += f"  Section A: {section_a_marks} marks\n"
    if section_b_marks > 0:
        result += f"  Section B: {section_b_marks} marks\n"
    if section_c_marks > 0:
        result += f"  Section C: {section_c_marks} marks\n"
    result += f"  TOTAL: {total} marks\n"

    # Validation hints
    if 150 >= total >= 100:
        result += "Total matches Final Exam (100-150 marks)"
    elif total == 50:
        result += "Total matches Sessional Exam (50 marks)"
    else:
        result += f"⚠️ Total is {total} marks (Expected: 50 or 100)"

    return result


@tool
def validate_exam_structure(
    exam_text: str, exam_type: str = "final", total_marks: int = 100
) -> str:
    """
    Validate that generated exam follows the required structure and formatting rules.

    Args:
        exam_text: The generated exam text to validate
        exam_type: Type of exam ("final" or "sessional")
        total_marks: Expected total marks (for reference only, validation is flexible)

    Returns:
        Validation result with pass/fail and specific issues found
    """
    checks = []
    issues = []

    # Check for tool output leakage
    if "Inspiration Question" in exam_text or "--- Inspiration" in exam_text:
        issues.append("Tool output visible")
        checks.append("Clean output (tool outputs hidden)")
    else:
        checks.append("Clean output (tool outputs hidden)")

    # Check for answer blanks
    if "Answer:" in exam_text or "_______" in exam_text:
        issues.append("Answer blanks found")
        checks.append("No answer blanks")
    else:
        checks.append("No answer blanks")

    # Check for section structure
    has_section_a = bool(re.search(r"Section\s+A", exam_text, re.IGNORECASE))
    has_section_b = bool(re.search(r"Section\s+B", exam_text, re.IGNORECASE))

    if not has_section_a:
        issues.append("Missing Section A (MCQs)")
        checks.append("Section A (MCQs)")
    else:
        checks.append("Section A (MCQs)")

    if not has_section_b:
        issues.append("Missing Section B (Short/Medium Questions)")
        checks.append("Section B (Short/Medium)")
    else:
        checks.append("Section B (Short/Medium)")

    # For final exams, ALWAYS require Section C (3-section structure)
    if exam_type == "final":
        has_section_c = bool(re.search(r"Section\s+C", exam_text, re.IGNORECASE))
        if not has_section_c:
            issues.append("Missing Section C (Long Questions) - Final exams must have 3 sections")
            checks.append("Section C (Long Questions)")
        else:
            checks.append("Section C (Long Questions)")

    # Check MCQ format (should have A. B. C. D. options)
    if has_section_a:
        mcq_pattern = r"[A-D]\.\s+.+"
        mcq_options = re.findall(mcq_pattern, exam_text)
        if len(mcq_options) < 4:
            issues.append("MCQs don't follow A/B/C/D format")
            checks.append("MCQ format (A/B/C/D)")
        else:
            checks.append("MCQ format (A/B/C/D)")

    # Check for marks allocation
    marks_pattern = r"\[(\d+)\s*marks?\]|\((\d+)\s*marks?\)"
    marks_found = re.findall(marks_pattern, exam_text, re.IGNORECASE)
    if not marks_found:
        issues.append("No marks allocation found")
        checks.append("Marks allocation")
    else:
        # Calculate total marks
        all_marks = [int(m[0] or m[1]) for m in marks_found]
        calculated_total = sum(all_marks)

        # For flexible total marks, just check that marks are allocated (not strict matching)
        if calculated_total <= 0:
            issues.append("Invalid marks allocation")
            checks.append("Marks allocation")
        else:
            checks.append(f"Marks allocated (Total: {calculated_total} marks)")

    # Check for answer key (faculty only - check if present)
    has_answer_key = bool(
        re.search(r"ANSWER\s+KEY|Answer\s+Key", exam_text, re.IGNORECASE)
    )
    if has_answer_key:
        checks.append("Answer key included")

    # Build result with progressive checks
    result = "VALIDATION CHECKS:\n" + "\n".join(checks)

    # Summary
    if not issues:
        result += "\n\nALL CHECKS PASSED - Exam is ready!"
        return result
    else:
        result += (
            "\n\n ISSUES FOUND:\n"
            + "\n".join(issues)
            + "\n\n Fix these and validate again."
        )
        return result


# ============================================================================
# Exam ReAct Agent
# ============================================================================


class ExamReactAgent:
    """
    A ReAct agent for exam generation with built-in conversational memory.
    The agent naturally handles:
    - Initial exam generation requests
    - Clarifications (e.g., "Follow the full final-exam pattern")
    - Modifications (e.g., "Add one more question", "Make it harder")
    - Multi-turn conversations
    """

    def __init__(self):
        """Initialize the exam ReAct agent with memory."""
        self.checkpointer = MemorySaver()
        self.current_user_id = None
        self.current_session_id = None
        self.agent = self._create_agent()

    def _create_agent(self):
        """Create the ReAct agent with tools and system prompt."""

        # Create tool wrapper that injects user context
        @tool("search_uploaded_lecture_content")
        def search_uploaded_content_wrapper(query: str) -> str:
            """
            Search through uploaded lecture slides, notes, or course materials.
            Use this to understand what topics were covered and get inspiration from actual lecture content.

            Args:
                query: What to search for (e.g., "networking protocols", "machine learning algorithms")

            Returns:
                Relevant content from uploaded course materials
            """
            try:
                import logging

                logger = logging.getLogger(__name__)
                from multiagent.memory.retriever_manager import get_session_retriever
                from multiagent.memory import session_context as _sess

                # Use stored user context, fallback to implicit session context if needed
                uid = self.current_user_id
                sid = self.current_session_id
                if uid is None or sid is None:
                    try:
                        ctx_uid, ctx_sid = _sess.get_current()
                        uid = uid if uid is not None else ctx_uid
                        sid = sid if sid is not None else ctx_sid
                    except Exception:
                        pass
                if uid is None or sid is None:
                    logger.warning(
                        "[ExamReactAgent] No user/session context available in tool after fallback. current_user_id/current_session_id is None."
                    )
                    return "⚠️ No user context available. Uploaded documents feature requires user authentication."

                logger.info(
                    f"[ExamReactAgent] Retrieving session docs for user_id={uid}, session_id={sid}"
                )
                retriever = get_session_retriever(uid, sid)

                if not retriever:
                    logger.warning(
                        f"[ExamReactAgent] No retriever found for user_id={uid}, session_id={sid}"
                    )
                    return "❌ No course materials uploaded yet. Please upload lecture slides or notes first to generate contextual exam questions."

                # Retrieve relevant chunks
                docs = retriever.get_relevant_documents(query)
                logger.info(
                    f"[ExamReactAgent] Retrieved {len(docs) if docs else 0} docs for query='{query}'"
                )

                if not docs:
                    return f"No content found for '{query}' in uploaded materials."

                # Format results
                content_parts = []
                for i, doc in enumerate(docs[:5], 1):  # Top 5 most relevant chunks
                    source = doc.metadata.get("source", "Unknown")
                    content_parts.append(
                        f"--- From {source} (Section {i}) ---\n{doc.page_content}"
                    )

                return "\n\n".join(content_parts)
            except Exception as e:
                return f"Error retrieving uploaded content: {e}"

        # Define tools (with wrapper for uploaded content)
        tools = [
            search_uploaded_content_wrapper,  # Uses context from instance
            search_exam_inspiration,
            calculate_exam_marks,
            validate_exam_structure,
        ]

        # Create the agent with checkpointer for memory
        return create_react_agent(
            model=llm,
            tools=tools,
            checkpointer=self.checkpointer,
            name="Exam Agent",
        )

    def _get_system_message(self, user_role: str = "student") -> str:
        """Get the system message based on user role."""
        if (user_role or "").lower() == "faculty":
            return """You are an expert exam creator for university faculty.

**YOUR PRIMARY TASK**: Generate complete, well-structured university exams based on user requirements.

**IMPORTANT TOOL USAGE**:
- You have access to `search_uploaded_lecture_content` to query uploaded course materials (lectures, slides, notes)
- You have access to `search_exam_inspiration` to find past exam questions for inspiration
- You have access to `calculate_exam_marks` to verify marks add up correctly
- You have access to `validate_exam_structure` to verify your exam follows all rules
- **PRIORITY**: Always check for uploaded lecture content first using `search_uploaded_lecture_content`
- Use uploaded content to understand what topics were actually taught and generate contextual questions
- Use `search_exam_inspiration` for question style ideas from past exams
- NEVER include the raw tool output in your final exam
- NEVER mention "Inspiration Question" or tool outputs in your response
- Extract ideas from both sources, then create NEW original questions based on the actual lecture content

**DEFAULT BEHAVIOR (when no specific format is requested)**:
Generate a balanced exam with:
- MCQs (Multiple Choice Questions) for fundamental concepts
- Short/Medium Questions for understanding and application
- This ensures comprehensive assessment unless user specifies otherwise

**EXAM STRUCTURE PATTERNS YOU MUST FOLLOW**:

**FOR FINAL EXAMS (any total marks, typically 100-150 marks)**:
The exam MUST have 3 sections, with marks distributed appropriately:

- Section A (MCQs): ~30-40% of total marks
  • Multiple choice questions (adjust quantity based on total marks)
  • Cover fundamental concepts with challenging distractors
  • Each MCQ must have exactly 4 options (A, B, C, D)
  • Example: For 100 marks → 15-20 MCQs (2 marks each)
  • Example: For 150 marks → 20-25 MCQs (2-3 marks each)

- Section B (Short/Medium Questions): ~30-40% of total marks
  • Questions requiring detailed explanations, calculations, comparisons
  • Test understanding and application
  • Example: For 100 marks → 4-6 questions (6-8 marks each)
  • Example: For 150 marks → 6-8 questions (6-8 marks each)

- Section C (Long/Complex Questions): ~20-30% of total marks
  • Comprehensive questions with multi-part sub-questions (a), (b), (c)
  • Integration of concepts, real-world scenarios, critical thinking
  • Example: For 100 marks → 2-3 questions (8-12 marks each)
  • Example: For 150 marks → 3-4 questions (10-15 marks each)

**FOR SESSIONAL/MIDTERM EXAMS (60 minutes, 50 marks)**:
- Section A (MCQs): 20 marks (~20 min)
  • 20 questions (1 mark each)
  • Basic concepts and definitions
  
- Section B (Short Answers): 20 marks (~25 min)
  • 10 brief questions (2 marks each)
  • Concise explanations (2-3 lines)
  
- Section C (Application): 10 marks (~15 min)
  • 1-2 problems (5-10 marks each)
  • Calculations or simple applications

**FOR QUIZZES (20-30 minutes, approximately 15-20 total marks)**:
- Primarily consist of **MCQs** and **2-3 Short Questions**.
- Ensure total time is appropriate for the questions.

**FORMATTING RULES (STRICTLY ENFORCE)**:
1. **MCQs**: Use this exact format:
   ```
   Question text here?
   A. Option A text
   B. Option B text
   C. Option C text
   D. Option D text
   ```

2. **Short/Medium Questions**: Use this format:
   ```
   Q1. Question text here?
   Q2. Question text here?
   ```

3. **Long Questions**: Either:
   - Single question: `Q1. [Long question text]`
   - Multi-part: `Q1. (a) ... (b) ... (c) ...`

**DIFFICULTY LEVELS**:
- **Hard**: Multi-step reasoning, derivations, edge cases, plausible MCQ distractors
- **Medium**: Standard application of concepts
- **Easy**: Basic recall and simple understanding

**CRITICAL FORMATTING REQUIREMENTS**:
1. **DO NOT include answer blanks** - No "Answer: _______" lines
2. **DO NOT include solution templates** - No pre-filled answer sections
3. **DO NOT show tool outputs** - Never include "Inspiration Question" text
4. **QUESTIONS ONLY** - Just the questions with marks indicated

**ANSWER KEY** (Faculty only):
After the exam questions, add a separate section:
```
--- ANSWER KEY ---
[Provide correct answers for all questions]
```

**CONVERSATIONAL MEMORY**:
- You remember all previous messages in this conversation
- If user asks to "add more questions", modify the PREVIOUSLY GENERATED exam
- If user says "follow the pattern", apply it to their EARLIER request
- If user says "make it harder", increase difficulty of the EXISTING exam
- Always maintain context from previous turns

**HANDLING USER REQUIREMENTS**:
- If user specifies a format (e.g., "only MCQs", "only short questions"), follow their specification exactly
- If user specifies total marks, distribute them across the 3 sections appropriately
- If NO specific format is requested, generate a balanced exam with MCQs AND short questions (and long questions for final exams)
- If user requests conflicting requirements, ASK for clarification

**CRITICAL WORKFLOW** (FOLLOW THIS EXACTLY):
1. Use `search_exam_inspiration` tool to get ideas (silently, internal use only)
2. Create NEW original questions inspired by (but not copying) the examples
3. Generate the complete exam with proper structure and formatting
4. **MANDATORY**: Use `validate_exam_structure` tool to verify your exam is correct (internal check only)
5. If validation fails, FIX the issues and validate again until it passes
6. Add answer key in separate section at the end (Faculty MUST have answer key)
7. **ONLY AFTER VALIDATION PASSES**: Present the final, complete exam to the user

**VALIDATION IS MANDATORY** (but silent to user):
- Call `validate_exam_structure(exam_text=your_generated_exam, exam_type="final" or "sessional", total_marks=expected_total_marks)`
- If validation reports issues, fix them immediately WITHOUT showing the validation output to the user
- Keep validating and fixing until all checks pass
- Only present the FINAL, VALIDATED exam to the user
- The user should ONLY see the clean exam paper, not validation messages or tool outputs
"""
        else:
            return """You are a helpful exam generation assistant for students creating practice/mock exams.

**YOUR PRIMARY TASK**: Generate realistic practice exams for university students.

**IMPORTANT TOOL USAGE**:
- You have access to `search_uploaded_lecture_content` to query uploaded course materials (lectures, slides, notes)
- You have access to `search_exam_inspiration` to find past exam questions for inspiration
- You have access to `validate_exam_structure` to verify your exam follows all rules
- **PRIORITY**: Always check for uploaded lecture content first using `search_uploaded_lecture_content`
- Use uploaded content to understand what topics were actually taught and generate contextual questions
- Use `search_exam_inspiration` for question style ideas from past exams
- NEVER include the raw tool output in your final exam
- Extract ideas from both sources, then create NEW original questions based on the actual lecture content

**DEFAULT BEHAVIOR (when no specific format is requested)**:
Generate a balanced practice exam with:
- MCQs (Multiple Choice Questions) for fundamental concepts
- Short/Medium Questions for understanding and application
- This ensures comprehensive practice unless user specifies otherwise

**EXAM STRUCTURE PATTERNS**:

**FOR FINAL PRACTICE EXAMS (any total marks, typically 100-150 marks)**:
The exam should have 3 sections:
- Section A (MCQs): ~30-40% of total marks
- Section B (Short/Medium Questions): ~30-40% of total marks
- Section C (Long Questions): ~20-30% of total marks

**FOR SESSIONAL PRACTICE EXAMS (60 minutes, 50 marks)**:
- Section A (MCQs): 20 marks (20 questions)
- Section B (Short Answers): 20 marks (10 questions)
- Section C (Application): 10 marks (1-2 problems)

**FOR PRACTICE QUIZZES (20-30 minutes, approximately 15-20 total marks)**:
- Primarily consist of **MCQs** and **2-3 Short Questions**.
- Focus on recent or focused topics for quick self-assessment.

**FORMATTING RULES**:
Same as faculty exams - MCQs with A/B/C/D format, numbered questions (Q1, Q2, etc.)

**CRITICAL FORMATTING REQUIREMENTS**:
1. **DO NOT include answer blanks** - No "Answer: _______" lines
2. **DO NOT include solution templates** - No pre-filled answer sections
3. **DO NOT show tool outputs** - Never include "Inspiration Question" text
4. **QUESTIONS ONLY** - Just the questions with marks indicated

**CONVERSATIONAL MEMORY**:
- You remember all previous messages in this conversation
- Handle modifications, clarifications, and follow-ups naturally
- Maintain context from earlier turns

**HANDLING USER REQUIREMENTS**:
- If user specifies a format (e.g., "only MCQs", "only short questions"), follow their specification exactly
- If NO specific format is requested, generate MCQs AND short questions for comprehensive practice
- If user requests conflicting requirements, ASK for clarification

**NOTE**: These are PRACTICE exams for studying, so they should be realistic but not identical to actual exams.

**CRITICAL WORKFLOW** (FOLLOW THIS EXACTLY):
1. Use `search_exam_inspiration` tool to get ideas (silently, internal use only)
2. Create NEW original questions inspired by the examples
3. Generate the complete practice exam with proper structure
4. **MANDATORY**: Use `validate_exam_structure` tool to verify your exam is correct (internal check only)
5. If validation fails, FIX the issues and validate again until it passes
6. **ONLY AFTER VALIDATION PASSES**: Present the final, complete practice exam to the user

**VALIDATION IS MANDATORY** (but silent to user):
- Call `validate_exam_structure(exam_text=your_generated_exam, exam_type="final" or "sessional", total_marks=expected_total_marks)`
- If validation reports issues, fix them immediately WITHOUT showing the validation output to the user
- Keep validating and fixing until all checks pass
- Only present the FINAL, VALIDATED exam to the user
- The user should ONLY see the clean exam paper, not validation messages or tool outputs
"""

    def stream(
        self,
        question: str,
        session_id: str = "default",
        user_id: int = None,
        user_role: str = "student",
    ):
        """
        Streaming version with TRUE token-level streaming.

        Phase 1: Run the ReAct agent to completion (tool calls + validation)
        Phase 2: Stream the final validated exam token-by-token using LLM streaming

        This approach ensures quality (validation runs) while providing
        progressive visual feedback to users.

        Args:
            question: The user's question/request
            session_id: Unique session identifier for conversation memory
            user_id: User ID for accessing uploaded documents
            user_role: "student" or "faculty"

        Yields:
            Individual tokens of the final exam
        """
        # Store user context for tool access
        self.current_user_id = user_id
        self.current_session_id = session_id

        # Configuration for memory checkpointing
        config = {"configurable": {"thread_id": f"exam_react::{session_id}"}}

        # Get system message based on role
        system_message = self._get_system_message(user_role)

        # Phase 1: Run agent to completion, collecting the final validated exam
        final_exam_content = ""

        # Stream the agent's response
        for step in self.agent.stream(
            {
                "messages": [
                    SystemMessage(content=system_message),
                    HumanMessage(content=question),
                ]
            },
            config,
            stream_mode="values",
        ):
            messages = step.get("messages", [])
            if messages:
                last_msg = messages[-1]
                # Collect the final AI message content (skip tool calls and validation outputs)
                if hasattr(last_msg, "content") and last_msg.content:
                    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
                        content = last_msg.content

                        # Skip validation check messages and inspiration outputs
                        if (
                            "🔍 VALIDATION CHECKS:" not in content
                            and "--- Inspiration Question" not in content
                            and "❌ VALIDATION FAILED" not in content
                            and "❌ ISSUES FOUND:" not in content
                        ):
                            final_exam_content = content

        # Phase 2: Stream the final exam token-by-token
        if final_exam_content:
            for token in self._stream_final_exam(final_exam_content):
                yield token

    def _stream_final_exam(self, exam_content: str):
        """
        Stream the final exam token-by-token using LLM streaming.

        This is called after the agent completes validation and tool calls,
        allowing for true token-level streaming of the final response.

        Args:
            exam_content: The validated exam content to stream

        Yields:
            Individual tokens from the LLM
        """
        # Use LLM streaming to output the final exam token-by-token
        prompt = f"Present the following exam exactly as shown, maintaining all formatting:\n\n{exam_content}"

        try:
            response = llm.stream([HumanMessage(content=prompt)])
            for chunk in response:
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error streaming exam: {e}"

    async def _astream_final_exam(self, exam_content: str):
        """
        Async version: Stream the final exam token-by-token using LLM streaming.

        This is called after the agent completes validation and tool calls,
        allowing for true token-level streaming of the final response.

        Args:
            exam_content: The validated exam content to stream

        Yields:
            Individual tokens from the LLM
        """
        # Use LLM streaming to output the final exam token-by-token
        prompt = f"Present the following exam exactly as shown, maintaining all formatting:\n\n{exam_content}"

        try:
            response = llm.astream([HumanMessage(content=prompt)])
            async for chunk in response:
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error streaming exam: {e}"

    async def stream_async(
        self,
        question: str,
        session_id: str = "default",
        user_id: int = None,
        user_role: str = "student",
    ) -> AsyncGenerator[str, None]:
        """
        Async streaming version with TRUE token-level streaming.

        Phase 1: Run the ReAct agent to completion (tool calls + validation)
        Phase 2: Stream the final validated exam token-by-token using LLM streaming

        This approach ensures quality (validation runs) while providing
        progressive visual feedback to users.

        Args:
            question: The user's question/request
            session_id: Unique session identifier for conversation memory
            user_id: User ID for accessing uploaded documents
            user_role: "student" or "faculty"

        Yields:
            Individual tokens of the final exam
        """
        # Store user context for tool access
        self.current_user_id = user_id
        self.current_session_id = session_id

        config = {"configurable": {"thread_id": f"exam_react::{session_id}"}}
        system_message = self._get_system_message(user_role)

        # Phase 1: Run agent to completion, collecting the final validated exam
        final_exam_content = ""

        async for step in self.agent.astream(
            {
                "messages": [
                    SystemMessage(content=system_message),
                    HumanMessage(content=question),
                ]
            },
            config,
            stream_mode="values",
        ):
            messages = step.get("messages", [])
            if messages:
                last_msg = messages[-1]
                # Collect the final AI message content (skip tool calls and validation outputs)
                if hasattr(last_msg, "content") and last_msg.content:
                    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
                        content = last_msg.content

                        # Skip validation check messages and inspiration outputs
                        if (
                            "🔍 VALIDATION CHECKS:" not in content
                            and "--- Inspiration Question" not in content
                            and "❌ VALIDATION FAILED" not in content
                            and "❌ ISSUES FOUND:" not in content
                        ):
                            final_exam_content = content

        # Phase 2: Stream the final exam token-by-token
        if final_exam_content:
            async for token in self._astream_final_exam(final_exam_content):
                yield token

    def answer(
        self, question: str, session_id: str = "default", user_role: str = "student"
    ) -> str:
        """
        Non-streaming answer method (collects all chunks).

        Args:
            question: The user's question/request
            session_id: Unique session identifier for conversation memory
            user_role: "student" or "faculty"

        Returns:
            Complete generated response
        """
        result = ""
        for chunk in self.stream(question, session_id, user_role):
            result += chunk
        return result


# Create singleton instance
exam_react_agent = ExamReactAgent()
