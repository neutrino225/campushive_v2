#!/usr/bin/env python3
"""
Quick test script for exam generation through main CLI
"""
import asyncio
import sys
import os

# Add root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.cli import handle_send
from rich.console import Console

console = Console()

async def test_faculty_exam():
    """Test faculty exam generation"""
    console.print("\n[bold]TEST 1: Faculty Final Exam[/bold]")
    console.print("=" * 60)
    await handle_send(
        "Generate a final exam for Artificial Intelligence",
        session_id="test_faculty_123",
        debug_graph=False,
        user_role="faculty"
    )
    console.print("\n" + "=" * 60)

async def test_student_exam():
    """Test student sessional exam generation"""
    console.print("\n[bold]TEST 2: Student Sessional Exam[/bold]")
    console.print("=" * 60)
    await handle_send(
        "Generate a sessional exam for Database Systems",
        session_id="test_student_456",
        debug_graph=False,
        user_role="student"
    )
    console.print("\n" + "=" * 60)

async def main():
    console.print("[bold cyan]Testing Exam Generation Through Main CLI[/bold cyan]\n")
    
    await test_faculty_exam()
    await asyncio.sleep(1)
    await test_student_exam()
    
    console.print("\n[bold green]✓ All tests completed![/bold green]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Tests interrupted[/yellow]")
