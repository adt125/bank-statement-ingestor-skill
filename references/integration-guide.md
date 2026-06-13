# Integration Guide

How to wire the pipeline into your existing backend.

## The 3 things you always need to swap

1. **Data model** — Replace `RawTransaction`/`CleanTransaction`/`NormalizedTransaction` with your ORM models
2. **DB layer** — Replace `DeduplicationStore` with your DB client
3. **Categories** — Update `CATEGORIES` in `normalizer.py` to match your taxonomy

---

## Django

### Add to urls.py
```python
from django.urls import path
from .views import upload_statements

urlpatterns = [
    path("api/statements/upload/", upload_statements),
]
```

### View
```python
# views.py
import tempfile, os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from scripts.pipeline import run_pipeline

@csrf_exempt
def upload_statements(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse({"error": "No files"}, status=400)

    tmp_dir, paths = tempfile.mkdtemp(), []
    for f in files:
        p = os.path.join(tmp_dir, f.name)
        with open(p, "wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
        paths.append(p)

    result = run_pipeline(paths)
    return JsonResponse({
        "new_inserted": result.new_inserted,
        "duplicates_skipped": result.duplicates_skipped,
        "errors": result.errors,
    })
```

### Swap the DB layer (Django ORM)
```python
# In scripts/deduplicator.py, replace DeduplicationStore with:
from myapp.models import Transaction

def exists(txn_hash: str) -> bool:
    return Transaction.objects.filter(hash=txn_hash).exists()

def insert(txn: NormalizedTransaction, txn_hash: str):
    Transaction.objects.get_or_create(
        hash=txn_hash,
        defaults={
            "date": txn.date, "merchant": txn.merchant,
            "category": txn.category, "amount": txn.amount,
            # ... map remaining fields
        }
    )
```

---

## FastAPI (existing app)

```python
# routers/statements.py
from fastapi import APIRouter, UploadFile, File
from scripts.pipeline import run_pipeline
import tempfile, os

router = APIRouter(prefix="/api/statements", tags=["statements"])

@router.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    tmp_dir, paths = tempfile.mkdtemp(), []
    for f in files:
        data = await f.read()
        p = os.path.join(tmp_dir, f.filename)
        open(p, "wb").write(data)
        paths.append(p)
    return run_pipeline(paths).__dict__

# In main.py:
# from routers.statements import router as statements_router
# app.include_router(statements_router)
```

---

## Express / Node.js

Use the pipeline as a subprocess from your Node backend:

```javascript
// routes/statements.js
const { exec } = require("child_process");
const multer   = require("multer");
const upload   = multer({ dest: "uploads/" });

router.post("/api/statements/upload", upload.array("files"), (req, res) => {
    const files = req.files.map(f => f.path).join(" ");
    exec(`python scripts/pipeline.py ${files}`, (err, stdout) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ message: "Done", output: stdout });
    });
});
```

Or run the FastAPI server as a sidecar and proxy requests to it from Node.

---

## Next.js API Routes

```typescript
// app/api/statements/upload/route.ts
import { NextRequest, NextResponse } from "next/server";
import { writeFile } from "fs/promises";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import os from "os";

const execAsync = promisify(exec);

export async function POST(req: NextRequest) {
    const form  = await req.formData();
    const files = form.getAll("files") as File[];
    const tmp   = os.tmpdir();
    const paths: string[] = [];

    for (const file of files) {
        const buf = Buffer.from(await file.arrayBuffer());
        const p   = path.join(tmp, file.name);
        await writeFile(p, buf);
        paths.push(p);
    }

    const { stdout } = await execAsync(`python scripts/pipeline.py ${paths.join(" ")}`);
    return NextResponse.json({ message: "Done", output: stdout });
}
```

---

## Supabase (replacing DeduplicationStore)

```python
from supabase import create_client
import os

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def exists(txn_hash: str) -> bool:
    r = supabase.table("transactions").select("id").eq("hash", txn_hash).execute()
    return len(r.data) > 0

def insert(txn: NormalizedTransaction, txn_hash: str):
    supabase.table("transactions").upsert({
        "hash": txn_hash, "date": txn.date, "merchant": txn.merchant,
        "category": txn.category, "subcategory": txn.subcategory,
        "amount": txn.amount, "txn_type": txn.txn_type, "bank": txn.bank,
        "description": txn.description, "tags": txn.tags,
    }).execute()
```
