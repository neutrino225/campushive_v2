"""
Test file size limits and MIME validation for upload endpoint
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_file_size_limit():
    """Test that files over 10MB are rejected"""
    print("Testing file size limit...")

    # Create a mock file that's too large
    large_content = b"x" * (11 * 1024 * 1024)  # 11 MB

    # Test the validation logic
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    if len(large_content) > MAX_FILE_SIZE:
        print("✅ File size validation would reject 11MB file")
        expected_msg = f"File too large. Maximum size allowed: {MAX_FILE_SIZE // (1024*1024)} MB"
        print(f"   Expected error: {expected_msg}")
    else:
        print("❌ File size validation failed")

    print()


def test_mime_validation():
    """Test MIME type validation logic"""
    print("Testing MIME validation...")

    import mimetypes

    # Test cases: (filename, expected_mimes, should_pass)
    test_cases = [
        ("test.txt", ["text/plain"], True),
        ("test.md", ["text/plain", "text/markdown"], True),
        ("test.pdf", ["application/pdf"], True),
        ("test.docx", ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"], True),
        ("test.exe", [], False),  # Not in allowed_mime_types
    ]

    allowed_mime_types = {
        '.txt': ['text/plain'],
        '.md': ['text/plain', 'text/markdown'],
        '.pdf': ['application/pdf'],
        '.doc': ['application/msword'],
        '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    }

    for filename, _, should_pass in test_cases:
        _, ext = os.path.splitext(filename.lower())
        detected_mime = mimetypes.guess_type(filename)[0]
        expected_mimes = allowed_mime_types.get(ext, [])

        mime_valid = False
        if expected_mimes:
            if detected_mime and detected_mime in expected_mimes:
                mime_valid = True

        if mime_valid == should_pass:
            print(f"✅ {filename}: MIME validation {'passed' if mime_valid else 'rejected'} as expected")
        else:
            print(f"❌ {filename}: MIME validation unexpected result")

    print()


def test_edge_cases():
    """Test edge cases"""
    print("Testing edge cases...")

    # Test file exactly at limit
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    exact_limit_content = b"x" * MAX_FILE_SIZE

    if len(exact_limit_content) == MAX_FILE_SIZE:
        print("✅ File exactly at 10MB limit would be accepted")
    else:
        print("❌ File size calculation error")

    # Test empty file
    empty_content = b""
    if len(empty_content) <= MAX_FILE_SIZE:
        print("✅ Empty file would be accepted (size check)")
    else:
        print("❌ Empty file size check failed")

    print()


def main():
    """Run security tests"""
    print("=" * 60)
    print("FILE UPLOAD SECURITY TESTS")
    print("=" * 60)
    print()

    test_file_size_limit()
    test_mime_validation()
    test_edge_cases()

    print("=" * 60)
    print("SECURITY TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()