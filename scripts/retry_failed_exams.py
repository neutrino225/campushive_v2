#!/usr/bin/env python3
"""
Script to manually retry failed exam uploads.
This bypasses the API and directly processes the exams.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
import traceback
from config import embeddings
from vector_store_manager import VectorStoreManager, VectorStoreType


def retry_exam(exam_id: int, db_path: str = "data/campushive.db"):
    """Retry processing a single failed exam."""
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get exam details
        cursor.execute('''
            SELECT id, file_path, course_name, exam_type, status 
            FROM uploaded_exams 
            WHERE id = ?
        ''', (exam_id,))
        
        exam = cursor.fetchone()
        
        if not exam:
            print(f"❌ Exam ID {exam_id} not found")
            return False
        
        exam_id, file_path, course_name, exam_type, status = exam
        
        print(f"\n{'='*60}")
        print(f"Processing Exam ID: {exam_id}")
        print(f"Course: {course_name}")
        print(f"Type: {exam_type}")
        print(f"Status: {status}")
        print(f"File: {file_path}")
        print(f"{'='*60}\n")
        
        # Check if file exists
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            print(f"❌ {error_msg}")
            cursor.execute('''
                UPDATE uploaded_exams 
                SET status = 'failed', error_message = ? 
                WHERE id = ?
            ''', (error_msg, exam_id))
            conn.commit()
            return False
        
        # Update status to processing
        print("📝 Updating status to 'processing'...")
        cursor.execute('''
            UPDATE uploaded_exams 
            SET status = 'processing', error_message = NULL 
            WHERE id = ?
        ''', (exam_id,))
        conn.commit()
        
        # Process the exam
        try:
            from app.utils.exams import (
                analyze_pdf_to_structured,
                structured_exam_to_documents,
                append_structured_exam_to_json,
            )
            
            # Step 1: Analyze PDF
            print("🔍 Step 1: Analyzing PDF...")
            structured = analyze_pdf_to_structured(file_path, course_name)
            
            if structured is None:
                raise RuntimeError("PDF analysis returned None")
            
            print(f"✓ Analysis succeeded: {len(structured.questions)} questions found")
            
            # Step 2: Save to structured exams JSON
            print("\n💾 Step 2: Saving to structured_exams.json...")
            struct_path = os.path.join(project_root, "data", "structured_exams.json")
            append_structured_exam_to_json(structured, struct_path)
            print("✓ Saved to JSON")
            
            # Step 3: Convert to documents
            print("\n📄 Step 3: Converting to documents...")
            docs = structured_exam_to_documents(structured, file_path)
            print(f"✓ Created {len(docs)} documents")
            
            # Step 4: Add to vector store
            print("\n🗄️  Step 4: Adding to vector store...")
            manager = VectorStoreManager(embeddings=embeddings)
            manager.add_documents_to_store(VectorStoreType.EXAMS, docs)
            print("✓ Added to vector store")
            
            # Mark as processed
            print("\n✅ Marking as processed...")
            cursor.execute('''
                UPDATE uploaded_exams 
                SET status = 'processed', error_message = NULL 
                WHERE id = ?
            ''', (exam_id,))
            conn.commit()
            
            print(f"\n🎉 Successfully processed exam ID {exam_id}")
            return True
            
        except Exception as e:
            # Mark as failed with error message
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            print(f"\n❌ Processing failed:")
            print(f"   {str(e)}")
            print(f"\n📋 Full traceback:")
            print(error_msg)
            
            cursor.execute('''
                UPDATE uploaded_exams 
                SET status = 'failed', error_message = ? 
                WHERE id = ?
            ''', (error_msg[:2000], exam_id))
            conn.commit()
            
            return False
    
    finally:
        conn.close()


def main():
    """Main function to retry failed exams."""
    print("\n" + "="*60)
    print("EXAM UPLOAD RETRY SCRIPT")
    print("="*60)
    
    db_path = os.path.join(project_root, "data", "campushive.db")
    
    # Get list of failed exams
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, filename, course_name, status 
        FROM uploaded_exams 
        WHERE status = 'failed' 
        ORDER BY id
    ''')
    failed_exams = cursor.fetchall()
    conn.close()
    
    if not failed_exams:
        print("\n✓ No failed exams found!")
        return
    
    print(f"\nFound {len(failed_exams)} failed exam(s):")
    for exam_id, filename, course, status in failed_exams:
        print(f"  - ID {exam_id}: {filename} ({course})")
    
    # Process exam IDs 4 and 5
    target_ids = [4, 5]
    results = []
    
    for exam_id in target_ids:
        success = retry_exam(exam_id, db_path)
        results.append((exam_id, success))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for exam_id, success in results:
        status_icon = "✅" if success else "❌"
        status_text = "SUCCESS" if success else "FAILED"
        print(f"{status_icon} Exam ID {exam_id}: {status_text}")
    
    success_count = sum(1 for _, success in results if success)
    print(f"\nTotal: {success_count}/{len(results)} exams processed successfully")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
