# Timetable Export: Download Links Implementation

## Overview

Updated the timetable export functionality to provide **clickable download links** in the chat UI, making it easy for users to download their timetables directly from the conversation.

**Changes Made:**

1. ✅ Added `/multiagent/download-timetable/{filename}` API endpoint
2. ✅ Modified export tool to return download URLs instead of file paths
3. ✅ Removed iCal and PDF support (simplified to CSV and Excel only)
4. ✅ Added security validation to prevent path traversal attacks

---

## 🔧 Technical Implementation

### 1. Download API Endpoint

**Location:** `app/routers/multiagent.py`

**Endpoint:** `GET /multiagent/download-timetable/{filename}`

**Features:**

- ✅ **Authentication required** - Uses `get_current_user` dependency
- ✅ **Security validation** - Prevents path traversal (`.., /, \`)
- ✅ **File type validation** - Only allows `.csv` and `.xlsx` files
- ✅ **Proper Content-Disposition** - Browser downloads file with correct name
- ✅ **Correct MIME types** - `text/csv` for CSV, Excel MIME type for XLSX

**Code:**

```python
@router.get("/download-timetable/{filename}")
async def download_timetable(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    # Security: Validate filename to prevent path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid filename"
        )

    # Only allow CSV and Excel files
    allowed_extensions = {'.csv', '.xlsx'}
    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only CSV and Excel files can be downloaded"
        )

    # Construct file path
    export_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'timetable_exports')
    file_path = os.path.join(export_dir, filename)

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Return file for download
    media_type = "text/csv" if file_ext == '.csv' else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
```

---

### 2. Export Tool Updates

**Location:** `multiagent/agents/timetable_agent.py`

**Changes:**

1. **Removed iCal and PDF support** - Simplified to CSV and Excel only
2. **Added download URL generation** - Uses base URL + filename
3. **Markdown link format** - Returns clickable links for the UI
4. **Enhanced Excel styling** - Auto-adjusts column widths for better formatting

**Updated Tool Signature:**

```python
@tool
def export_timetable(format_type: str, timetable_json: str, filename: str = "") -> str:
    """Export timetable to CSV or Excel format with downloadable link.

    Args:
        format_type: Either 'csv' or 'excel'
        timetable_json: JSON string of timetable data from additional_kwargs['data']
        filename: Optional custom filename (without extension)

    Returns:
        Success message with clickable download link
    """
```

**CSV Export Example:**

```python
# Generate download URL
base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
download_url = f"{base_url}/multiagent/download-timetable/{file_with_ext}"

return (
    f"✅ **CSV exported successfully!**\n\n"
    f"📥 **Download your timetable:**\n"
    f"[Click here to download {file_with_ext}]({download_url})\n\n"
    f"You can open this file in Excel, Google Sheets, or any spreadsheet application."
)
```

**Excel Export Enhancements:**

```python
# Export to Excel with auto-adjusted column widths
with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='Timetable')

    # Auto-adjust column widths
    worksheet = writer.sheets['Timetable']
    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        worksheet.column_dimensions[column_letter].width = adjusted_width
```

---

## 🔐 Security Features

### Path Traversal Prevention

```python
# Reject filenames with path traversal attempts
if '..' in filename or '/' in filename or '\\' in filename:
    raise HTTPException(status_code=403, detail="Invalid filename")
```

**Blocked Examples:**

- `../../../etc/passwd` ❌
- `folder/file.csv` ❌
- `folder\\file.csv` ❌

### File Type Validation

```python
# Only allow specific extensions
allowed_extensions = {'.csv', '.xlsx'}
file_ext = Path(filename).suffix.lower()
if file_ext not in allowed_extensions:
    raise HTTPException(status_code=403, detail="Only CSV and Excel files can be downloaded")
```

**Allowed:**

- `timetable_20251016.csv` ✅
- `my_schedule.xlsx` ✅

**Blocked:**

- `timetable.exe` ❌
- `script.py` ❌
- `malware.js` ❌

### Authentication Required

```python
async def download_timetable(
    filename: str,
    current_user: User = Depends(get_current_user)  # ✅ Must be logged in
):
```

---

## 📱 User Experience Flow

### Scenario: Student Exports Timetable

**Step 1: Generate Timetable**

```
User: "Show me timetable for Computer Vision AI-A and Agentic AI AI-A"
Agent: [Displays formatted timetable with all course details]
```

**Step 2: Request Export**

```
User: "Export this as Excel"
Agent: ✅ Excel file created successfully!

       📥 Download your timetable:
       [Click here to download timetable_20251016_143522.xlsx](http://localhost:8000/multiagent/download-timetable/timetable_20251016_143522.xlsx)

       Open it in Microsoft Excel, Google Sheets, or LibreOffice Calc.
```

**Step 3: Download**

- User clicks the link in the chat
- Browser authenticates request (JWT token from session)
- Server validates file access
- Browser downloads the file with proper name
- File opens in default spreadsheet application

---

## 🌐 Deployment Configuration

### Environment Variable

Set `API_BASE_URL` for different environments:

**Development:**

```bash
export API_BASE_URL=http://localhost:8000
```

**Production:**

```bash
export API_BASE_URL=https://campushive.yourdomain.com
```

**Docker:**

```yaml
environment:
  - API_BASE_URL=https://campushive.yourdomain.com
```

### CORS Configuration

Ensure CORS allows file downloads from your frontend:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,  # Required for authenticated downloads
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📊 File Format Details

### CSV Format

```csv
Day,Time,Course,Room
Monday,11:30-12:50,Computer Vision (AI-A),D-406
Monday,01:00-02:20,Agentic AI (AI-A),D-406
Wednesday,08:30-09:50,Computer Vision Lab (AI-A),C-Rawal 4
Wednesday,11:30-12:50,Computer Vision (AI-A),D-412
Wednesday,01:00-02:20,Agentic AI (AI-A),D-411
```

**Features:**

- ✅ Universal compatibility (Excel, Google Sheets, LibreOffice)
- ✅ No dependencies required
- ✅ Small file size
- ✅ Easy to parse programmatically

### Excel Format (.xlsx)

**Features:**

- ✅ Auto-adjusted column widths for readability
- ✅ Sorted by day and time
- ✅ Professional formatting
- ✅ Single sheet named "Timetable"
- ✅ No index column

**Column Width Calculation:**

```python
adjusted_width = min(max_length + 2, 50)  # Max 50 characters wide
```

---

## 🧪 Testing

### Test 1: CSV Export

```bash
curl -X GET "http://localhost:8000/multiagent/download-timetable/test_timetable.csv" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -o downloaded_timetable.csv
```

**Expected:** File downloads successfully with correct CSV content

### Test 2: Excel Export

```bash
curl -X GET "http://localhost:8000/multiagent/download-timetable/test_timetable.xlsx" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -o downloaded_timetable.xlsx
```

**Expected:** File downloads successfully, opens in Excel

### Test 3: Security - Path Traversal

```bash
curl -X GET "http://localhost:8000/multiagent/download-timetable/../../../etc/passwd" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected:** 403 Forbidden - "Invalid filename"

### Test 4: Security - Invalid File Type

```bash
curl -X GET "http://localhost:8000/multiagent/download-timetable/malware.exe" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected:** 403 Forbidden - "Only CSV and Excel files can be downloaded"

### Test 5: File Not Found

```bash
curl -X GET "http://localhost:8000/multiagent/download-timetable/nonexistent.csv" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected:** 404 Not Found - "File not found"

---

## 📁 File Structure

```
campushive_v2/
├── app/
│   └── routers/
│       └── multiagent.py          # Added download endpoint
├── data/
│   └── timetable_exports/         # Export storage directory
│       ├── timetable_20251016_143522.csv
│       ├── timetable_20251016_143530.xlsx
│       └── ...
└── multiagent/
    └── agents/
        └── timetable_agent.py     # Updated export tool
```

---

## ✅ Benefits

### 1. **Better UX**

- ✅ One-click download from chat
- ✅ No need to navigate file system
- ✅ Files named with timestamps (no overwrites)

### 2. **Security**

- ✅ Authentication required
- ✅ Path traversal protection
- ✅ File type validation
- ✅ No arbitrary file access

### 3. **Simplicity**

- ✅ Removed complex iCal/PDF code
- ✅ Only two formats to maintain
- ✅ Clear, focused functionality

### 4. **Deployment Ready**

- ✅ Configurable base URL
- ✅ Works in dev and production
- ✅ Proper CORS handling
- ✅ Secure file serving

---

## 🚀 Future Enhancements

### Optional Additions:

1. **File expiration** - Auto-delete exports after 24 hours
2. **Per-user directories** - Isolate exports by user ID
3. **Preview endpoint** - Show timetable in browser before download
4. **Email export** - Send timetable via email
5. **QR code generation** - Generate QR code for quick mobile access

### Implementation Example (File Expiration):

```python
# In a background task or cron job
import time
import os
from datetime import datetime, timedelta

def cleanup_old_exports():
    export_dir = 'data/timetable_exports'
    expiry_hours = 24

    for filename in os.listdir(export_dir):
        filepath = os.path.join(export_dir, filename)

        # Check file age
        file_age = time.time() - os.path.getmtime(filepath)
        if file_age > expiry_hours * 3600:
            os.remove(filepath)
            print(f"Deleted expired export: {filename}")
```

---

## 📋 Migration Notes

### Removed Features

- ❌ iCal export (`.ics` files)
- ❌ PDF export (was not implemented)

### Reason for Removal

1. **iCal complexity** - Required additional dependencies (`icalendar`, `pytz`)
2. **Limited use case** - Students prefer CSV/Excel for planning
3. **Maintenance burden** - More code to maintain and test
4. **Calendar apps** - Most students already have their university calendar

### Alternative for Calendar Integration

Students can:

1. Export to Excel
2. Use university's official calendar system
3. Manually add classes to Google Calendar
4. Use calendar apps that support CSV import

---

## 🎯 Summary

**What Changed:**

- ✅ Added secure download API endpoint with authentication
- ✅ Export tool now returns clickable markdown links
- ✅ Removed iCal and PDF support (CSV and Excel only)
- ✅ Enhanced Excel export with auto-adjusted columns
- ✅ Added comprehensive security validation

**Files Modified:**

1. `app/routers/multiagent.py` - Added `/download-timetable/{filename}` endpoint
2. `multiagent/agents/timetable_agent.py` - Updated export tool, removed iCal/PDF

**Result:**
Users can now easily download their timetables with a single click from the chat interface, with proper security and authentication! 🎉
